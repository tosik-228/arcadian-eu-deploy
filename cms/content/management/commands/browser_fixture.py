import json
import secrets
from io import BytesIO
from pathlib import Path
from PIL import Image
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django_otp.plugins.otp_totp.models import TOTPDevice
from content.models import Project, ProjectPhoto, Rate, RateDocument, Status
from content.images import prepare_image, store_image
from content.documents import prepare_document, store_document


class Command(BaseCommand):
    help = 'Temporary local browser acceptance fixtures; never available in production.'

    def add_arguments(self, parser):
        parser.add_argument('action', choices=['create', 'cleanup'])
        parser.add_argument('--state', required=True)

    def handle(self, *args, **options):
        if settings.PRODUCTION:
            raise CommandError('Fixtures are prohibited in production.')
        state = Path(options['state']).resolve()
        if options['action'] == 'cleanup':
            if not state.exists():
                return
            data = json.loads(state.read_text())
            data['projects'] += [str(value) for value in Project.history.filter(history_user_id=data['user_id']).values_list('id', flat=True)]
            data['rates'] += [str(value) for value in Rate.history.filter(history_user_id=data['user_id']).values_list('id', flat=True)]
            data['documents'] = data.get('documents', []) + [str(value) for value in RateDocument.history.filter(history_user_id=data['user_id']).values_list('id', flat=True)]
            for photo in ProjectPhoto.history.filter(project_id__in=data['projects']):
                data['files'].extend([photo.large, photo.card, photo.small])
            Project.objects.filter(id__in=data['projects']).delete()
            Project.history.filter(id__in=data['projects']).delete()
            ProjectPhoto.history.filter(project_id__in=data['projects']).delete()
            Rate.objects.filter(id__in=data['rates']).delete()
            Rate.history.filter(id__in=data['rates']).delete()
            data['files'].extend(RateDocument.history.filter(id__in=data['documents']).values_list('file_key', flat=True))
            RateDocument.objects.filter(id__in=data['documents']).delete()
            RateDocument.history.filter(id__in=data['documents']).delete()
            get_user_model().objects.filter(pk=data['user_id'], username=data['username']).delete()
            for key in data['files']:
                if key.startswith(('photos/', 'documents/')) and '..' not in key:
                    default_storage.delete(key)
            state.unlink()
            Path(data['upload']).unlink(missing_ok=True)
            if data.get('pdf_upload'):
                Path(data['pdf_upload']).unlink(missing_ok=True)
            self.stdout.write('Temporary fixtures removed.')
            return
        if state.exists():
            raise CommandError('Existing fixture state must be cleaned up first.')
        data = {'projects': [], 'rates': [], 'documents': [], 'files': [], 'username': 'browser-' + secrets.token_hex(6), 'password': secrets.token_urlsafe(24)}
        with transaction.atomic():
            user = get_user_model().objects.create_user(data['username'], password=data['password'], is_staff=True)
            user.user_permissions.set(Permission.objects.filter(content_type__app_label='content', content_type__model__in=['project', 'projectphoto', 'rate', 'ratedocument']))
            device = TOTPDevice.objects.create(user=user, name='Browser acceptance')
            data.update(user_id=user.pk, otp_key=device.key, otp_device=device.persistent_id)
            for index, sector in enumerate(['finishing', 'electrical', 'facades']):
                project = Project.objects.create(title='Acceptance ' + sector, title_pl='Realizacja próbna ' + sector,
                    title_nl='Proefproject ' + sector, description='Temporary acceptance fixture. Removed after verification.', category=sector, sort=index)
                data['projects'].append(str(project.id))
                for photo_index in range(2 if sector == 'finishing' else 1):
                    image = Image.new('RGB', (1600, 1200), ['#376880', '#ab7955', '#586c58'][index])
                    buffer = BytesIO()
                    image.save(buffer, 'JPEG')
                    photo = ProjectPhoto(project=project, description=f'Acceptance photograph {photo_index + 1}', sort=photo_index)
                    store_image(photo, prepare_image(SimpleUploadedFile('fixture.jpg', buffer.getvalue())))
                    photo.save()
                    data['files'].extend([photo.large, photo.card, photo.small])
                project.status = Status.PUBLISHED
                project.save()
            for index, worker in enumerate(['employee', 'independent', 'crew']):
                rate = Rate.objects.create(title='Acceptance ' + worker, description='Temporary rate for verification.',
                    category='electrical', worker_type=worker, basis='payroll_gross' if worker == 'employee' else 'invoice_ex_vat',
                    unit='hour_person' if worker != 'crew' else 'hour_crew', amount_from='24.00',
                    amount_to='32.00', visibility='public', status='published', sort=index, own_tools=worker != 'employee', own_vehicle=worker != 'employee')
                data['rates'].append(str(rate.id))
            private = Rate.objects.create(title='PRIVATE ACCEPTANCE RATE', description='Never public.', category='facades',
                worker_type='independent', basis='invoice_ex_vat', unit='m2', amount_from='99', status='published', visibility='private')
            data['rates'].append(str(private.id))
            from pypdf import PdfWriter
            writer = PdfWriter()
            writer.add_blank_page(width=595, height=842)
            pdf = BytesIO()
            writer.write(pdf)
            for sector in ['electrical', 'facades', 'finishing', 'subcontractors']:
                document = RateDocument(title='Acceptance PDF ' + sector, category=sector, status='published', visibility='public')
                store_document(document, prepare_document(SimpleUploadedFile('fixture.pdf', pdf.getvalue())))
                document.save()
                data['documents'].append(str(document.id))
                data['files'].append(document.file_key)
            document = RateDocument(title='PRIVATE ACCEPTANCE PDF', category='facades', status='published', visibility='private')
            store_document(document, prepare_document(SimpleUploadedFile('fixture.pdf', pdf.getvalue())))
            document.save()
            data['documents'].append(str(document.id))
            data['files'].append(document.file_key)
            data['pdf_upload'] = str(state.parent / 'browser-upload.pdf')
            Path(data['pdf_upload']).write_bytes(pdf.getvalue())
            data['upload'] = str(state.parent / 'browser-upload.jpg')
            image = Image.new('RGB', (3840, 2160), '#316279')
            image.save(data['upload'], 'MPO', save_all=True, append_images=[Image.new('RGB', (480, 270), 'blue')])
            state.write_text(json.dumps(data))
            state.chmod(0o600)
        self.stdout.write('Temporary browser fixtures created; private state saved.')
