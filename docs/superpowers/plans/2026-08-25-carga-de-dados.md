# Carga de Dados por planilha — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dar ao stack Django o primeiro caminho para dados entrarem no sistema — uma pasta `.xlsx` de cinco abas, pré-visualizada antes de qualquer escrita, capaz de criar o cenário oficial de uma cooperativa nova.

**Architecture:** Um módulo `apps/simulacao/planilha.py` com duas funções de responsabilidade única — `analisar(arquivo, cenario)` lê a pasta e classifica cada linha em criar/atualizar/rejeitar sem escrever nada, e `aplicar(...)` reanalisa e grava dentro de uma transação. As telas guardam o `.xlsx` sob um token entre a pré-visualização e a confirmação, de modo que o arquivo continue sendo a única fonte da verdade. A mesma fronteira que `legado.py` usa, pelo mesmo motivo: quase toda a lógica fica testável com um `.xlsx` montado em memória.

**Tech Stack:** Django 6, openpyxl 3.1.5 (já em `requirements.txt`), HTMX, pytest + pytest-django.

**Spec:** `docs/superpowers/specs/2026-08-25-carga-de-dados-design.md`

## Global Constraints

- **TDD estrito (red → green).** Teste que falha primeiro, confirmar que falha pela razão certa, implementar o mínimo, confirmar que passa. Regra do projeto (`CLAUDE.md`).
- **Fora de request usar `all_cooperativas`.** As funções de `planilha.py` recebem o `cenario` ou a `cooperativa` prontos e filtram por eles. Ver `docs/decisions/0006-engine-services-usam-all-cooperativas.md`.
- **`analisar` NUNCA escreve.** É a garantia que sustenta a pré-visualização, e tem teste dedicado.
- **`aplicar` grava tudo — inclusive a criação do cenário — dentro de um único `transaction.atomic()`,** para que uma pasta com erro não deixe um cenário vazio para trás.
- **Ordem de dependência das abas: Fábricas → Armazéns → Rotas → Previsões → Safras.** Imposta pelo código, não pelo arquivo.
- **Nomes resolvem contra (o que está no banco para o cenário) ∪ (o que abas anteriores da mesma pasta vão criar).** Sem isso o bootstrap é impossível: num cenário vazio, toda rota seria rejeitada.
- **Colisão de nome (fábrica e armazém com o mesmo nome no cenário) rejeita a linha como ambígua,** nomeando o conflito. O legado escolhe a fábrica em silêncio.
- **A convenção de `entidade_tipo`:** `'Armazém'` (com acento) identifica armazém; qualquer outro valor identifica fábrica. É o que `views.py::safras_grid` e `services.clone_scenario` já assumem.
- **Cabeçalhos são comparados normalizados:** `str(valor).strip().lower()`.
- **Semântica de UPSERT, nunca de remoção.** Uma pasta que não menciona uma fábrica existente não a apaga.
- **pt-BR em toda mensagem que o usuário lê.** Motivos de rejeição em português, nomeando a coluna.
- Rodar a suíte com `python -m pytest`. Os testes Django exigem o PostgreSQL local via `DJANGO_DB_*`. A suíte está verde em **209** testes antes desta fase.

---

## File Structure

| Arquivo | Responsabilidade |
|---|---|
| `apps/simulacao/planilha.py` (criar) | Formato das abas, `Relatorio` e suas partes, `analisar`, `aplicar`, `gerar_template`. Único módulo novo de produção. |
| `apps/simulacao/views.py` (modificar, acrescentar ao final) | `carga_upload`, `carga_preview`, `carga_template`. Sem lógica de planilha. |
| `apps/simulacao/urls.py` (modificar) | Três rotas novas. |
| `templates/simulacao/carga.html` + `_carga_content.html` (criar) | Tela de upload. |
| `templates/simulacao/carga_preview.html` + `_carga_preview_content.html` (criar) | Tela de pré-visualização. |
| `apps/simulacao/tests/planilha_fixtures.py` (criar) | Helper compartilhado que monta `.xlsx` em memória. |
| `apps/simulacao/tests/test_planilha_analisar.py` (criar) | Testes de `analisar` — a maior parte da lógica. |
| `apps/simulacao/tests/test_planilha_aplicar.py` (criar) | Testes de `aplicar`. |
| `apps/simulacao/tests/test_planilha_template.py` (criar) | Testes de `gerar_template`. |
| `apps/simulacao/tests/test_views_carga.py` (criar) | Testes das três views. |

A Task 1 cria o helper de fixtures; as Tasks 2, 3 e 5 o importam em vez de reescrevê-lo.

---

### Task 1: Fundação do parser — formato, relatório e as abas independentes

**Files:**
- Create: `apps/simulacao/planilha.py`
- Create: `apps/simulacao/tests/planilha_fixtures.py`
- Test: `apps/simulacao/tests/test_planilha_analisar.py`

**Interfaces:**
- Consumes: `apps.simulacao.models.{Fabrica, Armazem}`.
- Produces (consumido pelas Tasks 2-5):
  - `LinhaRejeitada(aba: str, linha: int, motivo: str, valores: dict)` — `linha` é o número **como aparece no Excel** (cabeçalho é a linha 1, então o primeiro dado é 2).
  - `ResumoAba(aba: str, criar: int, atualizar: int, rejeitadas: list[LinhaRejeitada])`
  - `Relatorio(abas: list[ResumoAba], erro_estrutural: str | None)` com as propriedades `tem_erro_estrutural`, `total_criar`, `total_atualizar`, `total_rejeitadas`, e o método `resumo(nome_aba) -> ResumoAba | None`.
  - `analisar(arquivo, cenario) -> Relatorio` — `cenario` pode ser `None` (bootstrap).
  - Constantes: `ABA_FABRICAS = 'Fábricas'`, `ABA_ARMAZENS = 'Armazéns'`, `ABA_ROTAS = 'Rotas'`, `ABA_PREVISOES = 'Previsões'`, `ABA_SAFRAS = 'Safras'`, `ABAS_NA_ORDEM`, `COLUNAS_POR_ABA`, `OBRIGATORIOS_POR_ABA`.
  - Do helper de teste: `montar_pasta(**abas) -> io.BytesIO` e `montar_pasta_bruta(dict) -> io.BytesIO`.

**Nesta task, `analisar` trata apenas Fábricas e Armazéns.** As outras três abas ganham um `ResumoAba` vazio; a Task 2 as preenche.

- [ ] **Step 1: Escrever o helper de fixtures**

Criar `apps/simulacao/tests/planilha_fixtures.py`:

```python
"""Monta pastas .xlsx em memória para os testes de planilha.

Existe para que os testes do parser não precisem de arquivo em disco nem de
fixture versionada -- cada teste declara exatamente as linhas de que precisa.
"""
import io

from openpyxl import Workbook

from apps.simulacao.planilha import (
    ABA_ARMAZENS, ABA_FABRICAS, ABA_PREVISOES, ABA_ROTAS, ABA_SAFRAS,
)

NOME_DA_ABA = {
    'fabricas': ABA_FABRICAS,
    'armazens': ABA_ARMAZENS,
    'rotas': ABA_ROTAS,
    'previsoes': ABA_PREVISOES,
    'safras': ABA_SAFRAS,
}


def montar_pasta(**abas):
    """montar_pasta(fabricas=[{'nome': 'X', ...}, ...]) -> BytesIO.

    A ordem das chaves do primeiro dict de cada aba define o cabeçalho.
    """
    wb = Workbook()
    wb.remove(wb.active)
    for chave, linhas in abas.items():
        ws = wb.create_sheet(NOME_DA_ABA[chave])
        if not linhas:
            continue
        colunas = list(linhas[0].keys())
        ws.append(colunas)
        for linha in linhas:
            ws.append([linha.get(c) for c in colunas])
    return _salvar(wb)


def montar_pasta_bruta(abas):
    """abas = {'Fábricas': [['nome', 'x'], ['A', 1]]} -- listas de listas, para
    exercitar cabeçalho irreconhecível e outros casos estruturais."""
    wb = Workbook()
    wb.remove(wb.active)
    for nome, linhas in abas.items():
        ws = wb.create_sheet(nome)
        for linha in linhas:
            ws.append(linha)
    return _salvar(wb)


def _salvar(wb):
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer
```

- [ ] **Step 2: Escrever os testes que falham**

Criar `apps/simulacao/tests/test_planilha_analisar.py`:

```python
import io

from django.test import TestCase

from apps.core.models import Cooperativa
from apps.simulacao.models import Armazem, Cenario, Fabrica
from apps.simulacao.planilha import ABA_ARMAZENS, ABA_FABRICAS, analisar
from apps.simulacao.tests.planilha_fixtures import montar_pasta, montar_pasta_bruta

FABRICA_OK = {
    'nome': 'FÁBRICA TESTE',
    'capacidade_estatica': 50000,
    'capacidade_esmagamento_diaria': 1200,
    'capacidade_recebimento_diaria': 2000,
    'limite_caminhoes': 60,
    'carga_media_caminhao': 36,
    'estoque_inicial': 8000,
}

ARMAZEM_OK = {
    'nome': 'ARMAZÉM A',
    'capacidade_estatica': 30000,
    'capacidade_expedicao_diaria': 900,
    'estoque_inicial': 12000,
}


class AnalisarEstruturaTests(TestCase):
    def test_arquivo_ilegivel_e_erro_estrutural(self):
        relatorio = analisar(io.BytesIO(b'isto nao e um xlsx'), None)

        self.assertTrue(relatorio.tem_erro_estrutural)
        self.assertIn('xlsx', relatorio.erro_estrutural.lower())

    def test_pasta_sem_nenhuma_aba_reconhecida_e_erro_estrutural(self):
        pasta = montar_pasta_bruta({'Planilha1': [['a', 'b'], [1, 2]]})

        relatorio = analisar(pasta, None)

        self.assertTrue(relatorio.tem_erro_estrutural)

    def test_aba_com_cabecalho_irreconhecivel_e_erro_estrutural(self):
        pasta = montar_pasta_bruta({ABA_FABRICAS: [['coluna_inventada'], ['x']]})

        relatorio = analisar(pasta, None)

        self.assertTrue(relatorio.tem_erro_estrutural)
        self.assertIn(ABA_FABRICAS, relatorio.erro_estrutural)

    def test_aba_ausente_nao_e_erro(self):
        """Uma pasta só com Fábricas é válida -- as demais abas ficam vazias."""
        relatorio = analisar(montar_pasta(fabricas=[FABRICA_OK]), None)

        self.assertFalse(relatorio.tem_erro_estrutural)
        self.assertEqual(relatorio.resumo(ABA_FABRICAS).criar, 1)
        self.assertEqual(relatorio.resumo(ABA_ARMAZENS).criar, 0)

    def test_cabecalho_e_normalizado(self):
        linha = {k.upper() + '  ': v for k, v in FABRICA_OK.items()}

        relatorio = analisar(montar_pasta(fabricas=[linha]), None)

        self.assertFalse(relatorio.tem_erro_estrutural)
        self.assertEqual(relatorio.resumo(ABA_FABRICAS).criar, 1)


class AnalisarFabricasArmazensTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome='Comigo', slug='comigo')
        self.cenario = Cenario.all_cooperativas.create(
            cooperativa=self.coop, nome='Oficial', is_oficial=True,
        )

    def test_cenario_none_conta_tudo_como_criacao(self):
        relatorio = analisar(montar_pasta(fabricas=[FABRICA_OK], armazens=[ARMAZEM_OK]), None)

        self.assertEqual(relatorio.resumo(ABA_FABRICAS).criar, 1)
        self.assertEqual(relatorio.resumo(ABA_FABRICAS).atualizar, 0)
        self.assertEqual(relatorio.resumo(ABA_ARMAZENS).criar, 1)

    def test_nome_ja_existente_no_cenario_conta_como_atualizacao(self):
        Fabrica.all_cooperativas.create(
            cooperativa=self.coop, cenario=self.cenario, nome='FÁBRICA TESTE',
            capacidade_estatica=1, capacidade_esmagamento_diaria=1,
            capacidade_recebimento_diaria=1, limite_caminhoes=1,
            carga_media_caminhao=1, estoque_inicial=1,
        )

        relatorio = analisar(montar_pasta(fabricas=[FABRICA_OK]), self.cenario)

        self.assertEqual(relatorio.resumo(ABA_FABRICAS).criar, 0)
        self.assertEqual(relatorio.resumo(ABA_FABRICAS).atualizar, 1)

    def test_campo_numerico_em_branco_rejeita_a_linha_e_nomeia_a_coluna(self):
        ruim = dict(FABRICA_OK, nome='SEM CAPACIDADE', capacidade_estatica=None)

        relatorio = analisar(montar_pasta(fabricas=[FABRICA_OK, ruim]), None)

        resumo = relatorio.resumo(ABA_FABRICAS)
        self.assertEqual(resumo.criar, 1)
        self.assertEqual(len(resumo.rejeitadas), 1)
        rejeitada = resumo.rejeitadas[0]
        self.assertIn('capacidade_estatica', rejeitada.motivo)
        self.assertEqual(rejeitada.valores['nome'], 'SEM CAPACIDADE')

    def test_numero_da_linha_e_o_do_excel(self):
        """Cabeçalho é a linha 1, então a segunda linha de dados é a 3."""
        ruim = dict(FABRICA_OK, nome='RUIM', estoque_inicial=None)

        relatorio = analisar(montar_pasta(fabricas=[FABRICA_OK, ruim]), None)

        self.assertEqual(relatorio.resumo(ABA_FABRICAS).rejeitadas[0].linha, 3)

    def test_valor_nao_numerico_rejeita_a_linha(self):
        ruim = dict(FABRICA_OK, nome='TEXTO NO NUMERO', limite_caminhoes='muitos')

        relatorio = analisar(montar_pasta(fabricas=[ruim]), None)

        resumo = relatorio.resumo(ABA_FABRICAS)
        self.assertEqual(resumo.criar, 0)
        self.assertIn('limite_caminhoes', resumo.rejeitadas[0].motivo)

    def test_nome_em_branco_rejeita_a_linha(self):
        relatorio = analisar(montar_pasta(fabricas=[dict(FABRICA_OK, nome=None)]), None)

        resumo = relatorio.resumo(ABA_FABRICAS)
        self.assertEqual(resumo.criar, 0)
        self.assertIn('nome', resumo.rejeitadas[0].motivo)

    def test_linha_ruim_nao_aborta_a_aba(self):
        outra = dict(FABRICA_OK, nome='OUTRA FÁBRICA')
        ruim = dict(FABRICA_OK, nome='RUIM', carga_media_caminhao=None)

        relatorio = analisar(montar_pasta(fabricas=[FABRICA_OK, ruim, outra]), None)

        resumo = relatorio.resumo(ABA_FABRICAS)
        self.assertEqual(resumo.criar, 2)
        self.assertEqual(len(resumo.rejeitadas), 1)

    def test_analisar_nao_escreve_nada(self):
        """A garantia que sustenta a pré-visualização."""
        antes = (Fabrica.all_cooperativas.count(), Armazem.all_cooperativas.count())

        analisar(montar_pasta(fabricas=[FABRICA_OK], armazens=[ARMAZEM_OK]), self.cenario)

        depois = (Fabrica.all_cooperativas.count(), Armazem.all_cooperativas.count())
        self.assertEqual(antes, depois)
```

- [ ] **Step 3: Rodar os testes e confirmar que falham**

Run: `python -m pytest apps/simulacao/tests/test_planilha_analisar.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'apps.simulacao.planilha'`

- [ ] **Step 4: Escrever `planilha.py`**

Criar `apps/simulacao/planilha.py`:

```python
"""Importação de dados de cenário a partir de uma pasta .xlsx de cinco abas.

`analisar` lê e classifica sem escrever nada; `aplicar` grava. A fronteira
existe para que a pré-visualização seja confiável e para que quase toda a
lógica seja testável com uma pasta montada em memória. Ver
docs/superpowers/specs/2026-08-25-carga-de-dados-design.md.
"""
from dataclasses import dataclass, field

from openpyxl import load_workbook

from apps.simulacao.models import Armazem, Fabrica

ABA_FABRICAS = 'Fábricas'
ABA_ARMAZENS = 'Armazéns'
ABA_ROTAS = 'Rotas'
ABA_PREVISOES = 'Previsões'
ABA_SAFRAS = 'Safras'

# A ordem É a ordem de dependência: Rotas, Previsões e Safras resolvem nomes
# contra o que Fábricas e Armazéns criaram antes delas.
ABAS_NA_ORDEM = [ABA_FABRICAS, ABA_ARMAZENS, ABA_ROTAS, ABA_PREVISOES, ABA_SAFRAS]

COLUNAS_POR_ABA = {
    ABA_FABRICAS: [
        'nome', 'capacidade_estatica', 'capacidade_esmagamento_diaria',
        'capacidade_recebimento_diaria', 'limite_caminhoes',
        'carga_media_caminhao', 'estoque_inicial',
    ],
    ABA_ARMAZENS: [
        'nome', 'capacidade_estatica', 'capacidade_expedicao_diaria', 'estoque_inicial',
    ],
    ABA_ROTAS: [
        'origem', 'destino', 'distancia_km', 'custo_frete_ton', 'custo_frete_entressafra',
    ],
    ABA_PREVISOES: ['entidade', 'mes_referencia', 'recebimento_produtor', 'vendas'],
    ABA_SAFRAS: ['unidade', 'data_inicio', 'data_fim'],
}

# Numéricos obrigatórios: célula em branco rejeita a linha. Espelha
# FABRICA/ARMAZEM_CAMPOS_NUMERICOS_OBRIGATORIOS do data_loader.py legado -- é a
# correção do bug A8 da Fase 1, em que NaN do pandas chegava ao Postgres como
# número válido.
OBRIGATORIOS_POR_ABA = {
    ABA_FABRICAS: COLUNAS_POR_ABA[ABA_FABRICAS][1:],
    ABA_ARMAZENS: COLUNAS_POR_ABA[ABA_ARMAZENS][1:],
}


@dataclass
class LinhaRejeitada:
    aba: str
    linha: int  # número como aparece no Excel: o cabeçalho é 1
    motivo: str
    valores: dict


@dataclass
class ResumoAba:
    aba: str
    criar: int = 0
    atualizar: int = 0
    rejeitadas: list = field(default_factory=list)


@dataclass
class Relatorio:
    abas: list = field(default_factory=list)
    erro_estrutural: str = None

    @property
    def tem_erro_estrutural(self):
        return self.erro_estrutural is not None

    @property
    def total_criar(self):
        return sum(a.criar for a in self.abas)

    @property
    def total_atualizar(self):
        return sum(a.atualizar for a in self.abas)

    @property
    def total_rejeitadas(self):
        return sum(len(a.rejeitadas) for a in self.abas)

    def resumo(self, nome_aba):
        for a in self.abas:
            if a.aba == nome_aba:
                return a
        return None


def _erro(mensagem):
    return Relatorio(abas=[ResumoAba(aba=n) for n in ABAS_NA_ORDEM], erro_estrutural=mensagem)


def _normalizar(valor):
    return str(valor).strip().lower() if valor is not None else ''


def _ler_abas(arquivo):
    """Devolve (abas, erro). abas = {nome: [(linha_excel, {coluna: valor})]}."""
    try:
        wb = load_workbook(arquivo, data_only=True, read_only=True)
    except Exception:  # noqa: BLE001 -- openpyxl levanta tipos variados
        return None, 'Arquivo não pôde ser lido como .xlsx.'

    presentes = [n for n in ABAS_NA_ORDEM if n in wb.sheetnames]
    if not presentes:
        return None, 'Nenhuma aba reconhecida. Esperadas: ' + ', '.join(ABAS_NA_ORDEM) + '.'

    abas = {n: [] for n in ABAS_NA_ORDEM}
    for nome in presentes:
        ws = wb[nome]
        linhas = ws.iter_rows(values_only=True)
        try:
            cabecalho = [_normalizar(c) for c in next(linhas)]
        except StopIteration:
            continue  # aba presente mas totalmente vazia: nada a importar
        faltando = [c for c in COLUNAS_POR_ABA[nome] if c not in cabecalho]
        if faltando:
            return None, (
                f"Aba '{nome}': coluna(s) ausente(s) no cabeçalho: {', '.join(faltando)}."
            )
        for numero, valores in enumerate(linhas, start=2):
            if all(v is None for v in valores):
                continue
            abas[nome].append((numero, dict(zip(cabecalho, valores))))
    return abas, None


def _numero(valores, coluna):
    """Devolve (numero, erro). Célula em branco e valor não numérico são erro."""
    bruto = valores.get(coluna)
    if bruto is None or (isinstance(bruto, str) and not bruto.strip()):
        return None, f'{coluna} em branco'
    try:
        return float(bruto), None
    except (TypeError, ValueError):
        return None, f'{coluna} não é um número: {bruto!r}'


def _texto(valores, coluna):
    bruto = valores.get(coluna)
    if bruto is None:
        return None
    return str(bruto).strip() or None


def _analisar_unidades(aba, linhas, existentes, resumo):
    """Fábricas e Armazéns: mesma forma, só muda a lista de obrigatórios.

    Devolve o conjunto de nomes que a pasta vai criar ou atualizar, para as
    abas seguintes resolverem contra ele.
    """
    nomes = set()
    for numero, valores in linhas:
        nome = _texto(valores, 'nome')
        if not nome:
            resumo.rejeitadas.append(LinhaRejeitada(aba, numero, 'nome em branco', valores))
            continue
        erros = []
        for coluna in OBRIGATORIOS_POR_ABA[aba]:
            _, erro = _numero(valores, coluna)
            if erro:
                erros.append(erro)
        if erros:
            resumo.rejeitadas.append(LinhaRejeitada(aba, numero, '; '.join(erros), valores))
            continue
        if nome in existentes:
            resumo.atualizar += 1
        else:
            resumo.criar += 1
        nomes.add(nome)
    return nomes


def analisar(arquivo, cenario):
    """Lê a pasta e classifica cada linha. NUNCA escreve.

    `cenario` pode ser None (bootstrap: o cenário ainda não existe). Nesse caso
    o lado-banco da resolução é vazio -- tudo é criação, e os nomes resolvem
    apenas contra a própria pasta.
    """
    abas, erro = _ler_abas(arquivo)
    if erro:
        return _erro(erro)

    if cenario is not None:
        fabricas_no_banco = set(
            Fabrica.all_cooperativas.filter(cenario=cenario).values_list('nome', flat=True)
        )
        armazens_no_banco = set(
            Armazem.all_cooperativas.filter(cenario=cenario).values_list('nome', flat=True)
        )
    else:
        fabricas_no_banco = set()
        armazens_no_banco = set()

    relatorio = Relatorio(abas=[ResumoAba(aba=n) for n in ABAS_NA_ORDEM])

    _analisar_unidades(
        ABA_FABRICAS, abas[ABA_FABRICAS], fabricas_no_banco, relatorio.resumo(ABA_FABRICAS),
    )
    _analisar_unidades(
        ABA_ARMAZENS, abas[ABA_ARMAZENS], armazens_no_banco, relatorio.resumo(ABA_ARMAZENS),
    )

    return relatorio
```

