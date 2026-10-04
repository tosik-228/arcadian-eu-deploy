from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.db import transaction
from simple_history.admin import SimpleHistoryAdmin
from .forms import ProjectForm, PhotoForm, PhotoFormSet, RateForm
from .images import store_image
from .models import Project, ProjectPhoto, Rate

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
