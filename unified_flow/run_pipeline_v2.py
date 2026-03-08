import sys
sys.stdout.reconfigure(encoding='utf-8')

import os, json, base64, time, uuid, argparse, urllib.request, wave, struct, math, subprocess
from dotenv import load_dotenv
load_dotenv()
import boto3

# ─── AWS Clients ──────────────────────────────────────────────────────────────
AWS_REGION  = os.environ.get('AWS_DEFAULT_REGION', 'us-east-1')
ACCOUNT_ID  = boto3.client('sts', region_name=AWS_REGION).get_caller_identity()['Account']

bedrock     = boto3.client('bedrock-runtime', region_name=AWS_REGION)
polly       = boto3.client('polly',           region_name=AWS_REGION)
s3          = boto3.client('s3',              region_name=AWS_REGION)
mc_base     = boto3.client('mediaconvert',    region_name=AWS_REGION)
iam         = boto3.client('iam',             region_name=AWS_REGION)

# ─── Configuration ────────────────────────────────────────────────────────────
S3_BUCKET       = os.environ.get('ASSETS_BUCKET', 'unified-flow-assets')
OUTPUT_DIR      = 'output'          # overridden per-run
NOVA_REEL_FPS   = 24                # Nova Reel outputs 24 fps
TARGET_FPS      = 60                # MediaConvert upsamples to 60 fps via FRAMEFORMER
CLIP_DURATION_S = 6                 # Nova Reel max per invocation (seconds)
WORDS_PER_SEC   = 2.0               # Polly rate estimate for SRT timing

# ─── S3 / IAM Bootstrap ───────────────────────────────────────────────────────
def ensure_s3_bucket():
    """Create the S3 bucket if it does not exist."""
    try:
        s3.head_bucket(Bucket=S3_BUCKET)
    except Exception:
        print(f"  Creating S3 bucket: {S3_BUCKET}")
        if AWS_REGION == 'us-east-1':
            s3.create_bucket(Bucket=S3_BUCKET)
        else:
            s3.create_bucket(
                Bucket=S3_BUCKET,
                CreateBucketConfiguration={'LocationConstraint': AWS_REGION}
            )
        s3.put_bucket_cors(
            Bucket=S3_BUCKET,
            CORSConfiguration={'CORSRules': [{
                'AllowedMethods': ['GET', 'PUT', 'POST'],
                'AllowedOrigins': ['*'],
                'AllowedHeaders': ['*'],
            }]}
        )

def get_or_create_mediaconvert_role() -> str:
    """Return ARN of the MediaConvert IAM role, creating it if needed."""
    role_name = 'MediaConvert_Unified_Flow_Role'
    try:
        return iam.get_role(RoleName=role_name)['Role']['Arn']
    except iam.exceptions.NoSuchEntityException:
        print(f"  Creating IAM role: {role_name}")
        trust = json.dumps({
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Principal": {"Service": "mediaconvert.amazonaws.com"},
                "Action": "sts:AssumeRole"
            }]
        })
        role_arn = iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=trust,
            Description='MediaConvert role for Unified Flow pipeline'
        )['Role']['Arn']
        iam.attach_role_policy(
            RoleName=role_name,
            PolicyArn='arn:aws:iam::aws:policy/AmazonS3FullAccess'
        )
        time.sleep(10)   # IAM propagation
        return role_arn

def get_mediaconvert_endpoint() -> str:
    """Return the account-specific MediaConvert endpoint URL.
    Uses the standard regional endpoint format to avoid DescribeEndpoints
    which requires a legacy subscription on some accounts.
    """
    try:
        # Try DescribeEndpoints first (works on most accounts)
        resp = mc_base.describe_endpoints(Mode='DEFAULT')
        return resp['Endpoints'][0]['Url']
    except Exception:
        # Fallback: construct endpoint from account ID + region
        # Format: https://{account_id}.mediaconvert.{region}.amazonaws.com
        sts = boto3.client('sts', region_name=AWS_REGION)
        account_id = sts.get_caller_identity()['Account']
        return f"https://{account_id}.mediaconvert.{AWS_REGION}.amazonaws.com"

def s3_upload(local_path: str, key: str, content_type='application/octet-stream') -> str:
    """Upload a local file to S3, return its s3:// URI."""
    s3.upload_file(local_path, S3_BUCKET, key, ExtraArgs={'ContentType': content_type})
    return f"s3://{S3_BUCKET}/{key}"

def s3_download(s3_uri: str, local_path: str):
    """Download an s3:// URI to a local path."""
    key = s3_uri.split(f's3://{S3_BUCKET}/')[-1]
    s3.download_file(S3_BUCKET, key, local_path)


