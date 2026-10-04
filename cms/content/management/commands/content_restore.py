import hashlib
import json
import os
import subprocess
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from content.models import Project, ProjectPhoto, Rate


class Command(BaseCommand):
    help = 'Restore into a fresh isolated restore_* database. Refuses existing users or content.'

    def add_arguments(self, parser):
        parser.add_argument('--archive', required=True)
        parser.add_argument('--identity', required=True)

    def handle(self, *args, **options):
        if not settings.DATABASES['default']['NAME'].startswith('restore_'):
            raise CommandError('Only an isolated restore_* database is allowed.')
        if get_user_model().objects.exists() or Project.objects.exists() or Rate.objects.exists() or ProjectPhoto.history.exists():
            raise CommandError('Restore target must be empty. Existing data will never be overwritten.')
        with tempfile.TemporaryDirectory(prefix='arcadian-restore-') as scratch:
            path = Path(scratch) / 'content.zip'
            subprocess.run(['age', '--decrypt', '--identity', options['identity'], '--output', str(path), options['archive']], check=True)
            with zipfile.ZipFile(path) as archive:
                manifest = json.loads(archive.read('manifest.json'))
                if manifest.get('format') != 1:
                    raise CommandError('Unsupported backup format.')
                data = archive.read('data.json')
                if hashlib.sha256(data).hexdigest() != manifest['export_sha256']:
                    raise CommandError('Export checksum mismatch.')
                # Validate every file before writing anything to the target.
                for key, expected in manifest['files'].items():
                    if not key.startswith('photos/') or '..' in PurePosixPath(key).parts or PurePosixPath(key).is_absolute():
                        raise CommandError('Invalid media path.')
                    digest = hashlib.sha256()
                    count = 0
                    with archive.open('media/' + key) as source:
                        while chunk := source.read(1024 * 1024):
                            digest.update(chunk)
                            count += len(chunk)
                    if digest.hexdigest() != expected['sha256'] or count != expected['bytes']:
                        raise CommandError('Media checksum mismatch.')
                    if default_storage.exists(key):
                        raise CommandError('Target media storage must be empty.')
                for key in manifest['files']:
                    with archive.open('media/' + key) as source:
                        default_storage.save(key, ContentFile(source.read()))
                fixture = Path(scratch) / 'data.json'
                fixture.write_bytes(data)
                call_command('loaddata', str(fixture), verbosity=0)
        self.stdout.write(json.dumps({'restored': True, 'files': len(manifest['files'])}))
