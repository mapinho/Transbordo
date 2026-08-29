from django.conf import settings
from django.db import connection
from django.db.utils import OperationalError
from django.http import JsonResponse


def healthz(request):
    """Health check: versão da aplicação + SELECT 1 no banco. Sem auth.
    Usado pelo HEALTHCHECK do container `web` e pelo poll do deploy.sh."""
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
        db_ok = True
    except OperationalError:
        db_ok = False
    return JsonResponse(
        {'version': settings.APP_VERSION, 'db': 'ok' if db_ok else 'erro'},
        status=200 if db_ok else 503,
    )
