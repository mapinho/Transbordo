# Espelhamento de Dados do Legado — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir uma ferramenta de desenvolvimento re-executável que espelha os dados de entrada do banco legado `comigo` (Streamlit/SQLAlchemy) para o schema Django, atribuídos a um tenant, de modo que as cinco grades da fase anterior possam ser exercitadas contra dados reais.

**Architecture:** Um módulo `apps/simulacao/legado.py` com duas funções de responsabilidade única e sem conhecimento uma da outra — `ler_legado(session)` devolve dicts puros lidos via o ORM SQLAlchemy da raiz, e `escrever(dados, cooperativa)` consome esses dicts e escreve no schema Django, apagando e recarregando o tenant inteiro dentro de uma transação. Um management command `espelhar_legado` cola as duas e carrega as guardas. A separação existe para que toda a lógica não-trivial (remapeamento de IDs, ordem de inserção) seja testável sem o banco legado, que não existe na CI.

**Tech Stack:** Django 6, SQLAlchemy 2.0 (leitura do legado), PostgreSQL (ambos os bancos), pytest + pytest-django.

**Spec:** `docs/superpowers/specs/2026-08-24-espelhamento-dados-legado-design.md`

## Global Constraints

- **TDD estrito (red → green).** Escrever o teste que falha primeiro, confirmar que falha pela razão certa, implementar o mínimo, confirmar que passa. É a regra do projeto (`CLAUDE.md`).
- **Fora de request, usar `all_cooperativas`, nunca `objects`.** O comando roda sem contextvar de tenant definida; `objects` (TenantManager) devolveria queryset vazio por design de falha-fechada. Ver `docs/decisions/0006-engine-services-usam-all-cooperativas.md`.
- **Toda a escrita dentro de um único `transaction.atomic()`.** Ou o tenant inteiro é substituído, ou nada é.
- **Não espelhar tabelas de saída da otimização:** `movimentacoes_diarias`, `resumo_mensal_fabrica`, `resumo_mensal_armazem`, `logs_execucao`.
- **`USE_TZ = True` e `TIME_ZONE = 'America/Sao_Paulo'`.** Os datetimes do legado são naive e devem virar aware explicitamente antes de serem escritos. **Correção pós-revisão:** a justificativa original desta linha — "ou Django os interpreta como UTC e desloca tudo em 3 horas" — é **falsa**. O Django 6 emite um `RuntimeWarning` e chama `make_aware` com o `TIME_ZONE` default, que é o mesmo fuso em que os valores foram gravados; não há deslocamento. A conversão explícita fica valendo por eliminar o warning (saída de teste impecável é constraint deste projeto) e por deixar a intenção legível. Os trechos de código das Tasks 2 abaixo refletem o plano original e foram superados pelo round de correção; a spec tem o registro correto.
- **A convenção de `entidade_tipo`:** o valor `'Armazém'` (com acento) identifica armazém; qualquer outro valor identifica fábrica. É o que `apps/simulacao/views.py::safras_grid` e `services.clone_scenario` já assumem.
- Rodar a suíte com `python -m pytest`. Os testes Django exigem o PostgreSQL local alcançável via `DJANGO_DB_*`.

---

## File Structure

| Arquivo | Responsabilidade |
|---|---|
| `apps/simulacao/legado.py` (criar) | `DadosLegado`, `abrir_sessao_legado`, `ler_legado`, `escrever`. Único módulo novo de produção. |
| `apps/simulacao/management/__init__.py` (criar) | Pacote vazio exigido pelo Django. |
| `apps/simulacao/management/commands/__init__.py` (criar) | Pacote vazio exigido pelo Django. |
| `apps/simulacao/management/commands/espelhar_legado.py` (criar) | Argparse, guardas, confirmação. Sem lógica de dados. |
| `apps/simulacao/tests/test_legado_leitura.py` (criar) | Testes de `ler_legado` — SQLite em memória, sem banco Django. |
| `apps/simulacao/tests/test_legado_escrita.py` (criar) | Testes de `escrever` — Django `TestCase`. |
| `apps/simulacao/tests/test_command_espelhar_legado.py` (criar) | Testes das guardas do comando. |

**Refinamento em relação à spec §2:** a spec descreve `ler_legado(database_url)`. O plano usa `ler_legado(session)`, recebendo uma `Session` SQLAlchemy já aberta, com a construção da engine isolada em `abrir_sessao_legado(database_url)`. Motivo: uma URL de SQLite em memória cria um banco novo e vazio a cada conexão, então uma função que constrói a própria engine é impossível de testar sem um Postgres legado. Injetar a sessão torna `ler_legado` testável com o mesmo padrão que `tests/conftest.py` já usa. A spec é atualizada no Step 9 da Task 3.

---

### Task 1: Leitura do banco legado (`DadosLegado` + `ler_legado`)

**Files:**
- Create: `apps/simulacao/legado.py`
- Test: `apps/simulacao/tests/test_legado_leitura.py`