# ════════════════════════════════════════════════════════════════════════════
# STEP 1 — Agentic Entity Detection + Cinematic Manifest  (Nova Pro)
# ════════════════════════════════════════════════════════════════════════════
def step1_agentic_manifest(user_prompt: str) -> dict:
    print("\n[1/6] Detecting genre & generating cinematic manifest via Nova Pro...")

    system_prompt = f"""You are an Elite Cinematographer and AI Video Director.
Your goal is to parse the user's prompt, classify the genre (Interior Design, Cinematic Action, Talking Head, etc.), and design a bulletproof video sequence.
Because AI Video Models hallucinate when movements are too complex, you MUST inject STRICT camera controls based on the genre into EVERY visual prompt.

GENRE EXAMPLES AND CAMERA CONTROLS (inject these directly into your visual prompts!):
- If INTERIOR/ARCHITECTURAL: [LOCKED STATIC CAMERA. TRIPOD SHOT. ZERO CAMERA MOVEMENT. NO PANNING. 50mm Lens. Photorealistic 8k architecture.]
- If ACTION/CAR: [DYNAMIC TRACKING SHOT. MOTION BLUR. DRONE FOOTAGE. Fast pacing.]
- If PERSON/PORTRAIT: [MEDIUM CLOSE UP. SHALLOW DEPTH OF FIELD. Bokeh background. Locked facial features. No body movement.]

Generate a logical sequence of shots. 
- A simple/short prompt only needs 1 or 2 shots.
- Complex stories or transformations (like 'bare floor to luxury build') need 3 shots.
Do NOT generate 3 shots if 1 shot is enough. 

RESPOND ONLY with a single JSON in the exact structure below:
{{
  "genre": "Architectural Build",
  "camera_rules": "[LOCKED STATIC CAMERA. TRIPOD SHOT. ZERO MOVEMENT.]",
  "strategy": {{"style": "8K ArchViz, photorealistic, soft natural lighting"}},
  "narration_ssml": "Where others see emptiness... we see potential.",
  "visual_prompts": [
    "Shot 1: [empty] A completely empty luxury living room, bare oak floors, white walls. [LOCKED STATIC CAMERA. TRIPOD SHOT. ZERO MOVEMENT.]",
    "Shot 2: [build] High-speed assembly: luxury leather furniture swirling onto the bare floor. [LOCKED STATIC CAMERA. TRIPOD SHOT. ZERO MOVEMENT.]"
  ]
}}"""

    body = {
        "messages": [{"role": "user", "content": [{"text": f"System: {system_prompt}\n\nUser Prompt: {user_prompt}"}]}],
        "inferenceConfig": {"maxTokens": 1024, "temperature": 0.6}
    }
    response = bedrock.invoke_model(
        modelId='amazon.nova-pro-v1:0', contentType='application/json',
        accept='application/json', body=json.dumps(body)
    )
    raw_text = json.loads(response['body'].read())['output']['message']['content'][0]['text']
    clean = raw_text.strip()
    if clean.startswith('```'):
        clean = clean.split('\n', 1)[1].rsplit('```', 1)[0]
    manifest = json.loads(clean)
    
    genre = manifest.get('genre', 'Unknown Genre')
    print(f"  Detected Genre : {genre}")
    print(f"  Camera Rules   : {manifest.get('camera_rules', 'None')}")
    print(f"  Prompts        : {len(manifest.get('visual_prompts', []))}")
    return manifest


# ════════════════════════════════════════════════════════════════════════════
# STEP 2 — Voiceover  (Amazon Polly Generative/Neural - Humanized)
# ════════════════════════════════════════════════════════════════════════════
def step2_synthesize_audio(manifest: dict) -> tuple:
    """Returns (local_path, s3_uri, duration_seconds, viseme_s3_uri)."""
    print("\n[2/6] Synthesising highly-conversational voiceover via Polly (Neural)...")
    
    # Extract narration, preferring raw text over pre-canned SSML
    raw_text = manifest.get('narration', manifest.get('narration_ssml', ''))
    if '<speak>' in raw_text:
        import re
        raw_text = re.sub('<[^<]+>', '', raw_text) # Strip existing SSML
    
    audio_path = os.path.join(OUTPUT_DIR, 'voiceover.mp3')
    
    try:
        # First try 'generative' engine which sounds incredibly natural (ElevenLabs competitor)
        ssml_gen = (
            f'<speak>'
            f'<amazon:domain name="conversational">'
            f'<prosody rate="90%" pitch="-2%">{raw_text}</prosody>'
            f'</amazon:domain>'
            f'</speak>'
        )
        resp = polly.synthesize_speech(
            Engine='generative', Text=ssml_gen, TextType='ssml',
            OutputFormat='mp3', VoiceId='Matthew', LanguageCode='en-US'
        )
        print("  Using Polly GENERATIVE engine for maximum realism.")
    except Exception as e:
        # Fallback to Neural if generative is not available in region or lacks permissions
        print(f"  Generative engine not available ({e}), falling back to High-Quality Neural.")
        # Neural Matthew doesn't support the 'conversational' domain tag or the 'pitch' tag.
        ssml_neural = f'<speak><prosody rate="90%">{raw_text}</prosody></speak>'
        resp = polly.synthesize_speech(
            Engine='neural', Text=ssml_neural, TextType='ssml',
            OutputFormat='mp3', VoiceId='Matthew', LanguageCode='en-US'
        )

    with open(audio_path, 'wb') as f:
        f.write(resp['AudioStream'].read())

    # Get word-level speech marks for perfect SRT captions
    viseme_resp = polly.synthesize_speech(
        Engine='neural', Text=raw_text, TextType='text', # Polly sometimes hates marks on complex SSML, so we use raw text
        OutputFormat='json', SpeechMarkTypes=['word'],
        VoiceId='Matthew', LanguageCode='en-US'
    )
    viseme_path = os.path.join(OUTPUT_DIR, 'visemes.json')
    with open(viseme_path, 'wb') as f:
        f.write(viseme_resp['AudioStream'].read())

    # Estimate duration accurately from the actual speech marks
    try:
        word_marks = [json.loads(l) for l in open(viseme_path) if l.strip()]
        dur = (word_marks[-1]['time'] / 1000.0 + 1.5) if word_marks else 10.0
    except Exception:
        dur = max(len(raw_text.split()) / 2.5, 4.0)

    print(f"  Voiceover saved: {audio_path}  (~{dur:.1f}s)")

    # Upload audio to S3 for MediaConvert
    audio_s3 = s3_upload(audio_path, f"{OUTPUT_DIR}/voiceover.mp3", 'audio/mpeg')
    viseme_s3 = s3_upload(viseme_path, f"{OUTPUT_DIR}/visemes.json", 'application/json')

    return audio_path, audio_s3, dur, viseme_path, viseme_s3


