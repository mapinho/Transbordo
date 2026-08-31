from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import connection
from django.db.utils import OperationalError
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.core import services
from apps.core.models import Cooperativa
from apps.core.permissions import e_admin_vector, requer_admin_vector
from apps.core.tenancy import obter_organizacao_corrente


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


@login_required
def home(request):
    org_id = obter_organizacao_corrente(request)
    if org_id is None and e_admin_vector(request.user):
        return render(request, 'core/home_consolidado.html', {
            'metricas': services.metricas_consolidadas(),
        })
    org = Cooperativa.objects.filter(id=org_id).first()
    cenarios_recentes = []
    if org_id:
        from apps.simulacao.models import Cenario
        cenarios_recentes = list(
            Cenario.all_cooperativas
            .filter(cooperativa_id=org_id)
            .order_by('-is_oficial', '-data_criacao')[:8]
        )
    return render(request, 'core/home_organizacao.html', {
        'org': org,
        'metricas': services.metricas_da_organizacao(org_id) if org_id else None,
        'cenarios_recentes': cenarios_recentes,
    })


@login_required
@requer_admin_vector
@require_POST
def selecionar_organizacao(request):
    org_id = (request.POST.get('org_id') or '').strip()
    if org_id and org_id.isdigit() and Cooperativa.objects.filter(id=org_id, ativo=True).exists():
        request.session['org_corrente_id'] = int(org_id)
    else:
        request.session.pop('org_corrente_id', None)
    return redirect('core:home')
