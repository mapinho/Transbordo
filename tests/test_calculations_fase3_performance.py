"""
Testes de performance (Fase 3) - eliminacao do padrao N+1 no laco de
simulacao diaria de `simular_periodo`/`otimizar_dia`.

Contexto (achado do roteiro estrategico, secao Fase 3): a cada dia
simulado (ate 730 dias em `max_dias`), `otimizar_dia` reconsultava
fabricas, armazens e rotas do banco -- dados estaticos por cenario -- e,
para cada rota, consultava a janela de safra do armazem DUAS vezes (uma
ao montar o objetivo do solver, outra ao ler o resultado). Alem disso,
`simular_periodo` reconsultava as previsoes mensais de cada fabrica/
armazem a cada dia, mesmo o mes so mudando uma vez por mes. O objetivo
aqui e provar isso via contagem real de queries SQL (nao apenas medir
tempo, que varia por maquina) -- antes e depois do pre-carregamento.
"""
import datetime

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

import calculations
from models import (
    Base,
    Armazem,
    Cenario,
    Fabrica,
    PrevisaoArmazem,
    PrevisaoFabrica,
    ResumoMensalFabrica,
    Rota,
    SafraUnidade,
)


@pytest.fixture()
def engine():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def session(engine):
    # expire_on_commit=False: em `simular_periodo` real, o commit só ocorre
    # uma vez no final do laço de dias, então os objetos pré-carregados
    # nunca expiram/recarregam no meio da simulação. Os testes locais aqui
    # fazem commits mais cedo (para popular o cenário), então precisam da
    # mesma configuração para não medir queries de re-hidratação do ORM
    # como se fossem parte do padrão N+1 sendo testado.
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    db = Session()
    try:
        yield db
    finally:
        db.close()


class QueryCounter:
    """Conta quantas queries SQL reais sao executadas no engine dentro do
    bloco `with`, via hook do SQLAlchemy -- nao depende de medir tempo."""

    def __init__(self, engine):
        self.engine = engine
        self.count = 0

    def __enter__(self):
        event.listen(self.engine, "before_cursor_execute", self._on_execute)
        return self

    def __exit__(self, *exc):
        event.remove(self.engine, "before_cursor_execute", self._on_execute)

    def _on_execute(self, conn, cursor, statement, parameters, context, executemany):
        self.count += 1


def _montar_cenario_basico(session, cenario_id, com_safra_cadastrada):
    # Estoques zerados e sem previsões de reposição: `armazens_vazios` fica
    # verdadeiro desde o dia 0, então quem controla exatamente quantos dias
    # `simular_periodo` executa é só `data_fim_previsao` (usado em
    # `_rodar_simulacao`) -- necessário para os testes de contagem de
    # queries/resultado abaixo terem um número de dias previsível.
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

    if com_safra_cadastrada:
        session.add(SafraUnidade(
            cenario_id=cenario_id, entidade_tipo='Armazém', entidade_id=armazem.id,
            data_inicio=datetime.date(2026, 1, 1), data_fim=datetime.date(2026, 12, 31),
        ))
    session.commit()
    return fabrica, armazem, rota


def _rodar_simulacao(session, cenario_id, dias):
    data_inicio = datetime.date(2026, 1, 1)
    data_fim = data_inicio + datetime.timedelta(days=dias - 1)
    calculations.simular_periodo(session, data_inicio, data_fim, cenario_id=cenario_id)


# ---------------------------------------------------------------------------
# 1. A janela de safra "sem cadastro" precisa continuar variando por ano ao
#    ser resolvida a partir de um valor cacheado -- nao pode "congelar" no
#    ano do primeiro dia simulado so porque o registro (None) foi cacheado.
# ---------------------------------------------------------------------------

def test_janela_safra_de_registro_fallback_varia_por_ano_quando_sem_cadastro():
    na_safra_2026, ini_2026, fim_2026 = calculations._janela_safra_de_registro(
        None, datetime.date(2026, 2, 1)
    )
    na_safra_2027, ini_2027, fim_2027 = calculations._janela_safra_de_registro(
        None, datetime.date(2027, 2, 1)
    )

    assert ini_2026 == datetime.date(2026, 1, 15) and fim_2026 == datetime.date(2026, 4, 15)
    assert ini_2027 == datetime.date(2027, 1, 15) and fim_2027 == datetime.date(2027, 4, 15)
    assert na_safra_2026 is True and na_safra_2027 is True


