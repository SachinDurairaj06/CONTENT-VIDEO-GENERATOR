import json
import boto3
import os
import uuid

bedrock_client = boto3.client('bedrock-runtime')
s3_client = boto3.client('s3')

BUCKET_NAME = os.environ.get('ASSETS_BUCKET', 'unified-flow-assets-bucket')

def lambda_handler(event, context):
    try:
        manifest = event.get('manifest', {})
        visual_prompts = manifest.get('visual_prompts', [])
        
        if not visual_prompts:
            return {'statusCode': 400, 'body': 'No visual prompts provided in manifest.'}
            
        job_ids = []
        s3_uris = []

        # Start an async generation job for each visual prompt
        for i, prompt in enumerate(visual_prompts):
            # Phase 1: Titan Image Gen for Keyframe (optional in MVP, but requested in PRD)
            job_id = str(uuid.uuid4())
            keyframe_key = f"keyframes/{job_id}.png"
            
            # Using Titan Image Gen v2 for the start frame
            titan_body = {
                "taskType": "TEXT_IMAGE",
                "textToImageParams": {
                    "text": prompt
                },
                "imageGenerationConfig": {
                    "numberOfImages": 1,
                    "height": 720,
                    "width": 1280,
                    "cfgScale": 8.0
                }
            }
            
            # Request Image Keyframe
            titan_resp = bedrock_client.invoke_model(
                modelId='amazon.titan-image-generator-v2:0',
                body=json.dumps(titan_body),
                accept='application/json',
                contentType='application/json'
            )
            
            titan_output = json.loads(titan_resp['body'].read())
            image_base64 = titan_output['images'][0]
            
            import base64
            image_bytes = base64.b64decode(image_base64)
            
            s3_client.put_object(
                Bucket=BUCKET_NAME,
                Key=keyframe_key,
                Body=image_bytes,
                ContentType='image/png'
            )
            
            keyframe_uri = f"s3://{BUCKET_NAME}/{keyframe_key}"
            
            # Phase 2: Start Nova Reel async video generation using the keyframe
            # Note: Bedrock has StartAsyncInvoke API for long running models like Nova Reel
            nova_body = {
                "taskType": "TEXT_TO_VIDEO",
                "textToVideoParams": {
                    "text": prompt,
                    "images": [
                        {
                            "format": "png",
                            "source": {
                                "s3Uri": keyframe_uri
                            }
                        }
                    ]
                },
                "videoGenerationConfig": {
                    "durationSeconds": 6,
                    "fps": 24,
                    "dimension": "1280x720"
                }
            }
            
            # Note: For Nova Reel we must use the Async completion API since it takes several minutes
            nova_job_resp = bedrock_client.start_async_invoke(
                modelId='amazon.nova-reel-v1:0',
                modelInput={'contentType': 'application/json', 'body': json.dumps(nova_body)},
                outputDataConfig={
                    's3OutputDataConfig': {
                        's3Uri': f"s3://{BUCKET_NAME}/video_outputs/"
                    }
                }
            )
            
            invocation_arn = nova_job_resp.get('invocationArn')
            job_ids.append(invocation_arn)
            
            # Keep track of expected output paths based on standard bedrock async formats
            # Actually, Bedrock places results in the s3OutputDataConfig prefix using the invocation ID
            # e.g., s3://{BUCKET_NAME}/video_outputs/{invocation_id}/output.mp4

        return {
            'statusCode': 200,
            'nova_invocation_arns': job_ids,
            'manifest': manifest,
            'audio_uri': event.get('audio_uri'),
            'viseme_uri': event.get('viseme_uri')
        }

    except Exception as e:
        print(f"Error starting visual generation: {str(e)}")
        return {'statusCode': 500, 'error': str(e)}