# ════════════════════════════════════════════════════════════════════════════
# STEP 3 — BGM: royalty-free track from Pixabay CDN
# ════════════════════════════════════════════════════════════════════════════
BGM_URLS = [
    "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3",
    "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-3.mp3",
    "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-5.mp3",
    "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-8.mp3",
    "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-9.mp3",
]

def step3_get_bgm(prompt: str = "") -> tuple:
    """Downloads BGM (either via yt-dlp if requested in prompt, or royalty-free fallback)."""
    import random
    bgm_path = os.path.join(OUTPUT_DIR, 'bgm.mp3')
    
    # Try yt-dlp if requested
    if 'music' in prompt.lower() or 'song' in prompt.lower() or 'skyfall' in prompt.lower():
        print("\n[3/6] Fetching requested music via YouTube...")
        try:
            import subprocess
            search_query = "cinematic ambient background music"
            if "skyfall" in prompt.lower():
                search_query = "skyfall bass boosted reverb"
            else:
                genres = ["ambient", "lofi", "acoustic", "piano", "synthwave", "orchestral", "ethereal", "chillout", "epic", "uplifting"]
                search_query = f"{prompt} {random.choice(genres)} background music no copyright"

            cmd = [
                sys.executable, '-m', 'yt_dlp',
                f'ytsearch1:{search_query}',
                '-x', '--audio-format', 'mp3',
                '-o', bgm_path,
                '--force-overwrites'
            ]
            subprocess.run(cmd, check=True, capture_output=True)
            if os.path.exists(bgm_path):
                print(f"  BGM downloaded via yt-dlp OK")
                bgm_s3 = s3_upload(bgm_path, f"{OUTPUT_DIR}/bgm.mp3", 'audio/mpeg')
                return bgm_path, bgm_s3
        except Exception as e:
            print(f"  yt-dlp failed: {e}. Falling back to default BGM.")

    print("\n[3/6] Downloading default royalty-free BGM...")
    
    # Shuffle URLs to avoid picking the same fallback each time
    urls_to_try = list(BGM_URLS)
    random.shuffle(urls_to_try)
    
    for url in urls_to_try:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=20) as r, open(bgm_path, 'wb') as f:
                f.write(r.read())
            print(f"  BGM downloaded OK")
            bgm_s3 = s3_upload(bgm_path, f"{OUTPUT_DIR}/bgm.mp3", 'audio/mpeg')
            return bgm_path, bgm_s3
        except Exception as e:
            print(f"  Failed ({str(e)[:60]}), trying next...")
    print("  No BGM available — voiceover only.")
    return None, None


# ════════════════════════════════════════════════════════════════════════════
# STEP 4 — BEAT DETECTION & GENAI VIDEO (Nova Canvas + Reel)
# ════════════════════════════════════════════════════════════════════════════
def step4_analyze_beats_and_sync(audio_path: str) -> list:
    """Uses librosa to find beats for visual synchronization."""
    print("\n[4/6] Analyzing music hits for video sync...")
    try:
        import librosa
        y, sr = librosa.load(audio_path, sr=None)
        tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
        beat_times = librosa.frames_to_time(beats, sr=sr)
        return list(beat_times)
    except Exception as e:
        print(f"  Beat detection failed: {e}. Falling back to 6s intervals.")
        return [i * 6.0 for i in range(10)]

_BLOCKED = ['kill','fight','battle','war','weapon','gun','shoot',
            'blood','violent','attack','dead','destroy','explosion']

def _sanitise(text: str) -> str:
    for w in _BLOCKED:
        text = text.replace(w, '').replace(w.capitalize(), '')
    return ' '.join(text.split())

def _generate_keyframe_png(prompt: str, idx: int, style: str = "Photorealistic", reference_b64: str = None) -> bytes:
    """
    Generate a PNG keyframe using Nova Canvas to act as the visual seed.
    """
    enriched = _sanitise(f"Cinematic, {style}, {prompt}, no text, no equipment.")[:500]
    
    body = {
        "taskType": "TEXT_IMAGE",
        "textToImageParams": {"text": enriched},
        "imageGenerationConfig": { "numberOfImages": 1, "height": 720, "width": 1280, "cfgScale": 8.0, "seed": idx * 37 + 13 }
    }
    
    try:
        print(f"    DEBUG: Invoking Canvas (Task: {body.get('taskType')})...", flush=True)
        resp = bedrock.invoke_model(
            modelId='amazon.nova-canvas-v1:0',
            body=json.dumps(body),
            accept='application/json', contentType='application/json'
        )
        print(f"    DEBUG: Canvas Success.", flush=True)
        output = json.loads(resp['body'].read())
        img_bytes = base64.b64decode(output['images'][0])
        print(f"    DEBUG: Decoded {len(img_bytes)} bytes.", flush=True)
        return img_bytes
    except Exception as e:
        print(f"    DEBUG: Canvas CRITICAL FAIL: {str(e)}", flush=True)
        return None