- [ ] **Step 5: Rodar os testes e confirmar que passam**

Run: `python -m pytest apps/simulacao/tests/test_planilha_analisar.py -v`
Expected: PASS (13 testes)

- [ ] **Step 6: Rodar a suíte inteira**

Run: `python -m pytest -q`
Expected: PASS — 209 anteriores + 13 = 222

- [ ] **Step 7: Commit**

```bash
git add apps/simulacao/planilha.py apps/simulacao/tests/planilha_fixtures.py apps/simulacao/tests/test_planilha_analisar.py
git commit -m "feat(carga): parser de planilha - estrutura, fabricas e armazens"
```

---

### Task 2: Resolução de nomes — Rotas, Previsões e Safras

**Files:**
- Modify: `apps/simulacao/planilha.py` (acrescentar funções; `analisar` ganha três blocos)
- Modify: `apps/simulacao/tests/test_planilha_analisar.py` (acrescentar uma classe)

**Interfaces:**
- Consumes: tudo o que a Task 1 produziu, incluindo `montar_pasta` de `planilha_fixtures.py` e as constantes `FABRICA_OK`/`ARMAZEM_OK` definidas em `test_planilha_analisar.py`.
- Produces: `analisar` passa a preencher os `ResumoAba` de Rotas, Previsões e Safras. Nenhuma assinatura pública nova; a Task 3 consome o mesmo `Relatorio`.

**A decisão central desta task,** e a razão de ela existir separada: os nomes resolvem contra
**(o que está no banco para o cenário) ∪ (o que as abas anteriores desta mesma pasta vão criar)**.
Resolver só contra o banco rejeitaria toda rota num cenário vazio — que é exatamente o caso de
bootstrap para o qual a fase inteira existe.

- [ ] **Step 1: Escrever os testes que falham**

Acrescentar ao final de `apps/simulacao/tests/test_planilha_analisar.py`:

```python
import datetime

from apps.simulacao.planilha import ABA_PREVISOES, ABA_ROTAS, ABA_SAFRAS

ROTA_OK = {
    'origem': 'ARMAZÉM A',
    'destino': 'FÁBRICA TESTE',
    'distancia_km': 118.5,
    'custo_frete_ton': 42.75,
    'custo_frete_entressafra': 38.0,
}


class AnalisarResolucaoTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome='Comigo', slug='comigo')
        self.cenario = Cenario.all_cooperativas.create(
            cooperativa=self.coop, nome='Oficial', is_oficial=True,
        )

    def test_rota_resolve_contra_unidades_criadas_na_mesma_pasta(self):
        """O caso do bootstrap: cenário vazio, tudo vem da própria pasta."""
        pasta = montar_pasta(fabricas=[FABRICA_OK], armazens=[ARMAZEM_OK], rotas=[ROTA_OK])

        relatorio = analisar(pasta, None)

        self.assertEqual(relatorio.resumo(ABA_ROTAS).criar, 1)
        self.assertEqual(relatorio.resumo(ABA_ROTAS).rejeitadas, [])

    def test_rota_resolve_contra_unidades_ja_no_banco(self):
        Fabrica.all_cooperativas.create(
            cooperativa=self.coop, cenario=self.cenario, nome='FÁBRICA TESTE',
            capacidade_estatica=1, capacidade_esmagamento_diaria=1,
            capacidade_recebimento_diaria=1, limite_caminhoes=1,
            carga_media_caminhao=1, estoque_inicial=1,
        )
        Armazem.all_cooperativas.create(
            cooperativa=self.coop, cenario=self.cenario, nome='ARMAZÉM A',
            capacidade_estatica=1, capacidade_expedicao_diaria=1, estoque_inicial=1,
        )

        relatorio = analisar(montar_pasta(rotas=[ROTA_OK]), self.cenario)

        self.assertEqual(relatorio.resumo(ABA_ROTAS).criar, 1)

    def test_rota_com_origem_inexistente_e_rejeitada_com_motivo(self):
        ruim = dict(ROTA_OK, origem='ARMAZÉM FANTASMA')

        relatorio = analisar(montar_pasta(fabricas=[FABRICA_OK], rotas=[ruim]), None)

        rejeitadas = relatorio.resumo(ABA_ROTAS).rejeitadas
        self.assertEqual(len(rejeitadas), 1)
        self.assertIn('ARMAZÉM FANTASMA', rejeitadas[0].motivo)

    def test_custo_entressafra_em_branco_assume_o_de_safra(self):
        """Comportamento do legado (data_loader.py:386-387), preservado."""
        sem = dict(ROTA_OK, custo_frete_entressafra=None)
        pasta = montar_pasta(fabricas=[FABRICA_OK], armazens=[ARMAZEM_OK], rotas=[sem])

        relatorio = analisar(pasta, None)

        self.assertEqual(relatorio.resumo(ABA_ROTAS).criar, 1)
        self.assertEqual(relatorio.resumo(ABA_ROTAS).rejeitadas, [])

    def test_previsao_resolve_fabrica_ou_armazem_pelo_nome(self):
        previsoes = [
            {'entidade': 'FÁBRICA TESTE', 'mes_referencia': datetime.date(2026, 3, 15),
             'recebimento_produtor': 4500.5, 'vendas': 1200.25},
            {'entidade': 'ARMAZÉM A', 'mes_referencia': datetime.date(2026, 3, 1),
             'recebimento_produtor': 7800.0, 'vendas': 300.0},
        ]
        pasta = montar_pasta(fabricas=[FABRICA_OK], armazens=[ARMAZEM_OK], previsoes=previsoes)

        relatorio = analisar(pasta, None)

        self.assertEqual(relatorio.resumo(ABA_PREVISOES).criar, 2)

    def test_previsao_com_entidade_desconhecida_e_rejeitada_nao_pulada(self):
        """O legado só incrementava `skipped`, sem registro nenhum."""
        previsoes = [{'entidade': 'NINGUÉM', 'mes_referencia': datetime.date(2026, 3, 1),
                      'recebimento_produtor': 1, 'vendas': 1}]

        relatorio = analisar(montar_pasta(fabricas=[FABRICA_OK], previsoes=previsoes), None)

        rejeitadas = relatorio.resumo(ABA_PREVISOES).rejeitadas
        self.assertEqual(len(rejeitadas), 1)
        self.assertIn('NINGUÉM', rejeitadas[0].motivo)

    def test_nome_ambiguo_e_rejeitado_nomeando_o_conflito(self):
        """O legado escolhe a fábrica em silêncio (data_loader.py:439-453)."""
        pasta = montar_pasta(
            fabricas=[dict(FABRICA_OK, nome='DUPLICADO')],
            armazens=[dict(ARMAZEM_OK, nome='DUPLICADO')],
            previsoes=[{'entidade': 'DUPLICADO', 'mes_referencia': datetime.date(2026, 3, 1),
                        'recebimento_produtor': 1, 'vendas': 1}],
        )

        relatorio = analisar(pasta, None)

        rejeitadas = relatorio.resumo(ABA_PREVISOES).rejeitadas
        self.assertEqual(len(rejeitadas), 1)
        self.assertIn('ambígu', rejeitadas[0].motivo.lower())

    def test_mes_referencia_nao_parseavel_rejeita_sem_abortar_a_aba(self):
        previsoes = [
            {'entidade': 'FÁBRICA TESTE', 'mes_referencia': 'mês que vem',
             'recebimento_produtor': 1, 'vendas': 1},
            {'entidade': 'FÁBRICA TESTE', 'mes_referencia': datetime.date(2026, 4, 1),
             'recebimento_produtor': 2, 'vendas': 2},
        ]

        relatorio = analisar(montar_pasta(fabricas=[FABRICA_OK], previsoes=previsoes), None)

        resumo = relatorio.resumo(ABA_PREVISOES)
        self.assertEqual(resumo.criar, 1)
        self.assertEqual(len(resumo.rejeitadas), 1)
        self.assertIn('mes_referencia', resumo.rejeitadas[0].motivo)

    def test_previsao_com_valores_em_branco_vale_zero(self):
        previsoes = [{'entidade': 'FÁBRICA TESTE', 'mes_referencia': datetime.date(2026, 3, 1),
                      'recebimento_produtor': None, 'vendas': None}]

        relatorio = analisar(montar_pasta(fabricas=[FABRICA_OK], previsoes=previsoes), None)

        self.assertEqual(relatorio.resumo(ABA_PREVISOES).criar, 1)
        self.assertEqual(relatorio.resumo(ABA_PREVISOES).rejeitadas, [])

    def test_safra_resolve_unidade_e_deriva_o_tipo(self):
        safras = [
            {'unidade': 'ARMAZÉM A', 'data_inicio': datetime.date(2026, 2, 1),
             'data_fim': datetime.date(2026, 5, 31)},
            {'unidade': 'FÁBRICA TESTE', 'data_inicio': datetime.date(2026, 2, 15),
             'data_fim': datetime.date(2026, 6, 15)},
        ]
        pasta = montar_pasta(fabricas=[FABRICA_OK], armazens=[ARMAZEM_OK], safras=safras)

        relatorio = analisar(pasta, None)

        self.assertEqual(relatorio.resumo(ABA_SAFRAS).criar, 2)

    def test_safra_com_data_fim_antes_do_inicio_e_rejeitada(self):
        safras = [{'unidade': 'ARMAZÉM A', 'data_inicio': datetime.date(2026, 5, 1),
                   'data_fim': datetime.date(2026, 2, 1)}]

        relatorio = analisar(montar_pasta(armazens=[ARMAZEM_OK], safras=safras), None)

        rejeitadas = relatorio.resumo(ABA_SAFRAS).rejeitadas
        self.assertEqual(len(rejeitadas), 1)
        self.assertIn('data_fim', rejeitadas[0].motivo)
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `python -m pytest apps/simulacao/tests/test_planilha_analisar.py -k Resolucao -v`
Expected: FAIL — os resumos de Rotas/Previsões/Safras vêm zerados, então `criar` é 0 onde os testes esperam 1 ou 2.

- [ ] **Step 3: Acrescentar a resolução a `planilha.py`**

Acrescentar `import datetime` ao topo, e ampliar o import de models:

```python
from apps.simulacao.models import (
    Armazem, Fabrica, PrevisaoArmazem, PrevisaoFabrica, Rota, SafraUnidade,
)
```

Acrescentar estas funções antes de `analisar`:

```python
def _data(valores, coluna):
    """Devolve (date, erro). Aceita date/datetime do Excel e texto ISO."""
    bruto = valores.get(coluna)
    if bruto is None or (isinstance(bruto, str) and not bruto.strip()):
        return None, f'{coluna} em branco'
    if isinstance(bruto, datetime.datetime):
        return bruto.date(), None
    if isinstance(bruto, datetime.date):
        return bruto, None
    try:
        return datetime.date.fromisoformat(str(bruto).strip()), None
    except ValueError:
        return None, f'{coluna} não é uma data válida (use AAAA-MM-DD): {bruto!r}'


