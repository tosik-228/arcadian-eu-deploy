import tempfile
from io import BytesIO
from pathlib import Path
from PIL import Image
from django.test import TestCase, TransactionTestCase, Client, override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import transaction
from django_otp.oath import totp
from django_otp.plugins.otp_totp.models import TOTPDevice
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from .models import Project, ProjectPhoto, Rate, RateDocument, Status
from .images import prepare_image, store_image
from .documents import prepare_document, store_document, store_translation, document_file_keys
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
        self.editor.user_permissions.set(Permission.objects.filter(content_type__app_label='content', content_type__model__in=['project', 'projectphoto', 'rate', 'ratedocument']))
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
        for path in ['/api/projects/', '/api/rates/', '/api/documents/']:
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
        upload.size = 50 * 1024 * 1024 + 1
        with self.assertRaises(ValidationError):
            prepare_image(upload)
        buffer = BytesIO()
        Image.new('RGB', (10, 10), 'red').save(buffer, 'WEBP', save_all=True,
            append_images=[Image.new('RGB', (10, 10), 'blue')], duration=100, loop=0)
        with self.assertRaises(ValidationError):
            prepare_image(SimpleUploadedFile('animation.webp', buffer.getvalue()))

    def test_mac_still_photo_containers_use_the_primary_photo(self):
        from pillow_heif import from_pillow
        for kind in ['MPO', 'TIFF', 'HEIF']:
            buffer = BytesIO()
            primary = Image.new('RGB', (320, 240), 'red')
            auxiliary = Image.new('RGB', (320, 240), 'blue')
            if kind == 'HEIF':
                container = from_pillow(primary)
                container.add_from_pillow(auxiliary)
                container.save(buffer, quality=95)
            else:
                primary.save(buffer, kind, save_all=True, append_images=[auxiliary])
            with self.subTest(kind=kind):
                prepared = prepare_image(SimpleUploadedFile('Photos-export.jpg', buffer.getvalue(), content_type='application/octet-stream'))
                with Image.open(BytesIO(prepared['variants']['large'])) as result:
                    self.assertEqual(result.size, (320, 240))
                    red, green, blue = result.getpixel((160, 120))
                    self.assertGreater(red, 200)
                    self.assertLess(blue, 50)
                    self.assertFalse(result.getexif())

    def test_4k_photo_preserves_resolution_and_creates_small_previews(self):
        buffer = BytesIO()
        exif = Image.Exif()
        exif[0x0112] = 6  # Portrait orientation from camera/Photos.
        exif[0x010E] = 'PRIVATE LOCATION'
        Image.new('RGB', (3840, 2160), '#abcdef').save(buffer, 'JPEG', exif=exif)
        prepared = prepare_image(SimpleUploadedFile('4k-from-Photos.jpeg', buffer.getvalue()))
        self.assertEqual((prepared['width'], prepared['height']), (2160, 3840))
        for key, dimensions in [('large', (2160, 3840)), ('card', (960, 720)), ('small', (480, 360))]:
            with Image.open(BytesIO(prepared['variants'][key])) as result:
                self.assertEqual(result.size, dimensions)
                self.assertFalse(result.getexif())
            self.assertNotIn(b'PRIVATE LOCATION', prepared['variants'][key])

    def test_empty_album_can_be_saved_as_draft(self):
        values = dict(title='Empty draft album', category='facades', status='draft', sort=0,
            **{'photos-TOTAL_FORMS': '0', 'photos-INITIAL_FORMS': '0', 'photos-MIN_NUM_FORMS': '0', 'photos-MAX_NUM_FORMS': '60'})
        response = self.verified_client().post('/admin/content/project/add/', values)
        self.assertEqual(response.status_code, 302)
        project = Project.objects.get(title='Empty draft album')
        self.assertEqual(project.photos.count(), 0)
        self.assertEqual(self.client.get('/api/projects/').json()['data'], [])

    def test_batch_rejection_identifies_the_file_without_partial_publication(self):
        values = dict(title='Invalid batch', description='Works', category='facades', status='published', sort=0,
            **{'photos-TOTAL_FORMS': '0', 'photos-INITIAL_FORMS': '0', 'photos-MIN_NUM_FORMS': '0', 'photos-MAX_NUM_FORMS': '60'},
            photographs=[self.photo_upload(), SimpleUploadedFile('broken-photo.heic', b'broken')])
        response = self.verified_client().post('/admin/content/project/add/', values)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'broken-photo.heic')
        self.assertFalse(Project.objects.filter(title='Invalid batch').exists())

    def pdf_upload(self, pages=1, encrypted=False, javascript=False):
        from pypdf import PdfWriter
        writer = PdfWriter()
        for _ in range(pages):
            writer.add_blank_page(width=595, height=842)
        if encrypted:
            writer.encrypt('private-password')
        if javascript:
            writer.add_js('app.alert("no scripts allowed");')
        buffer = BytesIO()
        writer.write(buffer)
        return SimpleUploadedFile('rates.pdf', buffer.getvalue(), content_type='application/pdf')

    def rate_document(self, category='electrical', status='published', visibility='public'):
        obj = RateDocument(title='PDF rate sheet', category=category, status=status, visibility=visibility)
        store_document(obj, prepare_document(self.pdf_upload()))
        obj.save()
        return obj

    def test_pdf_validation_rejects_fake_broken_encrypted_and_active_documents(self):
        inputs = [SimpleUploadedFile('fake.pdf', b'<svg/>', content_type='application/pdf'),
            SimpleUploadedFile('broken.pdf', b'%PDF-1.7\nbroken'), self.pdf_upload(encrypted=True),
            self.pdf_upload(javascript=True), self.pdf_upload(pages=201)]
        oversized = self.pdf_upload()
        oversized.size = 25 * 1024 * 1024 + 1
        inputs.append(oversized)
        for upload in inputs:
            with self.subTest(upload=upload.name, size=upload.size):
                with self.assertRaises(ValidationError):
                    prepare_document(upload)

    def test_pdf_categories_and_publication_control_api_and_downloads(self):
        public = [self.rate_document(category=category) for category in ['electrical', 'facades', 'finishing', 'subcontractors']]
        private = self.rate_document(status='published', visibility='private')
        draft = self.rate_document(status='draft')
        for obj in public:
            data = self.client.get(f'/api/documents/?category={obj.category}').json()['data']
            self.assertEqual([row['id'] for row in data], [str(obj.id)])
            self.assertNotIn('file_key', data[0])
            for download in ['', '?download=1']:
                response = self.client.get(f'/api/documents/{obj.id}/{download}')
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response['Content-Type'], 'application/pdf')
                self.assertTrue(response['Content-Disposition'].startswith('attachment' if download else 'inline'))
                import hashlib
                self.assertEqual(hashlib.sha256(b''.join(response.streaming_content)).hexdigest(), obj.file_sha256)
        for obj in [private, draft]:
            self.assertEqual(self.client.get(f'/api/documents/{obj.id}/').status_code, 404)
            self.client.force_login(self.editor)
            self.assertEqual(self.client.get(f'/api/documents/{obj.id}/').status_code, 404)
            self.client.logout()
            response = self.verified_client().get(f'/api/documents/{obj.id}/')
            self.assertEqual(response.status_code, 200)
            b''.join(response.streaming_content)
        public[0].status = 'archived'
        public[0].save()
        self.assertEqual(self.client.get(f'/api/documents/{public[0].id}/').status_code, 404)
        self.assertEqual(self.client.get('/api/documents/?category=electrical').json()['data'], [])

    def test_pdf_admin_upload_replace_and_history_restore_preserve_original_bytes(self):
        from django.core.files.storage import default_storage
        import hashlib
        client = self.verified_client()
        original = self.pdf_upload()
        original_bytes = original.read()
        original.seek(0)
        values = dict(title='Uploaded PDF', category='subcontractors', status='published', visibility='public', sort=0, upload=original)
        response = client.post('/admin/content/ratedocument/add/', values)
        self.assertEqual(response.status_code, 302, response.context['adminform'].form.errors.as_json() if response.status_code == 200 else '')
        obj = RateDocument.objects.get(title='Uploaded PDF')
        history = obj.history.first()
        old_key = obj.file_key
        self.assertEqual(obj.file_sha256, hashlib.sha256(original_bytes).hexdigest())
        values.update(saved_revision=obj.revision, upload=self.pdf_upload(pages=2))
        response = client.post(f'/admin/content/ratedocument/{obj.id}/change/', values)
        self.assertEqual(response.status_code, 302)
        obj.refresh_from_db()
        new_key = obj.file_key
        self.assertNotEqual(old_key, new_key)
        self.assertTrue(default_storage.exists(old_key))
        self.assertEqual(obj.page_count, 2)
        previous_url = f'/api/documents/{obj.id}/?revision={history.history_id}'
        self.assertEqual(self.client.get(previous_url).status_code, 404)
        previous = client.get(previous_url)
        self.assertEqual(b''.join(previous.streaming_content), original_bytes)
        self.assertEqual(client.get(previous_url.replace(str(history.history_id), 'invalid')).status_code, 404)
        values.pop('upload')
        values['saved_revision'] = obj.revision
        response = client.post(f'/admin/content/ratedocument/{obj.id}/history/{history.history_id}/', values)
        self.assertEqual(response.status_code, 302)
        obj.refresh_from_db()
        self.assertEqual(obj.file_key, old_key)
        self.assertEqual(obj.page_count, 1)
        self.assertEqual(obj.revision, 3)
        self.assertTrue(default_storage.exists(new_key))

    def test_publish_requires_title_description_and_photo(self):
        with self.assertRaises(ValidationError):
            Project(title='', description='', category='facades', status=Status.PUBLISHED).save()
        with self.assertRaises(ValidationError):
            Project(title='Facade', description='Works', category='facades', status=Status.PUBLISHED).save()

    def test_pdf_translations_share_publication_access_and_do_not_expose_storage_keys(self):
        import hashlib
        obj = self.rate_document()
        for index, language in enumerate(['ru', 'pl', 'nl'], start=2):
            store_translation(obj, language, prepare_document(self.pdf_upload(pages=index)))
        obj.save()
        row = self.client.get('/api/documents/').json()['data'][0]
        self.assertEqual(row['primary_language'], 'en')
        self.assertEqual([item['language'] for item in row['translations']], ['ru', 'pl', 'nl'])
        self.assertNotIn('file_key', str(row))
        self.assertNotIn('file_sha256', str(row))
        for language in ['ru', 'pl', 'nl']:
            response = self.client.get(f'/api/documents/{obj.id}/?language={language}&download=1')
            self.assertEqual(response.status_code, 200)
            self.assertIn(f'-{language}.pdf', response['Content-Disposition'])
            self.assertEqual(hashlib.sha256(b''.join(response.streaming_content)).hexdigest(), obj.translations[language]['file_sha256'])
        for language in ['fr', '', '../en', 'RU']:
            self.assertEqual(self.client.get(f'/api/documents/{obj.id}/', {'language': language}).status_code, 404)
        for changes in [{'status': 'draft'}, {'status': 'published', 'visibility': 'private'}, {'status': 'archived', 'visibility': 'public'}]:
            for name, value in changes.items():
                setattr(obj, name, value)
            obj.save()
            self.assertEqual(self.client.get('/api/documents/').json()['data'], [])
            for language in ['en', 'ru', 'pl', 'nl']:
                self.assertEqual(self.client.get(f'/api/documents/{obj.id}/?language={language}').status_code, 404)
            response = self.verified_client().get(f'/api/documents/{obj.id}/?language=ru')
            self.assertEqual(response.status_code, 200)
            b''.join(response.streaming_content)

    def test_translation_metadata_rejects_other_documents_and_unsafe_paths(self):
        obj = self.rate_document()
        store_translation(obj, 'ru', prepare_document(self.pdf_upload()))
        metadata = dict(obj.translations['ru'])
        invalid = [None, {'fr': metadata}, {'ru': {'file_key': 'missing'}},
            {'ru': dict(metadata, file_key='../private.pdf')},
            {'ru': dict(metadata, file_key=metadata['file_key'].replace(str(obj.id), str(self.rate_document().id)))},
            {'ru': dict(metadata, page_count=201)}, {'ru': dict(metadata, file_bytes=True)}]
        for translations in invalid:
            obj.translations = translations
            with self.assertRaises(ValidationError):
                obj.clean()

    def test_admin_translation_replace_remove_and_history_restore(self):
        from django.core.files.storage import default_storage
        client = self.verified_client()
        values = dict(title='English sheet', category='facades', status='published', visibility='public', sort=0,
            upload=self.pdf_upload(), translation_ru=self.pdf_upload(pages=2), translation_pl=self.pdf_upload(pages=3))
        response = client.post('/admin/content/ratedocument/add/', values)
        self.assertEqual(response.status_code, 302)
        obj = RateDocument.objects.get(title='English sheet')
        history = obj.history.first()
        english_key = obj.file_key
        original = dict(obj.translations)
        values = dict(title=obj.title, category=obj.category, status=obj.status, visibility=obj.visibility, sort=0,
            saved_revision=obj.revision, translation_ru=self.pdf_upload(pages=4), remove_pl='on')
        response = client.post(f'/admin/content/ratedocument/{obj.id}/change/', values)
        self.assertEqual(response.status_code, 302)
        obj.refresh_from_db()
        replacement = obj.translations['ru']['file_key']
        self.assertEqual(obj.file_key, english_key)
        self.assertNotEqual(replacement, original['ru']['file_key'])
        self.assertNotIn('pl', obj.translations)
        self.assertTrue(all(default_storage.exists(item['file_key']) for item in original.values()))
        self.assertEqual(self.client.get(f'/api/documents/{obj.id}/?language=pl').status_code, 404)
        previous_url = f'/api/documents/{obj.id}/?language=pl&revision={history.history_id}'
        self.assertEqual(self.client.get(previous_url).status_code, 404)
        response = client.get(previous_url)
        self.assertEqual(response.status_code, 200)
        b''.join(response.streaming_content)
        values = dict(title=obj.title, category=obj.category, status=obj.status, visibility=obj.visibility, sort=0,
            saved_revision=obj.revision)
        response = client.post(f'/admin/content/ratedocument/{obj.id}/history/{history.history_id}/', values)
        self.assertEqual(response.status_code, 302)
        obj.refresh_from_db()
        self.assertEqual(obj.translations, original)
        self.assertEqual(obj.file_key, english_key)
        self.assertTrue(default_storage.exists(replacement))
        normal = client.get(f'/admin/content/ratedocument/{obj.id}/change/')
        self.assertFalse(normal.context['adminform'].form.fields['upload'].disabled)
        self.assertFalse(normal.context['adminform'].form.fields['translation_ru'].disabled)

    def test_bad_translation_upload_does_not_partially_publish_an_english_document(self):
        values = dict(title='Invalid translation', category='facades', status='published', visibility='public', sort=0,
            upload=self.pdf_upload(), translation_ru=SimpleUploadedFile('bad.pdf', b'not a PDF'))
        response = self.verified_client().post('/admin/content/ratedocument/add/', values)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(RateDocument.objects.filter(title='Invalid translation').exists())

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
