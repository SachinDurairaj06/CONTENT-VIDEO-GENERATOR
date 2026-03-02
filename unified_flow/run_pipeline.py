"""
Unified Flow — Local End-to-End Pipeline Runner

Usage:
  1. Set environment variables:
     $env:AWS_ACCESS_KEY_ID = "your-key"
     $env:AWS_SECRET_ACCESS_KEY = "your-secret"
     $env:AWS_DEFAULT_REGION = "us-east-1"

  2. Run:
     python run_pipeline.py "Promote my organic honey from Himachal Pradesh for the winter season"

  3. Output:
     output/<job_id>/final_16x9.mp4
"""

import sys
import os
import json
import time
import base64
import subprocess
import uuid
import boto3
import sys
from dotenv import load_dotenv

# Ensure Windows prints emojis without crashing
sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()

# ─── Configuration ────────────────────────────────────────────────────
REGION = os.environ.get('AWS_DEFAULT_REGION', 'us-east-1')

session = boto3.Session(region_name=REGION)
bedrock = session.client('bedrock-runtime')
polly = session.client('polly')

JOB_ID = str(uuid.uuid4())[:8]
OUTPUT_DIR = os.path.join('output', JOB_ID)
os.makedirs(OUTPUT_DIR, exist_ok=True)

print(f"\n{'='*60}")
print(f"  UNIFIED FLOW — Concept-to-Render Pipeline")
print(f"  Job ID: {JOB_ID}")
print(f"  Region: {REGION}")
print(f"{'='*60}\n")


# ─── Helper ───────────────────────────────────────────────────────────
def run_ffmpeg(args, label="FFmpeg"):
    """Run an FFmpeg command, raise on failure."""
    cmd = ["ffmpeg", "-y"] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ❌ {label} FAILED:\n{result.stderr[:500]}")
        raise RuntimeError(f"{label} failed")
    print(f"  ✅ {label} done")
    return result


def ms_to_srt(ms):
    h = ms // 3_600_000
    m = (ms % 3_600_000) // 60_000
    s = (ms % 60_000) // 1_000
    ml = ms % 1_000
    return f"{h:02d}:{m:02d}:{s:02d},{ml:03d}"


# ─── STEP 1: Generate Manifest via Claude 3.5 ────────────────────────
def step1_generate_manifest(user_prompt):
    print("[1/5] Generating script & visual prompts via Amazon Nova Pro...")

    system_prompt = """You are an AI director for 'Unified Flow', a platform that creates culturally resonant promotional videos for Indian MSMEs.
Given a user's business idea, expand it into a precise multi-asset manifest.
Respond ONLY with a valid JSON object matching this schema:
{
  "narration": "A culturally nuanced script for voiceover. Keep under 30 seconds of spoken content. Do NOT use SSML tags.",
  "visual_prompts": [
     "Detailed prompt 1 for video generation - include camera angle, lighting, Indian cultural context",
     "Detailed prompt 2",
     "Detailed prompt 3"
  ],
  "metadata": {
     "language_code": "en-IN",
     "sentiment": "warm"
  }
}"""

    request_body = {
        "messages": [{"role": "user", "content": [{"text": f"System: {system_prompt}\n\nUser Idea: {user_prompt}"}]}],
        "inferenceConfig": {"maxTokens": 1024, "temperature": 0.5}
    }

    response = bedrock.invoke_model(
        modelId='amazon.nova-pro-v1:0',
        contentType='application/json',
        accept='application/json',
        body=json.dumps(request_body)
    )

    response_body = json.loads(response['body'].read())
    content_text = response_body['output']['message']['content'][0]['text']

    # Parse JSON (handle markdown wrappers)
    clean = content_text.strip()
    if clean.startswith("```json"):
        clean = clean[7:]
    if clean.startswith("```"):
        clean = clean[3:]
    if clean.endswith("```"):
        clean = clean[:-3]
    manifest = json.loads(clean.strip())

    # Save manifest
    manifest_path = os.path.join(OUTPUT_DIR, 'manifest.json')
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)

    print(f"  ✅ Manifest saved to {manifest_path}")
    print(f"  📖 Narration: {manifest['narration'][:80]}...")
    print(f"  🎨 Visual prompts: {len(manifest['visual_prompts'])} generated")
    return manifest