**Interfaces:**
- Consumes: os models SQLAlchemy da raiz (`models.py`), importados como `import models as legado`. O `pytest.ini` define `pythonpath = .`, então o módulo da raiz é importável por esse nome de dentro do app.
- Produces:
  - `DadosLegado` — dataclass com sete atributos, todos `list[dict]`: `cenarios`, `fabricas`, `armazens`, `rotas`, `previsoes_fabrica`, `previsoes_armazem`, `safras`.
  - `abrir_sessao_legado(database_url: str) -> sqlalchemy.orm.Session`
  - `ler_legado(session) -> DadosLegado`
  - Chaves exatas de cada dict, consumidas pela Task 2:
    - `cenarios`: `id`, `nome`, `is_oficial`, `data_criacao`
    - `fabricas`: `id`, `cenario_id`, `nome`, `capacidade_estatica`, `capacidade_esmagamento_diaria`, `capacidade_recebimento_diaria`, `limite_caminhoes`, `carga_media_caminhao`, `estoque_inicial`
    - `armazens`: `id`, `cenario_id`, `nome`, `capacidade_estatica`, `capacidade_expedicao_diaria`, `estoque_inicial`
    - `rotas`: `cenario_id`, `armazem_id`, `fabrica_id`, `distancia_km`, `custo_frete_ton`, `custo_frete_entressafra`
    - `previsoes_fabrica`: `fabrica_id`, `mes_referencia`, `recebimento_produtor`, `vendas`
    - `previsoes_armazem`: `armazem_id`, `mes_referencia`, `recebimento_produtor`, `vendas`
    - `safras`: `cenario_id`, `entidade_tipo`, `entidade_id`, `data_inicio`, `data_fim`

- [ ] **Step 1: Escrever os testes que falham**

Criar `apps/simulacao/tests/test_legado_leitura.py`:

```python
import datetime

from django.test import SimpleTestCase
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models as legado
from apps.simulacao.legado import ler_legado


class LerLegadoTests(SimpleTestCase):
    """Exercita ler_legado contra um SQLite em memória construído a partir
    do metadata do ORM legado -- mesmo padrão de tests/conftest.py. Não toca
    no banco Django, por isso SimpleTestCase."""

    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        legado.Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()

        cenario = legado.Cenario(
            nome='Oficial (Planejado)',
            is_oficial=True,
            data_criacao=datetime.datetime(2026, 6, 1, 14, 19, 30),
        )
        self.session.add(cenario)
        self.session.flush()

        fabrica = legado.Fabrica(
            cenario_id=cenario.id, nome='FÁBRICA RIO VERDE',
            capacidade_estatica=50000, capacidade_esmagamento_diaria=1200,
            capacidade_recebimento_diaria=2000, limite_caminhoes=60,
            carga_media_caminhao=36, estoque_inicial=8000,
        )
        armazem = legado.Armazem(
            cenario_id=cenario.id, nome='JATAÍ',
            capacidade_estatica=30000, capacidade_expedicao_diaria=900,
            estoque_inicial=12000,
        )
        self.session.add_all([fabrica, armazem])
        self.session.flush()

        self.session.add_all([
            legado.Rota(
                cenario_id=cenario.id, armazem_id=armazem.id, fabrica_id=fabrica.id,
                distancia_km=118.5, custo_frete_ton=42.75, custo_frete_entressafra=38.0,
            ),
            legado.PrevisaoFabrica(
                fabrica_id=fabrica.id, mes_referencia=datetime.date(2026, 3, 1),
                recebimento_produtor=4500.5, vendas=1200.25,
            ),
            legado.PrevisaoArmazem(
                armazem_id=armazem.id, mes_referencia=datetime.date(2026, 3, 1),
                recebimento_produtor=7800.0, vendas=300.0,
            ),
            legado.SafraUnidade(
                cenario_id=cenario.id, entidade_tipo='Armazém', entidade_id=armazem.id,
                data_inicio=datetime.date(2026, 2, 1), data_fim=datetime.date(2026, 5, 31),
            ),
        ])
        self.session.commit()

        self.cenario_id = cenario.id
        self.fabrica_id = fabrica.id
        self.armazem_id = armazem.id

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_le_as_sete_tabelas_de_entrada(self):
        dados = ler_legado(self.session)

        self.assertEqual(len(dados.cenarios), 1)
        self.assertEqual(len(dados.fabricas), 1)
        self.assertEqual(len(dados.armazens), 1)
        self.assertEqual(len(dados.rotas), 1)
        self.assertEqual(len(dados.previsoes_fabrica), 1)
        self.assertEqual(len(dados.previsoes_armazem), 1)
        self.assertEqual(len(dados.safras), 1)

    def test_cenario_carrega_todos_os_campos(self):
        dados = ler_legado(self.session)

        self.assertEqual(dados.cenarios[0], {
            'id': self.cenario_id,
            'nome': 'Oficial (Planejado)',
            'is_oficial': True,
            'data_criacao': datetime.datetime(2026, 6, 1, 14, 19, 30),
        })

    def test_fabrica_e_armazem_carregam_o_cenario_de_origem(self):
        dados = ler_legado(self.session)

        self.assertEqual(dados.fabricas[0]['cenario_id'], self.cenario_id)
        self.assertEqual(dados.fabricas[0]['nome'], 'FÁBRICA RIO VERDE')
        self.assertEqual(dados.fabricas[0]['limite_caminhoes'], 60)
        self.assertEqual(dados.armazens[0]['cenario_id'], self.cenario_id)
        self.assertEqual(dados.armazens[0]['nome'], 'JATAÍ')
        self.assertEqual(dados.armazens[0]['capacidade_expedicao_diaria'], 900)

    def test_rota_referencia_fabrica_e_armazem_pelo_id_legado(self):
        dados = ler_legado(self.session)

        self.assertEqual(dados.rotas[0]['armazem_id'], self.armazem_id)
        self.assertEqual(dados.rotas[0]['fabrica_id'], self.fabrica_id)
        self.assertEqual(dados.rotas[0]['custo_frete_entressafra'], 38.0)

    def test_previsoes_nao_carregam_cenario_id(self):
        """previsoes_fabrica/previsoes_armazem genuinamente não têm essa coluna
        no schema legado -- o escopo por cenário vem da fábrica/armazém."""
        dados = ler_legado(self.session)

        self.assertNotIn('cenario_id', dados.previsoes_fabrica[0])
        self.assertNotIn('cenario_id', dados.previsoes_armazem[0])
        self.assertEqual(dados.previsoes_fabrica[0]['fabrica_id'], self.fabrica_id)
        self.assertEqual(dados.previsoes_armazem[0]['armazem_id'], self.armazem_id)

    def test_safra_carrega_tipo_e_entidade(self):
        dados = ler_legado(self.session)

        self.assertEqual(dados.safras[0]['entidade_tipo'], 'Armazém')
        self.assertEqual(dados.safras[0]['entidade_id'], self.armazem_id)
        self.assertEqual(dados.safras[0]['data_inicio'], datetime.date(2026, 2, 1))
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `python -m pytest apps/simulacao/tests/test_legado_leitura.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'apps.simulacao.legado'`

- [ ] **Step 3: Escrever `legado.py` com a parte de leitura**

Criar `apps/simulacao/legado.py`:

```python
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
```

- [ ] **Step 4: Rodar os testes e confirmar que passam**

Run: `python -m pytest apps/simulacao/tests/test_legado_leitura.py -v`
Expected: PASS (6 testes)

- [ ] **Step 5: Commit**

```bash
git add apps/simulacao/legado.py apps/simulacao/tests/test_legado_leitura.py
git commit -m "feat(legado): ler dados de entrada do banco legado"
```

---

### Task 2: Escrita no schema Django (`escrever`)

**Files:**
- Modify: `apps/simulacao/legado.py` (acrescentar ao final)
- Test: `apps/simulacao/tests/test_legado_escrita.py`

**Interfaces:**
- Consumes: `DadosLegado` da Task 1, com as chaves de dict exatas listadas lá.
- Produces: `escrever(dados: DadosLegado, cooperativa) -> dict[str, int]`. O parâmetro `cooperativa` é uma instância de `apps.core.models.Cooperativa` já persistida. O retorno mapeia nome de tabela para número de linhas escritas, com estas sete chaves exatas, consumidas pela Task 3: `'cenarios'`, `'fabricas'`, `'armazens'`, `'rotas'`, `'previsoes_fabrica'`, `'previsoes_armazem'`, `'safras'`.

**Nota de implementação:** a lógica de remapeamento é a mesma de `apps/simulacao/services.py::clone_scenario`, que já resolve exatamente este problema ao clonar um cenário. Ler aquela função antes de escrever esta — inclusive o trecho que trata `SafraUnidade.entidade_tipo == 'Armazém'`.

- [ ] **Step 1: Escrever os testes que falham**

Criar `apps/simulacao/tests/test_legado_escrita.py`:

```python
import datetime

from django.test import TestCase
from django.utils import timezone

from apps.core.models import Cooperativa
from apps.simulacao.legado import DadosLegado, escrever
from apps.simulacao.models import (
    Armazem, Cenario, Fabrica, PrevisaoArmazem, PrevisaoFabrica, Rota, SafraUnidade,
)


