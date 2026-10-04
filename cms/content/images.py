from io import BytesIO
import fcntl
import os
import tempfile
import uuid
import warnings
from PIL import Image, ImageCms, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

register_heif_opener()
Image.MAX_IMAGE_PIXELS = 50_000_000
MAX_BYTES = 50 * 1024 * 1024


def prepare_image(upload):
    # Pillow's full-resolution buffers must fit one container even when both
    # Gunicorn workers receive a batch at once. The lock is shared across them.
    lock_path = os.path.join(tempfile.gettempdir(), 'arcadian-image-processing.lock')
    with open(lock_path, 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return _prepare_image(upload)


def _prepare_image(upload):
    if upload.size > MAX_BYTES:
        raise ValidationError('Одна фотография — не более 50 МБ.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            upload.seek(0)
            with Image.open(upload) as source:
                # MPO is a still-photo JPEG container (often a primary photo
                # plus an auxiliary image). Pillow calls it "animated" too.
                still_containers = {'MPO', 'HEIF', 'TIFF'}
                if source.format not in {'JPEG', 'PNG', 'WEBP', 'AVIF', 'BMP'} | still_containers:
                    raise ValidationError(f'Формат {source.format or "не определён"} не поддерживается. Выберите фотографию JPEG, HEIC, PNG, TIFF, WebP или AVIF.')
                if getattr(source, 'is_animated', False) and source.format not in still_containers:
                    raise ValidationError('Этот файл содержит анимацию. Выберите неподвижную фотографию.')
                if max(source.size) > 16384:
                    raise ValidationError('Размер фотографии превышает 16384 пикселя по стороне.')
                source.load()
                ImageOps.exif_transpose(source, in_place=True)
                profile = source.info.get('icc_profile')
                if profile:
                    try:
                        clean = ImageCms.profileToProfile(source, ImageCms.ImageCmsProfile(BytesIO(profile)),
                            ImageCms.createProfile('sRGB'), outputMode='RGB')
                    except (ImageCms.PyCMSError, ValueError, OSError):
                        clean = source.convert('RGB')
                else:
                    clean = source.convert('RGB')
                # Preserve all pixels in the viewing image. Clear metadata
                # explicitly; only the two previews are resized/cropped.
                clean.info.clear()
                # The independent RGB copy no longer needs the decoder's full
                # source buffer. Release it before WebP allocates its buffers.
                source.close()
                variants = {}
                for name, size in [('large', None), ('card', (960, 720)), ('small', (480, 360))]:
                    variant = clean if size is None else ImageOps.fit(clean, size, method=Image.Resampling.LANCZOS)
                    buffer = BytesIO()
                    variant.save(buffer, format='WEBP', quality=95 if name == 'large' else 82, method=4)
                    variants[name] = buffer.getvalue()
                return {'width': clean.width, 'height': clean.height, 'variants': variants}
    except ValidationError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValidationError('Фотография превышает 50 млн пикселей.')
    except (UnidentifiedImageError, OSError, ValueError):
        raise ValidationError('Файл повреждён или не является допустимой фотографией.')


def store_image(photo, prepared):
    # Versions are immutable; old variants remain available for recovery/history.
    version = uuid.uuid4()
    for name, data in prepared['variants'].items():
        key = f'photos/{photo.id}/{version}/{name}.webp'
        setattr(photo, name, default_storage.save(key, ContentFile(data)))
    photo.width, photo.height = prepared['width'], prepared['height']
