from io import BytesIO
import fcntl
import os
import tempfile
import uuid
import warnings
from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

register_heif_opener()
Image.MAX_IMAGE_PIXELS = 24_000_000
MAX_BYTES = 20 * 1024 * 1024


def prepare_image(upload):
    # Pillow's full-resolution buffers must fit one container even when both
    # Gunicorn workers receive a batch at once. The lock is shared across them.
    lock_path = os.path.join(tempfile.gettempdir(), 'arcadian-image-processing.lock')
    with open(lock_path, 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return _prepare_image(upload)


def _prepare_image(upload):
    if upload.size > MAX_BYTES:
        raise ValidationError('Одна фотография — не более 20 МБ.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            upload.seek(0)
            with Image.open(upload) as source:
                if source.format not in {'JPEG', 'PNG', 'WEBP', 'AVIF', 'HEIF'} or getattr(source, 'is_animated', False):
                    raise ValidationError('Принимаются фотографии JPEG, PNG, WebP, AVIF и HEIC; без анимации.')
                if max(source.size) > 8192:
                    raise ValidationError('Размер фотографии — не более 8192 пикселей по стороне.')
                source.load()
                image = ImageOps.exif_transpose(source).convert('RGB')
                image.thumbnail((2400, 2400), Image.Resampling.LANCZOS)
                # A new image has no source EXIF, GPS, XMP or filename metadata.
                clean = Image.new('RGB', image.size)
                clean.paste(image)
                variants = {}
                for name, size in [('large', None), ('card', (960, 720)), ('small', (480, 360))]:
                    variant = clean if size is None else ImageOps.fit(clean, size, method=Image.Resampling.LANCZOS)
                    buffer = BytesIO()
                    variant.save(buffer, format='WEBP', quality=86 if name == 'large' else 82, method=4)
                    variants[name] = buffer.getvalue()
                return {'width': clean.width, 'height': clean.height, 'variants': variants}
    except ValidationError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValidationError('Фотография превышает 24 млн пикселей. Уменьшите размер перед загрузкой.')
    except (UnidentifiedImageError, OSError, ValueError):
        raise ValidationError('Файл повреждён или не является допустимой фотографией.')


def store_image(photo, prepared):
    # Versions are immutable; old variants remain available for recovery/history.
    version = uuid.uuid4()
    for name, data in prepared['variants'].items():
        key = f'photos/{photo.id}/{version}/{name}.webp'
        setattr(photo, name, default_storage.save(key, ContentFile(data)))
    photo.width, photo.height = prepared['width'], prepared['height']
