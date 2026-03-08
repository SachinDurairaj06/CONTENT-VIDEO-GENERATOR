"""
Status Polling Lambda

This Lambda is called by API Gateway's /status endpoint.
It checks the execution status of the Step Functions pipeline
and returns the current state + output if finished.
"""
import json
import boto3

sfn_client = boto3.client('stepfunctions')


def lambda_handler(event, context):
    try:
        # Extract executionArn from query string
        execution_arn = event.get('queryStringParameters', {}).get('executionArn', '')

        if not execution_arn:
            return {
                'statusCode': 400,
                'headers': {'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({'error': 'Missing executionArn parameter'})
            }

        # Describe the execution
        response = sfn_client.describe_execution(
            executionArn=execution_arn
        )

        status = response['status']  # RUNNING | SUCCEEDED | FAILED | TIMED_OUT | ABORTED

        result = {
            'status': status,
            'startDate': response['startDate'].isoformat(),
        }

        if status == 'SUCCEEDED':
            output = json.loads(response.get('output', '{}'))
            result['output'] = {
                'final_video_uri': output.get('final_video_uri'),
                'download_url': output.get('download_url')
            }
        elif status == 'FAILED':
            result['output'] = {
                'error': response.get('error', 'Unknown error'),
                'cause': response.get('cause', '')
            }

        return {
            'statusCode': 200,
            'headers': {'Access-Control-Allow-Origin': '*', 'Content-Type': 'application/json'},
            'body': json.dumps(result)
        }

    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': str(e)})
        }