# ─── STEP 2: Synthesize Audio via Amazon Polly ───────────────────────
def step2_synthesize_audio(manifest):
    print("\n[2/5] 🔊 Synthesizing voiceover via Amazon Polly (Neural)...")

    narration = manifest['narration']
    lang_code = manifest.get('metadata', {}).get('language_code', 'en-IN')

    # Pick voice based on language
    voice_id = 'Kajal'  # Bilingual Hindi/English Neural voice

    # Generate MP3 audio
    audio_path = os.path.join(OUTPUT_DIR, 'voiceover.mp3')
    audio_resp = polly.synthesize_speech(
        Engine='neural',
        Text=narration,
        TextType='text',
        OutputFormat='mp3',
        VoiceId=voice_id,
        LanguageCode='en-IN'
    )

    with open(audio_path, 'wb') as f:
        f.write(audio_resp['AudioStream'].read())
    print(f"  ✅ Audio saved to {audio_path}")

    # Generate word-level speech marks for captions
    viseme_path = os.path.join(OUTPUT_DIR, 'speech_marks.json')
    try:
        marks_resp = polly.synthesize_speech(
            Engine='neural',
            Text=narration,
            TextType='text',
            OutputFormat='json',
            SpeechMarkTypes=['word'],
            VoiceId=voice_id,
            LanguageCode='en-IN'
        )
        with open(viseme_path, 'wb') as f:
            f.write(marks_resp['AudioStream'].read())
        print(f"  ✅ Speech marks saved to {viseme_path}")
    except Exception as e:
        print(f"  ⚠️ Speech marks failed (non-critical): {e}")
        viseme_path = None

    return audio_path, viseme_path


# ─── STEP 3: Generate Keyframe Images via Amazon Nova Canvas ─────────
def step3_generate_keyframes(manifest):
    print("\n[3/5] 🖼️  Generating keyframe images via Amazon Nova Canvas...")

    keyframe_paths = []
    for i, prompt in enumerate(manifest['visual_prompts']):
        print(f"  Generating keyframe {i+1}/{len(manifest['visual_prompts'])}...")

        # Sanitize prompt — remove words that trigger Nova Canvas content filters
        safe_words = ['kill', 'fight', 'battle', 'war', 'weapon', 'gun', 'shoot',
                      'blood', 'violent', 'attack', 'dead', 'destroy', 'explosion']
        clean_prompt = prompt
        for word in safe_words:
            clean_prompt = clean_prompt.replace(word, '').replace(word.capitalize(), '')
        clean_prompt = ' '.join(clean_prompt.split())  # remove extra spaces

        canvas_body = {
            "taskType": "TEXT_IMAGE",
            "textToImageParams": {
                "text": clean_prompt
            },
            "imageGenerationConfig": {
                "numberOfImages": 1,
                "height": 720,
                "width": 1280,
                "cfgScale": 6.5,
                "seed": i
            }
        }

        img_path = os.path.join(OUTPUT_DIR, f'keyframe_{i}.png')
        try:
            resp = bedrock.invoke_model(
                modelId='amazon.nova-canvas-v1:0',
                body=json.dumps(canvas_body),
                accept='application/json',
                contentType='application/json'
            )
            output = json.loads(resp['body'].read())
            img_b64 = output['images'][0]
            img_bytes = base64.b64decode(img_b64)
        except Exception as e:
            print(f"  Warning: Nova Canvas blocked prompt {i+1}, using fallback image: {e}")
            # Fallback: create a gradient placeholder image using only stdlib
            import struct, zlib
            def make_png(w, h, r, g, b):
                def png_chunk(tag, data):
                    c = zlib.crc32(tag + data) & 0xffffffff
                    return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', c)
                raw = b''
                for y in range(h):
                    raw += b'\x00'
                    for x in range(w):
                        fr = int(r * (1 - x/w) + 30 * (x/w))
                        fg = int(g * (1 - y/h) + 30 * (y/h))
                        fb = int(b)
                        raw += bytes([fr, fg, fb])
                compressed = zlib.compress(raw)
                ihdr_data = struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)
                return (b'\x89PNG\r\n\x1a\n' + png_chunk(b'IHDR', ihdr_data)
                        + png_chunk(b'IDAT', compressed) + png_chunk(b'IEND', b''))
            img_bytes = make_png(1280, 720, 20, 20, 80)  # dark blue gradient

        with open(img_path, 'wb') as f:
            f.write(img_bytes)

        keyframe_paths.append(img_path)
        print(f"  ✅ Keyframe {i+1} saved to {img_path}")

    return keyframe_paths


