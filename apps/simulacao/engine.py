import datetime
import json
import logging
import time

import pandas as pd
from django.db import transaction
from django.db.models import Max, Min
from ortools.linear_solver import pywraplp

from apps.simulacao.models import Armazem, Fabrica, Rota, SafraUnidade
from apps.simulacao.models import (
    Cenario,
    LogExecucao,
    MovimentacaoDiaria,
    PrevisaoArmazem,
    PrevisaoFabrica,
    ResumoMensalArmazem,
    ResumoMensalFabrica,
)

# Ver ADR 0006: engine.py e services.py consultam via `all_cooperativas`
# (nunca `objects`, o TenantManager fail-closed) porque recebem o limite de
# tenant explicitamente via `cenario_id`/`scenario_id` -- exatamente como o
# codigo SQLAlchemy original ja funcionava, sem nocao de "cooperativa da
# sessao corrente". Confiar no contexto implicito de middleware aqui
# quebraria silenciosamente (queryset vazio) toda chamada feita fora de uma
# requisicao HTTP -- um worker Procrastinate futuro, um management command,
# ou os proprios testes deste arquivo.

_RESERVED_LOG_RECORD_ATTRS = frozenset({
    'name', 'msg', 'args', 'levelname', 'levelno', 'pathname', 'filename',
    'module', 'exc_info', 'exc_text', 'stack_info', 'lineno', 'funcName',
    'created', 'msecs', 'relativeCreated', 'thread', 'threadName',
    'processName', 'process', 'taskName', 'message',
})