def step4_launch_nova_reel_jobs(manifest: dict, audio_duration: float, audio_path: str) -> list:
    print("\n[4/6] Step 4: Launching Video Generation via Nova Reel...", flush=True)
    prompts = manifest.get('visual_prompts', [])
    if not prompts:
        print("  ERROR: No prompts in manifest.")
        return []
    
    genre = manifest.get('genre', 'Unknown Genre')
    style = manifest.get('strategy', {}).get('style', 'Cinematic, high quality')
    camera_rules = manifest.get('camera_rules', '')
    
    print(f"  Genre  : {genre}")
    print(f"  Rules  : {camera_rules}")
    print(f"  Style  : {style}")

    # For now, we rely primarily on the LLM's strict camera rules in the prompts for temporal consistency.
    # We will generate a Canvas keyframe ONLY for the first shot as an establishing anchor.
    # (In a more advanced pipeline, you could do Image-to-Image for all 3 shots perfectly).
    
    print("  Step A: Generating Establishing Anchor Image...", flush=True)
    first_shot_prompt = prompts[0]
    anchor_bytes = _generate_keyframe_png(first_shot_prompt, idx=0, style=style)
    anchor_b64 = base64.b64encode(anchor_bytes).decode('utf-8') if anchor_bytes else None

    jobs = []
    
    # Calculate how many 6-second shots we actually need to cover the voiceover
    import math
    required_shots = max(1, math.ceil(audio_duration / 6.0))
    print(f"  Audio is {audio_duration:.1f}s. Generating {required_shots} shots to match duration.", flush=True)
    
    for i in range(required_shots):
        p = prompts[i % len(prompts)] # Loop back through prompts if we need more shots than we have prompts
        print(f"  Preparing Shot {i+1}/{required_shots}: {p[:60]}...", flush=True)
        
        shot_key = f"nova_reel/shot_{i}_{uuid.uuid4().hex[:6]}"
        s3_uri = f"s3://{S3_BUCKET}/{OUTPUT_DIR}/{shot_key}/".replace('\\', '/')
        
        # We only feed the anchor image to the first shot. Over time, we can extend this to track images continuously.
        seed_img = anchor_b64 if i == 0 else None
        
        model_input = {
            "taskType": "TEXT_VIDEO",
            "videoGenerationConfig": { 
                "durationSeconds": 6, "fps": 24, "dimension": "1280x720", "seed": 42 + i
            },
            "textToVideoParams": { "text": f"{p} {style}"[:500] }
        }
        if seed_img:
            model_input["textToVideoParams"]["images"] = [{"format": "png", "source": {"bytes": seed_img}}]

        try:
            print(f"  Attempting Invocation {i+1}...", flush=True)
            try:
                # Try dict input
                resp = bedrock.start_async_invoke(
                    modelId='amazon.nova-reel-v1:0', modelInput=model_input,
                    outputDataConfig={'s3OutputDataConfig': {'s3Uri': s3_uri}}
                )
            except Exception as e_inner:
                print(f"  Switching to String Input for Shot {i+1}...", flush=True)
                resp = bedrock.start_async_invoke(
                    modelId='amazon.nova-reel-v1:0', modelInput=json.dumps(model_input),
                    outputDataConfig={'s3OutputDataConfig': {'s3Uri': s3_uri}}
                )

            jobs.append({ 
                'arn': resp['invocationArn'], 
                'output_s3_prefix': f"{OUTPUT_DIR}/{shot_key}".replace('\\', '/'), 
                'shot_idx': i 
            })
            print(f"  Shot {i+1} SUCCESS.", flush=True)
        except Exception as e_outer:
            print(f"  Shot {i+1} CRITICAL FAIL: {str(e_outer)[:150]}", flush=True)

    return jobs