# ─── STEP 4: Generate Video via Nova Reel ─────────────────────────────
def step4_generate_video(manifest, keyframe_paths):
    print("\n[4/5] 🎬 Generating video via Amazon Nova Reel...")
    print("  ⏳ This takes 2-4 minutes. Polling for completion...")

    # Use the first visual prompt for video generation
    prompt = manifest['visual_prompts'][0]

    nova_body = {
        "taskType": "TEXT_VIDEO",
        "textToVideoParams": {
            "text": prompt
        },
        "videoGenerationConfig": {
            "durationSeconds": 6,
            "fps": 24,
            "dimension": "1280x720",
            "seed": 42
        }
    }

    # Nova Reel requires an AWS Marketplace subscription — using FFmpeg Ken Burns slideshow instead
    print("  📎 Using image slideshow approach with Ken Burns effect...")

    # Fallback: Create video from keyframe images using FFmpeg
    # This creates a smooth slideshow with ken-burns effect
    video_paths = []
    for i, kf in enumerate(keyframe_paths):
        clip_path = os.path.join(OUTPUT_DIR, f'clip_{i}.mp4')
        # 2-second per image with slow zoom (ken burns effect)
        run_ffmpeg([
            "-loop", "1", "-i", kf,
            "-vf", "scale=1280:720,zoompan=z='min(zoom+0.001,1.15)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=48:s=1280x720:fps=24",
            "-t", "2", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            clip_path
        ], f"Keyframe→Clip {i+1}")
        video_paths.append(clip_path)

    return video_paths


