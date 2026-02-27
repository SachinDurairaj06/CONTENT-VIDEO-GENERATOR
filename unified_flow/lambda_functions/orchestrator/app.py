import json
import boto3
import os
from style_injector import inject_style

bedrock_client = boto3.client('bedrock-runtime')


def check_guardrails(prompt: str) -> dict:
    """
    Content moderation using Amazon Bedrock Guardrails.
    Filters profanity, harmful content, and non-brand-compliant material.
    Returns {'safe': True/False, 'reason': str}.
    """
    try:
        response = bedrock_client.apply_guardrail(
            guardrailIdentifier=os.environ.get('GUARDRAIL_ID', 'unified-flow-guardrail'),
            guardrailVersion='DRAFT',
            source='INPUT',
            content=[
                {
                    'text': {
                        'text': prompt
                    }
                }
            ]
        )
        action = response.get('action', 'NONE')
        if action == 'GUARDRAIL_INTERVENED':
            outputs = response.get('outputs', [{}])
            reason = outputs[0].get('text', 'Content blocked by moderation policy.') if outputs else 'Blocked'
            return {'safe': False, 'reason': reason}
        return {'safe': True, 'reason': ''}
    except Exception as e:
        # If guardrail service is unavailable, log and proceed (fail-open for hackathon)
        print(f"Guardrail check failed (proceeding): {str(e)}")
        return {'safe': True, 'reason': ''}


def lambda_handler(event, context):
    try:
        # Extract user prompt and optional style from the event
        user_prompt = event.get('prompt', '')
        style_key = event.get('style', '')  # e.g., "diwali", "warli", "healthcare"

        if not user_prompt:
            return {'statusCode': 400, 'body': 'Missing prompt'}

        # ── Guardrail Check ───────────────────────────────────────
        moderation = check_guardrails(user_prompt)
        if not moderation['safe']:
            return {
                'statusCode': 403,
                'body': f"Content blocked: {moderation['reason']}"
            }

        # System instructions to enforce JSON output and multi-modal styling
        system_prompt = """
        You are an AI director for 'Unified Flow', a platform that creates culturally resonant promotional videos for Indian MSMEs.
        Given a user's business idea, expand it into a precise multi-asset manifest.
        Respond ONLY with a valid JSON object matching this schema:
        {
          "narration": "[A culturally nuanced SSML script for Amazon Polly. Use <speak> tags. Keep under 30 seconds.]",
          "visual_prompts": [
             "[Detailed prompt 1 for B-roll (Amazon Nova/Titan) - include camera angle, lighting, Indian cultural context, colors based on emotion]",
             "[Detailed prompt 2...]",
             "[Detailed prompt 3...]"
          ],
          "metadata": {
             "language_code": "[e.g., hi-IN or en-IN]",
             "aspect_ratio": "16:9",
             "sentiment": "[e.g., warm, festive, professional]"
          }
        }
        """

        # Prepare Bedrock request (Claude 3.5 Sonnet format)
        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1024,
            "system": system_prompt,
            "messages": [
                {
                    "role": "user",
                    "content": f"User Idea: {user_prompt}"
                }
            ],
            "temperature": 0.5
        }

        response = bedrock_client.invoke_model(
            modelId='anthropic.claude-3-5-sonnet-20241022-v2:0',
            contentType='application/json',
            accept='application/json',
            body=json.dumps(request_body)
        )

        response_body = json.loads(response['body'].read())
        content_text = response_body.get('content', [{}])[0].get('text', '')

        # Parse the JSON from the LLM response
        try:
            manifest = json.loads(content_text)
        except json.JSONDecodeError:
            # Fallback extraction if LLM adds markdown wrappers
            clean_text = content_text.strip()
            if clean_text.startswith("```json"):
                clean_text = clean_text[7:]
            if clean_text.endswith("```"):
                clean_text = clean_text[:-3]
            manifest = json.loads(clean_text)

        # ── Style Injection ───────────────────────────────────────
        if style_key and 'visual_prompts' in manifest:
            manifest['visual_prompts'] = [
                inject_style(vp, style_key) for vp in manifest['visual_prompts']
            ]

        return {
            'statusCode': 200,
            'body': manifest
        }

    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': str(e)
        }
