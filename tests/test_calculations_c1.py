import datetime

import pytest

import calculations
from models import MovimentacaoDiaria


def test_simular_periodo_nao_perde_dados_em_falha_no_meio_do_loop(
    session, cenario, fabrica, armazem, rota, monkeypatch
):
    """
    C1 regression test: se otimizar_dia lançar uma exceção durante o
    laço dia-a-dia, os dados anteriores (MovimentacaoDiaria) NÃO podem
    ter sido apagados permanentemente do banco. A operação de
    apagar+recalcular+inserir precisa ser atômica: em caso de falha,
    um rollback deve restaurar o estado anterior e a exceção original
    deve ser repropagada.
    """
    # 1. Dado existente representando histórico anterior do cenário.
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
        session.query(MovimentacaoDiaria)
        .filter_by(cenario_id=cenario.id)
        .count()
        == 1
    )

    # 2. Forçar uma falha no meio da simulação.
    def _falha_forcada(*args, **kwargs):
        raise RuntimeError("forced failure")

    monkeypatch.setattr(calculations, "otimizar_dia", _falha_forcada)

    # 3. Executar simular_periodo esperando que a exceção seja repropagada.
    with pytest.raises(RuntimeError, match="forced failure"):
        calculations.simular_periodo(
            session,
            data_inicio=datetime.date(2026, 1, 20),
            data_fim_previsao=datetime.date(2026, 1, 25),
            cenario_id=cenario.id,
        )

    # 4. Regression assertion: o dado anterior não pode ter sido apagado
    #    permanentemente. Como a exceção ocorreu no meio do processo, a
    #    operação inteira (delete + recompute + insert) deve ter sido
    #    revertida, preservando o estado anterior ao commit.
    session.rollback()
    count_apos_falha = (
        session.query(MovimentacaoDiaria)
        .filter_by(cenario_id=cenario.id)
        .count()
    )
    assert count_apos_falha >= 1, (
        "Dados anteriores de MovimentacaoDiaria foram perdidos "
        "permanentemente apos falha no meio da simulacao (bug C1)."
    )