# ════════════════════════════════════════════════════════════════════════════
# STEP 5 — Poll Nova Reel jobs until all complete, download clips
# ════════════════════════════════════════════════════════════════════════════
def step5_poll_and_collect_clips(jobs: list) -> list:
    """
    Polls all Nova Reel async invocations until COMPLETED or FAILED.
    Applies REVERSE VFX to shots flagged for assembly.
    """
    if not jobs:
        raise RuntimeError("No Nova Reel jobs were submitted in Step 4. Check errors above.")

    print(f"\n[5/6] Polling {len(jobs)} Nova Reel job(s) and applying VFX...")
    pending = {j['arn']: j for j in jobs}
    results = {}  # shot_idx -> local_path
    
    POLL_INTERVAL = 45
    MAX_WAIT = 1800
    elapsed = 0
    
    while pending and elapsed < MAX_WAIT:
        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL
        for arn, job in list(pending.items()):
            try:
                resp = bedrock.get_async_invoke(invocationArn=arn)
                status = resp.get('status', 'InProgress')
                if status == 'Completed':
                    # 1. Determine S3 key for download
                    s3_prefix = job['output_s3_prefix']
                    ls = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=s3_prefix)
                    keys = [o['Key'] for o in ls.get('Contents', []) if o['Key'].endswith('.mp4')]
                    if not keys:
                        print(f"  Warning: No MP4 for shot {job['shot_idx']+1}")
                        del pending[arn]
                        continue
                    
                    # 2. Download raw file
                    local_raw = os.path.join(OUTPUT_DIR, f"raw_shot_{job['shot_idx']}.mp4")
                    s3.download_file(S3_BUCKET, keys[0], local_raw)
                    
                    # 3. Apply REVERSE VFX if flagged (Legacy) or Prepare for Swipe
                    results[job['shot_idx']] = local_raw
                    
                    if job.get('reverse_vfx'):
                        local_final = os.path.join(OUTPUT_DIR, f"clip_{job['shot_idx']}.mp4")
                        subprocess.run(['ffmpeg', '-y', '-i', local_raw, '-vf', 'reverse', '-af', 'areverse', local_final], check=True, capture_output=True)
                        results[job['shot_idx']] = local_final
                    
                    del pending[arn]
                    print(f"  Shot {job['shot_idx']+1} DONE ({elapsed}s)")
                    
                elif status == 'Failed':
                    print(f"  Shot {job['shot_idx']+1} FAILED: {resp.get('failureMessage', 'unknown')}")
                    del pending[arn]
                else:
                    print(f"  Shot {job['shot_idx']+1} still {status} ({elapsed}s)")
            except Exception as e:
                print(f"  Poll error for shot {job['shot_idx']+1}: {e}")

    # Return ordered list
    return [results[i] for i in sorted(results.keys())]



# ════════════════════════════════════════════════════════════════════════════
# STEP 6 — AWS MediaConvert: Professional 60fps composition
# ════════════════════════════════════════════════════════════════════════════
def _build_srt(viseme_path: str) -> str:
    """Parse Polly word marks and generate SRT caption file."""
    srt_path = os.path.join(OUTPUT_DIR, 'captions.srt')
    try:
        word_marks = [json.loads(l) for l in open(viseme_path) if l.strip()]
        words_per_chunk = 6
        chunks, i = [], 0
        while i < len(word_marks):
            chunk = word_marks[i:i+words_per_chunk]
            start_ms = chunk[0]['time']
            end_ms = word_marks[i+words_per_chunk]['time'] if i+words_per_chunk < len(word_marks) else chunk[-1]['time'] + 600
            text = ' '.join(w['value'] for w in chunk)
            chunks.append((start_ms, end_ms, text))
            i += words_per_chunk

        def fmt(ms):
            h,rem = divmod(ms, 3_600_000)
            m,rem = divmod(rem, 60_000)
            s,ms_ = divmod(rem, 1000)
            return f"{h:02d}:{m:02d}:{s:02d},{ms_:03d}"

        with open(srt_path, 'w', encoding='utf-8') as f:
            for idx, (s, e, t) in enumerate(chunks, 1):
                f.write(f"{idx}\n{fmt(s)} --> {fmt(e)}\n{t}\n\n")
        print(f"  SRT generated: {len(chunks)} caption chunks")
    except Exception as e:
        print(f"  SRT generation failed ({e}), captions will be skipped")
        open(srt_path, 'w').close()
    return srt_path


def _upload_clips_to_s3(clip_paths: list) -> list:
    """Upload local clip MP4s to S3, return list of s3:// URIs."""
    uris = []
    for i, path in enumerate(clip_paths):
        key = f"{OUTPUT_DIR}/composed_clips/clip_{i}.mp4"
        uri = s3_upload(path, key, 'video/mp4')
        print(f"  Uploaded clip {i+1} → {uri}")
        uris.append(uri)
    return uris