def dados_de_exemplo():
    """Dois cenários, cada um com 1 fábrica + 1 armazém + 1 rota + previsões
    + 1 safra. Os IDs legados são deliberadamente altos e esparsos para que
    um remapeamento faltante fique evidente."""
    return DadosLegado(
        cenarios=[
            {'id': 6, 'nome': 'Oficial (Planejado)', 'is_oficial': True,
             'data_criacao': datetime.datetime(2026, 6, 1, 14, 19, 30)},
            {'id': 7, 'nome': 'Replanejado com Vendas', 'is_oficial': False,
             'data_criacao': datetime.datetime(2026, 6, 3, 13, 32, 48)},
        ],
        fabricas=[
            {'id': 101, 'cenario_id': 6, 'nome': 'FÁBRICA RIO VERDE',
             'capacidade_estatica': 50000, 'capacidade_esmagamento_diaria': 1200,
             'capacidade_recebimento_diaria': 2000, 'limite_caminhoes': 60,
             'carga_media_caminhao': 36, 'estoque_inicial': 8000},
            {'id': 102, 'cenario_id': 7, 'nome': 'FÁBRICA RIO VERDE',
             'capacidade_estatica': 50000, 'capacidade_esmagamento_diaria': 1200,
             'capacidade_recebimento_diaria': 2000, 'limite_caminhoes': 60,
             'carga_media_caminhao': 36, 'estoque_inicial': 8000},
        ],
        armazens=[
            {'id': 201, 'cenario_id': 6, 'nome': 'JATAÍ', 'capacidade_estatica': 30000,
             'capacidade_expedicao_diaria': 900, 'estoque_inicial': 12000},
            {'id': 202, 'cenario_id': 7, 'nome': 'JATAÍ', 'capacidade_estatica': 30000,
             'capacidade_expedicao_diaria': 900, 'estoque_inicial': 12000},
        ],
        rotas=[
            {'cenario_id': 6, 'armazem_id': 201, 'fabrica_id': 101,
             'distancia_km': 118.5, 'custo_frete_ton': 42.75, 'custo_frete_entressafra': 38.0},
            {'cenario_id': 7, 'armazem_id': 202, 'fabrica_id': 102,
             'distancia_km': 118.5, 'custo_frete_ton': 44.0, 'custo_frete_entressafra': 38.0},
        ],
        previsoes_fabrica=[
            {'fabrica_id': 101, 'mes_referencia': datetime.date(2026, 3, 1),
             'recebimento_produtor': 4500.5, 'vendas': 1200.25},
            {'fabrica_id': 102, 'mes_referencia': datetime.date(2026, 3, 1),
             'recebimento_produtor': 4500.5, 'vendas': 1800.0},
        ],
        previsoes_armazem=[
            {'armazem_id': 201, 'mes_referencia': datetime.date(2026, 3, 1),
             'recebimento_produtor': 7800.0, 'vendas': 300.0},
        ],
        safras=[
            {'cenario_id': 6, 'entidade_tipo': 'Armazém', 'entidade_id': 201,
             'data_inicio': datetime.date(2026, 2, 1), 'data_fim': datetime.date(2026, 5, 31)},
            {'cenario_id': 6, 'entidade_tipo': 'Fábrica', 'entidade_id': 101,
             'data_inicio': datetime.date(2026, 2, 15), 'data_fim': datetime.date(2026, 6, 15)},
        ],
    )


class EscreverTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome='Comigo', slug='comigo')

    def test_contagens_retornadas_batem_com_a_entrada(self):
        contagens = escrever(dados_de_exemplo(), self.coop)

        self.assertEqual(contagens, {
            'cenarios': 2, 'fabricas': 2, 'armazens': 2, 'rotas': 2,
            'previsoes_fabrica': 2, 'previsoes_armazem': 1, 'safras': 2,
        })

    def test_toda_linha_escrita_pertence_ao_tenant(self):
        escrever(dados_de_exemplo(), self.coop)

        for modelo in (Cenario, Fabrica, Armazem, Rota,
                       PrevisaoFabrica, PrevisaoArmazem, SafraUnidade):
            linhas = list(modelo.all_cooperativas.all())
            self.assertTrue(linhas, f'{modelo.__name__} não escreveu nada')
            for linha in linhas:
                self.assertEqual(
                    linha.cooperativa_id, self.coop.id,
                    f'{modelo.__name__} {linha.id} caiu no tenant errado',
                )

    def test_ids_sao_remapeados_e_nao_reaproveitam_os_do_legado(self):
        escrever(dados_de_exemplo(), self.coop)

        oficial = Cenario.all_cooperativas.get(nome='Oficial (Planejado)')
        fabrica = Fabrica.all_cooperativas.get(cenario_id=oficial.id)
        self.assertNotEqual(fabrica.id, 101)
        self.assertEqual(fabrica.nome, 'FÁBRICA RIO VERDE')

    def test_rota_aponta_para_fabrica_e_armazem_do_mesmo_cenario(self):
        escrever(dados_de_exemplo(), self.coop)

        for rota in Rota.all_cooperativas.all():
            self.assertEqual(rota.armazem.cenario_id, rota.cenario_id)
            self.assertEqual(rota.fabrica.cenario_id, rota.cenario_id)

    def test_safra_de_armazem_remapeia_entidade_id_para_o_armazem_django(self):
        escrever(dados_de_exemplo(), self.coop)

        oficial = Cenario.all_cooperativas.get(nome='Oficial (Planejado)')
        armazem = Armazem.all_cooperativas.get(cenario_id=oficial.id)
        safra = SafraUnidade.all_cooperativas.get(entidade_tipo='Armazém')

        self.assertEqual(safra.entidade_id, armazem.id)
        self.assertNotEqual(safra.entidade_id, 201)

    def test_safra_de_fabrica_remapeia_entidade_id_para_a_fabrica_django(self):
        escrever(dados_de_exemplo(), self.coop)

        oficial = Cenario.all_cooperativas.get(nome='Oficial (Planejado)')
        fabrica = Fabrica.all_cooperativas.get(cenario_id=oficial.id)
        safra = SafraUnidade.all_cooperativas.get(entidade_tipo='Fábrica')

        self.assertEqual(safra.entidade_id, fabrica.id)
        self.assertNotEqual(safra.entidade_id, 101)

    def test_previsao_segue_a_fabrica_do_cenario_correspondente(self):
        escrever(dados_de_exemplo(), self.coop)

        replanejado = Cenario.all_cooperativas.get(nome='Replanejado com Vendas')
        fabrica = Fabrica.all_cooperativas.get(cenario_id=replanejado.id)
        previsao = PrevisaoFabrica.all_cooperativas.get(fabrica_id=fabrica.id)

        self.assertEqual(previsao.vendas, 1800.0)

    def test_data_criacao_vira_aware_sem_deslocar_o_horario(self):
        """USE_TZ=True: escrever o datetime naive do legado sem converter faria
        o Django interpretá-lo como UTC, deslocando tudo em 3 horas."""
        escrever(dados_de_exemplo(), self.coop)

        oficial = Cenario.all_cooperativas.get(nome='Oficial (Planejado)')
        local = timezone.localtime(oficial.data_criacao)

        self.assertIsNotNone(oficial.data_criacao.tzinfo)
        self.assertEqual(
            (local.year, local.month, local.day, local.hour, local.minute),
            (2026, 6, 1, 14, 19),
        )

    def test_e_idempotente_entre_execucoes(self):
        primeira = escrever(dados_de_exemplo(), self.coop)
        segunda = escrever(dados_de_exemplo(), self.coop)

        self.assertEqual(primeira, segunda)
        self.assertEqual(Cenario.all_cooperativas.count(), 2)
        self.assertEqual(Fabrica.all_cooperativas.count(), 2)
        self.assertEqual(Rota.all_cooperativas.count(), 2)
        self.assertEqual(SafraUnidade.all_cooperativas.count(), 2)

    def test_nao_toca_nas_linhas_de_um_tenant_vizinho(self):
        vizinha = Cooperativa.objects.create(nome='Outra', slug='outra')
        cenario_vizinho = Cenario.all_cooperativas.create(
            cooperativa=vizinha, nome='Intocado', is_oficial=True,
        )
        Fabrica.all_cooperativas.create(
            cooperativa=vizinha, cenario=cenario_vizinho, nome='NÃO MEXER',
            capacidade_estatica=1, capacidade_esmagamento_diaria=1,
            capacidade_recebimento_diaria=1, limite_caminhoes=1,
            carga_media_caminhao=1, estoque_inicial=1,
        )

        escrever(dados_de_exemplo(), self.coop)
        escrever(dados_de_exemplo(), self.coop)

        self.assertEqual(Cenario.all_cooperativas.filter(cooperativa=vizinha).count(), 1)
        self.assertEqual(Fabrica.all_cooperativas.filter(cooperativa=vizinha).count(), 1)
        self.assertTrue(
            Fabrica.all_cooperativas.filter(cooperativa=vizinha, nome='NÃO MEXER').exists()
        )
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `python -m pytest apps/simulacao/tests/test_legado_escrita.py -v`
Expected: FAIL com `ImportError: cannot import name 'escrever' from 'apps.simulacao.legado'`

- [ ] **Step 3: Acrescentar `escrever` a `apps/simulacao/legado.py`**

Acrescentar os imports no topo do arquivo, abaixo dos que já existem:

```python
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
```

Acrescentar ao final do arquivo:

```python
def _tornar_aware(valor):
    """Datetimes do legado são naive e foram gravados em horário local
    (o app Streamlit roda no Brasil). Com USE_TZ=True, escrevê-los sem
    converter faria o Django tratá-los como UTC."""
    if valor is None:
        return None
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
                data_criacao=_tornar_aware(c['data_criacao']),
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

        Rota.all_cooperativas.bulk_create([
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
        ])

        PrevisaoFabrica.all_cooperativas.bulk_create([
            PrevisaoFabrica(
                cooperativa=cooperativa,
                fabrica_id=fabrica_map[p['fabrica_id']],
                mes_referencia=p['mes_referencia'],
                recebimento_produtor=p['recebimento_produtor'],
                vendas=p['vendas'],
            )
            for p in dados.previsoes_fabrica
        ])

        PrevisaoArmazem.all_cooperativas.bulk_create([
            PrevisaoArmazem(
                cooperativa=cooperativa,
                armazem_id=armazem_map[p['armazem_id']],
                mes_referencia=p['mes_referencia'],
                recebimento_produtor=p['recebimento_produtor'],
                vendas=p['vendas'],
            )
            for p in dados.previsoes_armazem
        ])

        SafraUnidade.all_cooperativas.bulk_create([
            SafraUnidade(
                cooperativa=cooperativa,
                cenario_id=cenario_map[s['cenario_id']],
                entidade_tipo=s['entidade_tipo'],
                entidade_id=(
                    armazem_map[s['entidade_id']]
                    if s['entidade_tipo'] == 'Armazém'
                    else fabrica_map[s['entidade_id']]
                ),
                data_inicio=s['data_inicio'],
                data_fim=s['data_fim'],
            )
            for s in dados.safras
        ])

    return {
        'cenarios': len(dados.cenarios),
        'fabricas': len(dados.fabricas),
        'armazens': len(dados.armazens),
        'rotas': len(dados.rotas),
        'previsoes_fabrica': len(dados.previsoes_fabrica),
        'previsoes_armazem': len(dados.previsoes_armazem),
        'safras': len(dados.safras),
    }
```

