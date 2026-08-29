from .base import *  # noqa: F401,F403

DEBUG = False

# TLS termina no Apache (proxy reverso) na frente da aplicação — o Django nunca
# fala HTTPS diretamente. Sem SECURE_PROXY_SSL_HEADER, request.is_secure()
# sempre volta False atrás do proxy.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

CSRF_TRUSTED_ORIGINS = [f'https://{host}' for host in ALLOWED_HOSTS if host]  # noqa: F405

# gunicorn serve os estáticos (comprimidos, hasheados) via WhiteNoise — sem
# Alias no Apache, sem volume. `collectstatic` roda no build do Docker.
MIDDLEWARE = (  # noqa: F405
    MIDDLEWARE[:1]  # noqa: F405
    + ['whitenoise.middleware.WhiteNoiseMiddleware']
    + MIDDLEWARE[1:]  # noqa: F405
)
STORAGES = {  # noqa: F405
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'},
}

import os  # noqa: E402

if os.getenv('DJANGO_EMAIL_HOST'):
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'  # noqa: F405
    EMAIL_HOST = os.getenv('DJANGO_EMAIL_HOST')
    EMAIL_PORT = int(os.getenv('DJANGO_EMAIL_PORT', '587'))
    EMAIL_HOST_USER = os.getenv('DJANGO_EMAIL_HOST_USER', '')
    EMAIL_HOST_PASSWORD = os.getenv('DJANGO_EMAIL_HOST_PASSWORD', '')
    EMAIL_USE_TLS = os.getenv('DJANGO_EMAIL_USE_TLS', 'true').lower() == 'true'
