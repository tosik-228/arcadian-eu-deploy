#!/usr/bin/env python3
import json
import os
import re
import sys
from pathlib import Path

# Input secrets come from a private file or the environment. Output remains private.
if len(sys.argv) != 3:
    raise SystemExit('Usage: render-deployment.py PRIVATE_ENV PRIVATE_SPEC_OUTPUT')
values = dict(os.environ)
for line in Path(sys.argv[1]).read_text().splitlines():
    if line and not line.startswith('#') and '=' in line:
        name, value = line.split('=', 1)
        values[name] = value.replace('\\n', '\n')


def need(name):
    value = values.get(name, '')
    if not value or value.startswith('REPLACE'):
        raise SystemExit(f'{name} must be configured before provisioning.')
    return value


def env(name, value=None, secret=False):
    return {'key': name, 'scope': 'RUN_TIME', 'type': 'SECRET' if secret else 'GENERAL', 'value': value if value is not None else need(name)}


cms_url = need('CMS_URL')
if cms_url != 'https://cms.arcadian-eu.com':
    raise SystemExit('This deployment is scoped to https://cms.arcadian-eu.com.')
if len(need('CMS_SECRET')) < 64:
    raise SystemExit('CMS_SECRET must contain at least 64 random characters.')
if need('S3_BUCKET') == need('BACKUP_S3_BUCKET'):
    raise SystemExit('Media and backups must use separate buckets.')
if not need('BACKUP_AGE_RECIPIENT').startswith('age1'):
    raise SystemExit('Configure the public age recipient; never place the private identity in the service.')
base = {'github': {'repo': 'tosik-228/arcadian-eu-deploy', 'branch': 'main', 'deploy_on_push': False},
        'source_dir': 'cms', 'dockerfile_path': 'cms/Dockerfile', 'instance_count': 1, 'instance_size_slug': 'apps-s-1vcpu-1gb'}
common = [env('DJANGO_ENV', 'production'), env('CMS_URL'), env('CMS_ALLOWED_HOSTS', 'cms.arcadian-eu.com,${APP_DOMAIN}'),
          env('CMS_SECRET', secret=True), env('SITE_ORIGINS', 'https://arcadian-eu.com,https://www.arcadian-eu.com'),
          env('DB_NAME'), env('DB_HOST'), env('DB_PORT', values.get('DB_PORT', '25060')), env('DB_CA_PEM', secret=True),
          env('S3_BUCKET'), env('S3_REGION'), env('S3_ENDPOINT')]
media_rw = [env('S3_ACCESS_KEY', secret=True), env('S3_SECRET_KEY', secret=True)]
service = dict(base, name='content', http_port=8055,
               envs=[env('DB_USER', need('RUNTIME_DB_USER')), env('DB_PASSWORD', need('RUNTIME_DB_PASSWORD'), secret=True)] + media_rw,
               health_check={'http_path': '/healthz/', 'initial_delay_seconds': 20, 'period_seconds': 10, 'timeout_seconds': 5, 'failure_threshold': 3},
               alerts=[{'rule': 'MEM_UTILIZATION', 'operator': 'GREATER_THAN', 'value': 85, 'window': 'FIVE_MINUTES'}])
migrate = dict(base, name='migrate', kind='PRE_DEPLOY', run_command="./entrypoint.sh sh -c 'python manage.py migrate --noinput && python manage.py grant_runtime'",
               envs=[env('DB_USER', need('MIGRATION_DB_USER')), env('DB_PASSWORD', need('MIGRATION_DB_PASSWORD'), secret=True)] +
               [env(key, secret=key.endswith('PASSWORD')) for key in ['RUNTIME_DB_USER', 'RUNTIME_DB_PASSWORD', 'BACKUP_DB_USER', 'BACKUP_DB_PASSWORD']] + media_rw)
backup = dict(base, name='backup', kind='SCHEDULED', schedule={'cron': '15 2 * * *', 'time_zone': 'UTC'},
              run_command='./entrypoint.sh python manage.py content_backup --output /tmp/arcadian-backup --upload',
              envs=[env('DB_USER', need('BACKUP_DB_USER')), env('DB_PASSWORD', need('BACKUP_DB_PASSWORD'), secret=True),
                    env('S3_ACCESS_KEY', need('S3_BACKUP_READ_ACCESS_KEY'), secret=True),
                    env('S3_SECRET_KEY', need('S3_BACKUP_READ_SECRET_KEY'), secret=True)] +
              [env(key, secret=key.endswith('ACCESS_KEY') or key.endswith('SECRET_KEY')) for key in [
                  'BACKUP_AGE_RECIPIENT', 'BACKUP_S3_BUCKET', 'BACKUP_S3_ENDPOINT', 'BACKUP_S3_REGION', 'BACKUP_S3_ACCESS_KEY', 'BACKUP_S3_SECRET_KEY']])
spec = {'name': 'arcadian-content', 'region': 'fra', 'domains': [{'domain': 'cms.arcadian-eu.com', 'type': 'PRIMARY'}],
        'envs': common, 'services': [service], 'jobs': [migrate, backup],
        'ingress': {'rules': [{'component': {'name': 'content'}, 'match': {'path': {'prefix': '/'}}}]},
        'alerts': [{'rule': 'DEPLOYMENT_FAILED'}, {'rule': 'DOMAIN_FAILED'}]}
output = Path(sys.argv[2]).resolve()
output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
with output.open('x') as file:
    os.chmod(file.name, 0o600)
    json.dump(spec, file, indent=2)
print('Private App Platform spec rendered. No resource was created; no secrets printed.')
