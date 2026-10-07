import hashlib
import os
import shutil
from pathlib import Path
import time
from functools import lru_cache
from django.conf import settings
from django.core.files.storage import default_storage
from django.db import connection
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.views.decorators.http import require_safe
from .models import Project, ProjectPhoto, Rate, RateDocument, Status, Category, DocumentCategory
from .documents import TRANSLATION_LANGUAGES

PUBLIC_FIELDS = ['id', 'title', 'description', 'title_pl', 'title_nl',
                 'description_pl', 'description_nl', 'category']
PAGE_SIZE = 12


def paginate(request, queryset, categories=Category.values):
    category = request.GET.get('category', '')
    if category:
        if category not in categories:
            return None
        queryset = queryset.filter(category=category)
    try:
        page = int(request.GET.get('page', '1'))
        if page < 1 or page > 1000:
            return None
    except (ValueError, TypeError):
        return None
    start = (page - 1) * PAGE_SIZE
    rows = list(queryset[start:start + PAGE_SIZE + 1])
    return rows[:PAGE_SIZE], len(rows) > PAGE_SIZE


def fields(obj, names):
    return {name: getattr(obj, name) for name in names}


@require_safe
def projects(request):
    result = paginate(request, Project.objects.filter(status=Status.PUBLISHED).prefetch_related('photos'))
    if result is None:
        return JsonResponse({'error': 'Invalid page or category.'}, status=400)
    rows, has_more = result
    data = []
    for obj in rows:
        row = fields(obj, PUBLIC_FIELDS + ['location', 'completed_year'])
        row['photos'] = [fields(photo, ['id', 'description', 'width', 'height']) for photo in obj.photos.all()]
        data.append(row)
    return JsonResponse({'data': data, 'has_more': has_more})


@require_safe
def rates(request):
    result = paginate(request, Rate.objects.filter(status=Status.PUBLISHED, visibility=Rate.Visibility.PUBLIC))
    if result is None:
        return JsonResponse({'error': 'Invalid page or category.'}, status=400)
    rows, has_more = result
    names = PUBLIC_FIELDS + ['worker_type', 'amount_from', 'amount_to', 'unit', 'basis', 'own_vehicle', 'own_tools']
    return JsonResponse({'data': [fields(obj, names) for obj in rows], 'has_more': has_more})


@require_safe
def documents(request):
    result = paginate(request, RateDocument.objects.filter(status=Status.PUBLISHED, visibility=Rate.Visibility.PUBLIC), DocumentCategory.values)
    if result is None:
        return JsonResponse({'error': 'Invalid page or category.'}, status=400)
    rows, has_more = result
    names = PUBLIC_FIELDS + ['effective_date', 'page_count', 'file_bytes']
    data = []
    for obj in rows:
        row = fields(obj, names)
        row['primary_language'] = 'en'
        row['translations'] = [{'language': language, 'page_count': obj.translations[language]['page_count'],
            'file_bytes': obj.translations[language]['file_bytes']} for language in TRANSLATION_LANGUAGES
            if language in obj.translations]
        data.append(row)
    return JsonResponse({'data': data, 'has_more': has_more})


@require_safe
def document(request, document_id):
    obj = RateDocument.objects.filter(pk=document_id).first()
    if obj is None or not obj.file_key:
        raise Http404
    user = request.user
    editor = user.is_authenticated and user.is_verified() and user.has_perm('content.view_ratedocument')
    if 'revision' in request.GET:
        if not editor:
            raise Http404
        try:
            revision = int(request.GET['revision'])
        except (ValueError, TypeError):
            raise Http404
        obj = obj.history.filter(history_id=revision).first()
        if obj is None or not obj.file_key:
            raise Http404
    if (obj.status != Status.PUBLISHED or obj.visibility != Rate.Visibility.PUBLIC) and not editor:
        raise Http404
    language = request.GET.get('language', 'en')
    if language == 'en':
        key, digest = obj.file_key, obj.file_sha256
    elif language in TRANSLATION_LANGUAGES and language in obj.translations:
        metadata = obj.translations[language]
        key, digest = metadata['file_key'], metadata['file_sha256']
    else:
        raise Http404
    try:
        body = default_storage.open(key, 'rb')
    except FileNotFoundError:
        raise Http404
    response = FileResponse(body, content_type='application/pdf',
        as_attachment=request.GET.get('download') == '1', filename=f'arcadian-{obj.category}-{obj.id}-{language}.pdf')
    response['ETag'] = '"' + digest + '"'
    return response


@require_safe
def image(request, image_id):
    size = request.GET.get('size', 'large')
    if size not in {'small', 'card', 'large'}:
        raise Http404
    photo = ProjectPhoto.objects.select_related('project').filter(pk=image_id).first()
    if photo is None:
        raise Http404
    user = request.user
    editor = user.is_authenticated and user.is_verified() and user.has_perm('content.view_project')
    if photo.project.status != Status.PUBLISHED and not editor:
        raise Http404
    key = getattr(photo, size)
    try:
        body = default_storage.open(key, 'rb')
    except FileNotFoundError:
        raise Http404
    response = FileResponse(body, content_type='image/webp')
    response['Content-Disposition'] = 'inline; filename="photo.webp"'
    response['ETag'] = '"' + hashlib.sha256(key.encode()).hexdigest() + '"'
    return response


@require_safe
def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
        if settings.PRODUCTION:
            storage_health(int(time.monotonic() // 60))
        return JsonResponse({'status': 'ready'})
    except Exception:
        return HttpResponse('Not ready', status=503, content_type='text/plain')


@lru_cache(maxsize=2)
def storage_health(minute):
    if settings.MEDIA_BACKEND == 'filesystem':
        root = Path(settings.MEDIA_ROOT)
        if not root.is_dir() or not os.access(root, os.R_OK | os.W_OK):
            raise OSError('Persistent media storage is unavailable.')
        if shutil.disk_usage(root).free < 128 * 1024 * 1024:
            raise OSError('Media storage needs free disk space.')
        return True
    default_storage.connection.meta.client.head_bucket(Bucket=settings.STORAGES['default']['OPTIONS']['bucket_name'])
    return True
