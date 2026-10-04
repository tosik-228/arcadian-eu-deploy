import hashlib
import fcntl
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

MAX_PDF_BYTES = 25 * 1024 * 1024


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