def _resolver(nome, fabricas, armazens):
    """Devolve (tipo, erro). tipo é 'Fábrica' ou 'Armazém'.

    Nome presente nos dois conjuntos é ambíguo -- rejeita em vez de escolher.
    O legado escolhe a fábrica em silêncio (data_loader.py:439-453).
    """
    eh_fabrica = nome in fabricas
    eh_armazem = nome in armazens
    if eh_fabrica and eh_armazem:
        return None, (
            f"'{nome}' é ambíguo: existe uma fábrica e um armazém com esse nome neste cenário"
        )
    if eh_fabrica:
        return 'Fábrica', None
    if eh_armazem:
        return 'Armazém', None
    return None, f"'{nome}' não corresponde a nenhuma fábrica nem armazém deste cenário"


def _chaves_de_rota(cenario):
    if cenario is None:
        return set()
    return {
        (r.armazem.nome, r.fabrica.nome)
        for r in Rota.all_cooperativas.filter(cenario=cenario).select_related(
            'armazem', 'fabrica'
        )
    }


def _chaves_de_previsao(cenario):
    if cenario is None:
        return set()
    chaves = {
        ('Fábrica', p.fabrica.nome, p.mes_referencia)
        for p in PrevisaoFabrica.all_cooperativas.filter(
            fabrica__cenario=cenario
        ).select_related('fabrica')
    }
    chaves |= {
        ('Armazém', p.armazem.nome, p.mes_referencia)
        for p in PrevisaoArmazem.all_cooperativas.filter(
            armazem__cenario=cenario
        ).select_related('armazem')
    }
    return chaves


def _chaves_de_safra(cenario):
    if cenario is None:
        return set()
    fabricas = dict(
        Fabrica.all_cooperativas.filter(cenario=cenario).values_list('id', 'nome')
    )
    armazens = dict(
        Armazem.all_cooperativas.filter(cenario=cenario).values_list('id', 'nome')
    )
    chaves = set()
    for s in SafraUnidade.all_cooperativas.filter(cenario=cenario):
        mapa = armazens if s.entidade_tipo == 'Armazém' else fabricas
        nome = mapa.get(s.entidade_id)
        if nome:
            chaves.add((s.entidade_tipo, nome, s.data_inicio))
    return chaves


def _analisar_rotas(linhas, fabricas, armazens, chaves_no_banco, resumo):
    for numero, valores in linhas:
        origem = _texto(valores, 'origem')
        destino = _texto(valores, 'destino')
        if not origem or not destino:
            resumo.rejeitadas.append(
                LinhaRejeitada(ABA_ROTAS, numero, 'origem ou destino em branco', valores)
            )
            continue
        if origem not in armazens:
            resumo.rejeitadas.append(LinhaRejeitada(
                ABA_ROTAS, numero,
                f"origem '{origem}' não corresponde a nenhum armazém deste cenário", valores,
            ))
            continue
        if destino not in fabricas:
            resumo.rejeitadas.append(LinhaRejeitada(
                ABA_ROTAS, numero,
                f"destino '{destino}' não corresponde a nenhuma fábrica deste cenário", valores,
            ))
            continue
        erros = []
        for coluna in ('distancia_km', 'custo_frete_ton'):
            _, erro = _numero(valores, coluna)
            if erro:
                erros.append(erro)
        # custo_frete_entressafra em branco assume custo_frete_ton
        # (data_loader.py:386-387); só um valor presente e não numérico é erro.
        if valores.get('custo_frete_entressafra') is not None:
            _, erro = _numero(valores, 'custo_frete_entressafra')
            if erro:
                erros.append(erro)
        if erros:
            resumo.rejeitadas.append(
                LinhaRejeitada(ABA_ROTAS, numero, '; '.join(erros), valores)
            )
            continue
        if (origem, destino) in chaves_no_banco:
            resumo.atualizar += 1
        else:
            resumo.criar += 1


def _analisar_previsoes(linhas, fabricas, armazens, chaves_no_banco, resumo):
    for numero, valores in linhas:
        nome = _texto(valores, 'entidade')
        if not nome:
            resumo.rejeitadas.append(
                LinhaRejeitada(ABA_PREVISOES, numero, 'entidade em branco', valores)
            )
            continue
        tipo, erro = _resolver(nome, fabricas, armazens)
        if erro:
            resumo.rejeitadas.append(LinhaRejeitada(ABA_PREVISOES, numero, erro, valores))
            continue
        mes, erro = _data(valores, 'mes_referencia')
        if erro:
            resumo.rejeitadas.append(LinhaRejeitada(ABA_PREVISOES, numero, erro, valores))
            continue
        mes = mes.replace(day=1)
        # recebimento_produtor e vendas em branco valem 0 (bug A9 da Fase 1).
        erro_numerico = None
        for coluna in ('recebimento_produtor', 'vendas'):
            if valores.get(coluna) is None:
                continue
            _, erro = _numero(valores, coluna)
            if erro:
                erro_numerico = erro
                break
        if erro_numerico:
            resumo.rejeitadas.append(
                LinhaRejeitada(ABA_PREVISOES, numero, erro_numerico, valores)
            )
            continue
        if (tipo, nome, mes) in chaves_no_banco:
            resumo.atualizar += 1
        else:
            resumo.criar += 1


