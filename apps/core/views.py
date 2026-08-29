from django.conf import settings
from django.http import JsonResponse


def healthz(request):
    """Stub de health check — só a versão por enquanto. O SELECT 1 e o
    HEALTHCHECK do container entram na Fase 10 (Deploy)."""
    return JsonResponse({'version': settings.APP_VERSION})