- [ ] **Step 4: Rodar os testes e confirmar que passam**

Run: `python -m pytest apps/simulacao/tests/test_legado_escrita.py -v`
Expected: PASS (10 testes)

- [ ] **Step 5: Rodar a suíte inteira, para garantir que nada regrediu**

Run: `python -m pytest -q`
Expected: PASS — 178 testes anteriores + 6 da Task 1 + 10 desta = 194

- [ ] **Step 6: Commit**

```bash
git add apps/simulacao/legado.py apps/simulacao/tests/test_legado_escrita.py
git commit -m "feat(legado): escrever dados do legado no schema Django"
```

---

### Task 3: Management command `espelhar_legado`

**Files:**
- Create: `apps/simulacao/management/__init__.py` (vazio)
- Create: `apps/simulacao/management/commands/__init__.py` (vazio)
- Create: `apps/simulacao/management/commands/espelhar_legado.py`
- Test: `apps/simulacao/tests/test_command_espelhar_legado.py`

**Interfaces:**
- Consumes: `abrir_sessao_legado`, `ler_legado`, `escrever` e `DadosLegado` das Tasks 1 e 2; `apps.core.models.Cooperativa` e `User`.
- Produces: o comando `espelhar_legado`, invocável por `python manage.py espelhar_legado` ou `django.core.management.call_command('espelhar_legado', ...)`.

**Nota sobre os testes:** os testes deste task **não** tocam o banco legado. Eles injetam `DadosLegado` construído à mão, substituindo `ler_legado`/`abrir_sessao_legado` por mocks — o que é possível justamente por causa da fronteira da Task 1. O caminho real de leitura é coberto pela verificação manual do Step 7.

- [ ] **Step 1: Escrever os testes que falham**

Criar `apps/simulacao/tests/test_command_espelhar_legado.py`:

