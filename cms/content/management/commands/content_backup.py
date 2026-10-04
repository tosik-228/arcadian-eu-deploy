import hashlib
import json
import os
import subprocess
import tempfile
import zipfile
from io import StringIO
from pathlib import Path
from datetime import datetime, timezone
from django.conf import settings
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from content.models import ProjectPhoto, RateDocument

EXCLUDE = ['contenttypes', 'auth.permission', 'sessions', 'axes']


class Command(BaseCommand):
    help = 'Consistent content/auth/history snapshot plus immutable images, encrypted to an offline age recipient.'

    def add_arguments(self, parser):
        parser.add_argument('--output', required=True)
        parser.add_argument('--upload', action='store_true')

    def handle(self, *args, **options):
        recipient = os.environ.get('BACKUP_AGE_RECIPIENT')
        if not recipient or not recipient.startswith('age1'):
            raise CommandError('Set BACKUP_AGE_RECIPIENT. The private identity must remain offline.')
        output = Path(options['output']).resolve()
        output.mkdir(parents=True, exist_ok=True, mode=0o700)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        target = output / f'arcadian-{stamp}.zip.age'
        with tempfile.TemporaryDirectory(prefix='arcadian-backup-') as scratch:
            archive_path = Path(scratch) / 'content.zip'
            stream = StringIO()
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
                call_command('dumpdata', exclude=EXCLUDE, natural_foreign=True, natural_primary=True,
                             use_base_manager=True, stdout=stream)
                keys = set()
                for model in [ProjectPhoto, ProjectPhoto.history.model]:
                    for values in model.objects.values_list('large', 'card', 'small').iterator():
                        keys.update(key for key in values if key)
                for model in [RateDocument, RateDocument.history.model]:
                    keys.update(key for key in model.objects.values_list('file_key', flat=True).iterator() if key)
            data = stream.getvalue().encode()
            manifest = {'format': 1, 'created_at': stamp, 'django': '5.2.17',
                        'export_sha256': hashlib.sha256(data).hexdigest(), 'files': {}}
            with zipfile.ZipFile(archive_path, 'w') as archive:
                archive.writestr('data.json', data, compress_type=zipfile.ZIP_DEFLATED)
                for key in sorted(keys):
                    if not key.startswith(('photos/', 'documents/')) or '..' in key.split('/'):
                        raise CommandError('Unexpected media key; backup refused.')
                    digest = hashlib.sha256()
                    count = 0
                    with default_storage.open(key, 'rb') as source, archive.open('media/' + key, 'w') as destination:
                        while chunk := source.read(1024 * 1024):
                            digest.update(chunk)
                            count += len(chunk)
                            destination.write(chunk)
                    manifest['files'][key] = {'sha256': digest.hexdigest(), 'bytes': count}
                archive.writestr('manifest.json', json.dumps(manifest), compress_type=zipfile.ZIP_DEFLATED)
            subprocess.run(['age', '--encrypt', '--recipient', recipient, '--output', str(target), str(archive_path)], check=True)
            target.chmod(0o600)
        if options['upload']:
            import boto3
            needed = ['BACKUP_S3_BUCKET', 'BACKUP_S3_ENDPOINT', 'BACKUP_S3_REGION', 'BACKUP_S3_ACCESS_KEY', 'BACKUP_S3_SECRET_KEY']
            if any(not os.environ.get(name) for name in needed):
                raise CommandError('Independent backup storage credentials must be configured.')
            if os.environ['BACKUP_S3_BUCKET'] == os.environ.get('S3_BUCKET'):
                raise CommandError('Backups must use a separate bucket.')
            client = boto3.client('s3', endpoint_url=os.environ['BACKUP_S3_ENDPOINT'], region_name=os.environ['BACKUP_S3_REGION'],
                                  aws_access_key_id=os.environ['BACKUP_S3_ACCESS_KEY'], aws_secret_access_key=os.environ['BACKUP_S3_SECRET_KEY'])
            client.upload_file(str(target), os.environ['BACKUP_S3_BUCKET'], 'arcadian/' + target.name,
                               ExtraArgs={'ContentType': 'application/octet-stream'})
        self.stdout.write(json.dumps({'archive': str(target), 'files': len(manifest['files']), 'uploaded': bool(options['upload'])}))
