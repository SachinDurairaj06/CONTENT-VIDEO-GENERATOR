import sys, os, os.path, json, base64, boto3
from dotenv import load_dotenv
load_dotenv()

AWS_REGION = os.environ.get('AWS_DEFAULT_REGION', 'us-east-1')
bedrock = boto3.client('bedrock-runtime', region_name=AWS_REGION)

img_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="

model_input = {
    "taskType": "TEXT_VIDEO",
    "videoGenerationConfig": { 
        "durationSeconds": 6, "fps": 24, "dimension": "1280x720", "seed": 42
    },
    "textToVideoParams": { 
        "text": "STATIC CAMERA. A bare room.",
        "images": [{"format": "png", "source": {"bytes": img_b64}}]
    }
}

try:
    resp = bedrock.start_async_invoke(
        modelId='amazon.nova-reel-v1:0', modelInput=model_input,
        outputDataConfig={'s3OutputDataConfig': {'s3Uri': "s3://unified-flow-assets/output/test/shot_images/"}}
    )
    print("SUCCESS WITH IMAGES")
except Exception as e:
    print(f"FAILED WITH IMAGES: {e}")
