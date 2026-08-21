import math

import pandas as pd
import pytest

import data_loader
from models import Armazem, Fabrica, PrevisaoArmazem, PrevisaoFabrica, Rota


def _patch_read_excel(monkeypatch, df):
    """Faz load_* lerem um DataFrame já pronto em memória, em vez de um
    arquivo .xlsx real -- evita surpresas de round-trip do Excel e permite
    controlar exatamente onde ficam os NaN/valores malformados."""
    monkeypatch.setattr(data_loader.pd, "read_excel", lambda *args, **kwargs: df)


# ---------------------------------------------------------------------------
# Bug A8 -- célula em branco vira NaN, que satisfeita silenciosamente colunas
# NOT NULL (NaN é um double precision válido e distinto de NULL no Postgres).
# ---------------------------------------------------------------------------

class TestBugA8NaoGravaNaNEmCampoObrigatorio:
    def test_load_factories_pula_linha_com_capacidade_estatica_nan(self, session, cenario, monkeypatch):
        df = pd.DataFrame([
            {
                "nome": "Fabrica Valida",
                "capacidade_estatica": 10000,
                "capacidade_esmagamento_diaria": 500,
                "capacidade_recebimento_diaria": 600,
                "limite_caminhoes": 20,
                "carga_media_caminhao": 30,
                "estoque_inicial": 1000,
            },
            {
                "nome": "Fabrica Quebrada",
                "capacidade_estatica": float("nan"),  # célula em branco no Excel
                "capacidade_esmagamento_diaria": 500,
                "capacidade_recebimento_diaria": 600,
                "limite_caminhoes": 20,
                "carga_media_caminhao": 30,
                "estoque_inicial": 1000,
            },
        ])
        _patch_read_excel(monkeypatch, df)

        data_loader.load_factories("fake.xlsx", cenario.id, session=session)

        fabricas = session.query(Fabrica).filter_by(cenario_id=cenario.id).all()
        nomes = {f.nome for f in fabricas}

        assert "Fabrica Valida" in nomes
        assert "Fabrica Quebrada" not in nomes, (
            "Linha com capacidade_estatica NaN não pode ser gravada no banco"
        )
        for f in fabricas:
            assert not math.isnan(f.capacidade_estatica)

    def test_load_factories_conta_apenas_linhas_validas(self, session, cenario, monkeypatch):
        df = pd.DataFrame([
            {
                "nome": "Fabrica Valida",
                "capacidade_estatica": 10000,
                "capacidade_esmagamento_diaria": 500,
                "capacidade_recebimento_diaria": 600,
                "limite_caminhoes": 20,
                "carga_media_caminhao": 30,
                "estoque_inicial": 1000,
            },
            {
                "nome": "Fabrica Quebrada",
                "capacidade_estatica": 10000,
                "capacidade_esmagamento_diaria": float("nan"),
                "capacidade_recebimento_diaria": 600,
                "limite_caminhoes": 20,
                "carga_media_caminhao": 30,
                "estoque_inicial": 1000,
            },
        ])
        _patch_read_excel(monkeypatch, df)

        count = data_loader.load_factories("fake.xlsx", cenario.id, session=session)

        assert count == 1

    def test_load_warehouses_pula_linha_com_estoque_inicial_nan(self, session, cenario, monkeypatch):
        df = pd.DataFrame([
            {
                "nome": "Armazem Valido",
                "capacidade_estatica": 5000,
                "capacidade_expedicao_diaria": 300,
                "estoque_inicial": 2000,
            },
            {
                "nome": "Armazem Quebrado",
                "capacidade_estatica": 5000,
                "capacidade_expedicao_diaria": 300,
                "estoque_inicial": float("nan"),
            },
        ])
        _patch_read_excel(monkeypatch, df)

        data_loader.load_warehouses("fake.xlsx", cenario.id, session=session)

        armazens = session.query(Armazem).filter_by(cenario_id=cenario.id).all()
        nomes = {a.nome for a in armazens}

        assert "Armazem Valido" in nomes
        assert "Armazem Quebrado" not in nomes, (
            "Linha com estoque_inicial NaN não pode ser gravada no banco"
        )
        for a in armazens:
            assert not math.isnan(a.estoque_inicial)

    def test_load_warehouses_nao_atualiza_registro_existente_com_nan(self, session, cenario, armazem, monkeypatch):
        """Se o armazém já existe e a nova planilha traz uma célula NaN, o
        registro existente não pode ser parcialmente sobrescrito com NaN."""
        df = pd.DataFrame([
            {
                "nome": armazem.nome,
                "capacidade_estatica": float("nan"),
                "capacidade_expedicao_diaria": 999,
                "estoque_inicial": 999,
            },
        ])
        _patch_read_excel(monkeypatch, df)

        original_capacidade = armazem.capacidade_estatica
        data_loader.load_warehouses("fake.xlsx", cenario.id, session=session)

        session.refresh(armazem)
        assert not math.isnan(armazem.capacidade_estatica)
        assert armazem.capacidade_estatica == original_capacidade
        # Nenhum campo deve ter sido meio-atualizado
        assert armazem.capacidade_expedicao_diaria != 999


