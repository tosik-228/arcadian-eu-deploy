import html
import os
import secrets
from pathlib import Path
from io import BytesIO
import qrcode
import qrcode.image.svg
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.password_validation import validate_password
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django_otp.plugins.otp_totp.models import TOTPDevice
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken


class Command(BaseCommand):
    help = 'Create a content editor with mandatory TOTP and one-time recovery codes. Never reset an existing user.'

    def add_arguments(self, parser):
        parser.add_argument('--output', required=True, help='Private local directory for initial credentials/QR.')

    def handle(self, *args, **options):
        username = os.environ.get('EDITOR_USERNAME', 'editor')
        password = os.environ.get('EDITOR_PASSWORD')
        if not password or len(password) < 14:
            raise CommandError('Set EDITOR_PASSWORD to at least 14 characters.')
        validate_password(password)
        output = Path(options['output']).resolve()
        output.mkdir(parents=True, exist_ok=True, mode=0o700)
        if get_user_model().objects.filter(username=username).exists():
            self.stdout.write('Editor already exists; credentials and OTP devices were preserved.')
            return
        with transaction.atomic():
            editor = get_user_model().objects.create_user(username, os.environ.get('EDITOR_EMAIL', ''), password, is_staff=True)
            group, _ = Group.objects.get_or_create(name='Редактор сайта')
            group.permissions.set(Permission.objects.filter(
                content_type__app_label='content', content_type__model__in=['project', 'projectphoto', 'rate', 'ratedocument'],
                codename__regex=r'^(add|change|delete|view)_',
            ))
            editor.groups.add(group)
            totp = TOTPDevice.objects.create(user=editor, name='Приложение-аутентификатор', confirmed=True)
            recovery = StaticDevice.objects.create(user=editor, name='Резервный код', confirmed=True)
            codes = [secrets.token_hex(8) for _ in range(10)]
            StaticToken.objects.bulk_create([StaticToken(device=recovery, token=code) for code in codes])
            buffer = BytesIO()
            qrcode.make(totp.config_url, image_factory=qrcode.image.svg.SvgPathImage).save(buffer)
            qr = buffer.getvalue().decode().split('?>', 1)[-1]
            url = os.environ['CMS_URL'].rstrip('/') + '/admin/'
            body = f'''<!doctype html><html lang="ru"><meta charset="utf-8"><title>Arcadian — первый вход</title>
<style>body{{font:18px system-ui;max-width:740px;margin:48px auto;padding:20px;color:#18212a}}svg{{width:260px;height:260px}}code{{word-break:break-all}}li{{margin:12px 0}}</style>
<h1>Arcadian — первый вход</h1><p>Это приватный файл. Не загружайте его на сайт.</p>
<ol><li>Добавьте QR-код в приложение-аутентификатор.</li><li>Откройте <a href="{html.escape(url)}">админку</a>.
Логин: <code>{html.escape(username)}</code>. Пароль: <code>{html.escape(password)}</code>.</li>
<li>Введите шестизначный код из приложения.</li></ol>
{qr}<p>Резервные коды (каждый действует один раз):</p><pre>{chr(10).join(codes)}</pre>
<p>Сохраните пароль и резервные коды в менеджере паролей. Удалите этот файл после настройки.</p></html>'''
            with (output / 'first-login.html').open('x') as file:
                os.chmod(file.name, 0o600)
                file.write(body)
            with (output / 'local-login.txt').open('w') as file:
                os.chmod(file.name, 0o600)
                file.write(f'Админка: {url}\nЛогин: {username}\nПароль: {password}\n2FA и резервные коды: first-login.html\n')
        self.stdout.write('Editor created. Private onboarding saved; no credentials printed.')
