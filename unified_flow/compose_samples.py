import os, sys, shutil, subprocess
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import run_pipeline_v2

# Override the output directory for this script
COMPOSE_DIR = 'output/good_samples'
run_pipeline_v2.OUTPUT_DIR = COMPOSE_DIR
os.makedirs(COMPOSE_DIR, exist_ok=True)

samples = {
    "Macro_Product": {
        "prompt": "Cinematic macro shot. Extreme close up view of a luxurious gold mechanical watch with moving gears.",
        "file": os.path.join(COMPOSE_DIR, "Macro_Product_16x9.mp4"),
        "narration": "Precision engineered. Every gear in perfect harmony."
    },
    "Ambient_Cinemagraph": {
        "prompt": "Cinematic establishing shot. A cozy cabin in snowy woods at twilight.",
        "file": os.path.join(COMPOSE_DIR, "Ambient_Cinemagraph_16x9.mp4"),
        "narration": "Find your perfect winter escape today."
    },
    "Drone_Landscape": {
        "prompt": "Cinematic sweeping drone shot. High altitude view flying extremely slowly over a majestic misty mountain.",
        "file": os.path.join(COMPOSE_DIR, "Drone_Landscape_16x9.mp4"),
        "narration": "Experience the untamed majesty of nature."
    }
}

for name, data in samples.items():
    print(f"\n==========================================")
    print(f"Processing {name} with Audio & Captions")
    print(f"==========================================")
    
    # Check if the base video actually exists
    if not os.path.exists(data["file"]):
        print(f"Skipping {name}, base video not found at {data['file']}")
        continue
    
    # 1. Voiceover
    # We pass a faux manifest to the synthesize_audio function
    manifest = {"narration": data["narration"]}
    # To prevent overwriting the same files, we prefix the output files
    run_pipeline_v2.OUTPUT_DIR = os.path.join(COMPOSE_DIR, name)
    os.makedirs(run_pipeline_v2.OUTPUT_DIR, exist_ok=True)
    
    audio_path, _, dur, viseme_path, _ = run_pipeline_v2.step2_synthesize_audio(manifest)
    
    # 2. BGM
    bgm_prompt = f"cinematic high quality background music {name}"
    bgm_path, _ = run_pipeline_v2.step3_get_bgm(bgm_prompt)
    
    # 3. Subtitles
    srt_path = run_pipeline_v2._build_srt(viseme_path)
    
    # 4. FFmpeg Composition with burnt-in Captions
    final_output = os.path.join(COMPOSE_DIR, f"{name}_Final.mp4")
    
    # Format subtitle path securely for windows ffmpeg (escape colon)
    # E.g. g:/ai for bharat/ -> g\:/ai for bharat/
    srt_formatted = srt_path.replace("\\", "/").replace(":", "\\:")
    
    ffmpeg_cmd = [
        '.venv\\Scripts\\ffmpeg.exe', '-y',  # Use environment ffmpeg if it exists, otherwise assuming it's in path
    ] if os.path.exists('.venv/Scripts/ffmpeg.exe') else ['ffmpeg', '-y']
    
    ffmpeg_cmd.extend([
        '-i', data['file'],
        '-i', audio_path,
        '-i', bgm_path,
        '-filter_complex',
        f"[1:a]volume=1.0,apad[vo];[2:a]volume=0.15[bgm];[vo][bgm]amix=inputs=2:duration=longest,afade=t=out:st=5:d=1[aout];[0:v]subtitles='{srt_formatted}'[vout]",
        '-map', '[vout]',
        '-map', '[aout]',
        '-c:v', 'libx264',
        '-c:a', 'aac',
        '-shortest',
        final_output
    ])
    
    print(f"  Running FFmpeg to compose {name}_Final.mp4...")
    try:
        subprocess.run(ffmpeg_cmd, check=True)
        print(f"  Successfully composed: {final_output}")
    except subprocess.CalledProcessError as e:
        print(f"  FFmpeg failed for {name}: {e}")

print("\nDone! Check output/good_samples/ for the *_Final.mp4 files.")