# ---------------------------------------------------------------------------
# Bug A9 -- .get(col, default) só cobre COLUNA ausente, não CÉLULA em branco.
# ---------------------------------------------------------------------------

class TestBugA9FallbackDeveTratarCelulaEmBrancoComoAusente:
    def test_load_routes_usa_fallback_quando_celula_entressafra_e_nan(self, session, cenario, armazem, fabrica, monkeypatch):
        df = pd.DataFrame([
            {
                "origem": armazem.nome,
                "destino": fabrica.nome,
                "distancia_km": 100,
                "custo_frete_ton": 25.0,
                "custo_frete_entressafra": float("nan"),  # coluna existe, célula em branco
            },
        ])
        _patch_read_excel(monkeypatch, df)

        data_loader.load_routes("fake.xlsx", cenario.id, session=session)

        rota = session.query(Rota).filter_by(cenario_id=cenario.id, armazem_id=armazem.id, fabrica_id=fabrica.id).first()
        assert rota is not None
        assert rota.custo_frete_entressafra == 25.0
        assert not (isinstance(rota.custo_frete_entressafra, float) and math.isnan(rota.custo_frete_entressafra))

    def test_load_routes_usa_valor_quando_celula_entressafra_preenchida(self, session, cenario, armazem, fabrica, monkeypatch):
        df = pd.DataFrame([
            {
                "origem": armazem.nome,
                "destino": fabrica.nome,
                "distancia_km": 100,
                "custo_frete_ton": 25.0,
                "custo_frete_entressafra": 18.5,
            },
        ])
        _patch_read_excel(monkeypatch, df)

        data_loader.load_routes("fake.xlsx", cenario.id, session=session)

        rota = session.query(Rota).filter_by(cenario_id=cenario.id, armazem_id=armazem.id, fabrica_id=fabrica.id).first()
        assert rota.custo_frete_entressafra == 18.5

    def test_load_routes_usa_fallback_quando_coluna_entressafra_totalmente_ausente(self, session, cenario, armazem, fabrica, monkeypatch):
        df = pd.DataFrame([
            {
                "origem": armazem.nome,
                "destino": fabrica.nome,
                "distancia_km": 100,
                "custo_frete_ton": 30.0,
                # sem a coluna custo_frete_entressafra
            },
        ])
        _patch_read_excel(monkeypatch, df)

        data_loader.load_routes("fake.xlsx", cenario.id, session=session)

        rota = session.query(Rota).filter_by(cenario_id=cenario.id, armazem_id=armazem.id, fabrica_id=fabrica.id).first()
        assert rota.custo_frete_entressafra == 30.0

    def test_load_previsoes_usa_zero_quando_celula_recebimento_e_vendas_sao_nan(self, session, cenario, fabrica, monkeypatch):
        df = pd.DataFrame([
            {
                "entidade": fabrica.nome,
                "mes_referencia": "2026-03-01",
                "recebimento_produtor": float("nan"),
                "vendas": float("nan"),
            },
        ])
        _patch_read_excel(monkeypatch, df)

        data_loader.load_previsoes("fake.xlsx", cenario.id, session=session)

        prev = session.query(PrevisaoFabrica).filter_by(fabrica_id=fabrica.id).first()
        assert prev is not None
        assert prev.recebimento_produtor == 0
        assert prev.vendas == 0


