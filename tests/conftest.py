import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import (
    Base,
    Cenario,
    Fabrica,
    Armazem,
    Rota,
)


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


@pytest.fixture()
def cenario(session):
    c = Cenario(nome="Cenário Teste", is_oficial=True)
    session.add(c)
    session.commit()
    return c


@pytest.fixture()
def fabrica(session, cenario):
    f = Fabrica(
        cenario_id=cenario.id,
        nome="Fábrica Teste",
        capacidade_estatica=10000,
        capacidade_esmagamento_diaria=500,
        capacidade_recebimento_diaria=600,
        limite_caminhoes=20,
        carga_media_caminhao=30,
        estoque_inicial=1000,
    )
    session.add(f)
    session.commit()
    return f


@pytest.fixture()
def armazem(session, cenario):
    a = Armazem(
        cenario_id=cenario.id,
        nome="Armazém Teste",
        capacidade_estatica=5000,
        capacidade_expedicao_diaria=300,
        estoque_inicial=2000,
    )
    session.add(a)
    session.commit()
    return a


@pytest.fixture()
def rota(session, armazem, fabrica):
    r = Rota(
        cenario_id=armazem.cenario_id,
        armazem_id=armazem.id,
        fabrica_id=fabrica.id,
        distancia_km=50,
        custo_frete_ton=20.0,
        custo_frete_entressafra=15.0,
    )
    session.add(r)
    session.commit()
    return r