def _build_mediaconvert_job(
    clip_s3_uris: list,
    audio_s3_uri: str,
    bgm_s3_uri: str,
    srt_s3_uri: str,
    output_prefix: str,
    mc_role_arn: str,
    audio_duration: float
) -> dict:
    """
    Build a MediaConvert job that:
    - Concatenates all Nova Reel clips sequentially
    - Overlays voiceover audio via ExternalAudioFileInput
    - Usamples from 24fps → 60fps via FRAMEFORMER
    - Burns SRT captions (if available)
    - Exports 3 aspect ratios: 16x9 (1280x720), 9x16 (720x1280), 1x1 (720x720)
    """
    # Build Input entries for each video clip
    # Audio comes from external voiceover file on the FIRST clip only;
    # MediaConvert extends it across subsequent inputs automatically.
    inputs = []
    for idx, clip_uri in enumerate(clip_s3_uris):
        inp = {
            "FileInput": clip_uri,
            "TimecodeSource": "ZEROBASED",
            "VideoSelector": {},
            "AudioSelectors": {}
        }
        if idx == 0:
            # Attach voiceover as the audio source for the whole timeline
            inp["AudioSelectors"]["Audio Selector 1"] = {
                "DefaultSelection": "DEFAULT",
                "ExternalAudioFileInput": audio_s3_uri,
                "Offset": 0
            }
        inputs.append(inp)

    def video_desc(width, height, crop_filter=None):
        """Build a VideoDescription for a given output resolution."""
        vd = {
            "Width": width,
            "Height": height,
            "CodecSettings": {
                "Codec": "H_264",
                "H264Settings": {
                    "RateControlMode": "QVBR",
                    "QvbrSettings": {"QvbrQualityLevel": 8},
                    "FramerateControl": "SPECIFIED",
                    "FramerateNumerator": TARGET_FPS,
                    "FramerateDenominator": 1,
                    "FramerateConversionAlgorithm": "FRAMEFORMER",
                    "CodecProfile": "HIGH",
                    "CodecLevel": "AUTO",
                    "InterlaceMode": "PROGRESSIVE",
                    "ScanTypeConversionMode": "INTERLACED",
                }
            }
        }
        if crop_filter:
            vd["VideoPreprocessors"] = {
                "ImageInserter": None  # placeholder; actual crop via Preprocessors not shown
            }
            # For aspect ratio crops we use ScalingBehavior instead
            vd["ScalingBehavior"] = "STRETCH_TO_OUTPUT"
        return vd

    # Caption settings (burn-in from SRT)
    caption_selector = {
        "CaptionSelectors": {
            "Captions Selector 1": {
                "SourceSettings": {
                    "SourceType": "SRT",
                    "FileSourceSettings": {
                        "SourceFile": srt_s3_uri
                    }
                }
            }
        }
    } if srt_s3_uri else {}

    burn_in_dest = {
        "DestinationSettings": {
            "DestinationType": "BURN_IN",
            "BurninDestinationSettings": {
                "FontSize": 32,
                "FontColor": "WHITE",
                "OutlineColor": "BLACK",
                "OutlineSize": 3,
                "ShadowColor": "BLACK",
                "ShadowOpacity": 100,
                "ShadowXOffset": 2,
                "ShadowYOffset": 2,
                "Alignment": "CENTERED",
                "XPosition": 0,
                "YPosition": 0,
                "TeletextSpacing": "FIXED_GRID",
                "BackgroundColor": "NONE"
            }
        },
        "CaptionSelectorName": "Captions Selector 1"
    }

    def make_output(name_modifier, width, height, pad_strategy="LETTERBOX"):
        out = {
            "NameModifier": name_modifier,
            "ContainerSettings": {
                "Container": "MP4",
                "Mp4Settings": {"CslgAtom": "INCLUDE", "CttsVersion": 0}
            },
            "VideoDescription": {
                "Width": width,
                "Height": height,
                "ScalingBehavior": pad_strategy,
                "CodecSettings": {
                    "Codec": "H_264",
                    "H264Settings": {
                        "RateControlMode": "QVBR",
                        "QvbrSettings": {"QvbrQualityLevel": 8},
                        "FramerateControl": "SPECIFIED",
                        "FramerateNumerator": TARGET_FPS,
                        "FramerateDenominator": 1,
                        "FramerateConversionAlgorithm": "FRAMEFORMER",
                        "CodecProfile": "HIGH",
                        "CodecLevel": "AUTO",
                        "InterlaceMode": "PROGRESSIVE",
                    }
                }
            },
            "AudioDescriptions": [
                {
                    "AudioSourceName": "Audio Selector 1",
                    "CodecSettings": {
                        "Codec": "AAC",
                        "AacSettings": {
                            "Bitrate": 192000,
                            "SampleRate": 48000,
                            "CodingMode": "CODING_MODE_2_0"
                        }
                    },
                    "AudioNormalizationSettings": {
                        "Algorithm": "ITU_BS_1770_3",
                        "AlgorithmControl": "CORRECT_AUDIO",
                        "TargetLkfs": -14.0  # Broadcast standard loudness
                    }
                }
            ]
        }
        # Only add captions if SRT is available
        if srt_s3_uri:
            out["CaptionDescriptions"] = [burn_in_dest]
        return out

    job_settings = {
        "TimecodeConfig": {"Source": "ZEROBASED"},
        "Inputs": inputs,
        "OutputGroups": [
            {
                "Name": "16x9 Landscape",
                "OutputGroupSettings": {
                    "Type": "FILE_GROUP_SETTINGS",
                    "FileGroupSettings": {
                        "Destination": f"s3://{S3_BUCKET}/{output_prefix}final_"
                    }
                },
                "Outputs": [
                    make_output("16x9_60fps", 1280, 720, "STRETCH_TO_OUTPUT"),
                    make_output("9x16_60fps",  720, 1280, "LETTERBOX"),
                    make_output("1x1_60fps",   720,  720, "LETTERBOX"),
                ]
            }
        ]
    }

    # Update first input with caption selector if SRT exists
    if srt_s3_uri:
        job_settings["Inputs"][0]["CaptionSelectors"] = {
            "Captions Selector 1": {
                "SourceSettings": {
                    "SourceType": "SRT",
                    "FileSourceSettings": {
                        "SourceFile": srt_s3_uri
                    }
                }
            }
        }

    return {
        "Role": mc_role_arn,
        "Settings": job_settings,
        "AccelerationSettings": {"Mode": "PREFERRED"},
        "StatusUpdateInterval": "SECONDS_30",
        "Queue": f"arn:aws:mediaconvert:{AWS_REGION}:{ACCOUNT_ID}:queues/Default"
    }


