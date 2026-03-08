import json
import base64
import boto3
from dotenv import load_dotenv
load_dotenv()

bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')

def test_canvas():
    prompt = "Cinematic 8K photo of Max Verstappen driving his Navy Blue and Red Bull Racing Formula 1 car"
    try:
        resp = bedrock.invoke_model(
            modelId='amazon.nova-canvas-v1:0',
            body=json.dumps({
                "taskType": "TEXT_IMAGE",
                "textToImageParams": {"text": prompt},
                "imageGenerationConfig": {
                    "numberOfImages": 1, "height": 720, "width": 1280
                }
            }),
            accept='application/json', contentType='application/json'
        )
        print("Canvas SUCCESS!")
    except Exception as e:
        print("Canvas FAILED:", e)

test_canvas()
