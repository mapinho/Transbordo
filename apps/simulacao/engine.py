import datetime
import json
import logging

from ortools.linear_solver import pywraplp

from apps.simulacao.models import Armazem, Fabrica, Rota, SafraUnidade

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