def test_janela_safra_de_registro_usa_datas_do_registro_quando_presente():
    safra = SafraUnidade(
        cenario_id=1, entidade_tipo='Armazém', entidade_id=1,
        data_inicio=datetime.date(2026, 2, 1), data_fim=datetime.date(2026, 3, 1),
    )
    na_safra, ini, fim = calculations._janela_safra_de_registro(safra, datetime.date(2026, 2, 15))
    assert na_safra is True
    assert ini == datetime.date(2026, 2, 1) and fim == datetime.date(2026, 3, 1)


# ---------------------------------------------------------------------------
# 2. otimizar_dia nao deve consultar o banco quando recebe dados
#    pre-carregados pelo chamador.
# ---------------------------------------------------------------------------

def test_otimizar_dia_nao_consulta_banco_quando_dados_pre_carregados(session, engine):
    cenario = Cenario(nome="C", is_oficial=True)
    session.add(cenario)
    session.commit()
    fabrica, armazem, rota = _montar_cenario_basico(session, cenario.id, com_safra_cadastrada=False)

    estoques = {f'F_{fabrica.id}': 0, f'A_{armazem.id}': 5000}

    with QueryCounter(engine) as counter:
        calculations.otimizar_dia(
            session, datetime.date(2026, 2, 1), estoques, cenario_id=cenario.id,
            fabricas=[fabrica], armazens=[armazem], rotas=[rota], safra_cache={},
        )

    assert counter.count == 0, (
        f"otimizar_dia executou {counter.count} query(ies) mesmo recebendo "
        "fábricas/armazéns/rotas/safra_cache pré-carregados"
    )


# ---------------------------------------------------------------------------
# 3. simular_periodo: a contagem de queries nao pode crescer
#    proporcionalmente ao numero de dias simulados (era O(dias); precisa
#    virar ~O(1)). Este e o "benchmark antes/depois" pedido no roteiro,
#    como assercao automatizada em vez de nota manual de PR.
# ---------------------------------------------------------------------------

def test_simular_periodo_contagem_de_queries_nao_escala_com_dias(engine):
    # expire_on_commit=False: em `simular_periodo` real, o commit só ocorre
    # uma vez no final do laço de dias, então os objetos pré-carregados
    # nunca expiram/recarregam no meio da simulação. Os testes locais aqui
    # fazem commits mais cedo (para popular o cenário), então precisam da
    # mesma configuração para não medir queries de re-hidratação do ORM
    # como se fossem parte do padrão N+1 sendo testado.
    Session = sessionmaker(bind=engine, expire_on_commit=False)

    def _run(dias):
        session = Session()
        try:
            cenario = Cenario(nome=f"C{dias}", is_oficial=False)
            session.add(cenario)
            session.commit()
            _montar_cenario_basico(session, cenario.id, com_safra_cadastrada=False)
            with QueryCounter(engine) as counter:
                _rodar_simulacao(session, cenario.id, dias)
            return counter.count
        finally:
            session.close()

    queries_10_dias = _run(10)
    queries_40_dias = _run(40)

    # Antes do pre-carregamento, cada dia extra adicionava multiplas
    # queries (fabricas + armazens + rotas + 2x safra por rota + previsoes
    # por entidade); o delta crescia quase 1:1 com os dias. Depois do
    # pre-carregamento, o delta deve ficar pequeno e constante.
    delta = queries_40_dias - queries_10_dias
    assert delta < 10, (
        f"contagem de queries cresceu {delta} entre 10 e 40 dias simulados "
        "(esperado: crescimento praticamente nulo, nao proporcional aos dias)"
    )


# ---------------------------------------------------------------------------
# 4. Previsoes mensais: precisam continuar produzindo o mesmo resultado
#    quando pre-carregadas (nao reconsultadas a cada dia).
# ---------------------------------------------------------------------------

def test_simular_periodo_usa_previsoes_pre_carregadas_e_mantem_resultado(session):
    cenario = Cenario(nome="C", is_oficial=True)
    session.add(cenario)
    session.commit()
    fabrica, armazem, rota = _montar_cenario_basico(session, cenario.id, com_safra_cadastrada=False)

    session.add(PrevisaoFabrica(
        fabrica_id=fabrica.id, mes_referencia=datetime.date(2026, 1, 1),
        recebimento_produtor=3100, vendas=0,
    ))
    session.add(PrevisaoArmazem(
        armazem_id=armazem.id, mes_referencia=datetime.date(2026, 1, 1),
        recebimento_produtor=0, vendas=0,
    ))
    session.commit()

    _rodar_simulacao(session, cenario.id, dias=15)

    resumo = session.query(ResumoMensalFabrica).filter_by(
        cenario_id=cenario.id, fabrica_id=fabrica.id
    ).first()
    # 3100 Ton / 31 dias (janeiro) * 15 dias simulados
    assert resumo is not None
    assert round(resumo.rec_produtor, 2) == round(3100 / 31 * 15, 2)
