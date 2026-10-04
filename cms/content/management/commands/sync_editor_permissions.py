from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = 'Add current content permissions to the existing editor group without changing users or authentication.'

    @transaction.atomic
    def handle(self, *args, **options):
        group = Group.objects.filter(name='Редактор сайта').first()
        if group is None:
            self.stdout.write('No existing editor group; bootstrap_editor will configure new editors.')
            return
        permissions = Permission.objects.filter(content_type__app_label='content',
            content_type__model__in=['project', 'projectphoto', 'rate', 'ratedocument'],
            codename__regex=r'^(add|change|delete|view)_')
        group.permissions.add(*permissions)
        self.stdout.write('Content editor permissions updated. Users, passwords and OTP devices were preserved.')
