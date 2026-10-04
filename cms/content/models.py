import uuid
from datetime import date
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models import Q
from simple_history.models import HistoricalRecords


def validate_completed_year(value):
    if value > date.today().year + 1:
        raise ValidationError("Год не может быть позже следующего календарного года.")


class Category(models.TextChoices):
    FINISHING = 'finishing', 'Отделка и реновация'
    FACADES = 'facades', 'Фасады'
    ELECTRICAL = 'electrical', 'Электрика'


class Status(models.TextChoices):
    DRAFT = 'draft', 'Черновик'
    PUBLISHED = 'published', 'Опубликовано'
    ARCHIVED = 'archived', 'Архив'


class ContentRecord(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField('Название (EN или общий текст)', max_length=180, blank=True)
    description = models.TextField('Описание (EN или общий текст)', blank=True, max_length=6000)
    title_pl = models.CharField('Название PL', max_length=180, blank=True)
    title_nl = models.CharField('Название NL', max_length=180, blank=True)
    description_pl = models.TextField('Описание PL', blank=True, max_length=6000)
    description_nl = models.TextField('Описание NL', blank=True, max_length=6000)
    category = models.CharField('Направление', max_length=20, choices=Category.choices)
    status = models.CharField('Состояние', max_length=12, choices=Status.choices, default=Status.DRAFT)
    sort = models.PositiveIntegerField('Порядок', default=0, help_text='Меньшее число — выше в списке.')
    revision = models.PositiveIntegerField('Версия', default=0, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField('Изменено', auto_now=True)

    class Meta:
        abstract = True
        ordering = ['sort', '-created_at', 'id']

    def __str__(self):
        return self.title or 'Без названия — черновик'

    def clean(self):
        super().clean()
        if self.status == Status.PUBLISHED:
            errors = {}
            if not self.title.strip():
                errors['title'] = 'Для публикации укажите название.'
            if not self.description.strip():
                errors['description'] = 'Для публикации укажите описание.'
            if errors:
                raise ValidationError(errors)

    def save(self, *args, **kwargs):
        # A stale browser form cannot silently overwrite a newer edit.
        with transaction.atomic():
            if not self._state.adding:
                current = type(self).objects.select_for_update().only('revision').get(pk=self.pk)
                expected = getattr(self, '_expected_revision', self.revision)
                if current.revision != expected:
                    raise ValidationError('Запись уже изменена. Обновите страницу и повторите правку.')
                self.revision = current.revision + 1
            else:
                self.revision = 1
            self.full_clean()
            return super().save(*args, **kwargs)


class Project(ContentRecord):
    location = models.CharField('Город / район', max_length=120, blank=True,
                                help_text='Без точного адреса заказчика.')
    completed_year = models.PositiveSmallIntegerField('Год завершения', blank=True, null=True,
        validators=[MinValueValidator(1990), validate_completed_year])
    history = HistoricalRecords()

    class Meta(ContentRecord.Meta):
        verbose_name = 'работа'
        verbose_name_plural = 'Работы'
        indexes = [models.Index(fields=['status', 'category', 'sort'])]

    def clean(self):
        super().clean()
        if self.status == Status.PUBLISHED and not getattr(self, '_allow_pending_photos', False):
            if self._state.adding or not self.photos.exists():
                raise ValidationError('Для публикации добавьте хотя бы одну фотографию.')


class ProjectPhoto(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='photos')
    description = models.CharField('Подпись к фотографии', max_length=240, blank=True)
    sort = models.PositiveIntegerField('Порядок', default=0)
    large = models.CharField(max_length=250, editable=False)
    card = models.CharField(max_length=250, editable=False)
    small = models.CharField(max_length=250, editable=False)
    width = models.PositiveIntegerField(editable=False)
    height = models.PositiveIntegerField(editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = 'фотография'
        verbose_name_plural = 'Фотографии'
        ordering = ['sort', 'created_at', 'id']

    def __str__(self):
        return self.description or 'Фотография'


class Rate(ContentRecord):
    class Worker(models.TextChoices):
        EMPLOYEE = 'employee', 'Работник в штате'
        INDEPENDENT = 'independent', 'Самостоятельный специалист'
        CREW = 'crew', 'Бригада — субподрядчик'

    class Unit(models.TextChoices):
        HOUR_PERSON = 'hour_person', 'Час / человек'
        DAY_PERSON = 'day_person', 'День / человек'
        HOUR_CREW = 'hour_crew', 'Час / бригада'
        M2 = 'm2', 'м²'
        M = 'm', 'Погонный метр'
        UNIT = 'unit', 'Единица'
        FIXED = 'fixed', 'Согласованный объём'

    class Basis(models.TextChoices):
        PAYROLL = 'payroll_gross', 'Зарплата — брутто'
        INVOICE = 'invoice_ex_vat', 'Счёт — без НДС'

    class Visibility(models.TextChoices):
        PRIVATE = 'private', 'Внутренняя'
        PUBLIC = 'public', 'Публичная'

    worker_type = models.CharField('Формат сотрудничества', max_length=20, choices=Worker.choices)
    visibility = models.CharField('Видимость', max_length=10, choices=Visibility.choices, default=Visibility.PRIVATE,
                                 help_text='На сайте: только «Публичная» + «Опубликовано».')
    amount_from = models.DecimalField('Сумма, EUR', max_digits=9, decimal_places=2, null=True, blank=True,
                                     validators=[MinValueValidator(Decimal('0.01'))])
    amount_to = models.DecimalField('До, EUR (если диапазон)', max_digits=9, decimal_places=2,
                                   null=True, blank=True, validators=[MinValueValidator(Decimal('0.01'))])
    unit = models.CharField('Единица расчёта', max_length=20, choices=Unit.choices)
    basis = models.CharField('Основание суммы', max_length=20, choices=Basis.choices)
    own_vehicle = models.BooleanField('Свой автомобиль', default=False)
    own_tools = models.BooleanField('Свой инструмент', default=False)
    history = HistoricalRecords()

    class Meta(ContentRecord.Meta):
        verbose_name = 'расценка'
        verbose_name_plural = 'Расценки'
        indexes = [models.Index(fields=['status', 'visibility', 'category', 'sort'])]
        constraints = [
            models.CheckConstraint(condition=Q(amount_from__isnull=True) | Q(amount_from__gt=0), name='rate_positive_from'),
            models.CheckConstraint(condition=Q(amount_to__isnull=True) | Q(amount_to__gte=models.F('amount_from'), amount_from__isnull=False), name='rate_valid_range'),
            models.CheckConstraint(condition=~Q(status='published', visibility='public') | Q(amount_from__isnull=False), name='rate_public_amount'),
            models.CheckConstraint(condition=(Q(worker_type='employee', basis='payroll_gross') | Q(worker_type__in=['independent', 'crew'], basis='invoice_ex_vat')), name='rate_worker_basis'),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.amount_to is not None and (self.amount_from is None or self.amount_to < self.amount_from):
            errors['amount_to'] = 'Верхняя сумма должна быть не меньше нижней.'
        if self.status == Status.PUBLISHED and self.visibility == self.Visibility.PUBLIC and self.amount_from is None:
            errors['amount_from'] = 'Для публичной расценки укажите сумму.'
        employee = self.worker_type == self.Worker.EMPLOYEE
        if self.worker_type and self.basis and (employee != (self.basis == self.Basis.PAYROLL)):
            errors['basis'] = 'Для штата — зарплата брутто; для специалиста или бригады — счёт без НДС.'
        if errors:
            raise ValidationError(errors)