def _ffmpeg_fallback_compose(clip_paths: list, audio_path: str, bgm_path: str, user_prompt: str = "") -> dict:
    """
    FFmpeg fallback when MediaConvert is unavailable.
    Concatenates Nova Reel clips, overlays voiceover+BGM, outputs 3 aspect ratios.
    """
    import subprocess, shutil

    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        raise RuntimeError("FFmpeg not found. Install ffmpeg or activate AWS MediaConvert.")

    concat_file = os.path.join(OUTPUT_DIR, 'concat.txt')
    with open(concat_file, 'w') as f:
        for cp in clip_paths:
            abs_path = os.path.abspath(cp).replace('\\', '/')
            f.write(f"file '{abs_path}'\n")

    concat_path = os.path.join(OUTPUT_DIR, 'raw_concat.mp4')
    subprocess.run([
        ffmpeg, '-y', '-f', 'concat', '-safe', '0', '-i', concat_file,
        '-c', 'copy', concat_path
    ], check=True, capture_output=True)

    RATIOS = {
        '16:9': ('1280', '720',  ''),
        '9:16': ('720',  '1280', ',transpose=1'),
        '1:1':  ('720',  '720',  ',crop=720:720'),
    }

    outputs = {}
    for ratio, (w, h, vf_extra) in RATIOS.items():
        out_name = f"final_{ratio.replace(':','x')}_60fps.mp4"
        out_path = os.path.join(OUTPUT_DIR, out_name)

        # Build audio filter
        # Input 0: video, Input 1: voiceover, Input 2: bgm (optional)
        if bgm_path and os.path.exists(bgm_path):
            is_edit = 'edit' in user_prompt.lower()
            bgm_vol = '0.7' if is_edit else '0.12'
            vo_vol = '0.3' if is_edit else '1.0'
            bgm_offset = ['-ss', '00:01:05'] if is_edit else [] # Start at the drop for edit videos
            
            audio_inputs = ['-i', audio_path] + bgm_offset + ['-i', bgm_path]
            # Use duration=longest so the amix track lasts as long as the 3-minute BGM
            # We use apad on the voiceover so it continues with silence after speaking
            audio_filter = f'[2:a]volume={bgm_vol}[bgm];[1:a]volume={vo_vol},apad[vo];[vo][bgm]amix=inputs=2:duration=longest[aout]'
            audio_map = ['-map', '[aout]', '-map', '0:v']
        else:
            audio_inputs = ['-i', audio_path]
            # pad with silence so the audio track is infinite, letting the video be the shortest input
            audio_filter = '[1:a]volume=1.0,apad[aout]'
            audio_map = ['-map', '[aout]', '-map', '0:v']

        vf = f'scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2{vf_extra}'

        cmd = (
            [ffmpeg, '-y',
             '-i', concat_path]
            + audio_inputs
            + ['-vf', vf,
               '-r', '60',
               '-filter_complex', audio_filter]
            + audio_map
            + ['-c:v', 'libx264', '-preset', 'fast', '-crf', '20',
               '-c:a', 'aac', '-b:a', '192k',
               '-shortest', out_path] 
        )
        print(f"  FFmpeg composing {ratio}...")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  FFmpeg error: {result.stderr[-500:]}")
            continue

        s3_key = f"{OUTPUT_DIR}/{out_name}"
        s3.upload_file(out_path, S3_BUCKET, s3_key, ExtraArgs={'ContentType': 'video/mp4'})
        url = s3.generate_presigned_url(
            'get_object',
            Params={'Bucket': S3_BUCKET, 'Key': s3_key},
            ExpiresIn=86400
        )
        outputs[ratio] = {'s3_uri': f"s3://{S3_BUCKET}/{s3_key}", 'presigned_url': url}
        print(f"  {ratio} done → {out_path}")

    return outputs


