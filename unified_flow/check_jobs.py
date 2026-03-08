import boto3
from dotenv import load_dotenv
load_dotenv()

bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')

resp = bedrock.list_async_invokes(maxResults=10)
jobs = resp.get('asyncInvokeSummaries', [])
print(f"Recent Nova Reel jobs ({len(jobs)} found):")
for job in jobs:
    arn_short = job['invocationArn'].split('/')[-1]
    status = job['status']
    failure = job.get('failureMessage', '')
    output_cfg = job.get('outputDataConfig', {}).get('s3OutputDataConfig', {})
    out_uri = output_cfg.get('s3Uri', 'N/A')
    print(f"\n  ID     : {arn_short}")
    print(f"  Status : {status}")
    print(f"  Output : {out_uri}")
    if failure:
        print(f"  ERROR  : {failure}")
