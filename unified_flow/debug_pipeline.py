"""Debug script - runs just steps 1-4 with full error output."""
import sys, os, json, base64, math, time, uuid
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
load_dotenv()
import boto3

AWS_REGION = os.environ.get('AWS_DEFAULT_REGION', 'us-east-1')
S3_BUCKET  = os.environ.get('ASSETS_BUCKET', 'unified-flow-assets')
bedrock    = boto3.client('bedrock-runtime', region_name=AWS_REGION)
polly      = boto3.client('polly', region_name=AWS_REGION)
s3         = boto3.client('s3', region_name=AWS_REGION)

OUTPUT_DIR = 'output/debug_run'
os.makedirs(OUTPUT_DIR, exist_ok=True)

print("=== Step 1: Nova Pro manifest ===")
body = {
    "messages": [{"role": "user", "content": [{"text": """System: You are a video director. Respond ONLY with valid JSON:
{"entities":[],"narration":"Test narration.","visual_prompts":["A kitchen interior, warm lighting"],"metadata":{"language_code":"en-IN","sentiment":"warm"}}

User Prompt: test video"""}]}],
    "inferenceConfig": {"maxTokens": 512, "temperature": 0.6}
}
r = bedrock.invoke_model(modelId='amazon.nova-pro-v1:0', contentType='application/json', accept='application/json', body=json.dumps(body))
raw = json.loads(r['body'].read())['output']['message']['content'][0]['text']
print("Nova Pro OK. Raw:", raw[:100])
manifest = json.loads(raw)

print("\n=== Step 2: Polly voiceover ===")
resp = polly.synthesize_speech(Engine='neural', Text='<speak>Test narration.</speak>', TextType='ssml', OutputFormat='mp3', VoiceId='Kajal', LanguageCode='en-IN')
audio_path = os.path.join(OUTPUT_DIR, 'voiceover.mp3')
with open(audio_path, 'wb') as f:
    f.write(resp['AudioStream'].read())
print(f"Polly OK. Saved: {audio_path}")

# Upload audio to S3
s3.upload_file(audio_path, S3_BUCKET, f"{OUTPUT_DIR}/voiceover.mp3")
audio_s3 = f"s3://{S3_BUCKET}/{OUTPUT_DIR}/voiceover.mp3"
print(f"S3 upload OK: {audio_s3}")

print("\n=== Step 4: Nova Reel MULTI_SHOT_AUTOMATED ===")
output_prefix = f"{OUTPUT_DIR}/nova_reel/job_0_{uuid.uuid4().hex[:8]}"
output_s3_uri = f"s3://{S3_BUCKET}/{output_prefix}/"

model_input = {
    "taskType": "MULTI_SHOT_AUTOMATED",
    "multiShotAutomatedParams": {
        "text": "Cinematic kitchen interior promotional video. Beautiful modular kitchen, warm lighting, smooth camera movement."
    },
    "videoGenerationConfig": {
        "durationSeconds": 12,
        "fps": 24,
        "dimension": "1280x720",
        "seed": 42
    }
}
print(f"Submitting to: {output_s3_uri}")
try:
    resp = bedrock.start_async_invoke(
        modelId='amazon.nova-reel-v1:1',
        modelInput=model_input,
        outputDataConfig={'s3OutputDataConfig': {'s3Uri': output_s3_uri}}
    )
    arn = resp['invocationArn']
    print(f"Nova Reel OK! ARN: {arn}")
    with open(os.path.join(OUTPUT_DIR, 'arn.txt'), 'w') as f:
        f.write(arn)
except Exception as e:
    print(f"Nova Reel FAILED: {type(e).__name__}: {e}")
