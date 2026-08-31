import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / '.env')

_version_file = BASE_DIR / 'VERSION'
if not _version_file.exists():
    raise RuntimeError(
        f"Arquivo VERSION ausente em {_version_file}. É a fonte de verdade da versão da aplicação "
        f"(ver docs/superpowers/specs/2026-08-28-fase8-versionamento-limpeza-design.md)."
    )
APP_VERSION = _version_file.read_text().strip()

GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'change-me')
ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')
    if host.strip()
]

INSTALLED_APPS = [
    'unfold',
    'unfold.contrib.filters',
    'unfold.contrib.forms',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
    'allauth.socialaccount.providers.microsoft',
    'django_htmx',
    'django_cotton',
    'crispy_forms',
    'crispy_tailwind',
    'django_tables2',
    'django_filters',
    'procrastinate.contrib.django',
    'apps.core',
    'apps.simulacao',
    'apps.integracoes',
    'apps.gestao',
]

AUTH_USER_MODEL = 'core.User'

SITE_ID = 1

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

ACCOUNT_ADAPTER = 'apps.core.adapters.NoSignupAccountAdapter'
SOCIALACCOUNT_ADAPTER = 'apps.core.adapters.AssociateByEmailSocialAdapter'
ACCOUNT_LOGIN_METHODS = {'username', 'email'}
ACCOUNT_SIGNUP_FIELDS = ['email*', 'username*', 'password1*', 'password2*']
ACCOUNT_EMAIL_VERIFICATION = 'none'
ACCOUNT_UNIQUE_EMAIL = True
SOCIALACCOUNT_AUTO_SIGNUP = False
# Clicar em "Entrar com Google/Microsoft" redireciona direto ao provedor, sem a
# tela intermediária de confirmação do allauth. Troca a proteção contra
# login-CSRF do allauth pela UX esperada; o parâmetro `state` do OAuth continua
# protegendo o callback.
SOCIALACCOUNT_LOGIN_ON_GET = True
SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'APPS': [{
            'client_id': os.getenv('GOOGLE_CLIENT_ID', ''),
            'secret': os.getenv('GOOGLE_CLIENT_SECRET', ''),
            'key': '',
        }],
        'SCOPE': ['profile', 'email'],
    },
    'microsoft': {
        'APPS': [{
            'client_id': os.getenv('MICROSOFT_CLIENT_ID', ''),
            'secret': os.getenv('MICROSOFT_CLIENT_SECRET', ''),
            'settings': {'tenant': os.getenv('MICROSOFT_TENANT', 'common')},
        }],
    },
}

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
DEFAULT_FROM_EMAIL = os.getenv('DJANGO_DEFAULT_FROM_EMAIL', 'nao-responda@transbordo.local')

LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/accounts/login/'

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'allauth.account.middleware.AccountMiddleware',
    'django_htmx.middleware.HtmxMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'apps.core.middleware.CooperativaScopeMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.core.context_processors.app_version',
                'apps.gestao.context_processors.menu',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# DJANGO_DB_* foi mantido distinto de DB_* (do antigo stack Streamlit/SQLAlchemy,
# removido no Cutover/Fase 11) para os dois nunca colidirem enquanto conviviam no
# mesmo .env — separação preservada como histórico, ver docs/decisions/0002.
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DJANGO_DB_NAME', 'transbordo'),
        'USER': os.getenv('DJANGO_DB_USER', 'transbordo'),
        'PASSWORD': os.getenv('DJANGO_DB_PASSWORD', ''),
        'HOST': os.getenv('DJANGO_DB_HOST', 'localhost'),
        'PORT': os.getenv('DJANGO_DB_PORT', '5432'),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'America/Sao_Paulo'
USE_I18N = True
USE_TZ = True
USE_THOUSAND_SEPARATOR = True

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

CRISPY_ALLOWED_TEMPLATE_PACKS = ['tailwind']
CRISPY_TEMPLATE_PACK = 'tailwind'

DJANGO_TABLES2_TEMPLATE = 'django_tables2/tailwind.html'

UNFOLD = {
    'SITE_TITLE': 'Transbordo — Admin',
    'SITE_HEADER': 'Transbordo — Admin',
    'COLORS': {
        'primary': {
            '500': '31 48 96',
            '600': '31 48 96',
            '700': '42 64 128',
        },
    },
}
