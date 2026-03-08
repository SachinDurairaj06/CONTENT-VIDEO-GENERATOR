import os, json, time, uuid, boto3
from dotenv import load_dotenv
load_dotenv()

AWS_REGION = os.environ.get('AWS_DEFAULT_REGION', 'us-east-1')
S3_BUCKET = os.environ.get('ASSETS_BUCKET', 'unified-flow-assets')
OUTPUT_DIR = 'output/good_samples'

os.makedirs(OUTPUT_DIR, exist_ok=True)

bedrock = boto3.client('bedrock-runtime', region_name=AWS_REGION)
s3 = boto3.client('s3', region_name=AWS_REGION)

prompts = {
    "Macro_Product": "Cinematic macro shot. Extreme close up view of a luxurious gold mechanical watch with moving gears. Dramatic studio lighting, dark background, sharp focus, 8k resolution. Subtle motion of gears.",
    "Ambient_Cinemagraph": "Cinematic establishing shot. A cozy cabin in snowy woods at twilight. Warm glowing windows. Only the snow is gently falling and smoke slowly rises from the chimney. Unmoving locked tripod camera, still landscape, photorealistic.",
    "Drone_Landscape": "Cinematic sweeping drone shot. High altitude view flying extremely slowly over a majestic misty mountain canyon at sunrise. Golden hour lighting, volumetric sunlight. Smooth slow sweeping camera movement."
}

jobs = {}

print("Submitting jobs to Nova Reel...")
for name, p in prompts.items():
    shot_key = f"nova_reel/sample_{name}_{uuid.uuid4().hex[:6]}"
    s3_uri = f"s3://{S3_BUCKET}/{shot_key}/".replace('\\', '/')
    
    model_input = {
        "taskType": "TEXT_VIDEO",
        "videoGenerationConfig": { 
            "durationSeconds": 6, "fps": 24, "dimension": "1280x720", "seed": 42
        },
        "textToVideoParams": { "text": p[:500] }
    }
    
    try:
        resp = bedrock.start_async_invoke(
            modelId='amazon.nova-reel-v1:0', 
            modelInput=model_input,
            outputDataConfig={'s3OutputDataConfig': {'s3Uri': s3_uri}}
        )
        jobs[resp['invocationArn']] = {'name': name, 's3_prefix': shot_key}
        print(f"  Submitted {name} successfully.")
    except Exception as e:
        # Fallback to string JSON if dict fails
        try:
            resp = bedrock.start_async_invoke(
                modelId='amazon.nova-reel-v1:0', 
                modelInput=json.dumps(model_input),
                outputDataConfig={'s3OutputDataConfig': {'s3Uri': s3_uri}}
            )
            jobs[resp['invocationArn']] = {'name': name, 's3_prefix': shot_key}
            print(f"  Submitted {name} successfully (fallback).")
        except Exception as e_inner:
             print(f"  Failed submitting {name}: {e_inner}")

print("Polling jobs (this takes about 2 to 3 minutes)...")
while jobs:
    time.sleep(30)
    for arn in list(jobs.keys()):
        job = jobs[arn]
        try:
            resp = bedrock.get_async_invoke(invocationArn=arn)
            status = resp.get('status', 'InProgress')
            if status == 'Completed':
                print(f"  {job['name']} COMPLETED. Downloading...")
                s3_prefix = job['s3_prefix'].replace('\\', '/')
                ls = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=s3_prefix)
                keys = [o['Key'] for o in ls.get('Contents', []) if o['Key'].endswith('.mp4')]
                if keys:
                    local_path = os.path.join(OUTPUT_DIR, f"{job['name']}_16x9.mp4")
                    s3.download_file(S3_BUCKET, keys[0], local_path)
                    print(f"    Saved: {local_path}")
                else:
                    print(f"    Warning: No MP4 found for {job['name']} in gs://{S3_BUCKET}/{s3_prefix}")
                del jobs[arn]
            elif status == 'Failed':
                print(f"  {job['name']} FAILED: {resp.get('failureMessage')}")
                del jobs[arn]
            else:
                print(f"  {job['name']} is {status}...")
        except Exception as e:
            print(f"  Error polling {job['name']}: {e}")

print(f"All done! Videos are located in g:\\ai for bharat\\unified_flow\\{OUTPUT_DIR}")