class JsonFormatter(logging.Formatter):
    """Formatter de logging que emite um objeto JSON por linha (structured
    logging). Porte 1:1 de `calculations.JsonFormatter` -- pura lógica de
    logging, sem dependência de ORM."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            'timestamp': self.formatTime(record, self.datefmt),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
        }

        for key, value in record.__dict__.items():
            if key not in _RESERVED_LOG_RECORD_ATTRS:
                payload[key] = value

        if record.exc_info:
            payload['exc_info'] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str, ensure_ascii=False)


_handler = logging.StreamHandler()
_handler.setFormatter(JsonFormatter())
logger = logging.getLogger(__name__)
logger.addHandler(_handler)
logger.setLevel(logging.INFO)
logger.propagate = False


def _janela_safra_de_registro(safra, data):
    """Versão pura de `obter_janela_safra`: recebe o registro SafraUnidade já
    buscado (ou None) e resolve (na_safra, data_inicio, data_fim) sem tocar
    o banco. Porte 1:1 de `calculations._janela_safra_de_registro`."""
    if safra:
        data_inicio, data_fim = safra.data_inicio, safra.data_fim
    else:
        ano = data.year
        data_inicio = datetime.date(ano, 1, 15)
        data_fim = datetime.date(ano, 4, 15)

    na_safra = data_inicio <= data <= data_fim
    return na_safra, data_inicio, data_fim


def obter_janela_safra(entidade_tipo, entidade_id, data, cenario_id):
    """Determina a janela de safra de uma unidade e se `data` está dentro
    dela. Porte de `calculations.obter_janela_safra` -- assinatura igual,
    menos o parâmetro `session` (Django não tem sessão)."""
    safra = SafraUnidade.all_cooperativas.filter(
        cenario_id=cenario_id,
        entidade_tipo=entidade_tipo,
        entidade_id=entidade_id,
    ).first()
    return _janela_safra_de_registro(safra, data)


def _carregar_safras_por_armazem(cenario_id):
    """Pré-carrega todos os SafraUnidade de armazéns do cenário, indexados
    por armazem_id. Porte de `calculations._carregar_safras_por_armazem`."""
    rows = SafraUnidade.all_cooperativas.filter(
        cenario_id=cenario_id,
        entidade_tipo='Armazém',
    )
    return {r.entidade_id: r for r in rows}


def otimizar_dia(data, estoques_atuais, estrategia='Econômico', cenario_id=None,
                  fabricas=None, armazens=None, rotas=None, safra_cache=None):
    """Otimiza a movimentação de soja para um dia específico. Porte 1:1 de
    `calculations.otimizar_dia` -- lógica do solver inalterada, só a camada
    de acesso a dados trocou de `session.query` para `Model.all_cooperativas`
    (ver ADR 0006). Assinatura igual, menos o parâmetro `session`."""
    solver = pywraplp.Solver.CreateSolver('SCIP')
    if not solver:
        solver = pywraplp.Solver.CreateSolver('GLOP')

    if not solver:
        logger.error("Nenhum solver (SCIP ou GLOP) disponível no OR-Tools.")
        raise RuntimeError("Nenhum solver OR-Tools disponivel (SCIP ou GLOP).")

    if fabricas is None:
        fabricas = list(Fabrica.all_cooperativas.filter(cenario_id=cenario_id))
    if armazens is None:
        armazens = list(Armazem.all_cooperativas.filter(cenario_id=cenario_id))
    if rotas is None:
        rotas = list(Rota.all_cooperativas.filter(cenario_id=cenario_id))

    if not rotas:
        return []

    v_mov = {}
    for r in rotas:
        v_mov[(r.armazem_id, r.fabrica_id)] = solver.NumVar(0, solver.infinity(), f'mov_{r.armazem_id}_{r.fabrica_id}')

    for a in armazens:
        movs_saindo = [v_mov[(a.id, f.id)] for f in fabricas if (a.id, f.id) in v_mov]
        if movs_saindo:
            solver.Add(solver.Sum(movs_saindo) <= a.capacidade_expedicao_diaria)
            solver.Add(solver.Sum(movs_saindo) <= max(0, estoques_atuais.get(f'A_{a.id}', 0)))

    for f in fabricas:
        movs_entrando = [v_mov[(a.id, f.id)] for a in armazens if (a.id, f.id) in v_mov]
        if not movs_entrando:
            continue

        recebimento_transbordo = solver.Sum(movs_entrando)
        solver.Add(recebimento_transbordo <= f.capacidade_recebimento_diaria)
        solver.Add(recebimento_transbordo <= f.limite_caminhoes * f.carga_media_caminhao)

    v_atendimento = {}
    for f in fabricas:
        demanda = max(0, f.capacidade_esmagamento_diaria - max(0, estoques_atuais.get(f'F_{f.id}', 0)))
        if demanda > 0:
            v_atendimento[f.id] = solver.NumVar(0, demanda, f'atend_{f.id}')
            movs_entrando = [v_mov[(a.id, f.id)] for a in armazens if (a.id, f.id) in v_mov]
            if movs_entrando:
                solver.Add(solver.Sum(movs_entrando) >= v_atendimento[f.id])

    p_atendimento = 10000000
    recompensa_base = 10000
    if estrategia == 'Econômico':
        recompensa_base = 100
    elif estrategia == 'Expedição':
        recompensa_base = 50000
    elif estrategia == 'Segurança':
        p_atendimento = 50000000

    objetivo = solver.Objective()
    for var in v_atendimento.values():
        objetivo.SetCoefficient(var, p_atendimento)

    for r in rotas:
        if safra_cache is not None:
            na_safra, d_ini, d_fim = _janela_safra_de_registro(safra_cache.get(r.armazem_id), data)
        else:
            na_safra, d_ini, _d_fim = obter_janela_safra('Armazém', r.armazem_id, data, cenario_id)

        if data < d_ini:
            solver.Add(v_mov[(r.armazem_id, r.fabrica_id)] == 0)
            continue

        custo_ton = r.custo_frete_ton if na_safra else r.custo_frete_entressafra
        incentivo_movimentar = recompensa_base + (1000 if na_safra else 0)
        objetivo.SetCoefficient(v_mov[(r.armazem_id, r.fabrica_id)], incentivo_movimentar - custo_ton)

    objetivo.SetMaximization()
    status = solver.Solve()

    if status == pywraplp.Solver.OPTIMAL or status == pywraplp.Solver.FEASIBLE:
        resultados = []
        for r in rotas:
            qtd = v_mov[(r.armazem_id, r.fabrica_id)].solution_value()
            if qtd > 0.001:
                if safra_cache is not None:
                    na_safra_real, _, _ = _janela_safra_de_registro(safra_cache.get(r.armazem_id), data)
                else:
                    na_safra_real, _, _ = obter_janela_safra('Armazém', r.armazem_id, data, cenario_id)
                custo_ton_real = r.custo_frete_ton if na_safra_real else r.custo_frete_entressafra

                resultados.append({
                    'armazem_id': r.armazem_id,
                    'fabrica_id': r.fabrica_id,
                    'quantidade_ton': qtd,
                    'custo_total': qtd * custo_ton_real,
                })
        return resultados

    logger.warning(
        "Otimização do dia %s (cenario_id=%s) não encontrou solução ótima/viável (status=%s).",
        data, cenario_id, status
    )
    return None


def simular_periodo(data_inicio, data_fim_previsao, cenario_id=None, estrategia='Econômico'):
    """Porte 1:1 de `calculations.simular_periodo`. A garantia de
    atomicidade (delete+recompute+insert) usa `transaction.atomic()` em vez
    de `session.commit()`/`session.rollback()` explícitos -- o efeito é o
    mesmo: uma exceção dentro do bloco reverte tudo dentro dele (até o
    savepoint mais próximo) e se repropaga. O registro de LogExecucao de
    sucesso fica FORA desse bloco, num segundo `.create()` autônomo, para
    preservar a mesma garantia do original ("commit separado, estritamente
    posterior ao principal")."""
    c_id = int(cenario_id) if cenario_id is not None else None
    inicio_execucao = time.monotonic()
    cenario = Cenario.all_cooperativas.get(id=c_id)
    cooperativa_id = cenario.cooperativa_id

    try:
        with transaction.atomic():
            MovimentacaoDiaria.all_cooperativas.filter(cenario_id=c_id).delete()
            ResumoMensalFabrica.all_cooperativas.filter(cenario_id=c_id).delete()
            ResumoMensalArmazem.all_cooperativas.filter(cenario_id=c_id).delete()

            data_inicio_ajustada = pd.to_datetime(data_inicio).date().replace(day=1)

            fabricas = list(Fabrica.all_cooperativas.filter(cenario_id=c_id))
            armazens = list(Armazem.all_cooperativas.filter(cenario_id=c_id))
            rotas = list(Rota.all_cooperativas.filter(cenario_id=c_id))
            safra_cache = _carregar_safras_por_armazem(c_id)

            fabrica_ids = [f.id for f in fabricas]
            armazem_ids = [a.id for a in armazens]
            previsoes_fab = {
                (p.fabrica_id, p.mes_referencia): p
                for p in PrevisaoFabrica.all_cooperativas.filter(fabrica_id__in=fabrica_ids)
            }
            previsoes_arm = {
                (p.armazem_id, p.mes_referencia): p
                for p in PrevisaoArmazem.all_cooperativas.filter(armazem_id__in=armazem_ids)
            }

            estoques_atuais = {}
            for f in fabricas:
                estoques_atuais[f'F_{f.id}'] = f.estoque_inicial
            for a in armazens:
                estoques_atuais[f'A_{a.id}'] = a.estoque_inicial

            data_atual = data_inicio_ajustada
            d_fim_p = pd.to_datetime(data_fim_previsao).date()

            resumos_fab = {}
            resumos_arm = {}
            dias_executados = 0
            max_dias = 730

            while True:
                mes_str = data_atual.strftime('%Y-%m')

                if mes_str not in resumos_fab:
                    resumos_fab[mes_str] = {f.id: {'rec_produtor': 0, 'rec_transbordo': 0, 'esmagado': 0, 'cap_estatica': f.capacidade_estatica} for f in fabricas}
                if mes_str not in resumos_arm:
                    resumos_arm[mes_str] = {a.id: {'rec_produtor': 0, 'envio_transbordo': 0, 'vendas': 0, 'cap_estatica': a.capacidade_estatica} for a in armazens}

                mes_atual_date = datetime.date(data_atual.year, data_atual.month, 1)
                dias_no_mes = pd.Period(data_atual.strftime('%Y-%m-%d')).days_in_month

                for f in fabricas:
                    prev = previsoes_fab.get((f.id, mes_atual_date))
                    if prev:
                        rec_diario = (prev.recebimento_produtor or 0) / dias_no_mes
                        vend_diario = (prev.vendas or 0) / dias_no_mes
                        estoques_atuais[f'F_{f.id}'] += (rec_diario - vend_diario)
                        resumos_fab[mes_str][f.id]['rec_produtor'] += rec_diario

                for a in armazens:
                    prev = previsoes_arm.get((a.id, mes_atual_date))
                    if prev:
                        rec_diario = (prev.recebimento_produtor or 0) / dias_no_mes
                        vend_diario = (prev.vendas or 0) / dias_no_mes
                        estoques_atuais[f'A_{a.id}'] += (rec_diario - vend_diario)
                        resumos_arm[mes_str][a.id]['rec_produtor'] += rec_diario
                        resumos_arm[mes_str][a.id]['vendas'] += vend_diario

                movimentacoes = otimizar_dia(
                    data_atual, estoques_atuais, estrategia=estrategia, cenario_id=c_id,
                    fabricas=fabricas, armazens=armazens, rotas=rotas, safra_cache=safra_cache,
                )

                if movimentacoes:
                    for mov in movimentacoes:
                        MovimentacaoDiaria.all_cooperativas.create(
                            cooperativa_id=cooperativa_id,
                            cenario_id=c_id,
                            data=data_atual,
                            armazem_id=mov['armazem_id'],
                            fabrica_id=mov['fabrica_id'],
                            quantidade_ton=mov['quantidade_ton'],
                            custo_total=mov['custo_total'],
                        )
                        estoques_atuais[f'A_{mov["armazem_id"]}'] -= mov['quantidade_ton']
                        estoques_atuais[f'F_{mov["fabrica_id"]}'] += mov['quantidade_ton']
                        resumos_arm[mes_str][mov['armazem_id']]['envio_transbordo'] += mov['quantidade_ton']
                        resumos_fab[mes_str][mov['fabrica_id']]['rec_transbordo'] += mov['quantidade_ton']

                for f in fabricas:
                    esmagado_real = min(max(0, estoques_atuais[f'F_{f.id}']), f.capacidade_esmagamento_diaria)
                    estoques_atuais[f'F_{f.id}'] -= esmagado_real
                    resumos_fab[mes_str][f.id]['esmagado'] += esmagado_real

                total_estoque_arm = sum(max(0, estoques_atuais[f'A_{a.id}']) for a in armazens)
                acabaram_previsoes = data_atual >= d_fim_p
                armazens_vazios = total_estoque_arm < 1.0

                eh_ultimo_dia_simulacao = (acabaram_previsoes and armazens_vazios) or dias_executados >= max_dias
                eh_ultimo_dia_mes = (data_atual + datetime.timedelta(days=1)).month != data_atual.month

                if eh_ultimo_dia_mes or eh_ultimo_dia_simulacao:
                    for f in fabricas:
                        resumos_fab[mes_str][f.id]['saldo_estoque'] = estoques_atuais[f'F_{f.id}']
                        resumos_fab[mes_str][f.id]['excedente'] = max(0, estoques_atuais[f'F_{f.id}'] - resumos_fab[mes_str][f.id]['cap_estatica'])
                    for a in armazens:
                        resumos_arm[mes_str][a.id]['saldo_estoque'] = estoques_atuais[f'A_{a.id}']
                        resumos_arm[mes_str][a.id]['excedente'] = max(0, estoques_atuais[f'A_{a.id}'] - resumos_arm[mes_str][a.id]['cap_estatica'])

                if eh_ultimo_dia_simulacao:
                    break

                data_atual += datetime.timedelta(days=1)
                dias_executados += 1

            for mes, fab_dict in resumos_fab.items():
                for f_id, dados in fab_dict.items():
                    ResumoMensalFabrica.all_cooperativas.create(
                        cooperativa_id=cooperativa_id, cenario_id=c_id, mes=mes, fabrica_id=f_id,
                        rec_produtor=dados['rec_produtor'], rec_transbordo=dados['rec_transbordo'],
                        esmagado=dados['esmagado'], saldo_estoque=dados.get('saldo_estoque', 0),
                        capacidade_estatica=dados['cap_estatica'], excedente=dados.get('excedente', 0),
                    )

            for mes, arm_dict in resumos_arm.items():
                for a_id, dados in arm_dict.items():
                    ResumoMensalArmazem.all_cooperativas.create(
                        cooperativa_id=cooperativa_id, cenario_id=c_id, mes=mes, armazem_id=a_id,
                        rec_produtor=dados['rec_produtor'], envio_transbordo=dados['envio_transbordo'],
                        vendas=dados['vendas'], saldo_estoque=dados.get('saldo_estoque', 0),
                        capacidade_estatica=dados['cap_estatica'], excedente=dados.get('excedente', 0),
                    )

        duracao_segundos = time.monotonic() - inicio_execucao
        dias_simulados = dias_executados + 1
        LogExecucao.all_cooperativas.create(
            cooperativa_id=cooperativa_id,
            cenario_id=c_id,
            status='sucesso',
            mensagem=f"Simulação concluída para cenario_id={c_id} em {dias_simulados} dia(s).",
            duracao_segundos=duracao_segundos,
            dias_simulados=dias_simulados,
        )

        logger.info(
            "Simulação concluída",
            extra={
                'cenario_id': c_id,
                'duracao_segundos': duracao_segundos,
                'dias_simulados': dias_simulados,
            },
        )
    except Exception:
        logger.error(
            "Falha na simulação",
            extra={'cenario_id': c_id},
            exc_info=True,
        )
        raise


def obter_range_previsoes(cenario_id=None):
    """Porte 1:1 de `calculations.obter_range_previsoes`."""
    min_f = PrevisaoFabrica.all_cooperativas.filter(fabrica__cenario_id=cenario_id).aggregate(Min('mes_referencia'))['mes_referencia__min']
    max_f = PrevisaoFabrica.all_cooperativas.filter(fabrica__cenario_id=cenario_id).aggregate(Max('mes_referencia'))['mes_referencia__max']
    min_a = PrevisaoArmazem.all_cooperativas.filter(armazem__cenario_id=cenario_id).aggregate(Min('mes_referencia'))['mes_referencia__min']
    max_a = PrevisaoArmazem.all_cooperativas.filter(armazem__cenario_id=cenario_id).aggregate(Max('mes_referencia'))['mes_referencia__max']

    dates = [d for d in [min_f, max_f, min_a, max_a] if d is not None]
    if not dates:
        return None, None

    start_date = min(dates)
    end_date_start_month = max(dates)
    end_date = (pd.Timestamp(end_date_start_month) + pd.offsets.MonthEnd(0)).date()

    return start_date, end_date
