"""
Media Composer Lambda

Downloads audio + video assets from S3, then uses FFmpeg to:
1. Concatenate video fragments
2. Apply boomerang (reverse + concat) filter
3. Speed adjustment (1.33x via setpts=0.75*PTS)
4. Overlay audio onto video
5. Export in 3 aspect ratios: 16:9, 9:16, 1:1
"""
import json
import boto3
import os
import subprocess
import uuid

s3_client = boto3.client('s3')
BUCKET_NAME = os.environ.get('ASSETS_BUCKET', 'unified-flow-assets-bucket')


def download_s3(uri, local_path):
    """Download an S3 object by its s3:// URI."""
    bucket = uri.split('/')[2]
    key = '/'.join(uri.split('/')[3:])
    s3_client.download_file(bucket, key, local_path)


def run_ffmpeg(args):
    """Run an FFmpeg command and raise on failure."""
    result = subprocess.run(
        ["ffmpeg", "-y"] + args,
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg failed: {result.stderr}")
    return result


def ms_to_srt_time(ms):
    """Convert milliseconds to SRT timestamp format (HH:MM:SS,mmm)."""
    hours = ms // 3_600_000
    minutes = (ms % 3_600_000) // 60_000
    seconds = (ms % 60_000) // 1_000
    millis = ms % 1_000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def generate_srt(viseme_json_path, srt_output_path, words_per_caption=4):
    """
    Parse Polly speech marks (JSONL with 'word' type entries) and
    generate an SRT subtitle file, grouping words into chunks.
    
    Each line in the Polly speech marks JSONL looks like:
    {"time": 100, "type": "word", "start": 0, "end": 5, "value": "Hello"}
    """
    word_marks = []
    with open(viseme_json_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            mark = json.loads(line)
            if mark.get('type') == 'word':
                word_marks.append(mark)

    if not word_marks:
        # Write empty SRT if no word marks found
        with open(srt_output_path, 'w') as f:
            f.write("")
        return

    # Group words into chunks
    srt_entries = []
    for i in range(0, len(word_marks), words_per_caption):
        chunk = word_marks[i:i + words_per_caption]
        start_ms = chunk[0]['time']
        # End time: start of next chunk, or last word + 500ms
        if i + words_per_caption < len(word_marks):
            end_ms = word_marks[i + words_per_caption]['time']
        else:
            end_ms = chunk[-1]['time'] + 500

        text = ' '.join(w['value'] for w in chunk)
        srt_entries.append((start_ms, end_ms, text))

    # Write SRT file
    with open(srt_output_path, 'w', encoding='utf-8') as f:
        for idx, (start, end, text) in enumerate(srt_entries, 1):
            f.write(f"{idx}\n")
            f.write(f"{ms_to_srt_time(start)} --> {ms_to_srt_time(end)}\n")
            f.write(f"{text}\n\n")


def lambda_handler(event, context):
    try:
        audio_uri = event.get('audio_uri')
        video_uris = event.get('video_uris', [])
        aspect_ratio = event.get('manifest', {}).get('metadata', {}).get('aspect_ratio', '16:9')

        if not video_uris or not audio_uri:
            return {'statusCode': 400, 'body': 'Missing media URIs for composition'}

        job_id = str(uuid.uuid4())
        tmp = f"/tmp/{job_id}"
        os.makedirs(tmp, exist_ok=True)

        # Download assets
        local_audio = f"{tmp}/audio.mp3"
        download_s3(audio_uri, local_audio)

        local_videos = []
        for i, v_uri in enumerate(video_uris):
            local_v = f"{tmp}/video_{i}.mp4"
            download_s3(v_uri, local_v)
            local_videos.append(local_v)

        # ── Step 1: Concatenate video fragments ──────────────────────
        concat_file = f"{tmp}/concat.txt"
        with open(concat_file, "w") as f:
            for v in local_videos:
                f.write(f"file '{v}'\n")

        stitched = f"{tmp}/stitched.mp4"
        run_ffmpeg([
            "-f", "concat", "-safe", "0",
            "-i", concat_file, "-c", "copy", stitched
        ])

        # ── Step 2: Boomerang filter (reverse + concat) ──────────────
        boomerang = f"{tmp}/boomerang.mp4"
        run_ffmpeg([
            "-i", stitched,
            "-filter_complex", "[0:v]reverse[r];[0:v][r]concat=n=2:v=1[v]",
            "-map", "[v]", boomerang
        ])

        # ── Step 3: Speed adjustment (1.33x) ─────────────────────────
        sped_up = f"{tmp}/sped_up.mp4"
        run_ffmpeg([
            "-i", boomerang,
            "-filter:v", "setpts=0.75*PTS",
            "-an", sped_up
        ])

        # ── Step 4: Audio overlay ────────────────────────────────────
        with_audio = f"{tmp}/with_audio.mp4"
        run_ffmpeg([
            "-i", sped_up, "-i", local_audio,
            "-c:v", "libx264", "-c:a", "aac",
            "-map", "0:v:0", "-map", "1:a:0",
            "-shortest", with_audio
        ])

        # ── Step 5: Dynamic Captioning (Polly word timestamps → SRT) ─
        viseme_uri = event.get('viseme_uri')
        composed_16_9 = f"{tmp}/final_16_9.mp4"

        if viseme_uri:
            # Download viseme/word marks JSON from S3
            local_visemes = f"{tmp}/visemes.json"
            download_s3(viseme_uri, local_visemes)

            # Parse word marks and generate SRT
            srt_path = f"{tmp}/captions.srt"
            generate_srt(local_visemes, srt_path)

            # Burn subtitles into video
            run_ffmpeg([
                "-i", with_audio,
                "-vf", f"subtitles={srt_path}:force_style='FontSize=22,PrimaryColour=&HFFFFFF,OutlineColour=&H000000,BorderStyle=3,Outline=2,Shadow=1,MarginV=30'",
                "-c:a", "copy", composed_16_9
            ])
        else:
            # No captions available — just rename
            os.rename(with_audio, composed_16_9)


        # ── Step 5: Multi-export (3 aspect ratios) ───────────────────
        outputs = {}

        # 16:9 is already done
        key_16_9 = f"final_renders/{job_id}_16x9.mp4"
        s3_client.upload_file(composed_16_9, BUCKET_NAME, key_16_9)
        outputs["16:9"] = f"s3://{BUCKET_NAME}/{key_16_9}"

        # 9:16 (vertical — crop center)
        composed_9_16 = f"{tmp}/final_9_16.mp4"
        run_ffmpeg([
            "-i", composed_16_9,
            "-vf", "crop=ih*9/16:ih,scale=720:1280",
            "-c:a", "copy", composed_9_16
        ])
        key_9_16 = f"final_renders/{job_id}_9x16.mp4"
        s3_client.upload_file(composed_9_16, BUCKET_NAME, key_9_16)
        outputs["9:16"] = f"s3://{BUCKET_NAME}/{key_9_16}"

        # 1:1 (square — crop center)
        composed_1_1 = f"{tmp}/final_1_1.mp4"
        run_ffmpeg([
            "-i", composed_16_9,
            "-vf", "crop=min(iw\\,ih):min(iw\\,ih),scale=720:720",
            "-c:a", "copy", composed_1_1
        ])
        key_1_1 = f"final_renders/{job_id}_1x1.mp4"
        s3_client.upload_file(composed_1_1, BUCKET_NAME, key_1_1)
        outputs["1:1"] = f"s3://{BUCKET_NAME}/{key_1_1}"

        # Generate presigned download URL for the requested ratio
        primary_key = {
            "16:9": key_16_9,
            "9:16": key_9_16,
            "1:1": key_1_1
        }.get(aspect_ratio, key_16_9)

        download_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': BUCKET_NAME, 'Key': primary_key},
            ExpiresIn=3600
        )

        return {
            'statusCode': 200,
            'body': 'Composition complete',
            'final_video_uri': outputs[aspect_ratio] if aspect_ratio in outputs else outputs["16:9"],
            'all_exports': outputs,
            'download_url': download_url
        }

    except Exception as e:
        print(f"Error composing media: {str(e)}")
        return {'statusCode': 500, 'error': str(e)}
