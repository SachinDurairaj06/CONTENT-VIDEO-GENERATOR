"""Quick test to verify Nova Reel start_async_invoke with correct API format."""
import boto3, json, os
from dotenv import load_dotenv
load_dotenv()

bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')
S3_BUCKET = os.environ.get('ASSETS_BUCKET', 'unified-flow-assets')

print(f"Bucket: {S3_BUCKET}")
print("Testing Nova Reel v1:1 with MULTI_SHOT_AUTOMATED (12s = 2 shots)...")

# Nova Reel v1:1 correct format — MULTI_SHOT_AUTOMATED
# duration must be multiple of 6, min 12s (2 shots), max 120s (20 shots)
model_input = {
    "taskType": "MULTI_SHOT_AUTOMATED",
    "multiShotAutomatedParams": {
        "text": "A beautiful sunrise over mountains, cinematic, golden hour, smooth camera movement over misty valleys"
    },
    "videoGenerationConfig": {
        "durationSeconds": 12,   # 2 shots x 6s — minimum for MULTI_SHOT_AUTOMATED
        "fps": 24,
        "dimension": "1280x720",
        "seed": 42
    }
}

output_s3_uri = f"s3://{S3_BUCKET}/test_nova_reel_v2/"

try:
    resp = bedrock.start_async_invoke(
        modelId='amazon.nova-reel-v1:1',
        modelInput=model_input,
        outputDataConfig={
            's3OutputDataConfig': {
                's3Uri': output_s3_uri
            }
        }
    )
    print(f"\nSUCCESS!")
    print(f"Invocation ARN: {resp['invocationArn']}")
except Exception as e:
    print(f"\nFAILED: {type(e).__name__}: {e}")
    print("\nTrying TEXT_VIDEO (single-shot, 6s) instead...")
    # Fallback: TEXT_VIDEO
    model_input_v2 = {
        "taskType": "TEXT_VIDEO",
        "textToVideoParams": {
            "text": "A beautiful sunrise over mountains, cinematic, golden hour"
        },
        "videoGenerationConfig": {
            "durationSeconds": 6,
            "fps": 24,
            "dimension": "1280x720"
        }
    }
    try:
        resp2 = bedrock.start_async_invoke(
            modelId='amazon.nova-reel-v1:0',
            modelInput=model_input_v2,
            outputDataConfig={'s3OutputDataConfig': {'s3Uri': output_s3_uri}}
        )
        print(f"TEXT_VIDEO SUCCESS! ARN: {resp2['invocationArn']}")
    except Exception as e2:
        print(f"TEXT_VIDEO also FAILED: {e2}")
