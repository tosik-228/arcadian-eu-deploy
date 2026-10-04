from django import forms
from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet
from .images import prepare_image
from .models import Project, ProjectPhoto, Rate, Status


class MultipleUpload(forms.ClearableFileInput):
    allow_multiple_selected = True


class PhotographBatch(forms.FileField):
    widget = MultipleUpload

    def clean(self, data, initial=None):
        if not data:
            return []
        values = data if isinstance(data, (list, tuple)) else [data]
        if len(values) > 10:
            raise ValidationError('За один раз загрузите не более 10 фотографий.')
        if sum(value.size for value in values) > 60 * 1024 * 1024:
            raise ValidationError('Суммарный размер одной загрузки — не более 60 МБ. Разделите фотографии на несколько загрузок.')
        return [prepare_image(super(PhotographBatch, self).clean(value, initial)) for value in values]


class RevisionForm(forms.ModelForm):
    saved_revision = forms.IntegerField(widget=forms.HiddenInput, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        current = type(self.instance).objects.filter(pk=self.instance.pk).values_list('revision', flat=True).first()
        self.initial['saved_revision'] = current if current is not None else self.instance.revision

    def clean(self):
        cleaned = super().clean()
        if not self.instance._state.adding:
            expected = cleaned.get('saved_revision')
            # The admin POST is inside a transaction; retain the lock through save.
            current = type(self.instance).objects.select_for_update().get(pk=self.instance.pk)
            if expected is None or current.revision != expected:
                raise ValidationError('Эта запись уже изменена. Обновите страницу перед сохранением.')
            self.instance._expected_revision = expected
        return cleaned


class ProjectForm(RevisionForm):
    photographs = PhotographBatch(label='Добавить фотографии', required=False,
        help_text='До 10 файлов и 60 МБ за раз; до 20 МБ и 24 млн пикселей каждый. JPEG, PNG, WebP, AVIF, HEIC. Геометки удаляются автоматически.')

    class Meta:
        model = Project
        fields = '__all__'

    def clean(self):
        self.instance._allow_pending_photos = not getattr(self, 'history_restore', False)
        cleaned = super().clean()
        self.instance._batch_photographs = cleaned.get('photographs', [])
        return cleaned


class PhotoForm(forms.ModelForm):
    upload = forms.FileField(label='Заменить / добавить', required=False)

    class Meta:
        model = ProjectPhoto
        fields = ['description', 'sort']

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('upload'):
            self.prepared = prepare_image(cleaned['upload'])
        elif self.instance._state.adding and (cleaned.get('description') or cleaned.get('sort')):
            raise ValidationError('Добавьте файл фотографии.')
        return cleaned


class PhotoFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        count = len(getattr(self.instance, '_batch_photographs', []))
        for form in self.forms:
            if form.cleaned_data and not form.cleaned_data.get('DELETE'):
                if not form.instance._state.adding or hasattr(form, 'prepared'):
                    count += 1
        if count > 60:
            raise ValidationError('В одной работе — не более 60 фотографий.')
        if self.instance.status == Status.PUBLISHED and count == 0:
            raise ValidationError('Для публикации оставьте хотя бы одну фотографию.')

    def save_new(self, form, commit=True):
        from .images import store_image
        if hasattr(form, 'prepared'):
            store_image(form.instance, form.prepared)
        return super().save_new(form, commit)

    def save_existing(self, form, instance, commit=True):
        from .images import store_image
        if hasattr(form, 'prepared'):
            store_image(instance, form.prepared)
        return super().save_existing(form, instance, commit)


class RateForm(RevisionForm):
    class Meta:
        model = Rate
        fields = '__all__'
