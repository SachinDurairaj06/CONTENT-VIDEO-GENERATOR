import sys, os, subprocess, random
import librosa

def run_cmd(args):
    print(f"RUNNING: {' '.join(args)}")
    subprocess.run(args, check=True)

def auto_edit(video_query, audio_query, output_file="final_edit.mp4"):
    os.makedirs("tmp_edit", exist_ok=True)
    audio_path = "tmp_edit/audio.mp3"
    video_path = "tmp_edit/source.mp4"

    # 1. Download Audio
    print("\n[1/4] Downloading target Audio...")
    run_cmd([sys.executable, '-m', 'yt_dlp', f'ytsearch1:{audio_query}', '-x', '--audio-format', 'mp3', '-o', audio_path, '--force-overwrites'])

    # 2. Download Video footage
    print("\n[2/4] Downloading raw Video footage...")
    # Prefer something under 10 minutes to process quickly.
    run_cmd([sys.executable, '-m', 'yt_dlp', f'ytsearch1:{video_query}', '--match-filter', 'duration < 600', '-f', 'bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4]/best', '-o', video_path, '--force-overwrites'])

    # 3. Analyze Beats
    print("\n[3/4] AI Analyzing Beats & Rhythm...")
    y, sr = librosa.load(audio_path, sr=None)
    # Get tempo and beat frames
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
    beat_times = list(librosa.frames_to_time(beats, sr=sr))
    
    # We want to start the edit at a massive drop if possible.
    # A simple proxy for a drop is finding when the RMS energy jumps.
    # For now, we'll just start at the 3rd or 4th beat to skip the very beginning, 
    # or let the user pass an offset. We'll start at 35s since "Skyfall" drops there.
    start_offset = 35.0
    
    # Filter beats after the offset, and keep them at least 0.4s apart (so no strobe-flashing cuts)
    filtered_beats = [start_offset]
    for b in beat_times:
        if b > start_offset and (b - filtered_beats[-1]) >= 0.4:
            filtered_beats.append(b)

    # We'll make a 25-second Short/TikTok
    target_duration = 25.0
    end_time = start_offset + target_duration
    filtered_beats = [b for b in filtered_beats if b <= end_time]
    
    if len(filtered_beats) < 2:
        # Fallback if beat detection failed
        filtered_beats = [start_offset + i*2.0 for i in range(12)]

    # Get video duration
    res = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', video_path], capture_output=True, text=True)
    video_duration = float(res.stdout.strip())

    # 4. Generate individual Micro-Clips to prevent FFmpeg Memory errors
    print("\n[4/4] Rendering Micro-Clips and Assembling Final Edit...")
    concat_file = "tmp_edit/concat.txt"
    clip_paths = []
    
    # Alternate zoom levels to create cinematic push-pull effect between cuts
    zoom_levels = ['1.08', '1.0', '1.12', '1.0', '1.05', '1.0']

    # Phase-based Narrative Flow
    # We divide the edit into 3 chapters: Build-up, Action, Victory
    n_total = len(filtered_beats) - 1
    phase_1_end = n_total // 4      # First 25%: Close-ups/Build-up
    phase_2_end = (n_total * 3) // 4 # Middle 50%: Pure Action

    for i in range(n_total):
        dur = filtered_beats[i+1] - filtered_beats[i]
        
        # Select source segment based on current phase of the edit
        if i < phase_1_end:
            # Build-up: Look in the first 20% of source (often includes intros/paddock/prep)
            v_start = random.uniform(2.0, video_duration * 0.2)
        elif i < phase_2_end:
            # Action: Look in the middle 60% of source
            v_start = random.uniform(video_duration * 0.2, video_duration * 0.8)
        else:
            # Victory: Look in the final 20% of source (podiums, flags, trophies)
            v_start = random.uniform(video_duration * 0.85, video_duration - dur - 2.0)

        clip_out = f"tmp_edit/clip_{i}.mp4"
        zoom = zoom_levels[i % len(zoom_levels)]
        
        # Fast: scale to slightly larger → crop center to 1080x1920
        # NO zoompan (too slow). This gives the illusion of a zoom cut instantly.
        cmd = [
            'ffmpeg', '-y', 
            '-ss', f"{v_start:.3f}", '-t', f"{dur:.3f}", '-i', video_path, 
            '-vf', (
                f"scale=iw*{zoom}:ih*{zoom},"          # Slight scale-up for push/pull feel
                f"scale=-2:1920,"                        # Scale height to 1920
                f"crop=1080:1920,"                       # Center-crop to portrait 9:16
                f"fps=30"                                # Lock to 30fps
            ),
            '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '22', '-an',
            clip_out
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        clip_paths.append(clip_out)
        print(f"  Rendered clip {i+1}/{len(filtered_beats)-1} ({dur:.2f}s)")
    
    # 5. Assemble and Mix Audio
    with open(concat_file, "w") as f:
        for cp in clip_paths:
            f.write(f"file '{os.path.abspath(cp)}'\n")

    raw_video = "tmp_edit/raw_concat.mp4"
    run_cmd([
        'ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', concat_file, 
        '-c', 'copy', raw_video
    ])

    run_cmd([
        'ffmpeg', '-y', 
        '-i', raw_video, 
        '-ss', str(start_offset), '-t', str(target_duration), '-i', audio_path, 
        '-map', '0:v', '-map', '1:a', 
        '-c:v', 'copy', 
        '-c:a', 'aac', '-b:a', '192k',
        '-shortest', 
        output_file
    ])
    
    print(f"\n==============================================")
    print(f"FAN CAM READY! File: {output_file}")
    print(f"==============================================")

if __name__ == '__main__':
    # You can change these searches to anything!
    vid = "Max Verstappen 4k overtakes no music"
    aud = "Skyfall bass boosted reverb"
    out = "Max_Verstappen_Edit.mp4"
    if len(sys.argv) > 1: vid = sys.argv[1]
    if len(sys.argv) > 2: aud = sys.argv[2]
    auto_edit(vid, aud, out)