def _analisar_safras(linhas, fabricas, armazens, chaves_no_banco, resumo):
    for numero, valores in linhas:
        nome = _texto(valores, 'unidade')
        if not nome:
            resumo.rejeitadas.append(
                LinhaRejeitada(ABA_SAFRAS, numero, 'unidade em branco', valores)
            )
            continue
        tipo, erro = _resolver(nome, fabricas, armazens)
        if erro:
            resumo.rejeitadas.append(LinhaRejeitada(ABA_SAFRAS, numero, erro, valores))
            continue
        inicio, erro_i = _data(valores, 'data_inicio')
        fim, erro_f = _data(valores, 'data_fim')
        if erro_i or erro_f:
            resumo.rejeitadas.append(LinhaRejeitada(
                ABA_SAFRAS, numero, '; '.join(e for e in (erro_i, erro_f) if e), valores,
            ))
            continue
        if fim < inicio:
            resumo.rejeitadas.append(LinhaRejeitada(
                ABA_SAFRAS, numero, 'data_fim é anterior a data_inicio', valores,
            ))
            continue
        if (tipo, nome, inicio) in chaves_no_banco:
            resumo.atualizar += 1
        else:
            resumo.criar += 1
```

Substituir, no final de `analisar`, as duas chamadas a `_analisar_unidades` e o `return` por:

```python
    nomes_fabricas = fabricas_no_banco | _analisar_unidades(
        ABA_FABRICAS, abas[ABA_FABRICAS], fabricas_no_banco, relatorio.resumo(ABA_FABRICAS),
    )
    nomes_armazens = armazens_no_banco | _analisar_unidades(
        ABA_ARMAZENS, abas[ABA_ARMAZENS], armazens_no_banco, relatorio.resumo(ABA_ARMAZENS),
    )

    _analisar_rotas(
        abas[ABA_ROTAS], nomes_fabricas, nomes_armazens,
        _chaves_de_rota(cenario), relatorio.resumo(ABA_ROTAS),
    )
    _analisar_previsoes(
        abas[ABA_PREVISOES], nomes_fabricas, nomes_armazens,
        _chaves_de_previsao(cenario), relatorio.resumo(ABA_PREVISOES),
    )
    _analisar_safras(
        abas[ABA_SAFRAS], nomes_fabricas, nomes_armazens,
        _chaves_de_safra(cenario), relatorio.resumo(ABA_SAFRAS),
    )

    return relatorio
```

O retorno de `_analisar_unidades`, que a Task 1 ignorava, passa a ser a união "banco ∪ pasta" — é ela
que faz o bootstrap funcionar.

- [ ] **Step 4: Rodar os testes e confirmar que passam**

Run: `python -m pytest apps/simulacao/tests/test_planilha_analisar.py -v`
Expected: PASS (24 testes)

- [ ] **Step 5: Rodar a suíte inteira**

Run: `python -m pytest -q`
Expected: PASS — 233

- [ ] **Step 6: Commit**

```bash
git add apps/simulacao/planilha.py apps/simulacao/tests/test_planilha_analisar.py
git commit -m "feat(carga): resolucao de nomes para rotas, previsoes e safras"
```

---

### Task 3: `aplicar` — a escrita

**Files:**
- Modify: `apps/simulacao/planilha.py` (acrescentar ao final)
- Test: `apps/simulacao/tests/test_planilha_aplicar.py`

**Interfaces:**
- Consumes: `analisar`, `_ler_abas`, `_numero`, `_texto`, `_data`, `_resolver`, `OBRIGATORIOS_POR_ABA` (Tasks 1-2), e `montar_pasta`.
- Produces: `aplicar(arquivo, cenario=None, cooperativa=None, nome_novo=None) -> tuple[Relatorio, Cenario | None]`.
  Com `cenario` dado, grava nele. Com `cenario=None`, exige `cooperativa` e `nome_novo`, e cria o
  cenário — marcando `is_oficial=True` se for o primeiro daquela cooperativa. Devolve `(relatorio, None)`
  sem escrever quando há erro estrutural. A Task 5 consome exatamente essa assinatura.

**Nota de implementação:** `aplicar` chama `analisar` e depois relê a pasta para gravar. O objeto de
arquivo precisa ser rebobinado (`arquivo.seek(0)`) entre as duas leituras — openpyxl consome o stream.

- [ ] **Step 1: Escrever os testes que falham**

Criar `apps/simulacao/tests/test_planilha_aplicar.py`:

```python
import datetime
import io

from django.test import TestCase

from apps.core.models import Cooperativa
from apps.simulacao.models import (
    Armazem, Cenario, Fabrica, PrevisaoFabrica, Rota, SafraUnidade,
)
from apps.simulacao.planilha import ABA_FABRICAS, analisar, aplicar
from apps.simulacao.tests.planilha_fixtures import montar_pasta
from apps.simulacao.tests.test_planilha_analisar import ARMAZEM_OK, FABRICA_OK, ROTA_OK

PREVISAO_OK = {
    'entidade': 'FÁBRICA TESTE', 'mes_referencia': datetime.date(2026, 3, 1),
    'recebimento_produtor': 4500.5, 'vendas': 1200.25,
}
SAFRA_OK = {
    'unidade': 'ARMAZÉM A', 'data_inicio': datetime.date(2026, 2, 1),
    'data_fim': datetime.date(2026, 5, 31),
}


def pasta_completa():
    return montar_pasta(
        fabricas=[FABRICA_OK], armazens=[ARMAZEM_OK], rotas=[ROTA_OK],
        previsoes=[PREVISAO_OK], safras=[SAFRA_OK],
    )


class AplicarTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome='Comigo', slug='comigo')

    def test_bootstrap_cria_o_cenario_e_o_marca_oficial(self):
        _, cenario = aplicar(pasta_completa(), cooperativa=self.coop, nome_novo='Oficial 2026')

        self.assertEqual(cenario.nome, 'Oficial 2026')
        self.assertTrue(cenario.is_oficial)
        self.assertEqual(cenario.cooperativa_id, self.coop.id)

    def test_segundo_cenario_da_cooperativa_nao_e_oficial(self):
        aplicar(pasta_completa(), cooperativa=self.coop, nome_novo='Primeiro')

        _, segundo = aplicar(pasta_completa(), cooperativa=self.coop, nome_novo='Segundo')

        self.assertFalse(segundo.is_oficial)

    def test_grava_as_cinco_abas(self):
        _, cenario = aplicar(pasta_completa(), cooperativa=self.coop, nome_novo='Oficial')

        self.assertEqual(Fabrica.all_cooperativas.filter(cenario=cenario).count(), 1)
        self.assertEqual(Armazem.all_cooperativas.filter(cenario=cenario).count(), 1)
        self.assertEqual(Rota.all_cooperativas.filter(cenario=cenario).count(), 1)
        self.assertEqual(
            PrevisaoFabrica.all_cooperativas.filter(fabrica__cenario=cenario).count(), 1
        )
        self.assertEqual(SafraUnidade.all_cooperativas.filter(cenario=cenario).count(), 1)

    def test_rota_aponta_para_as_unidades_criadas_na_mesma_pasta(self):
        _, cenario = aplicar(pasta_completa(), cooperativa=self.coop, nome_novo='Oficial')

        rota = Rota.all_cooperativas.get(cenario=cenario)
        self.assertEqual(rota.armazem.nome, 'ARMAZÉM A')
        self.assertEqual(rota.fabrica.nome, 'FÁBRICA TESTE')

    def test_safra_deriva_o_tipo_e_aponta_para_a_unidade(self):
        _, cenario = aplicar(pasta_completa(), cooperativa=self.coop, nome_novo='Oficial')

        safra = SafraUnidade.all_cooperativas.get(cenario=cenario)
        armazem = Armazem.all_cooperativas.get(cenario=cenario)
        self.assertEqual(safra.entidade_tipo, 'Armazém')
        self.assertEqual(safra.entidade_id, armazem.id)

    def test_reimportar_atualiza_em_vez_de_duplicar(self):
        _, cenario = aplicar(pasta_completa(), cooperativa=self.coop, nome_novo='Oficial')
        alterada = montar_pasta(
            fabricas=[dict(FABRICA_OK, estoque_inicial=9999)],
            armazens=[ARMAZEM_OK], rotas=[ROTA_OK],
        )

        aplicar(alterada, cenario=cenario)

        self.assertEqual(Fabrica.all_cooperativas.filter(cenario=cenario).count(), 1)
        self.assertEqual(Fabrica.all_cooperativas.get(cenario=cenario).estoque_inicial, 9999)

    def test_upsert_nao_apaga_o_que_a_pasta_nao_menciona(self):
        _, cenario = aplicar(pasta_completa(), cooperativa=self.coop, nome_novo='Oficial')

        aplicar(montar_pasta(fabricas=[dict(FABRICA_OK, nome='OUTRA')]), cenario=cenario)

        self.assertEqual(Fabrica.all_cooperativas.filter(cenario=cenario).count(), 2)

    def test_linhas_rejeitadas_nao_sao_gravadas_e_as_validas_sim(self):
        pasta = montar_pasta(
            fabricas=[FABRICA_OK, dict(FABRICA_OK, nome='RUIM', estoque_inicial=None)],
        )

        relatorio, cenario = aplicar(pasta, cooperativa=self.coop, nome_novo='Oficial')

        self.assertEqual(Fabrica.all_cooperativas.filter(cenario=cenario).count(), 1)
        self.assertEqual(len(relatorio.resumo(ABA_FABRICAS).rejeitadas), 1)

    def test_erro_estrutural_nao_cria_cenario_nem_grava(self):
        relatorio, cenario = aplicar(
            io.BytesIO(b'lixo'), cooperativa=self.coop, nome_novo='Nao Deve Existir',
        )

        self.assertTrue(relatorio.tem_erro_estrutural)
        self.assertIsNone(cenario)
        self.assertFalse(Cenario.all_cooperativas.filter(nome='Nao Deve Existir').exists())

    def test_relatorio_de_aplicar_bate_com_o_de_analisar(self):
        pasta = pasta_completa()
        previsto = analisar(pasta, None)
        pasta.seek(0)

        aplicado, _ = aplicar(pasta, cooperativa=self.coop, nome_novo='Oficial')

        self.assertEqual(aplicado.total_criar, previsto.total_criar)
        self.assertEqual(aplicado.total_rejeitadas, previsto.total_rejeitadas)

    def test_nao_toca_em_cenario_de_outra_cooperativa(self):
        outra = Cooperativa.objects.create(nome='Outra', slug='outra')
        alheio = Cenario.all_cooperativas.create(
            cooperativa=outra, nome='Alheio', is_oficial=True,
        )
        Fabrica.all_cooperativas.create(
            cooperativa=outra, cenario=alheio, nome='NÃO MEXER',
            capacidade_estatica=1, capacidade_esmagamento_diaria=1,
            capacidade_recebimento_diaria=1, limite_caminhoes=1,
            carga_media_caminhao=1, estoque_inicial=1,
        )

        aplicar(pasta_completa(), cooperativa=self.coop, nome_novo='Oficial')

        self.assertEqual(Fabrica.all_cooperativas.filter(cenario=alheio).count(), 1)
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `python -m pytest apps/simulacao/tests/test_planilha_aplicar.py -v`
Expected: FAIL com `ImportError: cannot import name 'aplicar' from 'apps.simulacao.planilha'`

