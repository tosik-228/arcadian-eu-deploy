#!/usr/bin/env python3
"""Generate private production configuration locally; never print credentials."""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument('--output', required=True)
parser.add_argument('--image', required=True)
args = parser.parse_args()
root = Path(args.output).resolve()
root.mkdir(mode=0o700, parents=True, exist_ok=True)
if any(root.glob('.env*')):
    raise SystemExit('Existing configuration is preserved. Use a fresh output directory.')

identity = root / 'backup-identity.txt'
if not identity.exists():
    subprocess.run(['age-keygen', '-o', str(identity)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
identity.chmod(0o600)
recipient = subprocess.check_output(['age-keygen', '-y', str(identity)], text=True).strip()
owner, runtime, backup, editor = [secrets.token_urlsafe(48) for _ in range(4)]

def write_env(name, values):
    descriptor = os.open(root / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w') as file:
        for key, value in values.items():
            file.write(f'{key}={value}\n')

write_env('.env', {'CMS_IMAGE': args.image})
write_env('.env.runtime', {
    'DJANGO_ENV': 'production', 'CMS_DEPLOYMENT': 'droplet',
    'CMS_URL': 'https://cms.arcadian-eu.com',
    'CMS_ALLOWED_HOSTS': 'cms.arcadian-eu.com,127.0.0.1,localhost',
    'CMS_TRUSTED_PROXY_NETWORKS': '172.30.77.0/28',
    'CMS_SECRET': secrets.token_urlsafe(64),
    'SITE_ORIGINS': 'https://arcadian-eu.com,https://www.arcadian-eu.com',
    'DB_NAME': 'arcadian_content', 'DB_USER': 'arcadian_runtime',
    'DB_PASSWORD': runtime, 'DB_HOST': '/run/arcadian-postgres', 'DB_PORT': '5432',
    'MEDIA_ROOT': '/data/media', 'BACKUP_AGE_RECIPIENT': recipient,
})
write_env('.env.database', {'POSTGRES_DB': 'arcadian_content', 'POSTGRES_USER': 'arcadian_owner', 'POSTGRES_PASSWORD': owner})
write_env('.env.migration', {
    'DB_USER': 'arcadian_owner', 'DB_PASSWORD': owner,
    'RUNTIME_DB_USER': 'arcadian_runtime', 'RUNTIME_DB_PASSWORD': runtime,
    'BACKUP_DB_USER': 'arcadian_backup', 'BACKUP_DB_PASSWORD': backup,
})
write_env('.env.backup', {'DB_USER': 'arcadian_backup', 'DB_PASSWORD': backup})
write_env('.env.bootstrap', {'EDITOR_USERNAME': 'editor', 'EDITOR_PASSWORD': editor})
print(json.dumps({'created': True, 'configuration': str(root), 'private_identity': 'local only; never upload to Droplet'}))
