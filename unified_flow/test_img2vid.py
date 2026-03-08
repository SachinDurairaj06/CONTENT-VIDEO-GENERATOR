import json
import base64
import boto3
import time
from dotenv import load_dotenv
load_dotenv()

bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')

def test_image_to_video():
    prompt = "A high-performance formula one race car speeding around a sunny track, bright orange and blue"
    print("Generating keyframe via Canvas...")
    resp = bedrock.invoke_model(
        modelId='amazon.nova-canvas-v1:0',
        body=json.dumps({
            "taskType": "TEXT_IMAGE",
            "textToImageParams": {"text": prompt},
            "imageGenerationConfig": {
                "numberOfImages": 1, "height": 720, "width": 1280,
                "cfgScale": 8.0, "seed": 42
            }
        }),
        accept='application/json', contentType='application/json'
    )
    img_b64 = json.loads(resp['body'].read())['images'][0]
    
    # Save the keyframe just to check it
    with open('test_keyframe.png', 'wb') as f:
        f.write(base64.b64decode(img_b64))
    print("Saved test_keyframe.png")

    model_input = {
        "taskType": "TEXT_VIDEO",
        "textToVideoParams": {
            "text": "Smooth motion, panning shot as the car speeds past",
            "images": [{"format": "png", "source": {"bytes": img_b64}}]
        },
        "videoGenerationConfig": {
            "durationSeconds": 6,
            "fps": 24,
            "dimension": "1280x720",
            "seed": 42
        }
    }

    print("Launching Nova Reel job...")
    resp = bedrock.start_async_invoke(
        modelId='amazon.nova-reel-v1:0',
        modelInput=model_input,
        outputDataConfig={"s3OutputDataConfig": {"s3Uri": "s3://unified-flow-assets/output/test_image_video/"}}
    )
    arn = resp['invocationArn']
    print(f"Launched! ARN: {arn}")

if __name__ == "__main__":
    test_image_to_video()

