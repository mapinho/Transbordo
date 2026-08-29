from .base import *  # noqa: F401,F403

DEBUG = False

# TLS termina no reverse proxy existente na frente da aplicação (Apache,
# já configurado em comigo.conf/comigo-le-ssl.conf) — o Django nunca fala
# HTTPS diretamente. Sem isso, request.is_secure() sempre volta False
# atrás do proxy. Serviço/whitenoise real ficam para a Fase 10 (Deploy).
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

CSRF_TRUSTED_ORIGINS = [f'https://{host}' for host in ALLOWED_HOSTS if host]  # noqa: F405

import os  # noqa: E402

if os.getenv('DJANGO_EMAIL_HOST'):
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'  # noqa: F405
    EMAIL_HOST = os.getenv('DJANGO_EMAIL_HOST')
    EMAIL_PORT = int(os.getenv('DJANGO_EMAIL_PORT', '587'))
    EMAIL_HOST_USER = os.getenv('DJANGO_EMAIL_HOST_USER', '')
    EMAIL_HOST_PASSWORD = os.getenv('DJANGO_EMAIL_HOST_PASSWORD', '')
    EMAIL_USE_TLS = os.getenv('DJANGO_EMAIL_USE_TLS', 'true').lower() == 'true'
