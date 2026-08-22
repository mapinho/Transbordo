import os

from .base import *  # noqa: F401,F403

DEBUG = False

# TLS termina no reverse proxy existente na frente da aplicação (Apache,
# já configurado em comigo.conf/comigo-le-ssl.conf) — o Django nunca fala
# HTTPS diretamente. Sem isso, request.is_secure() sempre volta False
# atrás do proxy. Serviço/whitenoise real ficam para a Fase 7 (Deploy).
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

CSRF_TRUSTED_ORIGINS = [f'https://{host}' for host in ALLOWED_HOSTS if host]  # noqa: F405