```python
import datetime
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from apps.core.models import Cooperativa, User
from apps.simulacao.legado import DadosLegado
from apps.simulacao.models import Cenario, Fabrica

CAMINHO = 'apps.simulacao.management.commands.espelhar_legado'


def dados_minimos():
    return DadosLegado(
        cenarios=[{'id': 6, 'nome': 'Oficial (Planejado)', 'is_oficial': True,
                   'data_criacao': datetime.datetime(2026, 6, 1, 14, 19, 30)}],
        fabricas=[{'id': 101, 'cenario_id': 6, 'nome': 'FÁBRICA RIO VERDE',
                   'capacidade_estatica': 50000, 'capacidade_esmagamento_diaria': 1200,
                   'capacidade_recebimento_diaria': 2000, 'limite_caminhoes': 60,
                   'carga_media_caminhao': 36, 'estoque_inicial': 8000}],
    )


@override_settings(DEBUG=True)
class EspelharLegadoTests(TestCase):
    def setUp(self):
        patch_sessao = mock.patch(f'{CAMINHO}.abrir_sessao_legado')
        patch_leitura = mock.patch(f'{CAMINHO}.ler_legado', return_value=dados_minimos())
        patch_env = mock.patch.dict(
            'os.environ', {'DATABASE_URL': 'postgresql://x/y'}, clear=False,
        )
        patch_sessao.start()
        patch_leitura.start()
        patch_env.start()
        self.addCleanup(patch_sessao.stop)
        self.addCleanup(patch_leitura.stop)
        self.addCleanup(patch_env.stop)

    def test_cria_o_tenant_quando_ele_nao_existe(self):
        call_command('espelhar_legado', '--yes', stdout=StringIO())

        coop = Cooperativa.objects.get(slug='comigo')
        self.assertEqual(Cenario.all_cooperativas.filter(cooperativa=coop).count(), 1)
        self.assertEqual(Fabrica.all_cooperativas.filter(cooperativa=coop).count(), 1)

    def test_reusa_o_tenant_quando_ele_ja_existe(self):
        existente = Cooperativa.objects.create(nome='Comigo', slug='comigo')

        call_command('espelhar_legado', '--yes', stdout=StringIO())

        self.assertEqual(Cooperativa.objects.filter(slug='comigo').count(), 1)
        self.assertEqual(
            Cenario.all_cooperativas.filter(cooperativa=existente).count(), 1
        )

    def test_respeita_o_slug_informado(self):
        call_command('espelhar_legado', '--cooperativa-slug', 'outra', '--yes',
                     stdout=StringIO())

        self.assertTrue(Cooperativa.objects.filter(slug='outra').exists())
        self.assertFalse(Cooperativa.objects.filter(slug='comigo').exists())

    def test_imprime_as_contagens_escritas(self):
        saida = StringIO()

        call_command('espelhar_legado', '--yes', stdout=saida)

        texto = saida.getvalue()
        self.assertIn('cenarios', texto)
        self.assertIn('fabricas', texto)

    def test_repoint_de_usuario_existente(self):
        User.objects.create_user(
            username='teste', password='x', papel=User.PAPEL_ADMIN_COOPERATIVA,
            cooperativa=Cooperativa.objects.create(nome='Antiga', slug='antiga'),
        )

        call_command('espelhar_legado', '--usuario', 'teste', '--yes', stdout=StringIO())

        usuario = User.objects.get(username='teste')
        self.assertEqual(usuario.cooperativa.slug, 'comigo')

    def test_falha_alto_quando_o_usuario_informado_nao_existe(self):
        with self.assertRaises(CommandError) as ctx:
            call_command('espelhar_legado', '--usuario', 'inexistente', '--yes',
                         stdout=StringIO())

        self.assertIn('inexistente', str(ctx.exception))

    def test_usuario_inexistente_nao_deixa_tenant_orfao(self):
        """A validação do usuário precisa vir antes do get_or_create do tenant."""
        with self.assertRaises(CommandError):
            call_command('espelhar_legado', '--usuario', 'inexistente', '--yes',
                         stdout=StringIO())

        self.assertFalse(Cooperativa.objects.filter(slug='comigo').exists())

    def test_sem_yes_e_sem_confirmacao_nao_escreve_nada(self):
        with mock.patch(f'{CAMINHO}.input', return_value='n', create=True):
            call_command('espelhar_legado', stdout=StringIO())

        self.assertEqual(Cenario.all_cooperativas.count(), 0)

    def test_sem_yes_mas_com_confirmacao_escreve(self):
        with mock.patch(f'{CAMINHO}.input', return_value='s', create=True):
            call_command('espelhar_legado', stdout=StringIO())

        self.assertEqual(Cenario.all_cooperativas.count(), 1)


@override_settings(DEBUG=False)
class GuardaDeProducaoTests(TestCase):
    def test_recusa_rodar_com_debug_desligado(self):
        with self.assertRaises(CommandError) as ctx:
            call_command('espelhar_legado', '--yes', stdout=StringIO())

        self.assertIn('DEBUG', str(ctx.exception))
        self.assertEqual(Cooperativa.objects.count(), 0)
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `python -m pytest apps/simulacao/tests/test_command_espelhar_legado.py -v`
Expected: FAIL com `CommandError: Unknown command: 'espelhar_legado'`

- [ ] **Step 3: Criar os pacotes de management**

```bash
mkdir -p apps/simulacao/management/commands
touch apps/simulacao/management/__init__.py
touch apps/simulacao/management/commands/__init__.py
```

- [ ] **Step 4: Escrever o comando**

Criar `apps/simulacao/management/commands/espelhar_legado.py`:

```python
"""Espelha os dados de entrada do banco legado para um tenant Django.

Ferramenta de DESENVOLVIMENTO e DESTRUTIVA: apaga tudo o que o tenant alvo
tem antes de recarregar. Ver
docs/superpowers/specs/2026-08-24-espelhamento-dados-legado-design.md.
"""
import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.core.models import Cooperativa, User
from apps.simulacao.legado import abrir_sessao_legado, escrever, ler_legado
from apps.simulacao.models import (
    Armazem, Cenario, Fabrica, PrevisaoArmazem, PrevisaoFabrica, Rota, SafraUnidade,
)

MODELOS_AFETADOS = (
    Cenario, Fabrica, Armazem, Rota, PrevisaoFabrica, PrevisaoArmazem, SafraUnidade,
)