def step6_mediaconvert_compose(
    clip_paths: list,
    audio_path: str,
    bgm_path: str,
    viseme_path: str,
    audio_duration: float
) -> dict:
    """
    Uses AWS MediaConvert to:
    1. Upload all assets to S3
    2. Concatenate Nova Reel clips
    3. Overlay voiceover audio
    4. Burn SRT captions
    5. Upsample to 60fps via FRAMEFORMER
    6. Export 16:9, 9:16, 1:1 formats
    Returns dict of {ratio: presigned_url}
    """
    print("\n[6/6] Composing final video with AWS MediaConvert (60fps)...")

    # ── 6a: Upload assets ────────────────────────────────────────────────
    print("  Uploading clips to S3...")
    clip_s3_uris = _upload_clips_to_s3(clip_paths)

    print("  Uploading audio to S3...")
    audio_s3 = s3_upload(audio_path, f"{OUTPUT_DIR}/voiceover_final.mp3", 'audio/mpeg')

    bgm_s3 = None
    if bgm_path and os.path.exists(bgm_path):
        bgm_s3 = s3_upload(bgm_path, f"{OUTPUT_DIR}/bgm_final.mp3", 'audio/mpeg')

    print("  Building SRT captions...")
    srt_path = _build_srt(viseme_path)
    srt_s3 = None
    if os.path.getsize(srt_path) > 0:
        srt_s3 = s3_upload(srt_path, f"{OUTPUT_DIR}/captions.srt", 'text/plain')
        print(f"  SRT uploaded → {srt_s3}")

    # ── 6b: Prepare MediaConvert ─────────────────────────────────────────
    print("  Fetching MediaConvert endpoint...")
    mc_endpoint = get_mediaconvert_endpoint()
    mc = boto3.client('mediaconvert', region_name=AWS_REGION, endpoint_url=mc_endpoint)

    print("  Ensuring IAM role for MediaConvert...")
    mc_role_arn = get_or_create_mediaconvert_role()

    output_prefix = f"{OUTPUT_DIR}/mediaconvert_out/"
    job_payload = _build_mediaconvert_job(
        clip_s3_uris, audio_s3, bgm_s3, srt_s3,
        output_prefix, mc_role_arn, audio_duration
    )

    # ── 6c: Submit job ───────────────────────────────────────────────────
    print("  Submitting MediaConvert job...")
    job_resp = mc.create_job(**job_payload)
    job_id = job_resp['Job']['Id']
    print(f"  Job ID: {job_id}")

    # ── 6d: Poll MediaConvert job ────────────────────────────────────────
    POLL_INTERVAL = 20
    MAX_WAIT = 900
    elapsed = 0
    while elapsed < MAX_WAIT:
        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL
        status_resp = mc.get_job(Id=job_id)
        status = status_resp['Job']['Status']
        pct = status_resp['Job'].get('JobPercentComplete', 0)
        print(f"  MediaConvert: {status} — {pct}% ({elapsed}s)")
        if status == 'COMPLETE':
            break
        if status in ('ERROR', 'CANCELED'):
            err = status_resp['Job'].get('ErrorMessage', 'Unknown error')
            raise RuntimeError(f"MediaConvert job failed: {err}")

    # ── 6e: Collect output locations ────────────────────────────────────
    outputs = {}
    suffixes = {
        '16:9':  f"{output_prefix}final_16x9_60fps.mp4",
        '9:16':  f"{output_prefix}final_9x16_60fps.mp4",
        '1:1':   f"{output_prefix}final_1x1_60fps.mp4",
    }
    for ratio, key in suffixes.items():
        url = s3.generate_presigned_url(
            'get_object',
            Params={'Bucket': S3_BUCKET, 'Key': key},
            ExpiresIn=86400  # 24-hour download link
        )
        outputs[ratio] = {'s3_uri': f"s3://{S3_BUCKET}/{key}", 'presigned_url': url}
        # Also download locally
        local_name = key.split('/')[-1]
        try:
            s3.download_file(S3_BUCKET, key, os.path.join(OUTPUT_DIR, local_name))
            print(f"  Downloaded: {local_name}")
        except Exception as e:
            print(f"  Could not download {local_name}: {e}")

    return outputs


# ════════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════════
DEFAULT_PROMPT = (
    "Promotional video for Seven Wonders Interiors Studio in Bangalore. "
    "Showcase their stunning modular kitchen designs, modern living rooms, "
    "and premium bedroom interiors. The studio creates luxurious yet functional "
    "spaces that transform houses into dream homes. Warm, aspirational tone."
)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('prompt', nargs='?', default=DEFAULT_PROMPT)
    args = parser.parse_args()

    global OUTPUT_DIR
    run_id = uuid.uuid4().hex[:8]
    OUTPUT_DIR = f'output/{run_id}'
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    sep = '=' * 68
    print(f"\n{sep}")
    print(f"  UNIFIED FLOW V3  |  Nova Reel + MediaConvert Pipeline")
    print(sep)
    print(f"  Prompt : {args.prompt[:75]}...")
    print(f"  Run ID : {run_id}")
    print(f"  Bucket : {S3_BUCKET}")
    print(f"  Target : {TARGET_FPS}fps output via AWS MediaConvert FRAMEFORMER")
    print(f"{sep}\n")

    # Bootstrap S3
    ensure_s3_bucket()

    # ── Run pipeline ──────────────────────────────────────────────────────
    manifest = step1_agentic_manifest(args.prompt)
    with open(os.path.join(OUTPUT_DIR, 'manifest.json'), 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    audio_path, audio_s3, audio_dur, viseme_path, viseme_s3 = step2_synthesize_audio(manifest)
    bgm_path, bgm_s3 = step3_get_bgm(args.prompt)

    nova_jobs = step4_launch_nova_reel_jobs(manifest, audio_dur, audio_path)
    clip_paths = step5_poll_and_collect_clips(nova_jobs)

    try:
        outputs = step6_mediaconvert_compose(
            clip_paths, audio_path, bgm_path, viseme_path, audio_dur
        )
    except Exception as mc_err:
        print(f"\n  MediaConvert unavailable ({mc_err.__class__.__name__}): {mc_err}")
        print("  Falling back to FFmpeg for local composition...")
        outputs = _ffmpeg_fallback_compose(clip_paths, audio_path, bgm_path, args.prompt)


    # ── Summary ───────────────────────────────────────────────────────────
    print(f"\n{sep}")
    print(f"  PIPELINE COMPLETE!")
    print(sep)
    for ratio, info in outputs.items():
        print(f"\n  [{ratio}]")
        print(f"    S3  : {info['s3_uri']}")
        print(f"    URL : {info['presigned_url']}")
        print(f"    [APP_OUTPUT_URL]: {info['presigned_url']}")
    local_files = [f for f in os.listdir(OUTPUT_DIR) if f.endswith('.mp4')]
    if local_files:
        print(f"\n  Local files in output/{run_id}/:")
        for f in local_files:
            print(f"    - {f}")
            print(f"    [APP_LOCAL_FILE]: {os.path.join(OUTPUT_DIR, f)}")
    print(f"\n{sep}\n")


if __name__ == '__main__':
    main()
