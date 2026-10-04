import tempfile
from io import BytesIO
from pathlib import Path
from PIL import Image
from django.test import TestCase, Client, override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import transaction
from django_otp.oath import totp
from django_otp.plugins.otp_totp.models import TOTPDevice
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from .models import Project, ProjectPhoto, Rate, Status
from .images import prepare_image, store_image
from .forms import RateForm
from .forms import PhotographBatch
from .middleware import client_ip
from .views import storage_health
import ipaddress
from django.test import RequestFactory


@override_settings(ALLOWED_HOSTS=['testserver'], AXES_ENABLED=False)
class ContentAcceptance(TestCase):
    def test_batch_total_size_is_rejected_before_decoding(self):
        files = [SimpleUploadedFile('large.jpg', b'x') for _ in range(4)]
        for file in files:
            file.size = 20 * 1024 * 1024
        with self.assertRaisesMessage(ValidationError, 'Суммарный размер'):
            PhotographBatch().clean(files)

    @override_settings(TRUSTED_PROXY_NETWORKS=[ipaddress.ip_network('172.30.77.0/28')])
    def test_proxy_client_ip_is_accepted_only_from_the_private_proxy_network(self):
        factory = RequestFactory()
        public = factory.get('/', REMOTE_ADDR='198.51.100.7', HTTP_X_ARCADIAN_CLIENT_IP='203.0.113.4')
        trusted = factory.get('/', REMOTE_ADDR='172.30.77.2', HTTP_X_ARCADIAN_CLIENT_IP='203.0.113.4')
        invalid = factory.get('/', REMOTE_ADDR='172.30.77.2', HTTP_X_ARCADIAN_CLIENT_IP='invalid')
        self.assertEqual(client_ip(public), '198.51.100.7')
        self.assertEqual(client_ip(trusted), '203.0.113.4')
        self.assertEqual(client_ip(invalid), '172.30.77.2')

    def test_production_filesystem_health_checks_the_persistent_directory(self):
        with override_settings(PRODUCTION=True, MEDIA_BACKEND='filesystem'):
            storage_health.cache_clear()
            self.assertEqual(self.client.get('/healthz/').status_code, 200)
            with override_settings(MEDIA_ROOT=Path(self.media.name) / 'absent'):
                storage_health.cache_clear()
                self.assertEqual(self.client.get('/healthz/').status_code, 503)
            storage_health.cache_clear()

    def setUp(self):
        self.media = tempfile.TemporaryDirectory(prefix='arcadian-acceptance-')
        self.settings_override = override_settings(MEDIA_ROOT=self.media.name)
        self.settings_override.enable()
        self.editor = get_user_model().objects.create_user('test-editor', password='strong-test-password-2026', is_staff=True)
        self.editor.user_permissions.set(Permission.objects.filter(content_type__app_label='content', content_type__model__in=['project', 'projectphoto', 'rate']))
        self.device = TOTPDevice.objects.create(user=self.editor, name='authenticator')

    def tearDown(self):
        self.settings_override.disable()
        self.media.cleanup()

    def photo_upload(self):
        image = Image.new('RGB', (1600, 1200), '#376880')
        exif = Image.Exif()
        exif[0x010E] = 'PRIVATE SOURCE METADATA'
        exif[0x010F] = 'Private camera'
        buffer = BytesIO()
        image.save(buffer, format='JPEG', exif=exif)
        return SimpleUploadedFile('private-address.jpg', buffer.getvalue(), content_type='image/jpeg')

    def project(self, status=Status.DRAFT):
        project = Project.objects.create(title='Acceptance project', description='Verified work description', category='electrical')
        photo = ProjectPhoto(project=project, sort=1)
        store_image(photo, prepare_image(self.photo_upload()))
        photo.save()
        if status != Status.DRAFT:
            project.status = status
            project.save()
        return project, photo

    def rate(self, **kwargs):
        values = dict(title='Specialist rate', description='Tools and travel agreed separately.', category='electrical',
                      worker_type='independent', basis='invoice_ex_vat', unit='hour_person', amount_from='30.00')
        values.update(kwargs)
        return Rate.objects.create(**values)

    def verified_client(self, enforce_csrf=False):
        client = Client(enforce_csrf_checks=enforce_csrf)
        client.force_login(self.editor)
        session = client.session
        session['otp_device_id'] = self.device.persistent_id
        session.save()
        return client

    def test_password_alone_does_not_open_admin_or_private_photos(self):
        project, photo = self.project()
        self.client.force_login(self.editor)
        self.assertEqual(self.client.get('/admin/').status_code, 302)
        self.assertEqual(self.client.get(f'/api/images/{photo.id}/').status_code, 404)
        self.assertEqual(self.client.get('/api/projects/').json()['data'], [])

    def test_totp_is_required_and_cannot_be_replayed(self):
        values = {'username': self.editor.username, 'password': 'strong-test-password-2026', 'otp_device': self.device.persistent_id}
        self.assertEqual(self.client.post('/admin/login/', values).status_code, 200)
        code = totp(self.device.bin_key, step=self.device.step, t0=self.device.t0, digits=self.device.digits)
        values['otp_token'] = f'{code:06d}'
        self.assertEqual(self.client.post('/admin/login/', values).status_code, 302)
        self.assertEqual(self.client.get('/admin/').status_code, 200)
        self.client.logout()
        self.assertEqual(self.client.post('/admin/login/', values).status_code, 200)

    def test_login_automatically_selects_totp_or_recovery_device(self):
        recovery = StaticDevice.objects.create(user=self.editor, name='recovery')
        StaticToken.objects.create(device=recovery, token='abcdef1234567890')
        values = {'username': self.editor.username, 'password': 'strong-test-password-2026',
                  'otp_token': f'{totp(self.device.bin_key):06d}'}
        self.assertEqual(self.client.post('/admin/login/', values).status_code, 302)
        self.client.logout()
        values['otp_token'] = 'abcdef1234567890'
        self.assertEqual(self.client.post('/admin/login/', values).status_code, 302)
        self.assertFalse(recovery.token_set.exists())

    def test_recovery_code_is_single_use(self):
        device = StaticDevice.objects.create(user=self.editor, name='recovery')
        StaticToken.objects.create(device=device, token='one-use-recovery')
        values = {'username': self.editor.username, 'password': 'strong-test-password-2026',
                  'otp_device': device.persistent_id, 'otp_token': 'one-use-recovery'}
        self.assertEqual(self.client.post('/admin/login/', values).status_code, 302)
        self.assertFalse(device.token_set.exists())
        self.client.logout()
        self.assertEqual(self.client.post('/admin/login/', values).status_code, 200)

    def test_editor_has_two_content_sections_and_no_user_management(self):
        response = self.verified_client().get('/admin/')
        self.assertContains(response, 'Работы')
        self.assertContains(response, 'Расценки')
        self.assertNotContains(response, '/admin/auth/')
        self.assertEqual(self.verified_client().get('/admin/auth/user/').status_code, 403)

    def test_csrf_required_for_writes(self):
        self.assertEqual(self.verified_client(True).post('/admin/content/rate/add/', {}).status_code, 403)

    def test_public_api_is_read_only_and_validates_pagination(self):
        for path in ['/api/projects/', '/api/rates/']:
            for method in ['post', 'put', 'delete']:
                self.assertEqual(getattr(self.client, method)(path).status_code, 405)
            self.assertEqual(self.client.get(path + '?page=-1').status_code, 400)
            self.assertEqual(self.client.get(path + '?page=abc').status_code, 400)
            self.assertEqual(self.client.get(path + '?category=unknown').status_code, 400)

    def test_private_rates_and_drafts_never_leave_public_api(self):
        self.rate(status=Status.PUBLISHED, visibility='private', title='INTERNAL RATE')
        self.rate(status=Status.DRAFT, visibility='public', title='DRAFT RATE')
        public = self.rate(status=Status.PUBLISHED, visibility='public')
        response = self.client.get('/api/rates/').json()
        self.assertEqual([row['id'] for row in response['data']], [str(public.id)])
        self.assertNotIn('visibility', response['data'][0])
        self.assertNotIn('revision', response['data'][0])

    def test_project_and_photos_disappear_on_unpublish(self):
        project, photo = self.project(Status.PUBLISHED)
        self.assertEqual(len(self.client.get('/api/projects/').json()['data']), 1)
        response = self.client.get(f'/api/images/{photo.id}/?size=card')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        b''.join(response.streaming_content)
        project.status = Status.DRAFT
        project.save()
        self.assertEqual(self.client.get('/api/projects/').json()['data'], [])
        self.assertEqual(self.client.get(f'/api/images/{photo.id}/?size=card').status_code, 404)
        response = self.verified_client().get(f'/api/images/{photo.id}/?size=small')
        self.assertEqual(response.status_code, 200)
        b''.join(response.streaming_content)

    def test_upload_ignores_spoofed_mime_and_strips_metadata(self):
        bad = SimpleUploadedFile('fake.jpg', b'<svg onload="alert(1)"></svg>', content_type='image/jpeg')
        with self.assertRaises(ValidationError):
            prepare_image(bad)
        prepared = prepare_image(self.photo_upload())
        for size, body in prepared['variants'].items():
            with Image.open(BytesIO(body)) as image:
                self.assertEqual(image.format, 'WEBP')
                self.assertFalse(image.getexif())
                self.assertNotIn('exif', image.info)
                self.assertNotIn('xmp', image.info)
                self.assertLessEqual(max(image.size), 2400)
        self.assertNotIn(b'PRIVATE SOURCE', prepared['variants']['large'])

    def test_oversize_and_animated_images_are_rejected(self):
        upload = self.photo_upload()
        upload.size = 20 * 1024 * 1024 + 1
        with self.assertRaises(ValidationError):
            prepare_image(upload)
        buffer = BytesIO()
        Image.new('RGB', (10, 10), 'red').save(buffer, 'WEBP', save_all=True,
            append_images=[Image.new('RGB', (10, 10), 'blue')], duration=100, loop=0)
        with self.assertRaises(ValidationError):
            prepare_image(SimpleUploadedFile('animation.webp', buffer.getvalue()))

    def test_publish_requires_title_description_and_photo(self):
        with self.assertRaises(ValidationError):
            Project(title='', description='', category='facades', status=Status.PUBLISHED).save()
        with self.assertRaises(ValidationError):
            Project(title='Facade', description='Works', category='facades', status=Status.PUBLISHED).save()

    def test_rate_range_basis_and_amount_are_validated(self):
        for changes in [dict(amount_from='40.00', amount_to='30.00'), dict(amount_from='0'),
                        dict(worker_type='employee', basis='invoice_ex_vat'),
                        dict(amount_from=None, status=Status.PUBLISHED, visibility='public')]:
            with self.assertRaises(ValidationError):
                with transaction.atomic():
                    self.rate(**changes)

    def test_stale_edit_is_rejected(self):
        rate = self.rate()
        stale = Rate.objects.get(pk=rate.pk)
        rate.description = 'Newer valid description'
        rate.save()
        stale.description = 'Stale overwrite'
        with self.assertRaises(ValidationError):
            stale.save()
        rate.refresh_from_db()
        self.assertEqual(rate.description, 'Newer valid description')

    def test_history_restore_retains_validation_and_creates_new_revision(self):
        rate = self.rate()
        original = rate.history.first()
        rate.description = 'Changed description'
        rate.save()
        client = self.verified_client()
        url = f'/admin/content/rate/{rate.id}/history/{original.history_id}/'
        response = client.get(url)
        self.assertEqual(response.status_code, 200)
        values = {name: getattr(original, name) for name in [
            'title', 'description', 'category', 'worker_type', 'unit', 'basis', 'status', 'visibility', 'sort',
        ]}
        values.update(amount_from='30.00', saved_revision=rate.revision, _save='1')
        response = client.post(url, values)
        self.assertEqual(response.status_code, 302)
        rate.refresh_from_db()
        self.assertEqual(rate.description, original.description)
        self.assertEqual(rate.revision, 3)
        self.assertEqual(rate.history.first().history_user_id, self.editor.id)

    def test_admin_bulk_upload_and_publish_are_one_transaction(self):
        values = dict(title='Bulk upload', description='Electrical work', category='electrical', status='published', sort=0,
                      **{'photos-TOTAL_FORMS': '0', 'photos-INITIAL_FORMS': '0', 'photos-MIN_NUM_FORMS': '0', 'photos-MAX_NUM_FORMS': '60'})
        values['photographs'] = [self.photo_upload(), self.photo_upload()]
        response = self.verified_client().post('/admin/content/project/add/', values)
        self.assertEqual(response.status_code, 302)
        project = Project.objects.get(title='Bulk upload')
        self.assertEqual(project.photos.count(), 2)
        self.assertEqual(len(self.client.get('/api/projects/').json()['data'][0]['photos']), 2)
        self.assertEqual(project.history.first().history_user_id, self.editor.id)

    def test_cannot_delete_last_photo_while_published(self):
        project, photo = self.project(Status.PUBLISHED)
        values = dict(title=project.title, description=project.description, category='electrical', status='published',
                      sort=0, saved_revision=project.revision, **{
            'photos-TOTAL_FORMS': '1', 'photos-INITIAL_FORMS': '1', 'photos-MIN_NUM_FORMS': '0', 'photos-MAX_NUM_FORMS': '60',
            'photos-0-id': str(photo.id), 'photos-0-project': str(project.id), 'photos-0-sort': '1', 'photos-0-DELETE': 'on',
        })
        response = self.verified_client().post(f'/admin/content/project/{project.id}/change/', values)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Для публикации оставьте хотя бы одну фотографию.')
        self.assertTrue(ProjectPhoto.objects.filter(pk=photo.id).exists())

    def test_cors_only_allows_known_public_origins(self):
        self.assertEqual(self.client.get('/api/projects/', HTTP_ORIGIN='http://127.0.0.1:8173')['Access-Control-Allow-Origin'], 'http://127.0.0.1:8173')
        self.assertNotIn('Access-Control-Allow-Origin', self.client.get('/api/projects/', HTTP_ORIGIN='https://untrusted.example'))
        self.assertNotIn('Access-Control-Allow-Origin', self.client.get('/admin/login/', HTTP_ORIGIN='http://127.0.0.1:8173'))

    def test_page_size_and_sector_filter_are_server_controlled(self):
        for index in range(13):
            self.rate(status=Status.PUBLISHED, visibility='public', sort=index)
        first = self.client.get('/api/rates/?page=1&limit=100000').json()
        second = self.client.get('/api/rates/?page=2').json()
        self.assertEqual(len(first['data']), 12)
        self.assertTrue(first['has_more'])
        self.assertEqual(len(second['data']), 1)
        self.assertFalse(second['has_more'])
        self.assertEqual(self.client.get('/api/rates/?category=facades').json()['data'], [])


@override_settings(ALLOWED_HOSTS=['testserver'], AXES_ENABLED=True, PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class LoginLockoutAcceptance(TestCase):
    def test_five_wrong_passwords_lock_account(self):
        get_user_model().objects.create_user('lockout-editor', password='valid-password', is_staff=True)
        for index in range(5):
            response = self.client.post('/admin/login/', {'username': 'lockout-editor', 'password': 'wrong-password'})
        self.assertEqual(response.status_code, 429)
        self.assertContains(response, 'Повторите через 15 минут', status_code=429)