class Command(BaseCommand):
    help = 'Espelha os dados de entrada do banco legado para um tenant Django.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--cooperativa-slug', default='comigo',
            help='Slug do tenant alvo; criado se não existir. Padrão: comigo.',
        )
        parser.add_argument(
            '--usuario', default=None,
            help='Username de um usuário JÁ EXISTENTE, a ser repontado para o tenant.',
        )
        parser.add_argument(
            '--yes', action='store_true',
            help='Pula a confirmação interativa.',
        )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                'espelhar_legado é uma ferramenta de desenvolvimento e apaga o tenant '
                'inteiro antes de recarregar. Recusando rodar com DEBUG desligado.'
            )

        database_url = os.environ.get('DATABASE_URL')
        if not database_url:
            raise CommandError(
                'DATABASE_URL não definida. É a conexão do banco legado (stack '
                'Streamlit); ver .env.'
            )

        # Validar o usuário ANTES de criar o tenant: um username errado não pode
        # deixar uma Cooperativa órfã para trás.
        usuario = None
        if options['usuario']:
            try:
                usuario = User.objects.get(username=options['usuario'])
            except User.DoesNotExist:
                raise CommandError(
                    f"Usuário '{options['usuario']}' não existe. Este comando repointa "
                    'um usuário existente, não cria usuários.'
                )

        slug = options['cooperativa_slug']
        cooperativa, criada = Cooperativa.objects.get_or_create(
            slug=slug, defaults={'nome': slug.capitalize()},
        )

        if not options['yes'] and not self._confirmar(cooperativa, criada):
            self.stdout.write('Cancelado. Nada foi alterado.')
            return

        sessao = abrir_sessao_legado(database_url)
        try:
            dados = ler_legado(sessao)
        finally:
            sessao.close()

        contagens = escrever(dados, cooperativa)

        if usuario is not None:
            usuario.cooperativa = cooperativa
            usuario.save(update_fields=['cooperativa'])
            self.stdout.write(
                f"Usuário '{usuario.username}' repontado para '{cooperativa.nome}'."
            )

        self.stdout.write(self.style.SUCCESS(f'Espelhado para {cooperativa.nome}:'))
        for tabela, quantidade in contagens.items():
            self.stdout.write(f'  {tabela}: {quantidade}')

    def _confirmar(self, cooperativa, criada):
        if criada:
            self.stdout.write(
                f"Tenant '{cooperativa.slug}' será criado — nada a apagar."
            )
        else:
            self.stdout.write(
                f"ATENÇÃO: tudo o que o tenant '{cooperativa.slug}' tem hoje será "
                'APAGADO e recarregado do legado:'
            )
            for modelo in MODELOS_AFETADOS:
                total = modelo.all_cooperativas.filter(cooperativa=cooperativa).count()
                self.stdout.write(f'  {modelo.__name__}: {total} linha(s)')
        return input('Continuar? [s/N] ').strip().lower() == 's'
```

- [ ] **Step 5: Rodar os testes e confirmar que passam**

Run: `python -m pytest apps/simulacao/tests/test_command_espelhar_legado.py -v`
Expected: PASS (10 testes)

- [ ] **Step 6: Rodar a suíte inteira**

Run: `python -m pytest -q`
Expected: PASS — 204 testes

- [ ] **Step 7: Verificação manual contra o banco legado real**

Este é o objetivo de todo o plano; a etapa não está concluída sem ele.

```bash
python manage.py espelhar_legado --usuario teste
```

Confirmar na saída: `cenarios: 7`, `fabricas: 14`, `armazens: 119`, `rotas: 238`, `previsoes_fabrica: 56`, `previsoes_armazem: 476`, `safras: 133`.

Depois:

```bash
python manage.py runserver
```

Logar como `teste` e abrir as cinco grades, confirmando que carregam dados reais e que salvar uma edição funciona:
- `/simulacao/cenarios/` — 7 cenários, um marcado como oficial
- `/simulacao/cenarios/<id>/fabricas/` — 2 fábricas
- `/simulacao/cenarios/<id>/armazens/` — 17 armazéns
- `/simulacao/cenarios/<id>/rotas/` — 34 rotas, com origem/destino resolvidos por nome
- `/simulacao/cenarios/<id>/previsoes/` — sub-grades de fábrica e de armazém
- `/simulacao/cenarios/<id>/safras/` — coluna "Unidade" com nomes, **nenhum "N/A"**

O "N/A" na grade de Safras é o sintoma exato de `entidade_id` mal remapeado: `safras_grid` cai nesse valor quando não acha a unidade. É a verificação mais importante da lista.

- [ ] **Step 8: Commit**

```bash
git add apps/simulacao/management apps/simulacao/tests/test_command_espelhar_legado.py
git commit -m "feat(legado): management command espelhar_legado"
```

- [ ] **Step 9: Sincronizar a spec com o refinamento de assinatura**

A spec §2 descreve `ler_legado(database_url)`; a implementação usa `ler_legado(session)` mais `abrir_sessao_legado(database_url)`, pelo motivo de testabilidade registrado na seção "File Structure" deste plano. Atualizar a §2 da spec para refletir as assinaturas reais e commitar.

```bash
git add docs/superpowers/specs/2026-08-24-espelhamento-dados-legado-design.md
git commit -m "docs: sync spec with the implemented ler_legado signature"
```

---

## Notas de encerramento

Depois da Task 3, dois itens de `CLAUDE.md` merecem revisão pelo dono do projeto, ambos consequência do que esta investigação apurou:

1. **Pendência A11** — a verificação de `cenario_id IS NULL` foi feita e deu zero em todas as tabelas. O item pode ser encerrado, ou o `ALTER TABLE ... SET NOT NULL` pode ser aplicado.
2. **Mapa de arquivos** — `apps/simulacao/legado.py` é um módulo novo de produção e deve entrar na seção "Architecture / File Map".
