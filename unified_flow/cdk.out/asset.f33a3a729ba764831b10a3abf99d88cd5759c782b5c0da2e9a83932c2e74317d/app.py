import json
import boto3
import os
import uuid

polly_client = boto3.client('polly')
s3_client = boto3.client('s3')

BUCKET_NAME = os.environ.get('ASSETS_BUCKET', 'unified-flow-assets-bucket')

def lambda_handler(event, context):
    try:
        # Event comes from Step Functions (the output of orchestrator)
        narration_ssml = event.get('narration', '')
        language_code = event.get('metadata', {}).get('language_code', 'en-IN')
        
        if not narration_ssml:
            return {'statusCode': 400, 'body': 'No narration provided'}

        # Determine voice based on language (e.g., Kajal for hi-IN/en-IN)
        voice_id = 'Kajal' if 'IN' in language_code else 'Joanna'

        job_id = str(uuid.uuid4())
        audio_key = f"audio/{job_id}.mp3"
        viseme_key = f"visemes/{job_id}.json"

        # 1. Generate Audio (MP3)
        audio_response = polly_client.synthesize_speech(
            Engine='neural',
            Text=f"<speak>{narration_ssml}</speak>",
            TextType='ssml',
            OutputFormat='mp3',
            VoiceId=voice_id,
            LanguageCode=language_code
        )
        
        if 'AudioStream' in audio_response:
            s3_client.put_object(
                Bucket=BUCKET_NAME,
                Key=audio_key,
                Body=audio_response['AudioStream'].read(),
                ContentType='audio/mpeg'
            )

        # 2. Generate Visemes (Speech Marks)
        viseme_response = polly_client.synthesize_speech(
            Engine='neural',
            Text=f"<speak>{narration_ssml}</speak>",
            TextType='ssml',
            OutputFormat='json',
            SpeechMarkTypes=['viseme', 'word'],
            VoiceId=voice_id,
            LanguageCode=language_code
        )
        
        if 'AudioStream' in viseme_response:
            s3_client.put_object(
                Bucket=BUCKET_NAME,
                Key=viseme_key,
                Body=viseme_response['AudioStream'].read(),
                ContentType='application/json'
            )

        # Return S3 URIs to the Step Function state
        return {
            'statusCode': 200,
            'audio_uri': f"s3://{BUCKET_NAME}/{audio_key}",
            'viseme_uri': f"s3://{BUCKET_NAME}/{viseme_key}",
            'job_id': job_id,
            'manifest': event # Pass through the manifest for subsequent steps
        }

    except Exception as e:
        print(f"Error synthensizing audio: {str(e)}")
        return {'statusCode': 500, 'error': str(e)}
