#!/usr/bin/env python3
"""Acceptance of the isolated local Droplet profile and a real encrypted restore."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
from datetime import datetime, timezone
import psycopg
from psycopg import sql

root = Path(__file__).resolve().parent
state = root / '.state/droplet-acceptance'
environment = dict(os.environ, DOCKER_CONTEXT='colima-arcadian-cms')
compose = ['docker-compose', '--project-name', 'arcadian-content-acceptance', '--env-file', str(state/'.env'),
           '-f', str(state/'compose.yml'), '-f', str(state/'compose.acceptance.yml')]

def run(service, *arguments, local=False):
    options = ['-e', 'DJANGO_ENV=local'] if local else []
    return subprocess.check_output(compose + ['run', '--rm', '--no-deps', *options, service, *arguments],
                                   env=environment, stderr=subprocess.PIPE)

def manage(service, *arguments, local=False):
    return run(service, 'python', 'manage.py', *arguments, local=local)

checks = []
def mark(name):
    checks.append({'name': name, 'result': 'PASS'})

denied = '''from django.db import connection,transaction
from django.db.utils import ProgrammingError
queries = QUERY_LIST
for statement in queries:
    try:
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(statement)
    except ProgrammingError as error:
        if getattr(error.__cause__, 'sqlstate', None) != '42501': raise
    else: raise RuntimeError('Restricted SQL operation unexpectedly succeeded.')
print('Restricted operations denied.')'''
web_queries = ['CREATE TABLE public.arcadian_acceptance_probe (id integer)',
               'UPDATE content_historicalproject SET title=title WHERE FALSE',
               'DELETE FROM content_historicalrate WHERE FALSE']
subprocess.check_output(['docker', 'exec', 'arcadian-content-acceptance-cms-1', 'python', 'manage.py', 'shell',
                         '-c', denied.replace('QUERY_LIST', repr(web_queries))], env=environment, stderr=subprocess.PIPE)
manage('backup', 'shell', '-c', denied.replace('QUERY_LIST', repr(['DELETE FROM auth_user WHERE FALSE'])))
mark('Runtime cannot create tables or modify history; backup role cannot write')

network = manage('migrate', 'shell', '-c',
                 'from django.db import connection; c=connection.cursor(); c.execute("SHOW listen_addresses"); assert c.fetchone()[0] == ""; print("Socket only.")')
mark('PostgreSQL accepts only password-authenticated Unix socket connections')

fixture_created = database_created = False
values = dict(line.split('=', 1) for line in (root/'.env').read_text().splitlines() if '=' in line)
if values.get('DJANGO_ENV') != 'local':
    raise RuntimeError('Restore acceptance uses only the existing local PostgreSQL instance.')
name = 'restore_droplet_' + secrets.token_hex(6)
local_env = {**os.environ, **values, 'CMS_DEPLOYMENT': 'local', 'DB_NAME': name}
python = str(root/'.venv/bin/python')
counter = 'from content.models import Project,Rate,ProjectPhoto; from django.contrib.auth import get_user_model; print(Project.objects.count(),Rate.objects.count(),ProjectPhoto.objects.count(),Project.history.count(),Rate.history.count(),get_user_model().objects.count())'

def local_manage(*arguments):
    return subprocess.check_output([python, str(root/'manage.py'), *arguments], env=local_env, stderr=subprocess.PIPE)

with tempfile.TemporaryDirectory(prefix='arcadian-droplet-restore-') as media:
    local_env['MEDIA_ROOT'] = media
    try:
        run('migrate', 'sh', '-c', 'mkdir -p /tmp/volume-check')
        # Only this disposable local database ever receives acceptance content.
        manage('migrate', 'browser_fixture', 'create', '--state', '/data/acceptance/backup-fixture.json', local=True)
        fixture_created = True
        source_counts = manage('migrate', 'shell', '-c', counter).decode().splitlines()[-1]
        metadata = json.loads(manage('backup', 'content_backup', '--output', '/data/backups').decode().splitlines()[-1])
        encrypted = run('backup', 'cat', metadata['archive'])
        archive = root/'.backups'/('droplet-acceptance-' + Path(metadata['archive']).name)
        archive.parent.mkdir(mode=0o700, exist_ok=True)
        archive.write_bytes(encrypted)
        archive.chmod(0o600)
        mark('Consistent encrypted backup uses the dedicated read-only SQL role')
        with psycopg.connect(dbname='postgres', user=values['DB_USER'], password=values['DB_PASSWORD'],
                             host=values['DB_HOST'], port=values['DB_PORT'], autocommit=True) as connection:
            connection.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
            database_created = True
        local_manage('migrate', '--noinput')
        restored = local_manage('content_restore', '--archive', str(archive), '--identity', str(state/'backup-identity.txt'))
        restored_counts = local_manage('shell', '-c', counter).decode().splitlines()[-1]
        assert source_counts == restored_counts, 'Restored database differs from its source.'
        fixture = json.loads(run('migrate', 'cat', '/data/acceptance/backup-fixture.json'))
        for key in fixture['files']:
            source = run('migrate', 'cat', '/data/media/' + key)
            assert hashlib.sha256(source).digest() == hashlib.sha256((Path(media)/key).read_bytes()).digest()
        mark('Restored all database rows and 12 WebP variants into a fresh local database')
        report = {'checked_at': datetime.now(timezone.utc).isoformat(),
                  'checks': checks, 'source_and_restored_counts': source_counts,
                  'verified_variants': len(fixture['files']), 'restore_result': json.loads(restored.decode().splitlines()[-1]),
                  'archive_sha256': hashlib.sha256(encrypted).hexdigest(), 'private_identity': 'stays on Mac'}
        (root/'.state/droplet-backup-acceptance.json').write_text(json.dumps(report, indent=2))
        print(json.dumps(report))
    finally:
        if fixture_created:
            manage('migrate', 'browser_fixture', 'cleanup', '--state', '/data/acceptance/backup-fixture.json', local=True)
        if database_created:
            with psycopg.connect(dbname='postgres', user=values['DB_USER'], password=values['DB_PASSWORD'],
                                 host=values['DB_HOST'], port=values['DB_PORT'], autocommit=True) as connection:
                connection.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))
