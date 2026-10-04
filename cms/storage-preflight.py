#!/usr/bin/env python3
import json
import secrets
import sys
import urllib.request
import urllib.error
import boto3
from botocore.config import Config
from pathlib import Path

if len(sys.argv) != 2:
    raise SystemExit('Usage: storage-preflight.py PRIVATE_ENV (requires bucket administration credentials)')
values = {}
for line in Path(sys.argv[1]).read_text().splitlines():
    if line and not line.startswith('#') and '=' in line:
        name, value = line.split('=', 1)
        values[name] = value
results = []
for prefix in ['S3', 'BACKUP_S3']:
    endpoint = values[prefix + '_ENDPOINT']
    if not endpoint.startswith('https://'):
        raise SystemExit('HTTPS storage is required.')
    client = boto3.client('s3', endpoint_url=endpoint, region_name=values[prefix + '_REGION'],
                          aws_access_key_id=values[prefix + '_ACCESS_KEY'],
                          aws_secret_access_key=values[prefix + '_SECRET_KEY'],
                          config=Config(connect_timeout=3, read_timeout=5, retries={'max_attempts': 1}))
    bucket = values[prefix + '_BUCKET']
    # Deliberately enables retention; run during authorized infrastructure setup.
    client.put_bucket_versioning(Bucket=bucket, VersioningConfiguration={'Status': 'Enabled'})
    if client.get_bucket_versioning(Bucket=bucket).get('Status') != 'Enabled':
        raise SystemExit('Bucket versioning was not enabled.')
    key = '.arcadian-preflight/' + secrets.token_hex(16)
    response = client.put_object(Bucket=bucket, Key=key, Body=b'private-storage-probe', ACL='private')
    version = response.get('VersionId')
    try:
        url = endpoint.replace('https://', 'https://' + bucket + '.', 1) + '/' + key
        try:
            urllib.request.urlopen(url, timeout=10)
        except urllib.error.HTTPError as error:
            if error.code != 403:
                raise
        else:
            raise SystemExit('Anonymous object read succeeded; deployment refused.')
        data = client.get_object(Bucket=bucket, Key=key)['Body'].read()
        if data != b'private-storage-probe':
            raise SystemExit('Authenticated storage read failed.')
        results.append({'bucket': bucket, 'versioning': 'Enabled', 'anonymous_read': 'denied', 'authenticated_read': 'PASS'})
    finally:
        args = {'Bucket': bucket, 'Key': key}
        if version:
            args['VersionId'] = version
        client.delete_object(**args)
print(json.dumps({'result': 'PASS', 'checks': results}))
