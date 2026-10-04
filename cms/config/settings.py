import os
import ipaddress
from pathlib import Path
from datetime import timedelta
from django.core.exceptions import ImproperlyConfigured
from botocore.config import Config

BASE_DIR = Path(__file__).resolve().parent.parent
if (BASE_DIR / '.env').exists():
    for line in (BASE_DIR / '.env').read_text().splitlines():
        if line and not line.startswith('#') and '=' in line:
            name, value = line.split('=', 1)
            os.environ.setdefault(name, value)


def required(name):
    value = os.environ.get(name)
    if not value:
        raise ImproperlyConfigured(f'{name} must be configured.')
    return value


ENVIRONMENT = os.environ.get('DJANGO_ENV', 'production')
if ENVIRONMENT not in {'local', 'production'}:
    raise ImproperlyConfigured('DJANGO_ENV must be local or production.')
PRODUCTION = ENVIRONMENT == 'production'
DEPLOYMENT = os.environ.get('CMS_DEPLOYMENT', 'managed' if PRODUCTION else 'local')
if DEPLOYMENT not in {'local', 'managed', 'droplet'} or (PRODUCTION and DEPLOYMENT == 'local'):
    raise ImproperlyConfigured('Production requires an explicit managed or droplet deployment.')
MEDIA_BACKEND = 'filesystem' if DEPLOYMENT in {'local', 'droplet'} else 's3'
TRUSTED_PROXY_NETWORKS = [ipaddress.ip_network(value.strip()) for value in
    os.environ.get('CMS_TRUSTED_PROXY_NETWORKS', '').split(',') if value.strip()]
SECRET_KEY = required('CMS_SECRET')
if PRODUCTION and (len(SECRET_KEY) < 64 or not required('CMS_URL').startswith('https://')):
    raise ImproperlyConfigured('Production requires a strong secret and HTTPS CMS_URL.')
DEBUG = False
ALLOWED_HOSTS = required('CMS_ALLOWED_HOSTS').split(',')
INSTALLED_APPS = [
    'content.apps.ArcadianAdminConfig', 'django.contrib.auth',
    'django.contrib.contenttypes', 'django.contrib.sessions',
    'django.contrib.messages', 'django.contrib.staticfiles',
    'django_otp', 'django_otp.plugins.otp_totp', 'django_otp.plugins.otp_static',
    'simple_history', 'corsheaders', 'axes', 'content.apps.ContentConfig',
]
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django_otp.middleware.OTPMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'simple_history.middleware.HistoryRequestMiddleware',
    'content.middleware.ResponsePolicyMiddleware',
    'axes.middleware.AxesMiddleware',
]
ROOT_URLCONF = 'config.urls'
TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [BASE_DIR / 'templates'], 'APP_DIRS': True,
    'OPTIONS': {'context_processors': [
        'django.template.context_processors.request',
        'django.contrib.auth.context_processors.auth',
        'django.contrib.messages.context_processors.messages',
    ]},
}]
WSGI_APPLICATION = 'config.wsgi.application'
DATABASES = {'default': {
    'ENGINE': 'django.db.backends.postgresql',
    'NAME': required('DB_NAME'), 'USER': required('DB_USER'),
    'PASSWORD': required('DB_PASSWORD'), 'HOST': required('DB_HOST'),
    'PORT': os.environ.get('DB_PORT', '5432'),
    'CONN_MAX_AGE': 60, 'CONN_HEALTH_CHECKS': True,
    'OPTIONS': {'connect_timeout': 5},
}}
if PRODUCTION and DEPLOYMENT == 'droplet':
    if DATABASES['default']['HOST'] != '/run/arcadian-postgres':
        raise ImproperlyConfigured('Droplet PostgreSQL must use the private /run/arcadian-postgres Unix socket.')
elif PRODUCTION:
    DATABASES['default']['OPTIONS'].update({
        'sslmode': 'verify-full', 'sslrootcert': required('DB_CA_FILE'),
    })
AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesStandaloneBackend',
    'django.contrib.auth.backends.ModelBackend',
]
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.Argon2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
]
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 14}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]
LANGUAGE_CODE = 'ru'
TIME_ZONE = 'Europe/Brussels'
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / '.static'
MEDIA_ROOT = Path(os.environ.get('MEDIA_ROOT', BASE_DIR / '.media'))
if PRODUCTION and DEPLOYMENT == 'droplet' and MEDIA_ROOT != Path('/data/media'):
    raise ImproperlyConfigured('Droplet media requires the persistent /data/media volume.')
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'},
}
if MEDIA_BACKEND == 's3':
    if not required('S3_ENDPOINT').startswith('https://'):
        raise ImproperlyConfigured('Production media storage must use HTTPS.')
    STORAGES['default'] = {
        'BACKEND': 'storages.backends.s3.S3Storage',
        'OPTIONS': {
            'access_key': required('S3_ACCESS_KEY'), 'secret_key': required('S3_SECRET_KEY'),
            'bucket_name': required('S3_BUCKET'), 'endpoint_url': required('S3_ENDPOINT'),
            'region_name': required('S3_REGION'), 'default_acl': None,
            'file_overwrite': False, 'querystring_auth': True,
            'object_parameters': {'CacheControl': 'private, no-store'},
            'client_config': Config(connect_timeout=3, read_timeout=5, retries={'max_attempts': 1}),
        },
    }
DATA_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024
FILE_UPLOAD_TEMP_DIR = os.environ.get('UPLOAD_TEMP_DIR')
DATA_UPLOAD_MAX_NUMBER_FILES = 10
DATA_UPLOAD_MAX_NUMBER_FIELDS = 1000
SESSION_COOKIE_NAME = 'arcadian_session'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = PRODUCTION
SESSION_COOKIE_SAMESITE = 'Strict'
SESSION_COOKIE_AGE = 8 * 60 * 60
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
CSRF_COOKIE_SECURE = PRODUCTION
CSRF_COOKIE_SAMESITE = 'Strict'
CSRF_TRUSTED_ORIGINS = required('CMS_URL').rstrip('/').split(',')
SECURE_SSL_REDIRECT = PRODUCTION
SECURE_REDIRECT_EXEMPT = [r'^healthz/$']
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https') if PRODUCTION else None
SECURE_HSTS_SECONDS = 31536000 if PRODUCTION else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = PRODUCTION
SECURE_HSTS_PRELOAD = PRODUCTION
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'
X_FRAME_OPTIONS = 'DENY'
CORS_ALLOWED_ORIGINS = required('SITE_ORIGINS').split(',')
CORS_ALLOW_CREDENTIALS = False
CORS_URLS_REGEX = r'^/api/'
CORS_ALLOW_METHODS = ['GET', 'HEAD', 'OPTIONS']
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = timedelta(minutes=15)
AXES_LOCKOUT_PARAMETERS = ['username', 'ip_address']
AXES_RESET_ON_SUCCESS = True
AXES_CLIENT_IP_CALLABLE = 'content.middleware.client_ip'
AXES_LOCKOUT_TEMPLATE = 'admin/locked.html'
OTP_TOTP_ISSUER = 'Arcadian'
OTP_TOTP_THROTTLE_FACTOR = 2
OTP_STATIC_THROTTLE_FACTOR = 2
SIMPLE_HISTORY_REVERT_DISABLED = False
LOGGING = {
    'version': 1, 'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'root': {'handlers': ['console'], 'level': 'WARNING'},
    'loggers': {'django.server': {'handlers': ['console'], 'level': 'INFO', 'propagate': False}},
}
