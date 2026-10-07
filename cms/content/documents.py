import hashlib
import fcntl
import json
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

MAX_PDF_BYTES = 25 * 1024 * 1024
TRANSLATION_LANGUAGES = ('ru', 'pl', 'nl')


def validate_translations(document):
    translations = document.translations
    if not isinstance(translations, dict) or set(translations) - set(TRANSLATION_LANGUAGES):
        raise ValidationError('Дополнительные PDF: допустимы только RU, PL и NL.')
    for metadata in translations.values():
        if not isinstance(metadata, dict) or set(metadata) != {'file_key', 'file_sha256', 'file_bytes', 'page_count'}:
            raise ValidationError('Некорректные данные перевода PDF.')
        key = metadata['file_key']
        if not isinstance(key, str) or not re.fullmatch(rf'documents/{document.id}/[0-9a-f-]{{36}}\.pdf', key):
            raise ValidationError('Некорректный ключ перевода PDF.')
        if not isinstance(metadata['file_sha256'], str) or not re.fullmatch('[0-9a-f]{64}', metadata['file_sha256']):
            raise ValidationError('Некорректная контрольная сумма перевода PDF.')
        for field, maximum in [('file_bytes', MAX_PDF_BYTES), ('page_count', 200)]:
            if type(metadata[field]) is not int or not 1 <= metadata[field] <= maximum:
                raise ValidationError('Некорректный размер перевода PDF.')


def document_file_keys(document):
    keys = {document.file_key} if document.file_key else set()
    keys.update(metadata['file_key'] for metadata in document.translations.values())
    return keys


def prepare_document(upload):
    # Share the image decoder's lock: a PDF parser and a 48MP decoder must
    # not compete for the same small web container's memory.
    with open(Path(tempfile.gettempdir()) / 'arcadian-image-processing.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return _prepare_document(upload)


def _prepare_document(upload):
    if upload.size > MAX_PDF_BYTES:
        raise ValidationError('PDF — не более 25 МБ.')
    upload.seek(0)
    body = upload.read(MAX_PDF_BYTES + 1)
    if len(body) > MAX_PDF_BYTES or not body.startswith(b'%PDF-'):
        raise ValidationError('Выберите настоящий PDF-документ, не изображение или переименованный файл.')
    # Parsing untrusted PDFs is isolated from the web worker with hard resource
    # limits. Original document bytes are never rewritten or publicly exposed
    # before successful validation and an explicit publication.
    with tempfile.TemporaryDirectory(prefix='arcadian-pdf-') as scratch:
        source = Path(scratch) / 'upload.pdf'
        source.write_bytes(body)
        try:
            process = subprocess.run([sys.executable, str(Path(__file__).with_name('pdf_check.py')), str(source)],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=12, check=False)
            if process.returncode:
                raise ValidationError('Не удалось проверить PDF. Экспортируйте документ заново без пароля и повторите загрузку.')
            result = json.loads(process.stdout)
        except (subprocess.TimeoutExpired, ValueError, OSError) as error:
            raise ValidationError('Не удалось проверить PDF в допустимое время. Экспортируйте документ заново.') from error
    if result.get('error'):
        raise ValidationError(result['error'])
    return {'body': body, 'sha256': hashlib.sha256(body).hexdigest(), 'pages': result['pages']}


def store_document(document, prepared):
    # Each replacement has a different immutable key. History and encrypted
    # backups retain every referenced version, including deleted records.
    key = f'documents/{document.id}/{uuid.uuid4()}.pdf'
    document.file_key = default_storage.save(key, ContentFile(prepared['body']))
    document.file_sha256 = prepared['sha256']
    document.file_bytes = len(prepared['body'])
    document.page_count = prepared['pages']


def store_translation(document, language, prepared):
    if language not in TRANSLATION_LANGUAGES:
        raise ValidationError('Выберите RU, PL или NL для дополнительного PDF.')
    key = f'documents/{document.id}/{uuid.uuid4()}.pdf'
    translations = dict(document.translations)
    translations[language] = {
        'file_key': default_storage.save(key, ContentFile(prepared['body'])),
        'file_sha256': prepared['sha256'], 'file_bytes': len(prepared['body']), 'page_count': prepared['pages'],
    }
    document.translations = translations
