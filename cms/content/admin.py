from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.db import transaction
from simple_history.admin import SimpleHistoryAdmin
from .forms import ProjectForm, PhotoForm, PhotoFormSet, RateForm, RateDocumentForm
from .images import store_image
from .documents import store_document
from .models import Project, ProjectPhoto, Rate, RateDocument

TRANSLATIONS = ('Переводы (необязательно)', {
    'fields': ('title_pl', 'description_pl', 'title_nl', 'description_nl'),
    'classes': ('collapse',),
    'description': 'Если перевод пуст, сайт показывает общий текст. Автоматического перевода нет.',
})


class PhotoInline(admin.TabularInline):
    model = ProjectPhoto
    form = PhotoForm
    formset = PhotoFormSet
    fields = ('preview', 'upload', 'description', 'sort')
    readonly_fields = ('preview',)
    extra = 0
    max_num = 60

    @admin.display(description='Фотография')
    def preview(self, obj):
        if not obj or not obj.small:
            return '—'
        return format_html('<img src="{}?size=small" width="160" height="120" alt="{}">',
                           reverse('content_image', args=[obj.id]), obj.description)


class ContentAdmin(SimpleHistoryAdmin):
    @transaction.atomic
    def history_form_view(self, request, *args, **kwargs):
        return super().history_form_view(request, *args, **kwargs)


@admin.register(Project)
class ProjectAdmin(ContentAdmin):
    change_form_template = 'admin/content/project/change_form.html'
    form = ProjectForm
    inlines = [PhotoInline]
    list_display = ('title', 'category', 'status', 'photo_count', 'updated_at')
    list_filter = ('status', 'category')
    search_fields = ('title', 'description', 'location')
    actions = None
    readonly_fields = ('updated_at',)
    fieldsets = [
        (None, {'fields': ('saved_revision', 'title', 'description', 'category', 'status', 'photographs')}),
        ('Детали', {'fields': ('location', 'completed_year', 'sort', 'updated_at'), 'classes': ('collapse',)}),
        TRANSLATIONS,
    ]

    @admin.display(description='Фото')
    def photo_count(self, obj):
        return obj.photos.count()

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if '/history/' in request.path:
            form.history_restore = True
            form.base_fields['photographs'].disabled = True
            form.base_fields['photographs'].help_text = 'История восстанавливает текст и состояние. Состав фотографий меняется в карточке работы.'
        return form

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        project = form.instance
        order = project.photos.order_by('-sort').values_list('sort', flat=True).first() or 0
        for index, prepared in enumerate(form.cleaned_data.get('photographs', []), start=1):
            photo = ProjectPhoto(project=project, sort=order + index)
            store_image(photo, prepared)
            photo.save()
        project._allow_pending_photos = False
        project.full_clean()


@admin.register(Rate)
class RateAdmin(ContentAdmin):
    def get_model_perms(self, request):
        # Keep existing amount records and direct history links available.
        # New prices are managed through PDF documents on the dashboard.
        return {}

    form = RateForm
    list_display = ('title', 'worker_type', 'amount_from', 'unit', 'visibility', 'status', 'updated_at')
    list_filter = ('worker_type', 'visibility', 'status', 'category')
    search_fields = ('title', 'description')
    actions = None
    readonly_fields = ('updated_at',)
    fieldsets = [
        (None, {'fields': ('saved_revision', 'title', 'description', 'category', 'worker_type')}),
        ('Сумма и условия', {'fields': ('amount_from', 'amount_to', 'unit', 'basis', 'own_vehicle', 'own_tools')}),
        ('Публикация', {'fields': ('visibility', 'status', 'sort', 'updated_at')}),
        TRANSLATIONS,
    ]


@admin.register(RateDocument)
class RateDocumentAdmin(ContentAdmin):
    form = RateDocumentForm
    list_display = ('title', 'category', 'status', 'visibility', 'page_count', 'updated_at')
    list_filter = ('category', 'status', 'visibility')
    search_fields = ('title', 'description')
    actions = None
    readonly_fields = ('current_document', 'updated_at')
    fieldsets = [
        (None, {'fields': ('saved_revision', 'title', 'category', 'upload', 'current_document', 'description', 'status')}),
        ('Детали', {'fields': ('visibility', 'effective_date', 'sort', 'updated_at'), 'classes': ('collapse',)}),
        TRANSLATIONS,
    ]

    @admin.display(description='Текущий PDF')
    def current_document(self, obj):
        if not obj or not obj.file_key:
            return 'PDF ещё не загружен.'
        url = reverse('content_document', args=[obj.id])
        history = getattr(obj, '_history', None)
        if history:
            url += f'?revision={history.history_id}'
        download = url + ('&' if history else '?') + 'download=1'
        return format_html('<a href="{}" target="_blank" rel="noopener noreferrer">Просмотреть PDF</a> · <a href="{}">Скачать</a> · {} стр. · {} МБ',
            url, download, obj.page_count, round(obj.file_bytes / (1024 * 1024), 2))

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if '/history/' in request.path:
            form.base_fields['upload'].disabled = True
            form.base_fields['upload'].help_text = 'Восстановление истории возвращает предыдущую версию PDF и её описание.'
        return form

    def save_model(self, request, obj, form, change):
        if hasattr(form, 'prepared'):
            store_document(obj, form.prepared)
        obj._allow_pending_document = False
        super().save_model(request, obj, form, change)
