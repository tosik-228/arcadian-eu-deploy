#!/usr/bin/env python3
import hashlib
import json
import os
import secrets
import subprocess
import tempfile
from pathlib import Path
import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parent
values = dict(line.split('=', 1) for line in (ROOT / '.env').read_text().splitlines() if '=' in line)
if values.get('DJANGO_ENV') != 'local':
    raise RuntimeError('This acceptance script only runs locally.')
env = dict(os.environ, **values)
python = str(ROOT / '.venv/bin/python')
state = ROOT / '.state/backup-fixture.json'
identity = ROOT / '.state/backup-identity.txt'
recipient = ROOT / '.state/backup-recipient.txt'
if not identity.exists():
    subprocess.run(['age-keygen', '-o', str(identity)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    identity.chmod(0o600)
    recipient.write_bytes(subprocess.check_output(['age-keygen', '-y', str(identity)]))
env['BACKUP_AGE_RECIPIENT'] = recipient.read_text().strip()

def manage(*args, environment=env):
    return subprocess.check_output([python, str(ROOT/'manage.py'), *args], env=environment, stderr=subprocess.PIPE)

name = 'restore_arcadian_' + secrets.token_hex(6)
created = False
fixture_created = False
with tempfile.TemporaryDirectory(prefix='arcadian-restored-media-') as media:
    restore_env = dict(env, DB_NAME=name, MEDIA_ROOT=media)
    try:
        manage('browser_fixture', 'create', '--state', str(state))
        fixture_created = True
        with psycopg.connect(dbname='postgres', user=env['DB_USER'], password=env['DB_PASSWORD'], host=env['DB_HOST'], port=env['DB_PORT'], autocommit=True) as connection:
            connection.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
            created = True
        source_stats = manage('shell', '-c', "from content.models import Project,Rate,ProjectPhoto; print(Project.objects.count(),Rate.objects.count(),ProjectPhoto.objects.count(),Project.history.count(),Rate.history.count())").decode().splitlines()[-1]
        backup_env = dict(env, DB_USER=env['BACKUP_DB_USER'], DB_PASSWORD=env['BACKUP_DB_PASSWORD'])
        result = json.loads(manage('content_backup', '--output', str(ROOT / '.backups'), environment=backup_env).decode().splitlines()[-1])
        manage('migrate', '--noinput', environment=restore_env)
        manage('content_restore', '--archive', result['archive'], '--identity', str(identity), environment=restore_env)
        restored_stats = manage('shell', '-c', "from content.models import Project,Rate,ProjectPhoto; print(Project.objects.count(),Rate.objects.count(),ProjectPhoto.objects.count(),Project.history.count(),Rate.history.count())", environment=restore_env).decode().splitlines()[-1]
        if source_stats != restored_stats:
            raise RuntimeError('Restored row counts do not match the source.')
        fixture = json.loads(state.read_text())
        for key in fixture['files']:
            if hashlib.sha256((ROOT / '.media' / key).read_bytes()).digest() != hashlib.sha256((Path(media) / key).read_bytes()).digest():
                raise RuntimeError('Restored image differs from source.')
        report = {'result': 'PASS', 'row_counts_projects_rates_photos_history': restored_stats, 'verified_image_variants': len(fixture['files']), 'archive': Path(result['archive']).name, 'restore_target': 'fresh temporary PostgreSQL database', 'private_key': 'kept offline in cms/.state, excluded from Git'}
        (ROOT / '.state/backup-acceptance.json').write_text(json.dumps(report, indent=2))
        print(json.dumps(report))
    finally:
        if fixture_created:
            manage('browser_fixture', 'cleanup', '--state', str(state))
        if created:
            with psycopg.connect(dbname='postgres', user=env['DB_USER'], password=env['DB_PASSWORD'], host=env['DB_HOST'], port=env['DB_PORT'], autocommit=True) as connection:
                connection.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))
