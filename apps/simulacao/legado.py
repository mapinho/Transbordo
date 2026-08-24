"""Espelhamento dos dados de entrada do banco legado (stack Streamlit/SQLAlchemy)
para o schema Django.

Ferramenta de desenvolvimento com prazo de validade: morre quando o stack
Streamlit for aposentado e o banco `comigo` deixar de ser fonte. Ver
docs/superpowers/specs/2026-08-24-espelhamento-dados-legado-design.md.
"""
from dataclasses import dataclass, field

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models as legado


@dataclass
class DadosLegado:
    """Dados de entrada lidos do legado, como dicts puros.

    Deliberadamente sem nenhum objeto SQLAlchemy nem Django: é a fronteira
    que permite testar `escrever` sem o banco legado, e `ler_legado` sem o
    banco Django.
    """

    cenarios: list[dict] = field(default_factory=list)
    fabricas: list[dict] = field(default_factory=list)
    armazens: list[dict] = field(default_factory=list)
    rotas: list[dict] = field(default_factory=list)
    previsoes_fabrica: list[dict] = field(default_factory=list)
    previsoes_armazem: list[dict] = field(default_factory=list)
    safras: list[dict] = field(default_factory=list)


def abrir_sessao_legado(database_url: str):
    """Sessão SQLAlchemy sobre o banco legado.

    Não usa `data_loader.get_engine()` de propósito: aquele módulo importa
    Streamlit e chama `st.error`, o que não faz sentido num management command.
    """
    engine = create_engine(database_url)
    return sessionmaker(bind=engine)()


def ler_legado(session) -> DadosLegado:
    """Lê as sete tabelas de entrada. As tabelas de saída da otimização
    (movimentacoes_diarias, resumo_mensal_*, logs_execucao) ficam de fora:
    são regeneráveis pelo engine e nenhuma tela Django as lê ainda."""
    return DadosLegado(
        cenarios=[
            {
                'id': c.id,
                'nome': c.nome,
                'is_oficial': bool(c.is_oficial),
                'data_criacao': c.data_criacao,
            }
            for c in session.query(legado.Cenario).order_by(legado.Cenario.id)
        ],
        fabricas=[
            {
                'id': f.id,
                'cenario_id': f.cenario_id,
                'nome': f.nome,
                'capacidade_estatica': f.capacidade_estatica,
                'capacidade_esmagamento_diaria': f.capacidade_esmagamento_diaria,
                'capacidade_recebimento_diaria': f.capacidade_recebimento_diaria,
                'limite_caminhoes': f.limite_caminhoes,
                'carga_media_caminhao': f.carga_media_caminhao,
                'estoque_inicial': f.estoque_inicial,
            }
            for f in session.query(legado.Fabrica).order_by(legado.Fabrica.id)
        ],
        armazens=[
            {
                'id': a.id,
                'cenario_id': a.cenario_id,
                'nome': a.nome,
                'capacidade_estatica': a.capacidade_estatica,
                'capacidade_expedicao_diaria': a.capacidade_expedicao_diaria,
                'estoque_inicial': a.estoque_inicial,
            }
            for a in session.query(legado.Armazem).order_by(legado.Armazem.id)
        ],
        rotas=[
            {
                'cenario_id': r.cenario_id,
                'armazem_id': r.armazem_id,
                'fabrica_id': r.fabrica_id,
                'distancia_km': r.distancia_km,
                'custo_frete_ton': r.custo_frete_ton,
                'custo_frete_entressafra': r.custo_frete_entressafra,
            }
            for r in session.query(legado.Rota).order_by(legado.Rota.id)
        ],
        previsoes_fabrica=[
            {
                'fabrica_id': p.fabrica_id,
                'mes_referencia': p.mes_referencia,
                'recebimento_produtor': p.recebimento_produtor,
                'vendas': p.vendas,
            }
            for p in session.query(legado.PrevisaoFabrica).order_by(legado.PrevisaoFabrica.id)
        ],
        previsoes_armazem=[
            {
                'armazem_id': p.armazem_id,
                'mes_referencia': p.mes_referencia,
                'recebimento_produtor': p.recebimento_produtor,
                'vendas': p.vendas,
            }
            for p in session.query(legado.PrevisaoArmazem).order_by(legado.PrevisaoArmazem.id)
        ],
        safras=[
            {
                'cenario_id': s.cenario_id,
                'entidade_tipo': s.entidade_tipo,
                'entidade_id': s.entidade_id,
                'data_inicio': s.data_inicio,
                'data_fim': s.data_fim,
            }
            for s in session.query(legado.SafraUnidade).order_by(legado.SafraUnidade.id)
        ],
    )