# ---------------------------------------------------------------------------
# Bug A10 -- nenhuma linha malformada pode abortar o import inteiro sem
# feedback, perdendo o progresso das linhas já processadas na mesma chamada.
# ---------------------------------------------------------------------------

class TestBugA10NaoDeveCrasharEmLinhaMalformada:
    def test_load_previsoes_data_invalida_nao_derruba_outras_linhas_validas(self, session, cenario, fabrica, monkeypatch):
        df = pd.DataFrame([
            {
                "entidade": fabrica.nome,
                "mes_referencia": "isso-nao-e-uma-data",  # dispara ValueError em pd.to_datetime
                "recebimento_produtor": 100,
                "vendas": 50,
            },
            {
                "entidade": fabrica.nome,
                "mes_referencia": "2026-04-01",
                "recebimento_produtor": 200,
                "vendas": 80,
            },
        ])
        _patch_read_excel(monkeypatch, df)

        # Não deve levantar exceção
        count, skipped = data_loader.load_previsoes("fake.xlsx", cenario.id, session=session)

        assert count == 1
        assert skipped >= 1

        previsoes = session.query(PrevisaoFabrica).filter_by(fabrica_id=fabrica.id).all()
        assert len(previsoes) == 1
        assert previsoes[0].recebimento_produtor == 200
        assert previsoes[0].vendas == 80

    def test_load_routes_coluna_obrigatoria_ausente_nao_crasha(self, session, cenario, armazem, fabrica, monkeypatch):
        """Linha malformada (coluna 'distancia_km' totalmente ausente) deve ser
        ignorada com feedback, sem derrubar a chamada inteira com traceback."""
        df = pd.DataFrame([
            {
                "origem": armazem.nome,
                "destino": fabrica.nome,
                "custo_frete_ton": 25.0,
                # 'distancia_km' ausente -> KeyError na versão antiga do código
            },
        ])
        _patch_read_excel(monkeypatch, df)

        count, skipped = data_loader.load_routes("fake.xlsx", cenario.id, session=session)

        assert count == 0
        assert skipped >= 1
        assert session.query(Rota).filter_by(cenario_id=cenario.id).count() == 0

    def test_load_factories_linha_malformada_nao_impede_linhas_validas(self, session, cenario, monkeypatch):
        """Uma exceção inesperada em uma linha (aqui, um tipo que quebra a
        checagem de nome) não pode impedir que outras linhas válidas do
        mesmo arquivo sejam importadas."""
        df = pd.DataFrame([
            {
                "nome": "Fabrica Com Falha",
                "capacidade_estatica": 10000,
                "capacidade_esmagamento_diaria": 500,
                "capacidade_recebimento_diaria": 600,
                "limite_caminhoes": 20,
                "carga_media_caminhao": 30,
                "estoque_inicial": 1000,
            },
            {
                "nome": "Fabrica OK",
                "capacidade_estatica": 20000,
                "capacidade_esmagamento_diaria": 800,
                "capacidade_recebimento_diaria": 900,
                "limite_caminhoes": 25,
                "carga_media_caminhao": 35,
                "estoque_inicial": 500,
            },
        ])
        _patch_read_excel(monkeypatch, df)

        # Corrompe a query do SQLAlchemy só na primeira linha para simular uma
        # falha inesperada em runtime (ex.: erro de conexão/driver) sem afetar
        # a segunda linha processada.
        original_query = session.query
        call_count = {"n": 0}

        def flaky_query(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("falha simulada de banco")
            return original_query(*args, **kwargs)

        monkeypatch.setattr(session, "query", flaky_query)

        # Não deve propagar a exceção, e a segunda linha (válida) deve ser
        # importada mesmo com a falha na primeira.
        count = data_loader.load_factories("fake.xlsx", cenario.id, session=session)

        assert count == 1
        nomes = {f.nome for f in session.query(Fabrica).filter_by(cenario_id=cenario.id).all()}
        assert "Fabrica OK" in nomes
        assert "Fabrica Com Falha" not in nomes