- [ ] **Step 3: Escrever `aplicar`**

Acrescentar ao topo de `planilha.py`:

```python
from django.db import transaction
```

e incluir `Cenario` no import de models.

Acrescentar ao final do arquivo:

```python
def aplicar(arquivo, cenario=None, cooperativa=None, nome_novo=None):
    """Reanalisa a pasta e grava as linhas válidas. Devolve (relatorio, cenario).

    Com `cenario=None`, cria o cenário a partir de `cooperativa` e `nome_novo`,
    marcando-o oficial se for o primeiro daquela cooperativa. A criação acontece
    DENTRO da mesma transação que grava as linhas, para que uma pasta com erro
    não deixe um cenário vazio para trás.

    Devolve (relatorio, None) sem escrever nada quando há erro estrutural.
    """
    relatorio = analisar(arquivo, cenario)
    if relatorio.tem_erro_estrutural:
        return relatorio, None

    arquivo.seek(0)
    abas, erro = _ler_abas(arquivo)
    if erro:  # defensivo: a mesma pasta acabou de ser lida com sucesso
        return _erro(erro), None

    with transaction.atomic():
        if cenario is None:
            primeiro = not Cenario.all_cooperativas.filter(cooperativa=cooperativa).exists()
            cenario = Cenario.all_cooperativas.create(
                cooperativa=cooperativa, nome=nome_novo, is_oficial=primeiro,
            )
        coop = cenario.cooperativa

        fabricas = _gravar_unidades(Fabrica, ABA_FABRICAS, abas[ABA_FABRICAS], cenario, coop)
        armazens = _gravar_unidades(Armazem, ABA_ARMAZENS, abas[ABA_ARMAZENS], cenario, coop)
        _gravar_rotas(abas[ABA_ROTAS], cenario, coop, fabricas, armazens)
        _gravar_previsoes(abas[ABA_PREVISOES], coop, fabricas, armazens)
        _gravar_safras(abas[ABA_SAFRAS], cenario, coop, fabricas, armazens)

    return relatorio, cenario


def _gravar_unidades(modelo, aba, linhas, cenario, coop):
    """Fábricas e Armazéns. Devolve {nome: instância} do cenário ao final."""
    existentes = {u.nome: u for u in modelo.all_cooperativas.filter(cenario=cenario)}
    for _numero, valores in linhas:
        nome = _texto(valores, 'nome')
        if not nome:
            continue
        numeros = {}
        invalida = False
        for coluna in OBRIGATORIOS_POR_ABA[aba]:
            valor, erro = _numero(valores, coluna)
            if erro:
                invalida = True
                break
            numeros[coluna] = valor
        if invalida:
            continue
        unidade = existentes.get(nome) or modelo(cooperativa=coop, cenario=cenario, nome=nome)
        for coluna, valor in numeros.items():
            setattr(unidade, coluna, valor)
        if aba == ABA_FABRICAS:
            unidade.limite_caminhoes = int(unidade.limite_caminhoes)
        unidade.full_clean()
        unidade.save()
        existentes[nome] = unidade
    return existentes


def _gravar_rotas(linhas, cenario, coop, fabricas, armazens):
    for _numero, valores in linhas:
        origem = _texto(valores, 'origem')
        destino = _texto(valores, 'destino')
        if origem not in armazens or destino not in fabricas:
            continue
        distancia, erro_d = _numero(valores, 'distancia_km')
        custo, erro_c = _numero(valores, 'custo_frete_ton')
        if erro_d or erro_c:
            continue
        if valores.get('custo_frete_entressafra') is None:
            entressafra = custo
        else:
            entressafra, erro_e = _numero(valores, 'custo_frete_entressafra')
            if erro_e:
                continue
        armazem = armazens[origem]
        fabrica = fabricas[destino]
        rota = Rota.all_cooperativas.filter(
            cenario=cenario, armazem=armazem, fabrica=fabrica,
        ).first() or Rota(
            cooperativa=coop, cenario=cenario, armazem=armazem, fabrica=fabrica,
        )
        rota.distancia_km = distancia
        rota.custo_frete_ton = custo
        rota.custo_frete_entressafra = entressafra
        rota.full_clean()
        rota.save()


def _gravar_previsoes(linhas, coop, fabricas, armazens):
    for _numero, valores in linhas:
        nome = _texto(valores, 'entidade')
        if not nome:
            continue
        tipo, erro = _resolver(nome, set(fabricas), set(armazens))
        if erro:
            continue
        mes, erro = _data(valores, 'mes_referencia')
        if erro:
            continue
        mes = mes.replace(day=1)
        numeros = {}
        invalida = False
        for coluna in ('recebimento_produtor', 'vendas'):
            if valores.get(coluna) is None:
                numeros[coluna] = 0
                continue
            valor, erro = _numero(valores, coluna)
            if erro:
                invalida = True
                break
            numeros[coluna] = valor
        if invalida:
            continue
        if tipo == 'Fábrica':
            modelo, campo, unidade = PrevisaoFabrica, 'fabrica', fabricas[nome]
        else:
            modelo, campo, unidade = PrevisaoArmazem, 'armazem', armazens[nome]
        previsao = modelo.all_cooperativas.filter(
            mes_referencia=mes, **{campo: unidade},
        ).first() or modelo(cooperativa=coop, mes_referencia=mes, **{campo: unidade})
        previsao.recebimento_produtor = numeros['recebimento_produtor']
        previsao.vendas = numeros['vendas']
        previsao.full_clean()
        previsao.save()


def _gravar_safras(linhas, cenario, coop, fabricas, armazens):
    for _numero, valores in linhas:
        nome = _texto(valores, 'unidade')
        if not nome:
            continue
        tipo, erro = _resolver(nome, set(fabricas), set(armazens))
        if erro:
            continue
        inicio, erro_i = _data(valores, 'data_inicio')
        fim, erro_f = _data(valores, 'data_fim')
        if erro_i or erro_f or fim < inicio:
            continue
        unidade = armazens[nome] if tipo == 'Armazém' else fabricas[nome]
        safra = SafraUnidade.all_cooperativas.filter(
            cenario=cenario, entidade_tipo=tipo, entidade_id=unidade.id, data_inicio=inicio,
        ).first() or SafraUnidade(
            cooperativa=coop, cenario=cenario, entidade_tipo=tipo,
            entidade_id=unidade.id, data_inicio=inicio,
        )
        safra.data_fim = fim
        safra.full_clean()
        safra.save()
```

- [ ] **Step 4: Rodar os testes e confirmar que passam**

Run: `python -m pytest apps/simulacao/tests/test_planilha_aplicar.py -v`
Expected: PASS (11 testes)

- [ ] **Step 5: Rodar a suíte inteira**

Run: `python -m pytest -q`
Expected: PASS — 244

- [ ] **Step 6: Commit**

```bash
git add apps/simulacao/planilha.py apps/simulacao/tests/test_planilha_aplicar.py
git commit -m "feat(carga): aplicar - grava a planilha e cria o cenario no bootstrap"
```

---

### Task 4: Template gerado

**Files:**
- Modify: `apps/simulacao/planilha.py` (acrescentar ao final)
- Test: `apps/simulacao/tests/test_planilha_template.py`

**Interfaces:**
- Consumes: `COLUNAS_POR_ABA`, `ABAS_NA_ORDEM`, `analisar` (Tasks 1-2).
- Produces: `gerar_template() -> io.BytesIO` — pasta `.xlsx` com as cinco abas, cada uma contendo apenas a linha de cabeçalho. A Task 5 a serve por HTTP.

**Por que gerar em vez de versionar um arquivo:** os quatro `.xlsx` em `templates/` são artefatos
estáticos que envelhecem em silêncio quando o schema muda. Gerar a partir de `COLUNAS_POR_ABA` — a
mesma constante que o parser consome — elimina a categoria de bug.

- [ ] **Step 1: Escrever os testes que falham**

Criar `apps/simulacao/tests/test_planilha_template.py`:

```python
from django.test import SimpleTestCase
from openpyxl import load_workbook

from apps.simulacao.planilha import (
    ABAS_NA_ORDEM, COLUNAS_POR_ABA, analisar, gerar_template,
)


class GerarTemplateTests(SimpleTestCase):
    def test_tem_as_cinco_abas_na_ordem_de_dependencia(self):
        wb = load_workbook(gerar_template())

        self.assertEqual(wb.sheetnames, ABAS_NA_ORDEM)

    def test_cada_aba_tem_o_cabecalho_que_o_parser_espera(self):
        wb = load_workbook(gerar_template())

        for nome in ABAS_NA_ORDEM:
            cabecalho = [c.value for c in wb[nome][1]]
            self.assertEqual(cabecalho, COLUNAS_POR_ABA[nome], f'aba {nome}')

    def test_nao_traz_linhas_de_dados(self):
        wb = load_workbook(gerar_template())

        for nome in ABAS_NA_ORDEM:
            self.assertEqual(wb[nome].max_row, 1, f'aba {nome}')

    def test_o_proprio_parser_aceita_o_template_vazio(self):
        """A prova de que template e parser não divergem."""
        relatorio = analisar(gerar_template(), None)

        self.assertFalse(relatorio.tem_erro_estrutural)
        self.assertEqual(relatorio.total_criar, 0)
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `python -m pytest apps/simulacao/tests/test_planilha_template.py -v`
Expected: FAIL com `ImportError: cannot import name 'gerar_template'`

- [ ] **Step 3: Escrever `gerar_template`**

Acrescentar `import io` e `from openpyxl import Workbook` ao topo de `planilha.py`, e ao final:

```python
def gerar_template():
    """Pasta modelo com as cinco abas e seus cabeçalhos, sem dados.

    Construída a partir de COLUNAS_POR_ABA -- a mesma constante que o parser
    consome -- para que o template não possa divergir do que a importação aceita.
    """
    wb = Workbook()
    wb.remove(wb.active)
    for nome in ABAS_NA_ORDEM:
        ws = wb.create_sheet(nome)
        ws.append(COLUNAS_POR_ABA[nome])
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer
```

- [ ] **Step 4: Rodar os testes e confirmar que passam**

Run: `python -m pytest apps/simulacao/tests/test_planilha_template.py -v`
Expected: PASS (4 testes)

- [ ] **Step 5: Commit**

```bash
git add apps/simulacao/planilha.py apps/simulacao/tests/test_planilha_template.py
git commit -m "feat(carga): template .xlsx gerado a partir das colunas do parser"
```

---

### Task 5: As telas — upload, pré-visualização, confirmação e download

**Files:**
- Modify: `apps/simulacao/views.py` (acrescentar ao final)
- Modify: `apps/simulacao/urls.py` (três rotas)
- Create: `templates/simulacao/carga.html`, `templates/simulacao/_carga_content.html`
- Create: `templates/simulacao/carga_preview.html`, `templates/simulacao/_carga_preview_content.html`
- Modify: `templates/simulacao/_cenarios_content.html` (link para a carga)
- Test: `apps/simulacao/tests/test_views_carga.py`

**Interfaces:**
- Consumes: `analisar(arquivo, cenario)`, `aplicar(arquivo, cenario=None, cooperativa=None, nome_novo=None) -> (Relatorio, Cenario | None)`, `gerar_template() -> BytesIO`, `ABAS_NA_ORDEM`.
- Produces: as URLs nomeadas `simulacao:carga`, `simulacao:carga_preview`, `simulacao:carga_template`.

**Armazenamento entre as duas requisições:** o `.xlsx` vai para `MEDIA_ROOT/carga/<token>.xlsx`, com
`token` gerado por `secrets.token_urlsafe(16)`. O token e o alvo ficam em `request.session['carga']`,
o que impede um usuário de alcançar o upload de outro — o token sozinho nunca é autoridade suficiente.
O arquivo é apagado ao aplicar e substituído a cada novo upload do mesmo usuário.

- [ ] **Step 1: Escrever os testes que falham**

Criar `apps/simulacao/tests/test_views_carga.py`:

```python
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from apps.core.models import Cooperativa, User
from apps.simulacao.models import Cenario, Fabrica
from apps.simulacao.planilha import ABAS_NA_ORDEM
from apps.simulacao.tests.planilha_fixtures import montar_pasta
from apps.simulacao.tests.test_planilha_analisar import ARMAZEM_OK, FABRICA_OK

XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


def upload(nome='dados.xlsx', **abas):
    if not abas:
        abas = {'fabricas': [FABRICA_OK], 'armazens': [ARMAZEM_OK]}
    return SimpleUploadedFile(nome, montar_pasta(**abas).read(), content_type=XLSX)


class CargaTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome='Comigo', slug='comigo')
        self.user = User.objects.create_user(
            username='teste', password='segredo123',
            papel=User.PAPEL_ADMIN_COOPERATIVA, cooperativa=self.coop,
        )
        self.client.force_login(self.user)

    def test_exige_login(self):
        self.client.logout()

        resposta = self.client.get(reverse('simulacao:carga'))

        self.assertEqual(resposta.status_code, 302)

    def test_template_e_servido_como_xlsx(self):
        resposta = self.client.get(reverse('simulacao:carga_template'))

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta['Content-Type'], XLSX)
        self.assertIn('attachment', resposta['Content-Disposition'])

    def test_upload_para_cenario_novo_mostra_previsao_sem_escrever(self):
        resposta = self.client.post(
            reverse('simulacao:carga'),
            {'nome_novo': 'Oficial 2026', 'arquivo': upload()}, follow=True,
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'Oficial 2026')
        self.assertFalse(Cenario.all_cooperativas.exists())
        self.assertFalse(Fabrica.all_cooperativas.exists())

    def test_confirmar_grava_e_cria_o_cenario_oficial(self):
        self.client.post(
            reverse('simulacao:carga'),
            {'nome_novo': 'Oficial 2026', 'arquivo': upload()}, follow=True,
        )
        token = self.client.session['carga']['token']

        self.client.post(reverse('simulacao:carga_preview', args=[token]), follow=True)

        cenario = Cenario.all_cooperativas.get(nome='Oficial 2026')
        self.assertTrue(cenario.is_oficial)
        self.assertEqual(Fabrica.all_cooperativas.filter(cenario=cenario).count(), 1)

    def test_upload_para_cenario_existente(self):
        cenario = Cenario.all_cooperativas.create(
            cooperativa=self.coop, nome='Oficial', is_oficial=True,
        )
        self.client.post(
            reverse('simulacao:carga'),
            {'cenario_id': cenario.id, 'arquivo': upload()}, follow=True,
        )
        token = self.client.session['carga']['token']

        self.client.post(reverse('simulacao:carga_preview', args=[token]), follow=True)

        self.assertEqual(Fabrica.all_cooperativas.filter(cenario=cenario).count(), 1)
        self.assertEqual(Cenario.all_cooperativas.count(), 1)

    def test_cenario_de_outra_cooperativa_nao_e_alcancavel(self):
        outra = Cooperativa.objects.create(nome='Outra', slug='outra')
        alheio = Cenario.all_cooperativas.create(
            cooperativa=outra, nome='Alheio', is_oficial=True,
        )

        resposta = self.client.post(
            reverse('simulacao:carga'), {'cenario_id': alheio.id, 'arquivo': upload()},
        )

        self.assertEqual(resposta.status_code, 404)
        self.assertFalse(Fabrica.all_cooperativas.exists())

    def test_arquivo_ilegivel_mostra_erro_estrutural_e_nao_oferece_confirmar(self):
        ruim = SimpleUploadedFile('x.xlsx', b'nao e um xlsx', content_type=XLSX)

        resposta = self.client.post(
            reverse('simulacao:carga'), {'nome_novo': 'Qualquer', 'arquivo': ruim}, follow=True,
        )

        self.assertContains(resposta, 'xlsx')
        self.assertNotContains(resposta, 'name="confirmar"')

    def test_preview_de_token_alheio_e_404(self):
        self.client.post(
            reverse('simulacao:carga'),
            {'nome_novo': 'Oficial', 'arquivo': upload()}, follow=True,
        )

        resposta = self.client.get(
            reverse('simulacao:carga_preview', args=['token-inventado'])
        )

        self.assertEqual(resposta.status_code, 404)

    def test_previsao_lista_as_linhas_rejeitadas(self):
        ruim = upload(
            fabricas=[FABRICA_OK, dict(FABRICA_OK, nome='RUIM', estoque_inicial=None)]
        )

        resposta = self.client.post(
            reverse('simulacao:carga'), {'nome_novo': 'Oficial', 'arquivo': ruim}, follow=True,
        )

        self.assertContains(resposta, 'estoque_inicial')

    def test_pagina_de_upload_lista_as_cinco_abas_esperadas(self):
        resposta = self.client.get(reverse('simulacao:carga'))

        for nome in ABAS_NA_ORDEM:
            self.assertContains(resposta, nome)
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `python -m pytest apps/simulacao/tests/test_views_carga.py -v`
Expected: FAIL com `NoReverseMatch: Reverse for 'carga' not found`

- [ ] **Step 3: Escrever as views**

Acrescentar ao final de `apps/simulacao/views.py` (e os imports que faltarem ao topo):

```python
import secrets

from django.core.files.storage import default_storage
from django.http import FileResponse, Http404

from apps.simulacao.planilha import ABAS_NA_ORDEM, analisar, aplicar, gerar_template

XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


def _caminho_da_carga(token):
    return f'carga/{token}.xlsx'


@login_required
def carga_template(request):
    return FileResponse(
        gerar_template(), as_attachment=True,
        filename='modelo-carga-comigo.xlsx', content_type=XLSX,
    )


@login_required
def carga_upload(request):
    cooperativa_id = request.user.cooperativa_id
    cenarios = list(Cenario.all_cooperativas.filter(cooperativa_id=cooperativa_id))

    if request.method == 'POST':
        arquivo = request.FILES.get('arquivo')
        if not arquivo:
            return HttpResponseBadRequest('Nenhum arquivo enviado.')

        cenario_id = request.POST.get('cenario_id')
        nome_novo = (request.POST.get('nome_novo') or '').strip()
        if cenario_id:
            # Filtrar pela cooperativa: um cenário alheio não é distinguível
            # de um inexistente.
            get_object_or_404(
                Cenario.all_cooperativas, id=cenario_id, cooperativa_id=cooperativa_id,
            )
        elif not nome_novo:
            return HttpResponseBadRequest(
                'Informe um cenário existente ou o nome de um novo.'
            )

        anterior = request.session.get('carga')
        if anterior:
            default_storage.delete(_caminho_da_carga(anterior['token']))

        token = secrets.token_urlsafe(16)
        default_storage.save(_caminho_da_carga(token), arquivo)
        request.session['carga'] = {
            'token': token,
            'cenario_id': int(cenario_id) if cenario_id else None,
            'nome_novo': nome_novo or None,
        }
        return redirect('simulacao:carga_preview', token=token)

    context = {'cenarios': cenarios, 'abas': ABAS_NA_ORDEM}
    template = 'simulacao/_carga_content.html' if request.htmx else 'simulacao/carga.html'
    return render(request, template, context)


@login_required
def carga_preview(request, token):
    guardado = request.session.get('carga')
    if not guardado or guardado['token'] != token:
        raise Http404('Carga não encontrada.')

    cooperativa_id = request.user.cooperativa_id
    cenario = None
    if guardado['cenario_id']:
        cenario = get_object_or_404(
            Cenario.all_cooperativas,
            id=guardado['cenario_id'], cooperativa_id=cooperativa_id,
        )

    caminho = _caminho_da_carga(token)

    if request.method == 'POST':
        with default_storage.open(caminho, 'rb') as arquivo:
            _relatorio, gravado = aplicar(
                arquivo, cenario=cenario,
                cooperativa=request.user.cooperativa, nome_novo=guardado['nome_novo'],
            )
        default_storage.delete(caminho)
        del request.session['carga']
        if gravado is None:
            return HttpResponseBadRequest('A planilha não pôde ser aplicada.')
        return redirect('simulacao:fabricas_grid', cenario_id=gravado.id)

    with default_storage.open(caminho, 'rb') as arquivo:
        relatorio = analisar(arquivo, cenario)

    context = {
        'relatorio': relatorio, 'token': token,
        'cenario': cenario, 'nome_novo': guardado['nome_novo'],
    }
    template = (
        'simulacao/_carga_preview_content.html' if request.htmx
        else 'simulacao/carga_preview.html'
    )
    return render(request, template, context)
```

