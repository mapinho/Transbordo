"""Métricas agregadas para os dashboards da home (Fase 12).

Cross-tenant deliberado: usa os managers `all_cooperativas`, não `objects`
(que é fail-closed pelo contextvar de tenant). Não deve ser chamado de uma
view comum — só das telas de home, que resolvem o escopo explicitamente.
"""
from django.db.models import Q, Sum

from apps.core.models import Cooperativa
from apps.simulacao.models import (
    Armazem, Cenario, Fabrica, LogExecucao, MovimentacaoDiaria,
)
from apps.simulacao.services import KG_PER_SACA, KG_PER_TON


def _cenario_oficial(cooperativa_id):
    return (
        Cenario.all_cooperativas
        .filter(cooperativa_id=cooperativa_id, is_oficial=True)
        .first()
    )


def _ultima_simulacao(cooperativa_id, oficial):
    qs = LogExecucao.all_cooperativas.filter(
        cooperativa_id=cooperativa_id, status=LogExecucao.Status.SUCESSO,
    )
    qs = qs.filter(Q(cenario__isnull=True) | Q(cenario_id=getattr(oficial, 'id', None)))
    log = qs.order_by('-data_execucao').first()
    return log.data_execucao if log else None


def metricas_da_organizacao(cooperativa_id):
    oficial = _cenario_oficial(cooperativa_id)
    cenarios = Cenario.all_cooperativas.filter(cooperativa_id=cooperativa_id).count()
    if oficial is None:
        return {
            'fabricas': 0, 'armazens': 0, 'cenarios': cenarios,
            'toneladas': None, 'sacas': None, 'frete': None, 'ultima_simulacao': None,
        }
    agg = MovimentacaoDiaria.all_cooperativas.filter(cenario_id=oficial.id).aggregate(
        ton=Sum('quantidade_ton'), frete=Sum('custo_total'),
    )
    toneladas = agg['ton'] or 0.0
    frete = agg['frete'] or 0.0
    return {
        'fabricas': Fabrica.all_cooperativas.filter(cenario_id=oficial.id).count(),
        'armazens': Armazem.all_cooperativas.filter(cenario_id=oficial.id).count(),
        'cenarios': cenarios,
        'toneladas': toneladas,
        'sacas': toneladas * KG_PER_TON / KG_PER_SACA,
        'frete': frete,
        'ultima_simulacao': _ultima_simulacao(cooperativa_id, oficial),
    }


def metricas_consolidadas():
    por_organizacao = []
    tot = {'organizacoes': 0, 'fabricas': 0, 'armazens': 0, 'toneladas': 0.0,
           'sacas': 0.0, 'frete': 0.0}
    for coop in Cooperativa.objects.filter(ativo=True).order_by('nome'):
        m = metricas_da_organizacao(coop.id)
        tot['organizacoes'] += 1
        tot['fabricas'] += m['fabricas']
        tot['armazens'] += m['armazens']
        tot['toneladas'] += m['toneladas'] or 0.0
        tot['sacas'] += m['sacas'] or 0.0
        tot['frete'] += m['frete'] or 0.0
        por_organizacao.append({
            'id': coop.id, 'nome': coop.nome,
            'fabricas': m['fabricas'], 'armazens': m['armazens'],
            'toneladas': m['toneladas'], 'frete': m['frete'],
            'ultima_simulacao': m['ultima_simulacao'],
        })
    return {'totais': tot, 'por_organizacao': por_organizacao}
