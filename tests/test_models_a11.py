import datetime

import pytest
from sqlalchemy.exc import IntegrityError

from models import Fabrica, MovimentacaoDiaria, SafraUnidade


def test_fabrica_cenario_id_cannot_be_null(session):
    """A11: Fabrica.cenario_id must be NOT NULL so rows can't become orphaned."""
    f = Fabrica(
        cenario_id=None,
        nome="Fábrica Órfã",
        capacidade_estatica=10000,
        capacidade_esmagamento_diaria=500,
        capacidade_recebimento_diaria=600,
        limite_caminhoes=20,
        carga_media_caminhao=30,
        estoque_inicial=1000,
    )
    session.add(f)
    with pytest.raises(IntegrityError):
        session.commit()


def test_movimentacao_diaria_cenario_id_cannot_be_null(session, armazem, fabrica):
    """A11: MovimentacaoDiaria.cenario_id must be NOT NULL so rows can't become orphaned."""
    m = MovimentacaoDiaria(
        cenario_id=None,
        data=datetime.date(2026, 1, 1),
        armazem_id=armazem.id,
        fabrica_id=fabrica.id,
        quantidade_ton=100.0,
        custo_total=500.0,
    )
    session.add(m)
    with pytest.raises(IntegrityError):
        session.commit()


def test_safra_unidade_cenario_id_cannot_be_null(session):
    """A11: SafraUnidade.cenario_id must be NOT NULL so rows can't become orphaned."""
    s = SafraUnidade(
        cenario_id=None,
        entidade_tipo="fabrica",
        entidade_id=1,
        data_inicio=datetime.date(2026, 1, 1),
        data_fim=datetime.date(2026, 12, 31),
    )
    session.add(s)
    with pytest.raises(IntegrityError):
        session.commit()