- [ ] **Step 4: Registrar as URLs**

Acrescentar a `apps/simulacao/urls.py`, dentro de `urlpatterns`:

```python
    path('carga/', views.carga_upload, name='carga'),
    path('carga/template/', views.carga_template, name='carga_template'),
    path('carga/<str:token>/', views.carga_preview, name='carga_preview'),
```

Ordenação obrigatória: `carga/template/` vem **antes** de `carga/<str:token>/`, senão o token
`template` captura a rota do download.

- [ ] **Step 5: Escrever os templates**

Criar `templates/simulacao/carga.html`:

```html
{% extends "base.html" %}
{% block content %}
{% include "simulacao/_carga_content.html" %}
{% endblock %}
```

Criar `templates/simulacao/_carga_content.html`:

```html
<h1 class="text-xl font-semibold mb-4">Carga de Dados</h1>

<c-card class="mb-6">
    <h2 class="font-medium mb-3">Enviar planilha</h2>
    <p class="text-sm mb-4">
        Uma pasta <code>.xlsx</code> com as abas
        {% for aba in abas %}<strong>{{ aba }}</strong>{% if not forloop.last %}, {% endif %}{% endfor %}.
        Abas ausentes são ignoradas. Nada é gravado até você confirmar na tela seguinte.
    </p>
    <p class="mb-4">
        <a href="{% url 'simulacao:carga_template' %}" class="text-[--cor-primaria] hover:underline">
            Baixar planilha modelo
        </a>
    </p>

    <form method="post" enctype="multipart/form-data" action="{% url 'simulacao:carga' %}"
          class="flex flex-col gap-4">
        {% csrf_token %}
        <div>
            <label class="block text-sm mb-1" for="id_cenario_id">Importar em um cenário existente</label>
            <select id="id_cenario_id" name="cenario_id" class="border rounded px-2 py-1">
                <option value="">— criar um cenário novo —</option>
                {% for cenario in cenarios %}
                <option value="{{ cenario.id }}">{{ cenario.nome }}</option>
                {% endfor %}
            </select>
        </div>
        <div>
            <label class="block text-sm mb-1" for="id_nome_novo">…ou nomeie um cenário novo</label>
            <input type="text" id="id_nome_novo" name="nome_novo" class="border rounded px-2 py-1">
            {% if not cenarios %}
            <p class="text-sm mt-1">
                Esta cooperativa ainda não tem cenários — o primeiro será marcado como oficial.
            </p>
            {% endif %}
        </div>
        <div>
            <label class="block text-sm mb-1" for="id_arquivo">Planilha</label>
            <input type="file" id="id_arquivo" name="arquivo" accept=".xlsx" required
                   class="border rounded px-2 py-1">
        </div>
        <div>
            <button type="submit"
                    class="rounded bg-[--cor-primaria] hover:bg-[--cor-primaria-hover] text-white px-4 py-2">
                Pré-visualizar
            </button>
        </div>
    </form>
</c-card>
```

Criar `templates/simulacao/carga_preview.html`:

```html
{% extends "base.html" %}
{% block content %}
{% include "simulacao/_carga_preview_content.html" %}
{% endblock %}
```

Criar `templates/simulacao/_carga_preview_content.html`:

```html
<h1 class="text-xl font-semibold mb-4">
    Pré-visualização — {% if cenario %}{{ cenario.nome }}{% else %}{{ nome_novo }} (novo){% endif %}
</h1>

{% if relatorio.tem_erro_estrutural %}
<c-card class="mb-6">
    <h2 class="font-medium mb-2">A planilha não pôde ser lida</h2>
    <p>{{ relatorio.erro_estrutural }}</p>
    <p class="mt-4">
        <a href="{% url 'simulacao:carga' %}" class="text-[--cor-primaria] hover:underline">
            Enviar outra planilha
        </a>
    </p>
</c-card>
{% else %}

<c-card class="mb-6">
    <table class="w-full text-sm">
        <thead>
            <tr class="text-left border-b border-[--cor-borda]">
                <th class="py-2">Aba</th>
                <th class="py-2">Criar</th>
                <th class="py-2">Atualizar</th>
                <th class="py-2">Rejeitadas</th>
            </tr>
        </thead>
        <tbody>
            {% for resumo in relatorio.abas %}
            <tr class="border-b border-[--cor-borda]">
                <td class="py-2">{{ resumo.aba }}</td>
                <td class="py-2">{{ resumo.criar }}</td>
                <td class="py-2">{{ resumo.atualizar }}</td>
                <td class="py-2">{{ resumo.rejeitadas|length }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</c-card>

{% if relatorio.total_rejeitadas %}
<c-card class="mb-6">
    <h2 class="font-medium mb-3">Linhas rejeitadas ({{ relatorio.total_rejeitadas }})</h2>
    <p class="text-sm mb-3">
        Estas linhas não serão importadas; as demais serão. Corrija a planilha e reenvie, ou
        confirme para importar apenas o que está válido.
    </p>
    <table class="w-full text-sm">
        <thead>
            <tr class="text-left border-b border-[--cor-borda]">
                <th class="py-2">Aba</th>
                <th class="py-2">Linha</th>
                <th class="py-2">Motivo</th>
            </tr>
        </thead>
        <tbody>
            {% for resumo in relatorio.abas %}{% for rejeitada in resumo.rejeitadas %}
            <tr class="border-b border-[--cor-borda]">
                <td class="py-2">{{ rejeitada.aba }}</td>
                <td class="py-2">{{ rejeitada.linha }}</td>
                <td class="py-2">{{ rejeitada.motivo }}</td>
            </tr>
            {% endfor %}{% endfor %}
        </tbody>
    </table>
</c-card>
{% endif %}

<form method="post" action="{% url 'simulacao:carga_preview' token=token %}" class="flex gap-3">
    {% csrf_token %}
    <button type="submit" name="confirmar" value="1"
            class="rounded bg-[--cor-primaria] hover:bg-[--cor-primaria-hover] text-white px-4 py-2">
        Confirmar e importar
    </button>
    <a href="{% url 'simulacao:carga' %}"
       class="rounded border border-[--cor-borda] px-4 py-2">Cancelar</a>
</form>
{% endif %}
```

- [ ] **Step 6: Ligar a carga à tela de Cenários**

Acrescentar ao final de `templates/simulacao/_cenarios_content.html`:

```html
<p class="mt-6">
    <a href="{% url 'simulacao:carga' %}" class="text-[--cor-primaria] hover:underline">
        Carregar dados por planilha
    </a>
</p>
```

- [ ] **Step 7: Rodar os testes e confirmar que passam**

Run: `python -m pytest apps/simulacao/tests/test_views_carga.py -v`
Expected: PASS (10 testes)

- [ ] **Step 8: Rodar a suíte inteira**

Run: `python -m pytest -q`
Expected: PASS — 258

- [ ] **Step 9: Commit**

```bash
git add apps/simulacao/views.py apps/simulacao/urls.py templates/simulacao/ apps/simulacao/tests/test_views_carga.py
git commit -m "feat(carga): telas de upload, pre-visualizacao e confirmacao"
```

- [ ] **Step 10: Emendar o roteiro e o mapa de arquivos**

Duas edições de documentação, ambas exigidas pela spec:

1. Em `docs/superpowers/specs/2026-08-22-fase5-arquitetura-saas-django.md`, seção "Fases de migração":
   inserir a Carga de Dados entre a fase 3 (UI) e a fase 4 (Procrastinate), renumerando as seguintes,
   com a justificativa de uma linha — a otimização não tem o que otimizar sem dados carregados.
2. Em `CLAUDE.md`, seção "Architecture / File Map": acrescentar `apps/simulacao/planilha.py`, seguindo
   o estilo das entradas vizinhas.

```bash
git add docs/superpowers/specs/2026-08-22-fase5-arquitetura-saas-django.md CLAUDE.md
git commit -m "docs: place Carga de Dados in the migration phase sequence"
```

---

## Verificação manual (do controlador, não do implementador)

Depois da Task 5, e não antes:

1. `python manage.py runserver`, logar, abrir `/simulacao/carga/`.
2. Baixar a planilha modelo e conferir as cinco abas.
3. Preencher com os dados reais de uma cooperativa e importar num cenário novo.
4. Conferir que as cinco grades mostram o mesmo que `espelhar_legado` produziu a partir do banco
   legado — dois caminhos independentes para o mesmo destino, a checagem cruzada mais forte
   disponível.
5. Reenviar a mesma planilha e confirmar que a pré-visualização passa a dizer "atualizar", não "criar".
