import json
import boto3
import time
import uuid
import os
import subprocess
from dotenv import load_dotenv

load_dotenv()

bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')
S3_BUCKET = 'unified-flow-assets'

def generate_reverse_assembly():
    print("==================================================")
    print(" AI VFX ENGINE: The 'Reverse Disassembly' Method ")
    print("==================================================")
    
    # We ask the AI to dismantle the car cleanly (Exploded View), which it understands much better mathematically.
    prompt = (
        "3D exploded-view animation in a dark studio. A pristine Italian hypercar smoothly dismantles itself in mid-air. "
        "First, the carbon fiber exterior shell lifts off and floats away. "
        "Next, the leather seats and steering wheel detach and separate. "
        "Finally, only the massive V12 engine block remains floating. "
        "Clean mechanical separation, ultra-realistic, 8k."
    )
    
    print(f"\nPrompt length: {len(prompt)} chars")
    print(f"Prompt: {prompt}\n")

    model_input = {
        "taskType": "TEXT_VIDEO",
        "textToVideoParams": {
            "text": prompt
        },
        "videoGenerationConfig": {
            "durationSeconds": 6,
            "fps": 24,
            "dimension": "1280x720",
            "seed": 88
        }
    }

    output_prefix = f"output/assembly_vfx/job_{uuid.uuid4().hex[:8]}"
    output_s3_uri = f"s3://{S3_BUCKET}/{output_prefix}/"

    print("1. Launching Nova Reel Disassembly Job...")
    resp = bedrock.start_async_invoke(
        modelId='amazon.nova-reel-v1:0',
        modelInput=model_input,
        outputDataConfig={"s3OutputDataConfig": {"s3Uri": output_s3_uri}}
    )
    arn = resp['invocationArn']
    print(f"   Job ARN: {arn.split('/')[-1]}")
    print("   Waiting for rendering (~3 mins)...")

    while True:
        status_resp = bedrock.get_async_invoke(invocationArn=arn)
        status = status_resp.get('status', 'InProgress')
        if status == 'Completed':
            print("\n   Nova Reel Generation DONE!")
            break
        elif status == 'Failed':
            print(f"\n   FAILED: {status_resp.get('failureMessage')}")
            return
        
        print(".", end="", flush=True)
        time.sleep(15)

    # Download Output
    os.makedirs("output/assembly_vfx", exist_ok=True)
    raw_path = "output/assembly_vfx/raw_disassembly.mp4"
    final_path = "output/assembly_vfx/final_assembly_vfx.mp4"
    
    s3 = boto3.client('s3')
    try:
        ls = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=output_prefix)
        keys = [o['Key'] for o in ls.get('Contents', []) if o['Key'].endswith('.mp4')]
        if keys:
            print(f"\n2. Downloading raw footage from S3...")
            s3.download_file(S3_BUCKET, keys[0], raw_path)
            print(f"   Saved to: {raw_path}")
            
            print("\n3. Applying FFmpeg Chronological Reversal (VFX Assembly)...")
            cmd = [
                'ffmpeg', '-y',
                '-i', raw_path,
                '-vf', 'reverse', # Reverses the video frames chronologically!
                '-c:v', 'libx264',
                '-preset', 'fast',
                '-crf', '18',
                final_path
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            
            print(f"\nSUCCESS! AI VFX Assembly generated completely.")
            print(f"Final Video: {os.path.abspath(final_path)}")
            os.system(f'explorer.exe "{os.path.abspath("output/assembly_vfx")}"')
            
    except Exception as e:
        print(f"Pipeline failed: {e}")

if __name__ == "__main__":
    generate_reverse_assembly()
