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

from django.db import transaction
from django.utils import timezone

from apps.simulacao.models import (
    Armazem,
    Cenario,
    Fabrica,
    PrevisaoArmazem,
    PrevisaoFabrica,
    Rota,
    SafraUnidade,
)


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


def _data_criacao_aware(valor):
    """`Cenario.data_criacao` no legado é nullable; no Django é
    `DateTimeField(default=timezone.now)`, sem `null=True`. Um `None` explícito
    aqui bypassa esse default e vira `IntegrityError` (NOT NULL). Por isso,
    ausência de valor cai no default do próprio modelo -- `timezone.now()` --
    em vez de propagar `None`.

    Para um valor presente, naive (horário local do Brasil, onde o app
    Streamlit roda), torná-lo aware evita o `RuntimeWarning` de "naive
    datetime" que o Django emite ao gravar um `DateTimeField` naive com
    `USE_TZ=True`."""
    if valor is None:
        return timezone.now()
    if timezone.is_naive(valor):
        return timezone.make_aware(valor)
    return valor


def _apagar_tenant(cooperativa):
    """Ordem inversa de dependência. Explícita em vez de confiar no cascade
    do `Cenario`, para não quebrar em silêncio se algum `on_delete` mudar."""
    SafraUnidade.all_cooperativas.filter(cooperativa=cooperativa).delete()
    PrevisaoFabrica.all_cooperativas.filter(cooperativa=cooperativa).delete()
    PrevisaoArmazem.all_cooperativas.filter(cooperativa=cooperativa).delete()
    Rota.all_cooperativas.filter(cooperativa=cooperativa).delete()
    Fabrica.all_cooperativas.filter(cooperativa=cooperativa).delete()
    Armazem.all_cooperativas.filter(cooperativa=cooperativa).delete()
    Cenario.all_cooperativas.filter(cooperativa=cooperativa).delete()


def escrever(dados: DadosLegado, cooperativa) -> dict[str, int]:
    """Substitui o conteúdo do tenant pelos dados do legado e devolve as
    contagens por tabela.

    DESTRUTIVO: apaga tudo o que o tenant tem antes de inserir. Edições
    feitas nas grades são perdidas. Ver §3 da spec.

    Usa `all_cooperativas` porque roda fora de request, sem contextvar de
    tenant definida -- `objects` devolveria queryset vazio (ADR 0006).

    O remapeamento de IDs espelha `services.clone_scenario`, que resolve o
    mesmo problema ao clonar um cenário.
    """
    with transaction.atomic():
        _apagar_tenant(cooperativa)

        cenario_map = {}
        for c in dados.cenarios:
            novo = Cenario.all_cooperativas.create(
                cooperativa=cooperativa,
                nome=c['nome'],
                is_oficial=c['is_oficial'],
                data_criacao=_data_criacao_aware(c['data_criacao']),
            )
            cenario_map[c['id']] = novo.id

        fabrica_map = {}
        for f in dados.fabricas:
            nova = Fabrica.all_cooperativas.create(
                cooperativa=cooperativa,
                cenario_id=cenario_map[f['cenario_id']],
                nome=f['nome'],
                capacidade_estatica=f['capacidade_estatica'],
                capacidade_esmagamento_diaria=f['capacidade_esmagamento_diaria'],
                capacidade_recebimento_diaria=f['capacidade_recebimento_diaria'],
                limite_caminhoes=f['limite_caminhoes'],
                carga_media_caminhao=f['carga_media_caminhao'],
                estoque_inicial=f['estoque_inicial'],
            )
            fabrica_map[f['id']] = nova.id

        armazem_map = {}
        for a in dados.armazens:
            novo = Armazem.all_cooperativas.create(
                cooperativa=cooperativa,
                cenario_id=cenario_map[a['cenario_id']],
                nome=a['nome'],
                capacidade_estatica=a['capacidade_estatica'],
                capacidade_expedicao_diaria=a['capacidade_expedicao_diaria'],
                estoque_inicial=a['estoque_inicial'],
            )
            armazem_map[a['id']] = novo.id

        rotas = [
            Rota(
                cooperativa=cooperativa,
                cenario_id=cenario_map[r['cenario_id']],
                armazem_id=armazem_map[r['armazem_id']],
                fabrica_id=fabrica_map[r['fabrica_id']],
                distancia_km=r['distancia_km'],
                custo_frete_ton=r['custo_frete_ton'],
                custo_frete_entressafra=r['custo_frete_entressafra'],
            )
            for r in dados.rotas
        ]
        Rota.all_cooperativas.bulk_create(rotas)

        previsoes_fabrica = [
            PrevisaoFabrica(
                cooperativa=cooperativa,
                fabrica_id=fabrica_map[p['fabrica_id']],
                mes_referencia=p['mes_referencia'],
                recebimento_produtor=p['recebimento_produtor'],
                vendas=p['vendas'],
            )
            for p in dados.previsoes_fabrica
        ]
        PrevisaoFabrica.all_cooperativas.bulk_create(previsoes_fabrica)

        previsoes_armazem = [
            PrevisaoArmazem(
                cooperativa=cooperativa,
                armazem_id=armazem_map[p['armazem_id']],
                mes_referencia=p['mes_referencia'],
                recebimento_produtor=p['recebimento_produtor'],
                vendas=p['vendas'],
            )
            for p in dados.previsoes_armazem
        ]
        PrevisaoArmazem.all_cooperativas.bulk_create(previsoes_armazem)

        # `entidade_id` é um IntegerField simples, sem FK dos dois lados: o
        # legado pode ter uma safra apontando para um armazém/fábrica que já
        # não existe. Espelhando `services.clone_scenario`, a linha órfã é
        # pulada em vez de abortar o espelhamento inteiro com um KeyError --
        # e a contagem devolvida reflete o que foi de fato gravado, para que
        # um `safras: 130` contra um esperado 133 torne o descarte visível.
        safras = []
        for s in dados.safras:
            entidade_map = armazem_map if s['entidade_tipo'] == 'Armazém' else fabrica_map
            novo_entidade_id = entidade_map.get(s['entidade_id'])
            if novo_entidade_id is None:
                continue
            safras.append(SafraUnidade(
                cooperativa=cooperativa,
                cenario_id=cenario_map[s['cenario_id']],
                entidade_tipo=s['entidade_tipo'],
                entidade_id=novo_entidade_id,
                data_inicio=s['data_inicio'],
                data_fim=s['data_fim'],
            ))
        SafraUnidade.all_cooperativas.bulk_create(safras)

    return {
        'cenarios': len(dados.cenarios),
        'fabricas': len(dados.fabricas),
        'armazens': len(dados.armazens),
        'rotas': len(rotas),
        'previsoes_fabrica': len(previsoes_fabrica),
        'previsoes_armazem': len(previsoes_armazem),
        'safras': len(safras),
    }