# ─── STEP 5: Compose Final Video with FFmpeg ─────────────────────────
def step5_compose(video_paths, audio_path, viseme_path):
    print("\n[5/5] 🎞️  Composing final video with FFmpeg...")

    # 5a. Concatenate all clips
    concat_file = os.path.join(OUTPUT_DIR, 'concat.txt')
    with open(concat_file, 'w') as f:
        for v in video_paths:
            f.write(f"file '{os.path.abspath(v)}'\n")

    stitched = os.path.join(OUTPUT_DIR, 'stitched.mp4')
    run_ffmpeg([
        "-f", "concat", "-safe", "0",
        "-i", concat_file, "-c", "copy", stitched
    ], "Concatenate clips")

    # 5b. Generate SRT captions from speech marks
    srt_path = os.path.join(OUTPUT_DIR, 'captions.srt')
    has_captions = False
    if viseme_path and os.path.exists(viseme_path):
        try:
            word_marks = []
            with open(viseme_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    mark = json.loads(line)
                    if mark.get('type') == 'word':
                        word_marks.append(mark)

            if word_marks:
                with open(srt_path, 'w', encoding='utf-8') as f:
                    for i in range(0, len(word_marks), 4):
                        chunk = word_marks[i:i+4]
                        start = chunk[0]['time']
                        end = word_marks[i+4]['time'] if i+4 < len(word_marks) else chunk[-1]['time'] + 500
                        text = ' '.join(w['value'] for w in chunk)
                        idx = (i // 4) + 1
                        f.write(f"{idx}\n{ms_to_srt(start)} --> {ms_to_srt(end)}\n{text}\n\n")
                has_captions = True
                print(f"  ✅ Captions generated: {srt_path}")
        except Exception as e:
            print(f"  ⚠️ Caption generation failed (non-critical): {e}")

    # 5c. Overlay audio onto video
    with_audio = os.path.join(OUTPUT_DIR, 'with_audio.mp4')
    run_ffmpeg([
        "-i", stitched, "-i", audio_path,
        "-c:v", "libx264", "-c:a", "aac",
        "-map", "0:v:0", "-map", "1:a:0",
        "-shortest", with_audio
    ], "Audio overlay")

    # 5d. Skip caption burning on Windows (FFmpeg subtitle path escaping is unreliable)
    # Captions are still saved as an SRT file alongside the video
    source_16_9 = with_audio

    # 5e. Export 16:9 (copy)
    final_16_9 = os.path.join(OUTPUT_DIR, 'final_16x9.mp4')
    run_ffmpeg([
        "-i", source_16_9, "-c", "copy", final_16_9
    ], "Export 16:9")

    # 5f. Export 9:16 (vertical crop)
    final_9_16 = os.path.join(OUTPUT_DIR, 'final_9x16.mp4')
    run_ffmpeg([
        "-i", source_16_9,
        "-vf", "crop=ih*9/16:ih,scale=720:1280",
        "-c:a", "copy", final_9_16
    ], "Export 9:16")

    # 5g. Export 1:1 (square crop)
    final_1_1 = os.path.join(OUTPUT_DIR, 'final_1x1.mp4')
    run_ffmpeg([
        "-i", source_16_9,
        "-vf", "crop=ih:ih,scale=720:720",
        "-c:a", "copy", final_1_1
    ], "Export 1:1")

    return final_16_9, final_9_16, final_1_1


# ─── MAIN ─────────────────────────────────────────────────────────────
def main():
    if len(sys.argv) < 2:
        print("Usage: python run_pipeline.py \"Your business idea here\"")
        print("Example: python run_pipeline.py \"Promote my organic honey from Himachal Pradesh\"")
        sys.exit(1)

    user_prompt = sys.argv[1]
    print(f"🚀 Prompt: \"{user_prompt}\"\n")

    start_time = time.time()

    # Step 1: Claude generates the creative manifest
    manifest = step1_generate_manifest(user_prompt)

    # Step 2: Polly synthesizes audio + word marks
    audio_path, viseme_path = step2_synthesize_audio(manifest)

    # Step 3: Titan generates keyframe images
    keyframe_paths = step3_generate_keyframes(manifest)

    # Step 4: Nova Reel generates video (or fallback to slideshow)
    video_paths = step4_generate_video(manifest, keyframe_paths)

    # Step 5: FFmpeg composes the final MP4 in 3 ratios
    final_16_9, final_9_16, final_1_1 = step5_compose(video_paths, audio_path, viseme_path)

    elapsed = time.time() - start_time

    print(f"\n{'='*60}")
    print(f"  ✅ PIPELINE COMPLETE in {elapsed:.1f}s")
    print(f"{'='*60}")
    print(f"  📁 Output folder: {os.path.abspath(OUTPUT_DIR)}")
    print(f"  🎬 16:9 (YouTube):  {final_16_9}")
    print(f"  📱 9:16 (Reels):    {final_9_16}")
    print(f"  ⬛ 1:1  (Square):   {final_1_1}")
    print(f"  📖 Manifest:        {os.path.join(OUTPUT_DIR, 'manifest.json')}")
    print(f"  🔊 Audio:           {audio_path}")
    print(f"{'='*60}\n")


if __name__ == '__main__':
    main()
