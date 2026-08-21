"""
Testes de observabilidade (Fase 4 - "Otimização - Observabilidade").

Cobre duas mudanças, ambas restritas a `calculations.py`/`models.py`:

1. `calculations.JsonFormatter`: cada linha de log passa a ser um objeto
   JSON (structured logging), machine-parseable por um futuro dashboard de
   operação.
2. `simular_periodo` passa a gravar uma linha em `LogExecucao` a cada
   execução bem-sucedida (duração + escopo/dias simulados), preservando a
   garantia de atomicidade C1 (delete+recompute+insert continuam atômicos
   entre si; o registro de log é estritamente posterior ao commit
   principal e não pode "vazar" de uma transação revertida).
"""
import datetime
import json
import logging

import pytest

import calculations
from models import Armazem, Cenario, Fabrica, LogExecucao, MovimentacaoDiaria, Rota


# ---------------------------------------------------------------------------
# 1. JsonFormatter
# ---------------------------------------------------------------------------

def test_json_formatter_produz_json_valido_com_level_e_message():
    formatter = calculations.JsonFormatter()
    record = logging.LogRecord(
        name="calculations",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="Simulação concluída",
        args=(),
        exc_info=None,
    )

    formatted = formatter.format(record)
    parsed = json.loads(formatted)

    assert parsed["level"] == "INFO"
    assert parsed["message"] == "Simulação concluída"
    assert "timestamp" in parsed
    assert parsed["logger"] == "calculations"


def test_json_formatter_repassa_campos_extras_do_log_call():
    formatter = calculations.JsonFormatter()
    record = logging.LogRecord(
        name="calculations",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="Simulação concluída",
        args=(),
        exc_info=None,
    )
    # Simula o efeito de logger.info(msg, extra={...}): os campos extras
    # são anexados diretamente ao __dict__ do record pelo próprio módulo
    # `logging` antes de chegar ao formatter.
    record.cenario_id = 7
    record.duracao_segundos = 1.23

    parsed = json.loads(formatter.format(record))

    assert parsed["cenario_id"] == 7
    assert parsed["duracao_segundos"] == 1.23


# ---------------------------------------------------------------------------
# Helper: cenário com estoques zerados, para controlar exatamente quantos
# dias `simular_periodo` executa apenas via `data_fim_previsao` (mesmo
# padrão de `tests/test_calculations_fase3_performance.py`).
# ---------------------------------------------------------------------------

def _montar_cenario_zerado(session, cenario_id):
    fabrica = Fabrica(
        cenario_id=cenario_id, nome="Fábrica 1", capacidade_estatica=100000,
        capacidade_esmagamento_diaria=1000, capacidade_recebimento_diaria=1000,
        limite_caminhoes=50, carga_media_caminhao=30, estoque_inicial=0,
    )
    armazem = Armazem(
        cenario_id=cenario_id, nome="Armazém 1", capacidade_estatica=50000,
        capacidade_expedicao_diaria=1000, estoque_inicial=0,
    )
    session.add_all([fabrica, armazem])
    session.commit()

    rota = Rota(
        cenario_id=cenario_id, armazem_id=armazem.id, fabrica_id=fabrica.id,
        distancia_km=10, custo_frete_ton=5.0, custo_frete_entressafra=8.0,
    )
    session.add(rota)
    session.commit()
    return fabrica, armazem, rota


# ---------------------------------------------------------------------------
# 2. Execução bem-sucedida grava exatamente uma linha em LogExecucao.
# ---------------------------------------------------------------------------

def test_simular_periodo_sucesso_grava_log_execucao(session):
    cenario = Cenario(nome="Cenário Fase4", is_oficial=False)
    session.add(cenario)
    session.commit()
    _montar_cenario_zerado(session, cenario.id)

    dias = 7
    data_inicio = datetime.date(2026, 1, 1)
    data_fim = data_inicio + datetime.timedelta(days=dias - 1)

    calculations.simular_periodo(session, data_inicio, data_fim, cenario_id=cenario.id)

    logs = session.query(LogExecucao).filter_by(cenario_id=cenario.id).all()
    assert len(logs) == 1

    log = logs[0]
    assert log.status == "sucesso"
    assert log.cenario_id == cenario.id
    assert log.duracao_segundos is not None
    assert log.duracao_segundos >= 0
    assert log.dias_simulados == dias


# ---------------------------------------------------------------------------
# 3. Caracterização: a garantia de atomicidade C1 não pode ser enfraquecida
#    pela adição do log de sucesso -- em caso de falha no meio do loop, os
#    dados anteriores de MovimentacaoDiaria continuam sobrevivendo ao
#    rollback, e nenhuma linha de LogExecucao (que só é gravada após o
#    commit principal, no caminho de sucesso) deve ter sido criada.
# ---------------------------------------------------------------------------

def test_simular_periodo_falha_nao_perde_dados_nem_grava_log_sucesso(
    session, cenario, fabrica, armazem, rota, monkeypatch
):
    mov_existente = MovimentacaoDiaria(
        cenario_id=cenario.id,
        data=datetime.date(2026, 1, 20),
        armazem_id=armazem.id,
        fabrica_id=fabrica.id,
        quantidade_ton=123.45,
        custo_total=999.99,
    )
    session.add(mov_existente)
    session.commit()

    assert (
        session.query(MovimentacaoDiaria).filter_by(cenario_id=cenario.id).count() == 1
    )

    def _falha_forcada(*args, **kwargs):
        raise RuntimeError("forced failure")

    monkeypatch.setattr(calculations, "otimizar_dia", _falha_forcada)

    with pytest.raises(RuntimeError, match="forced failure"):
        calculations.simular_periodo(
            session,
            data_inicio=datetime.date(2026, 1, 20),
            data_fim_previsao=datetime.date(2026, 1, 25),
            cenario_id=cenario.id,
        )

    session.rollback()

    count_mov_apos_falha = (
        session.query(MovimentacaoDiaria).filter_by(cenario_id=cenario.id).count()
    )
    assert count_mov_apos_falha >= 1, (
        "Dados anteriores de MovimentacaoDiaria foram perdidos "
        "permanentemente apos falha no meio da simulacao (bug C1)."
    )

    count_log_apos_falha = (
        session.query(LogExecucao).filter_by(cenario_id=cenario.id).count()
    )
    assert count_log_apos_falha == 0, (
        "Uma linha de LogExecucao de sucesso sobreviveu a uma execução que "
        "falhou -- o registro de log deve ser posterior/atômico ao commit "
        "principal, nunca independente dele."
    )
