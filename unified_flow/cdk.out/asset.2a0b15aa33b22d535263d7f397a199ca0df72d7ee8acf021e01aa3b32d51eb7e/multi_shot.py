"""
Multi-Shot Mode Module

Enables chaining multiple 6-second Nova Reel clips into longer videos
up to 120 seconds, as specified in the PRD's "Multi-shot Automated" mode.

This module splits the visual prompts into 6-second shots and manages
the async Nova Reel invocations + sequential concatenation.
"""
import json
import boto3
import math
import os

bedrock_client = boto3.client('bedrock-runtime')
s3_client = boto3.client('s3')
BUCKET_NAME = os.environ.get('ASSETS_BUCKET', 'unified-flow-assets-bucket')

# Nova Reel constraints from PRD
SHOT_DURATION_SECONDS = 6
MAX_VIDEO_DURATION_SECONDS = 120
MAX_SHOTS = MAX_VIDEO_DURATION_SECONDS // SHOT_DURATION_SECONDS  # 20 shots


def calculate_shots(target_duration_seconds: int, visual_prompts: list) -> list:
    """
    Calculate how many 6-second shots are needed and distribute
    the visual prompts across them.

    If target_duration > len(visual_prompts) * 6, prompts are cycled.
    If target_duration < len(visual_prompts) * 6, prompts are truncated.

    Args:
        target_duration_seconds: Desired total video length (must be multiple of 6, max 120)
        visual_prompts: List of prompt strings from the manifest

    Returns:
        List of prompt strings, one per 6-second shot
    """
    # Clamp duration
    target_duration_seconds = min(target_duration_seconds, MAX_VIDEO_DURATION_SECONDS)
    target_duration_seconds = max(target_duration_seconds, SHOT_DURATION_SECONDS)

    # Round to nearest multiple of 6
    num_shots = math.ceil(target_duration_seconds / SHOT_DURATION_SECONDS)
    num_shots = min(num_shots, MAX_SHOTS)

    if not visual_prompts:
        return []

    # Distribute prompts across shots (cycle if needed)
    shot_prompts = []
    for i in range(num_shots):
        prompt_idx = i % len(visual_prompts)
        shot_prompts.append(visual_prompts[prompt_idx])

    return shot_prompts


def start_multi_shot_generation(
    shot_prompts: list,
    keyframe_uris: list = None
) -> list:
    """
    Start async Nova Reel video generation for each shot.

    Args:
        shot_prompts: List of prompts, one per 6-second clip
        keyframe_uris: Optional S3 URIs for keyframe images (one per shot)

    Returns:
        List of invocation ARNs for tracking
    """
    invocation_arns = []

    for i, prompt in enumerate(shot_prompts):
        nova_body = {
            "taskType": "TEXT_TO_VIDEO",
            "textToVideoParams": {
                "text": prompt
            },
            "videoGenerationConfig": {
                "durationSeconds": SHOT_DURATION_SECONDS,
                "fps": 24,
                "dimension": "1280x720"
            }
        }

        # Add keyframe image if available
        if keyframe_uris and i < len(keyframe_uris):
            nova_body["textToVideoParams"]["images"] = [
                {
                    "format": "png",
                    "source": {
                        "s3Uri": keyframe_uris[i]
                    }
                }
            ]

        try:
            response = bedrock_client.start_async_invoke(
                modelId='amazon.nova-reel-v1:0',
                modelInput={
                    'contentType': 'application/json',
                    'body': json.dumps(nova_body)
                },
                outputDataConfig={
                    's3OutputDataConfig': {
                        's3Uri': f"s3://{BUCKET_NAME}/video_outputs/"
                    }
                }
            )
            invocation_arns.append(response.get('invocationArn'))
        except Exception as e:
            print(f"Failed to start shot {i}: {str(e)}")
            invocation_arns.append(None)

    return invocation_arns


def get_video_duration_label(num_shots: int) -> str:
    """Returns a human-readable duration label."""
    total_seconds = num_shots * SHOT_DURATION_SECONDS
    if total_seconds < 60:
        return f"{total_seconds}s"
    minutes = total_seconds // 60
    remaining = total_seconds % 60
    if remaining:
        return f"{minutes}m {remaining}s"
    return f"{minutes}m"
