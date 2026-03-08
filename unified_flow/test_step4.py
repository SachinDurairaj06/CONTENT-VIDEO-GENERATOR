"""Test exactly what step4 does with full error output."""
import sys, os, json, math, uuid
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
load_dotenv()
import boto3

AWS_REGION = os.environ.get('AWS_DEFAULT_REGION', 'us-east-1')
S3_BUCKET  = os.environ.get('ASSETS_BUCKET', 'unified-flow-assets')
bedrock    = boto3.client('bedrock-runtime', region_name=AWS_REGION)
s3         = boto3.client('s3', region_name=AWS_REGION)
OUTPUT_DIR = 'output/step4_test'
os.makedirs(OUTPUT_DIR, exist_ok=True)

audio_duration = 24.0  # simulate ~24s audio
SHOT_DURATION = 12
num_jobs = max(1, round(audio_duration / SHOT_DURATION))
per_job_duration = max(12, int(round(audio_duration / num_jobs / 6)) * 6)
per_job_duration = min(per_job_duration, 120)

print(f"num_jobs={num_jobs}, per_job_duration={per_job_duration}s")
print(f"S3_BUCKET={S3_BUCKET}")

# Simulate one job
prompt = "Luxurious modular kitchen interior, warm ambient lighting, smooth cinematic camera movement"
output_prefix = f"{OUTPUT_DIR}/nova_reel/job_0_{uuid.uuid4().hex[:8]}"
output_s3_uri = f"s3://{S3_BUCKET}/{output_prefix}/"

rich_prompt = (
    f"Cinematic promotional video. {prompt}. "
    f"Natural camera movement, smooth transitions between shots, "
    f"warm professional lighting, ultra-realistic, 8K quality, no text overlays, no logos."
)

model_input = {
    "taskType": "MULTI_SHOT_AUTOMATED",
    "multiShotAutomatedParams": {"text": rich_prompt},
    "videoGenerationConfig": {
        "durationSeconds": per_job_duration,
        "fps": 24,
        "dimension": "1280x720",
        "seed": 13
    }
}

print(f"\nSubmitting Nova Reel job to: {output_s3_uri}")
print(f"Model input: {json.dumps(model_input, indent=2)}")

try:
    resp = bedrock.start_async_invoke(
        modelId='amazon.nova-reel-v1:1',
        modelInput=model_input,
        outputDataConfig={'s3OutputDataConfig': {'s3Uri': output_s3_uri}}
    )
    print(f"\nSUCCESS! ARN: {resp['invocationArn']}")
except Exception as e:
    print(f"\nFAILED: {type(e).__name__}: {e}")
