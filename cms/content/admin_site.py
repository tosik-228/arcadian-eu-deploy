from django_otp.admin import OTPAdminSite
from django.conf import settings
from django_otp.admin import OTPAdminAuthenticationForm
from django_otp.plugins.otp_totp.models import TOTPDevice
from django_otp.plugins.otp_static.models import StaticDevice


class ArcadianLoginForm(OTPAdminAuthenticationForm):
    def clean_otp(self, user):
        token = self.cleaned_data.get('otp_token', '').strip()
        if user and token and not self.cleaned_data.get('otp_device'):
            model = TOTPDevice if token.isdecimal() and len(token) == 6 else StaticDevice
            devices = list(model.objects.filter(user=user, confirmed=True)[:2])
            if len(devices) == 1:
                self.cleaned_data['otp_device'] = devices[0].persistent_id
        return super().clean_otp(user)


class ArcadianAdminSite(OTPAdminSite):
    login_form = ArcadianLoginForm
    login_template = 'admin/arcadian_login.html'
    site_header = 'Arcadian — содержание сайта'
    site_title = 'Arcadian'
    index_title = 'Работы и расценки'
    site_url = settings.CORS_ALLOWED_ORIGINS[0]
    enable_nav_sidebar = False
