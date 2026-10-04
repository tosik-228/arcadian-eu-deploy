from django.apps import AppConfig
from django.contrib.admin.apps import AdminConfig


class ArcadianAdminConfig(AdminConfig):
    default_site = 'content.admin_site.ArcadianAdminSite'


class ContentConfig(AppConfig):
    name = 'content'
    verbose_name = 'Содержание сайта'
