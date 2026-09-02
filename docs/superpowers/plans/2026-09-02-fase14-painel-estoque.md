# Fase 14 — Painel de Movimentação de Estoque — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Uma aba "Estoque" dentro do cenário que mostra as movimentações de estoque de uma simulação (`ResumoMensalArmazem` / `ResumoMensalFabrica`) em três visões — Sistema (mensal), Por armazém, Por fábrica — com card de pico, comparação entre cenários, filtros de mês/unidade, exportação Excel/CSV e um gráfico de linha, sinalizando excedente e ruptura.

**Architecture:** Módulo novo `apps/simulacao/estoque.py` (funções puras, agregação por ORM sobre `ResumoMensal*`, `Model.objects` escopado), `EstoqueForm` em `apps/simulacao/forms.py`, views novas em `apps/simulacao/views.py` (`estoque_tab`, `estoque_export`), 5 parciais HTMX, Chart.js via o mesmo padrão lazy da Fase 13 (ADR 0013). Espelha ponto a ponto a arquitetura da Fase 13 (`apps/simulacao/resultados.py` + aba "Resultados") mas como código próprio — sem tocar `resultados.py`, `services.py`, `engine.py`, `tasks.py`, `apps/integracoes`, `mcp_server.py`. Nenhum model muda — sem migrations.

**Tech Stack:** Django 6, HTMX, django-cotton, daisyUI, Chart.js 4.4.7 (CDN, ADR 0013), openpyxl (já é dep), PostgreSQL, pytest.

**Spec:** `docs/superpowers/specs/2026-09-02-fase14-painel-estoque-design.md` — leia os dois.

## Global Constraints

Todo requisito de tarefa inclui implicitamente esta seção.

- **Sem migrations.** Nenhum model muda. `python manage.py makemigrations --check --dry-run` tem de sair "No changes detected".
- **TDD estrito** (red → green): teste que falha → confirma que falha pelo motivo certo → mínimo → verde. Testes em `apps/simulacao/tests/` (+ um em `apps/core/tests/test_render_smoke.py`).
- **Banco real:** PostgreSQL local via `DJANGO_DB_*` (`config.settings.dev`, default do `pytest.ini`). Suíte atual = **433 passed**; ao fim continua verde + os novos (~45).
- **Fonte única de dados:** `ResumoMensalArmazem` (`mes` `'YYYY-MM'`, `armazem` FK, `rec_produtor`, `envio_transbordo`, `vendas`, `saldo_estoque`, `capacidade_estatica`, `excedente` — todos FloatField) e `ResumoMensalFabrica` (idem, mas `rec_transbordo` e `esmagado` no lugar de `envio_transbordo` e `vendas`). O engine grava **uma linha por (unidade, mês)** por execução (wipe + rewrite). `saldo_estoque` / `capacidade_estatica` / `excedente` são snapshots de fim de mês (níveis, não somáveis entre meses); os demais são fluxos.
- **Tenancy:** `estoque.py` usa `ResumoMensalArmazem.objects` / `ResumoMensalFabrica.objects` / `Cenario.objects` / `Armazem.objects` / `Fabrica.objects` (escopado pelo contextvar via `CooperativaScopeMiddleware`), **não** `all_cooperativas`. Testes de unidade setam o contextvar no `setUp` com `apps.core.tenancy.definir_cooperativa_atual(coop_id)` e resetam no `tearDown` com `resetar_cooperativa_atual`.
- **Gate das views:** `@login_required` + `@requer_membro_organizacao` (de `apps.core.permissions`). Anônimo → redireciona login; Admin Vector sem organização → `PermissionDenied` (403); membro ou Admin Vector com organização → passa. Cenário de outra coop → 404. Deep-link sem resultado → 200 estado vazio, não 404.
- **Formatação pt-BR:** filtro `volume` de `apps/simulacao/templatetags/simulacao_filters.py` para toda célula numérica. **Só toneladas** — sem `moeda`, sem sacas.
- **Comparação:** templatetag `variacao` (reaproveitado da Fase 13; `text-error` ↑ maior / `text-success` ↓ menor; U+2212). `estoque.py` devolve só os números crus (`float | None | "novo"`).
- **Chart.js:** versão exata `4.4.7`, de `https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js`. Carregado **só** no parcial `_estoque_grafico.html`, nunca no `base.html`. Ids próprios (`grafico-estoque`, `grafico-estoque-dados`, `window._estoqueChart`).
- **`PAGE_SIZE = 100`**, `EXPORT_MAX = 50_000` — constantes em `apps/simulacao/estoque.py`.
- **`RecorteGrandeDemais`** — exceção de módulo em `estoque.py` (2 linhas, não acopla ao `resultados`).
- **BOM do CSV** = o escape `"﻿"`, **nunca** um caractere BOM literal na fonte.
- **`VERSION` → `1.3.0`** ao fim (minor, aditivo); tag `v1.3.0` anotada, local (não pushed automaticamente).

## Config das visões (referência — usada por várias tarefas)

O dict `VISOES` em `apps/simulacao/estoque.py` mapeia `visao ∈ {"sistema","armazem","fabrica"}` → definição. `ROTULOS_VISAO = (("sistema","Sistema"),("armazem","Por armazém"),("fabrica","Por fábrica"))`.

| `visao` | fonte | colunas de dimensão | colunas de métrica (chaves de linha) | pagina | `_chave` |
|---|---|---|---|---|---|
| `"sistema"` | merge das 2 tabelas por mês | Mês | `recebimento`·`transbordo`·`esmagamento`·`vendas`·`saldo`·`capacidade`·`excedente` | não | `(mes,)` |
| `"armazem"` | `ResumoMensalArmazem` | Mês, Armazém (`unidade`) | `rec_produtor`·`envio_transbordo`·`vendas`·`saldo`·`capacidade`·`excedente` | sim | `(mes, unidade)` |
| `"fabrica"` | `ResumoMensalFabrica` | Mês, Fábrica (`unidade`) | `rec_produtor`·`rec_transbordo`·`esmagado`·`saldo`·`capacidade`·`excedente` | sim | `(mes, unidade)` |

Todas as colunas de métrica: `{"tipo": "num", "comparavel": True}`. Coluna Mês: `{"key": "mes", "tipo": "mes"}`. Coluna de unidade: `{"key": "unidade", "tipo": "texto"}` (label "Armazém" ou "Fábrica"). Na visão "sistema": `recebimento` = Σ `rec_produtor` das **duas** tabelas; `transbordo` = Σ `envio_transbordo` (armazéns) — não somar `rec_transbordo` das fábricas (é o mesmo número por construção do engine). `saldo`/`capacidade`/`excedente` no mapa de linha vêm de `saldo_estoque`/`capacidade_estatica`/`excedente` do model.

---

### Task 1: `EstoqueForm` + config das visões

**Files:**
- Modify: `apps/simulacao/forms.py`
- Create: `apps/simulacao/estoque.py` (só constantes + `VISOES` + `ROTULOS_VISAO` + `normalizar_visao` + `RecorteGrandeDemais` + os dois helpers de queryset)
- Test: `apps/simulacao/tests/test_estoque_config.py`

**Interfaces:**
- Produces:
  - `apps/simulacao/estoque.py`: `PAGE_SIZE = 100`, `EXPORT_MAX = 50_000`, `VISOES: dict[str, dict]` (chaves `"sistema"`/`"armazem"`/`"fabrica"`, cada uma `{"fonte","colunas","pagina"}`), `ROTULOS_VISAO`, `class RecorteGrandeDemais(Exception)`, `normalizar_visao(visao) -> str` (entrada inválida → `"sistema"`), `_queryset_unidade(modelo, cenario_id, fonte, filtros) -> QuerySet` (filtra por `cenario_id` + `mes__gte/lte` + `armazem_id__in`/`fabrica_id__in` conforme `fonte`).
  - `apps/simulacao/forms.py`: `EstoqueForm(forms.Form)` com `__init__(self, *args, cenario=None, **kwargs)`; campos `mes_de`/`mes_ate` (`CharField`, `required=False`, `RegexValidator(r"^\d{4}-\d{2}$")`, `widget=TextInput(attrs={"type": "month", ...})`), `armazem_ids`/`fabrica_ids` (`ModelMultipleChoiceField`, `required=False`, mesmos `_MULTI_ATTRS` do `ResultadosForm`). `filtros_limpos(self) -> dict` → `{"mes_de","mes_ate","armazem_ids","fabrica_ids"}` (`""` para meses ausentes, listas de ids para os multi) após `is_valid()`.

- [ ] **Step 1: Write the failing test**

```python
# apps/simulacao/tests/test_estoque_config.py
from django.test import TestCase

from apps.core.models import Cooperativa
from apps.core.tenancy import definir_cooperativa_atual, resetar_cooperativa_atual
from apps.simulacao import estoque
from apps.simulacao.forms import EstoqueForm
from apps.simulacao.models import Armazem, Cenario, Fabrica


class VisoesConfigTests(TestCase):
    def test_tres_visoes_existem_com_colunas_de_metrica_comparaveis(self):
        for visao in ("sistema", "armazem", "fabrica"):
            self.assertIn(visao, estoque.VISOES, visao)
            metricas = [c for c in estoque.VISOES[visao]["colunas"] if c["tipo"] == "num"]
            self.assertGreaterEqual(len(metricas), 6, visao)
            self.assertTrue(all(c.get("comparavel") for c in metricas), visao)

    def test_sistema_nao_pagina_por_unidade_pagina(self):
        self.assertFalse(estoque.VISOES["sistema"]["pagina"])
        self.assertTrue(estoque.VISOES["armazem"]["pagina"])
        self.assertTrue(estoque.VISOES["fabrica"]["pagina"])

    def test_colunas_de_dimensao(self):
        chaves_sistema = [c["key"] for c in estoque.VISOES["sistema"]["colunas"]]
        self.assertEqual(chaves_sistema[0], "mes")
        self.assertNotIn("unidade", chaves_sistema)
        self.assertEqual([c["key"] for c in estoque.VISOES["armazem"]["colunas"]][:2], ["mes", "unidade"])

    def test_normalizar_visao(self):
        self.assertEqual(estoque.normalizar_visao("armazem"), "armazem")
        self.assertEqual(estoque.normalizar_visao(None), "sistema")
        self.assertEqual(estoque.normalizar_visao("xpto"), "sistema")

    def test_rotulos_visao_sao_pares(self):
        self.assertEqual(dict(estoque.ROTULOS_VISAO)["armazem"], "Por armazém")


class EstoqueFormTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome="C", slug="c")
        self._tok = definir_cooperativa_atual(self.coop.id)
        self.cenario = Cenario.objects.create(cooperativa=self.coop, nome="Cen")
        self.arm = Armazem.objects.create(
            cooperativa=self.coop, cenario=self.cenario, nome="A1",
            capacidade_estatica=1, capacidade_expedicao_diaria=1, estoque_inicial=0)

    def tearDown(self):
        resetar_cooperativa_atual(self._tok)

    def test_form_vazio_valido_filtros_vazios(self):
        form = EstoqueForm({}, cenario=self.cenario)
        self.assertTrue(form.is_valid())
        self.assertEqual(form.filtros_limpos(),
                         {"mes_de": "", "mes_ate": "", "armazem_ids": [], "fabrica_ids": []})

    def test_form_com_mes_e_armazem(self):
        form = EstoqueForm(
            {"mes_de": "2026-01", "mes_ate": "2026-06", "armazem_ids": [self.arm.id]},
            cenario=self.cenario)
        self.assertTrue(form.is_valid(), form.errors)
        f = form.filtros_limpos()
        self.assertEqual(f["mes_de"], "2026-01")
        self.assertEqual(f["armazem_ids"], [self.arm.id])

    def test_mes_formato_invalido_rejeitado(self):
        form = EstoqueForm({"mes_de": "janeiro"}, cenario=self.cenario)
        self.assertFalse(form.is_valid())

    def test_armazem_de_outro_cenario_invalido(self):
        outro = Cenario.objects.create(cooperativa=self.coop, nome="Outro")
        arm2 = Armazem.objects.create(
            cooperativa=self.coop, cenario=outro, nome="A2",
            capacidade_estatica=1, capacidade_expedicao_diaria=1, estoque_inicial=0)
        form = EstoqueForm({"armazem_ids": [arm2.id]}, cenario=self.cenario)
        self.assertFalse(form.is_valid())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest apps/simulacao/tests/test_estoque_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'apps.simulacao.estoque'` / `ImportError` de `EstoqueForm`.

- [ ] **Step 3: Create `apps/simulacao/estoque.py`** (só config nesta task)

```python
"""Motor de agregação do painel de Estoque (Fase 14). Funções puras sobre
`ResumoMensalArmazem` / `ResumoMensalFabrica`, via ORM escopado (`objects`),
não `all_cooperativas` (diferente de `services.py` — ver ADR 0006 e a spec
2026-09-02)."""
from apps.simulacao.models import (  # noqa: F401  (Cenario/Armazem/Fabrica usados nas tasks seguintes)
    Armazem,
    Cenario,
    Fabrica,
    ResumoMensalArmazem,
    ResumoMensalFabrica,
)

PAGE_SIZE = 100
EXPORT_MAX = 50_000

ROTULOS_VISAO = (("sistema", "Sistema"), ("armazem", "Por armazém"), ("fabrica", "Por fábrica"))


class RecorteGrandeDemais(Exception):
    """O recorte tem mais linhas do que o `limite` passado a `agregar`."""


_COL_MES = {"key": "mes", "label": "Mês", "tipo": "mes"}


def _m(key, label):
    return {"key": key, "label": label, "tipo": "num", "comparavel": True}


VISOES = {
    "sistema": {
        "fonte": "sistema",
        "colunas": [
            _COL_MES,
            _m("recebimento", "Recebimento"), _m("transbordo", "Transbordo"),
            _m("esmagamento", "Esmagamento"), _m("vendas", "Vendas"),
            _m("saldo", "Saldo"), _m("capacidade", "Cap. Estática"),
            _m("excedente", "Excedente"),
        ],
        "pagina": False,
    },
    "armazem": {
        "fonte": "armazem",
        "colunas": [
            _COL_MES, {"key": "unidade", "label": "Armazém", "tipo": "texto"},
            _m("rec_produtor", "Rec. Produtor"), _m("envio_transbordo", "Envio Transbordo"),
            _m("vendas", "Vendas"), _m("saldo", "Saldo"),
            _m("capacidade", "Cap. Estática"), _m("excedente", "Excedente"),
        ],
        "pagina": True,
    },
    "fabrica": {
        "fonte": "fabrica",
        "colunas": [
            _COL_MES, {"key": "unidade", "label": "Fábrica", "tipo": "texto"},
            _m("rec_produtor", "Rec. Produtor"), _m("rec_transbordo", "Rec. Transbordo"),
            _m("esmagado", "Esmagado"), _m("saldo", "Saldo"),
            _m("capacidade", "Cap. Estática"), _m("excedente", "Excedente"),
        ],
        "pagina": True,
    },
}


def normalizar_visao(visao):
    return visao if visao in VISOES else "sistema"


def _queryset_unidade(modelo, cenario_id, fonte, filtros):
    """QuerySet de `modelo` (`ResumoMensal*`) filtrado por cenário + mês + unidade.
    `fonte` ∈ {"armazem","fabrica"} decide qual filtro de id aplicar."""
    qs = modelo.objects.filter(cenario_id=cenario_id)
    if filtros.get("mes_de"):
        qs = qs.filter(mes__gte=filtros["mes_de"])
    if filtros.get("mes_ate"):
        qs = qs.filter(mes__lte=filtros["mes_ate"])
    if fonte == "armazem" and filtros.get("armazem_ids"):
        qs = qs.filter(armazem_id__in=filtros["armazem_ids"])
    if fonte == "fabrica" and filtros.get("fabrica_ids"):
        qs = qs.filter(fabrica_id__in=filtros["fabrica_ids"])
    return qs
```

- [ ] **Step 4: Modify `apps/simulacao/forms.py`** — adicionar `EstoqueForm` (o `_MULTI_ATTRS` já existe no módulo)

```python
# no topo, junto aos imports:
from django.core.validators import RegexValidator

# ... _DATE_ATTRS / _MULTI_ATTRS já existem ...
_MES_ATTRS = {"type": "month", "class": "input input-bordered input-sm"}
_valida_mes = RegexValidator(r"^\d{4}-\d{2}$", "Use o formato AAAA-MM.")


class EstoqueForm(forms.Form):
    mes_de = forms.CharField(
        required=False, validators=[_valida_mes],
        widget=forms.TextInput(attrs=_MES_ATTRS))
    mes_ate = forms.CharField(
        required=False, validators=[_valida_mes],
        widget=forms.TextInput(attrs=_MES_ATTRS))
    armazem_ids = forms.ModelMultipleChoiceField(queryset=Armazem.objects.none(), required=False)
    fabrica_ids = forms.ModelMultipleChoiceField(queryset=Fabrica.objects.none(), required=False)

    def __init__(self, *args, cenario=None, **kwargs):
        super().__init__(*args, **kwargs)
        if cenario is not None:
            self.fields["armazem_ids"].queryset = Armazem.objects.filter(cenario=cenario)
            self.fields["fabrica_ids"].queryset = Fabrica.objects.filter(cenario=cenario)
        self.fields["armazem_ids"].widget.attrs.update(_MULTI_ATTRS)
        self.fields["fabrica_ids"].widget.attrs.update(_MULTI_ATTRS)

    def filtros_limpos(self):
        d = self.cleaned_data
        return {
            "mes_de": d.get("mes_de") or "",
            "mes_ate": d.get("mes_ate") or "",
            "armazem_ids": [a.id for a in d.get("armazem_ids", [])],
            "fabrica_ids": [f.id for f in d.get("fabrica_ids", [])],
        }
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest apps/simulacao/tests/test_estoque_config.py -v`
Expected: PASS (todos). Depois: `python manage.py check` limpo; `python manage.py makemigrations --check --dry-run` → "No changes detected".

- [ ] **Step 6: Commit**

```bash
git add apps/simulacao/estoque.py apps/simulacao/forms.py apps/simulacao/tests/test_estoque_config.py
git commit -m "feat(estoque): config das visões + EstoqueForm (Fase 14)"
```

---

### Task 2: `estoque.agregar()` — as três visões

**Files:**
- Modify: `apps/simulacao/estoque.py`
- Test: `apps/simulacao/tests/test_estoque_agregar.py`

**Interfaces:**
- Consumes: `VISOES`, `normalizar_visao`, `PAGE_SIZE`, `RecorteGrandeDemais`, `_queryset_unidade` (Task 1).
- Produces:
  - `_mes_ptbr(mes: str) -> str` — `"2026-01"` → `"01/2026"`.
  - `_agregar_sistema(cenario_id: int, filtros: dict) -> list[dict]` — uma linha por mês (`{"mes", "recebimento", "transbordo", "esmagamento", "vendas", "saldo", "capacidade", "excedente"}`), ordenada por `mes`, com o merge das duas tabelas.
  - `_alerta_da_linha(linha: dict) -> str | None` — `"ruptura"` se `linha["saldo"] < 0`; senão `"excedente"` se `linha["excedente"] > 0`; senão `None`.
  - `agregar(cenario_id: int, visao: str, filtros: dict, pagina: int | None = 1, limite: int | None = None) -> dict` com o formato:
    ```python
    {
      "colunas": [...],                                   # == VISOES[visao]["colunas"]
      "linhas": [ {"mes": "2026-01", "unidade": "ARM X"?,  # `unidade` só nas visões por unidade
                   "recebimento"/"rec_produtor"/...: float, "saldo": float,
                   "capacidade": float, "excedente": float,
                   "_chave": tuple, "_alerta": str | None}, ... ],
      "totais": {"<cada metrica>": float},                # fluxos = Σ; saldo/excedente = pico; capacidade = const
      "paginacao": {"pagina": int, "num_paginas": int, "total": int} | None,
    }
    ```
    - `pagina=None` → sem paginação. `limite` não-nulo e nº de linhas do recorte > `limite` → `raise RecorteGrandeDemais(total)` **antes** de materializar as linhas por unidade (na "sistema" o check é depois — são ≤12 linhas).

- [ ] **Step 1: Write the failing test**

```python
# apps/simulacao/tests/test_estoque_agregar.py
from django.test import TestCase

from apps.core.models import Cooperativa
from apps.core.tenancy import definir_cooperativa_atual, resetar_cooperativa_atual
from apps.simulacao import estoque
from apps.simulacao.models import (
    Armazem, Cenario, Fabrica, ResumoMensalArmazem, ResumoMensalFabrica,
)

VAZIO = {"mes_de": "", "mes_ate": "", "armazem_ids": [], "fabrica_ids": []}


class AgregarTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome="C", slug="c")
        self._tok = definir_cooperativa_atual(self.coop.id)
        self.cen = Cenario.objects.create(cooperativa=self.coop, nome="Cen")
        self.a1 = self._arm("ARM1"); self.a2 = self._arm("ARM2")
        self.f1 = self._fab("FAB1")
        # jan
        self._ra(self.a1, "2026-01", rec_produtor=100, envio_transbordo=40, vendas=10,
                 saldo=50, cap=200, excedente=0)
        self._ra(self.a2, "2026-01", rec_produtor=60, envio_transbordo=20, vendas=5,
                 saldo=35, cap=100, excedente=0)
        self._rf(self.f1, "2026-01", rec_produtor=0, rec_transbordo=60, esmagado=50,
                 saldo=10, cap=300, excedente=0)
        # fev — a1 estoura, f1 rompe
        self._ra(self.a1, "2026-02", rec_produtor=300, envio_transbordo=0, vendas=0,
                 saldo=250, cap=200, excedente=50)
        self._rf(self.f1, "2026-02", rec_produtor=0, rec_transbordo=0, esmagado=400,
                 saldo=-30, cap=300, excedente=0)

    def tearDown(self):
        resetar_cooperativa_atual(self._tok)

    def _arm(self, nome):
        return Armazem.objects.create(
            cooperativa=self.coop, cenario=self.cen, nome=nome,
            capacidade_estatica=1, capacidade_expedicao_diaria=1, estoque_inicial=0)

    def _fab(self, nome):
        return Fabrica.objects.create(
            cooperativa=self.coop, cenario=self.cen, nome=nome,
            capacidade_estatica=1, capacidade_esmagamento_diaria=1,
            capacidade_recebimento_diaria=1, limite_caminhoes=1,
            carga_media_caminhao=1, estoque_inicial=0)

    def _ra(self, arm, mes, **kw):
        ResumoMensalArmazem.objects.create(
            cooperativa=self.coop, cenario=self.cen, armazem=arm, mes=mes,
            rec_produtor=kw["rec_produtor"], envio_transbordo=kw["envio_transbordo"],
            vendas=kw["vendas"], saldo_estoque=kw["saldo"],
            capacidade_estatica=kw["cap"], excedente=kw["excedente"])

    def _rf(self, fab, mes, **kw):
        ResumoMensalFabrica.objects.create(
            cooperativa=self.coop, cenario=self.cen, fabrica=fab, mes=mes,
            rec_produtor=kw["rec_produtor"], rec_transbordo=kw["rec_transbordo"],
            esmagado=kw["esmagado"], saldo_estoque=kw["saldo"],
            capacidade_estatica=kw["cap"], excedente=kw["excedente"])

    def test_sistema_soma_as_duas_tabelas_por_mes(self):
        d = estoque.agregar(self.cen.id, "sistema", VAZIO)
        self.assertEqual([l["mes"] for l in d["linhas"]], ["2026-01", "2026-02"])
        jan = d["linhas"][0]
        self.assertEqual(jan["recebimento"], 160.0)   # 100 + 60 + 0
        self.assertEqual(jan["transbordo"], 60.0)     # 40 + 20 (envio dos armazéns)
        self.assertEqual(jan["esmagamento"], 50.0)
        self.assertEqual(jan["vendas"], 15.0)
        self.assertEqual(jan["saldo"], 95.0)          # 50 + 35 + 10
        self.assertEqual(jan["capacidade"], 600.0)    # 200 + 100 + 300
        self.assertIsNone(jan["_alerta"])
        self.assertEqual(jan["_chave"], ("2026-01",))
        self.assertNotIn("unidade", jan)

    def test_sistema_totais_pico(self):
        d = estoque.agregar(self.cen.id, "sistema", VAZIO)
        self.assertEqual(d["totais"]["recebimento"], 460.0)   # 160 + 300
        self.assertEqual(d["totais"]["saldo"], 220.0)         # pico = fev (250 + -30)
        self.assertEqual(d["totais"]["excedente"], 50.0)      # pico = fev
        self.assertEqual(d["totais"]["capacidade"], 600.0)

    def test_sistema_alerta_ruptura_tem_prioridade(self):
        d = estoque.agregar(self.cen.id, "sistema", VAZIO)
        fev = d["linhas"][1]
        self.assertEqual(fev["saldo"], 220.0)      # 250 + (-30)
        # nenhuma linha "sistema" fica negativa aqui; testa a prioridade na visão fábrica
        df = estoque.agregar(self.cen.id, "fabrica", VAZIO)
        fev_f = [l for l in df["linhas"] if l["mes"] == "2026-02"][0]
        self.assertEqual(fev_f["_alerta"], "ruptura")

    def test_armazem_uma_linha_por_unidade_mes(self):
        d = estoque.agregar(self.cen.id, "armazem", VAZIO)
        self.assertEqual(len(d["linhas"]), 3)   # a1 jan, a2 jan, a1 fev
        l0 = d["linhas"][0]
        self.assertEqual((l0["mes"], l0["unidade"]), ("2026-01", "ARM1"))
        self.assertEqual(l0["envio_transbordo"], 40.0)
        self.assertEqual(l0["_chave"], ("2026-01", "ARM1"))
        fev_a1 = [l for l in d["linhas"] if l["mes"] == "2026-02"][0]
        self.assertEqual(fev_a1["_alerta"], "excedente")

    def test_fabrica_colunas_proprias(self):
        d = estoque.agregar(self.cen.id, "fabrica", VAZIO)
        self.assertIn("rec_transbordo", d["linhas"][0])
        self.assertIn("esmagado", d["linhas"][0])
        self.assertNotIn("envio_transbordo", d["linhas"][0])

    def test_filtro_mes(self):
        f = {**VAZIO, "mes_de": "2026-02"}
        d = estoque.agregar(self.cen.id, "sistema", f)
        self.assertEqual([l["mes"] for l in d["linhas"]], ["2026-02"])

    def test_filtro_armazem(self):
        f = {**VAZIO, "armazem_ids": [self.a2.id]}
        d = estoque.agregar(self.cen.id, "armazem", f)
        self.assertEqual({l["unidade"] for l in d["linhas"]}, {"ARM2"})

    def test_filtro_que_zera(self):
        f = {**VAZIO, "mes_de": "2030-01"}
        d = estoque.agregar(self.cen.id, "sistema", f)
        self.assertEqual(d["linhas"], [])
        self.assertEqual(d["totais"]["recebimento"], 0.0)

    def test_paginacao_por_unidade(self):
        for i in range(3, 160):
            self._ra(self.a1, f"2027-{i:02d}"[:7] if i < 13 else f"20{27 + i // 12}-{i % 12 + 1:02d}",
                     rec_produtor=1, envio_transbordo=0, vendas=0, saldo=1, cap=1, excedente=0)
        d1 = estoque.agregar(self.cen.id, "armazem", VAZIO, pagina=1)
        self.assertEqual(len(d1["linhas"]), 100)
        self.assertEqual(d1["paginacao"]["num_paginas"], 2)
        d2 = estoque.agregar(self.cen.id, "armazem", VAZIO, pagina=2)
        self.assertEqual(len(d2["linhas"]), d1["paginacao"]["total"] - 100)

    def test_limite_excedido_levanta(self):
        with self.assertRaises(estoque.RecorteGrandeDemais):
            estoque.agregar(self.cen.id, "armazem", VAZIO, pagina=None, limite=2)

    def test_sem_paginacao_quando_pagina_none(self):
        d = estoque.agregar(self.cen.id, "armazem", VAZIO, pagina=None)
        self.assertIsNone(d["paginacao"])

    def test_nao_vaza_outro_cenario(self):
        outro = Cenario.objects.create(cooperativa=self.coop, nome="Outro")
        a = Armazem.objects.create(
            cooperativa=self.coop, cenario=outro, nome="X",
            capacidade_estatica=1, capacidade_expedicao_diaria=1, estoque_inicial=0)
        ResumoMensalArmazem.objects.create(
            cooperativa=self.coop, cenario=outro, armazem=a, mes="2026-01",
            rec_produtor=999, envio_transbordo=0, vendas=0, saldo_estoque=0,
            capacidade_estatica=0, excedente=0)
        d = estoque.agregar(self.cen.id, "sistema", VAZIO)
        self.assertEqual(d["totais"]["recebimento"], 460.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest apps/simulacao/tests/test_estoque_agregar.py -v`
Expected: FAIL — `AttributeError: module 'apps.simulacao.estoque' has no attribute 'agregar'`.

- [ ] **Step 3: Implement em `apps/simulacao/estoque.py`**

```python
# no topo do módulo, junto aos imports:
from django.db.models import Sum

# --- helpers ---

def _mes_ptbr(mes):
    return f"{mes[5:7]}/{mes[0:4]}"


def _alerta_da_linha(linha):
    if linha.get("saldo", 0.0) < 0:
        return "ruptura"
    if linha.get("excedente", 0.0) > 0:
        return "excedente"
    return None


_METRICAS_SISTEMA = ("recebimento", "transbordo", "esmagamento", "vendas",
                     "saldo", "capacidade", "excedente")


def _mes_zerado(mes):
    d = {"mes": mes}
    for k in _METRICAS_SISTEMA:
        d[k] = 0.0
    return d


def _agregar_sistema(cenario_id, filtros):
    arm = (_queryset_unidade(ResumoMensalArmazem, cenario_id, "armazem", filtros)
           .values("mes")
           .annotate(rp=Sum("rec_produtor"), tb=Sum("envio_transbordo"), vd=Sum("vendas"),
                     sl=Sum("saldo_estoque"), cp=Sum("capacidade_estatica"), ex=Sum("excedente")))
    fab = (_queryset_unidade(ResumoMensalFabrica, cenario_id, "fabrica", filtros)
           .values("mes")
           .annotate(rp=Sum("rec_produtor"), esm=Sum("esmagado"),
                     sl=Sum("saldo_estoque"), cp=Sum("capacidade_estatica"), ex=Sum("excedente")))
    por_mes = {}
    for r in arm:
        m = por_mes.setdefault(r["mes"], _mes_zerado(r["mes"]))
        m["recebimento"] += r["rp"] or 0.0
        m["transbordo"] += r["tb"] or 0.0
        m["vendas"] += r["vd"] or 0.0
        m["saldo"] += r["sl"] or 0.0
        m["capacidade"] += r["cp"] or 0.0
        m["excedente"] += r["ex"] or 0.0
    for r in fab:
        m = por_mes.setdefault(r["mes"], _mes_zerado(r["mes"]))
        m["recebimento"] += r["rp"] or 0.0
        m["esmagamento"] += r["esm"] or 0.0
        m["saldo"] += r["sl"] or 0.0
        m["capacidade"] += r["cp"] or 0.0
        m["excedente"] += r["ex"] or 0.0
    linhas = []
    for mes in sorted(por_mes):
        linha = por_mes[mes]
        linha["_chave"] = (mes,)
        linha["_alerta"] = _alerta_da_linha(linha)
        linhas.append(linha)
    return linhas


def _linhas_por_unidade(cenario_id, fonte, filtros):
    if fonte == "armazem":
        modelo, campo, extras = ResumoMensalArmazem, "armazem__nome", ("envio_transbordo", "vendas")
    else:
        modelo, campo, extras = ResumoMensalFabrica, "fabrica__nome", ("rec_transbordo", "esmagado")
    campos = ["mes", campo, "rec_produtor", *extras, "saldo_estoque", "capacidade_estatica", "excedente"]
    qs = _queryset_unidade(modelo, cenario_id, fonte, filtros).values(*campos).order_by("mes", campo)
    return qs, campo, extras


def agregar(cenario_id, visao, filtros, pagina=1, limite=None):
    visao = normalizar_visao(visao)
    cfg = VISOES[visao]

    if visao == "sistema":
        linhas = _agregar_sistema(cenario_id, filtros)
        if limite is not None and len(linhas) > limite:
            raise RecorteGrandeDemais(len(linhas))
        totais = _totais(linhas, _METRICAS_SISTEMA)
        return {"colunas": cfg["colunas"], "linhas": linhas, "totais": totais, "paginacao": None}

    qs, campo, extras = _linhas_por_unidade(cenario_id, cfg["fonte"], filtros)
    total = qs.count()
    if limite is not None and total > limite:
        raise RecorteGrandeDemais(total)
    paginacao = None
    if cfg["pagina"] and pagina is not None:
        num_paginas = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        pagina = min(max(1, pagina), num_paginas)
        ini = (pagina - 1) * PAGE_SIZE
        qs = qs[ini:ini + PAGE_SIZE]
        paginacao = {"pagina": pagina, "num_paginas": num_paginas, "total": total}

    metricas = ("rec_produtor", *extras, "saldo", "capacidade", "excedente")
    linhas = []
    for row in qs:
        linha = {"mes": row["mes"], "unidade": row[campo],
                 "rec_produtor": row["rec_produtor"] or 0.0,
                 "saldo": row["saldo_estoque"] or 0.0,
                 "capacidade": row["capacidade_estatica"] or 0.0,
                 "excedente": row["excedente"] or 0.0}
        for e in extras:
            linha[e] = row[e] or 0.0
        linha["_chave"] = (row["mes"], row[campo])
        linha["_alerta"] = _alerta_da_linha(linha)
        linhas.append(linha)
    return {"colunas": cfg["colunas"], "linhas": linhas,
            "totais": _totais(linhas, metricas), "paginacao": paginacao}


def _totais(linhas, metricas):
    tot = {m: 0.0 for m in metricas}
    for linha in linhas:
        for m in metricas:
            if m in ("saldo", "excedente"):
                tot[m] = max(tot[m], linha.get(m, 0.0))
            elif m == "capacidade":
                tot[m] = linha.get(m, tot[m])
            else:
                tot[m] += linha.get(m, 0.0)
    return tot
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest apps/simulacao/tests/test_estoque_agregar.py -v`
Expected: PASS (todos).

- [ ] **Step 5: Commit**

```bash
git add apps/simulacao/estoque.py apps/simulacao/tests/test_estoque_agregar.py
git commit -m "feat(estoque): agregar() — sistema (merge) + por armazém/fábrica"
```

---

### Task 3: `card_de_pico` + `card_com_delta` + `cenarios_comparaveis` + `_traduzir_filtros` + `_delta`

**Files:**
- Modify: `apps/simulacao/estoque.py`
- Test: `apps/simulacao/tests/test_estoque_card.py`

**Interfaces:**
- Consumes: `_agregar_sistema` (Task 2), `_queryset_unidade` (Task 1).
- Produces:
  - `_delta(atual, comparado) -> float | None | "novo"` — mesma regra da Fase 13.
  - `_traduzir_filtros(filtros: dict, cenario_id: int) -> dict` — re-resolve `armazem_ids`/`fabrica_ids` por nome para `cenario_id`.
  - `card_de_pico(cenario_id: int, filtros: dict) -> dict` → `{"recebimento","transbordo","esmagamento","vendas","saldo","capacidade","excedente","saldo_min","mes_ruptura"}` (fluxos = Σ de todos os meses; `saldo`/`excedente` = máx mensal; `capacidade` = constante; `saldo_min` = mín mensal, `mes_ruptura` = `_mes_ptbr` do mês do mín se `< 0`, senão `None`).
  - `card_com_delta(cenario_id: int, cenario_comparado_id: int | None, filtros: dict) -> dict` → `card_de_pico` + `"delta": {<7 métricas>} | None` (comparado com `_traduzir_filtros`; `None` → `delta` None).
  - `cenarios_comparaveis(cenario_id: int, cooperativa_id: int) -> list[dict]` — cenários da coop com ao menos um `ResumoMensalArmazem` **ou** `ResumoMensalFabrica`, exceto `cenario_id`, ordenados `-is_oficial, nome`.

- [ ] **Step 1: Write the failing test**

```python
# apps/simulacao/tests/test_estoque_card.py
from django.test import TestCase

from apps.core.models import Cooperativa
from apps.core.tenancy import definir_cooperativa_atual, resetar_cooperativa_atual
from apps.simulacao import estoque
from apps.simulacao.models import (
    Armazem, Cenario, Fabrica, ResumoMensalArmazem, ResumoMensalFabrica,
)

VAZIO = {"mes_de": "", "mes_ate": "", "armazem_ids": [], "fabrica_ids": []}


class CardTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome="C", slug="c")
        self._tok = definir_cooperativa_atual(self.coop.id)
        self.cen = self._cenario_com_estoque("Atual", saldo_fev=250, exc_fev=50)
        self.comp = self._cenario_com_estoque("Comp", saldo_fev=100, exc_fev=0)

    def tearDown(self):
        resetar_cooperativa_atual(self._tok)

    def _cenario_com_estoque(self, nome, saldo_fev, exc_fev):
        cen = Cenario.objects.create(cooperativa=self.coop, nome=nome)
        arm = Armazem.objects.create(
            cooperativa=self.coop, cenario=cen, nome="ARM",
            capacidade_estatica=1, capacidade_expedicao_diaria=1, estoque_inicial=0)
        fab = Fabrica.objects.create(
            cooperativa=self.coop, cenario=cen, nome="FAB",
            capacidade_estatica=1, capacidade_esmagamento_diaria=1,
            capacidade_recebimento_diaria=1, limite_caminhoes=1,
            carga_media_caminhao=1, estoque_inicial=0)
        ResumoMensalArmazem.objects.create(
            cooperativa=self.coop, cenario=cen, armazem=arm, mes="2026-01",
            rec_produtor=100, envio_transbordo=30, vendas=10, saldo_estoque=50,
            capacidade_estatica=200, excedente=0)
        ResumoMensalArmazem.objects.create(
            cooperativa=self.coop, cenario=cen, armazem=arm, mes="2026-02",
            rec_produtor=200, envio_transbordo=0, vendas=0, saldo_estoque=saldo_fev,
            capacidade_estatica=200, excedente=exc_fev)
        ResumoMensalFabrica.objects.create(
            cooperativa=self.coop, cenario=cen, fabrica=fab, mes="2026-01",
            rec_produtor=0, rec_transbordo=30, esmagado=20, saldo_estoque=10,
            capacidade_estatica=300, excedente=0)
        return cen

    def test_card_de_pico(self):
        c = estoque.card_de_pico(self.cen.id, VAZIO)
        self.assertEqual(c["recebimento"], 300.0)   # 100 + 200 + 0
        self.assertEqual(c["transbordo"], 30.0)
        self.assertEqual(c["esmagamento"], 20.0)
        self.assertEqual(c["saldo"], 250.0)         # pico = fev (250 + 0)
        self.assertEqual(c["excedente"], 50.0)
        self.assertEqual(c["capacidade"], 400.0)    # 200 + 200(?) -> ver nota
        self.assertIsNone(c["mes_ruptura"])

    def test_card_ruptura(self):
        ResumoMensalFabrica.objects.create(
            cooperativa=self.coop, cenario=self.cen,
            fabrica=Fabrica.objects.filter(cenario=self.cen).first(), mes="2026-03",
            rec_produtor=0, rec_transbordo=0, esmagado=500, saldo_estoque=-40,
            capacidade_estatica=300, excedente=0)
        c = estoque.card_de_pico(self.cen.id, VAZIO)
        self.assertEqual(c["saldo_min"], -40.0)
        self.assertEqual(c["mes_ruptura"], "03/2026")

    def test_card_com_delta(self):
        c = estoque.card_com_delta(self.cen.id, self.comp.id, VAZIO)
        # saldo pico atual 250 vs comp 100 → +150%
        self.assertAlmostEqual(c["delta"]["saldo"], (250 - 100) / 100 * 100, places=6)
        self.assertEqual(c["delta"]["excedente"], None)   # comp excedente pico = 0, atual > 0

    def test_card_com_delta_sem_comparado(self):
        c = estoque.card_com_delta(self.cen.id, None, VAZIO)
        self.assertIsNone(c["delta"])

    def test_cenarios_comparaveis(self):
        Cenario.objects.create(cooperativa=self.coop, nome="Sem Estoque")
        lista = estoque.cenarios_comparaveis(self.cen.id, self.coop.id)
        self.assertEqual(sorted(c["nome"] for c in lista), ["Comp"])
```

> **Nota sobre `test_card_de_pico` (`capacidade`):** o `_agregar_sistema` soma `capacidade_estatica` de **todas** as unidades daquele mês. Jan tem ARM (200) + FAB (300) = 500; fev só tem ARM (200). `capacidade` no card = `linhas[0]["capacidade"]` (o 1º mês, jan) = **500**. Ajuste a asserção para `500.0` — ou, se preferir consistência, o implementador pode fixar o fixture para todas as unidades aparecerem em todos os meses. Escolha uma e deixe explícito no relatório.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest apps/simulacao/tests/test_estoque_card.py -v`
Expected: FAIL — `AttributeError: ... has no attribute 'card_de_pico'`.

- [ ] **Step 3: Implement em `apps/simulacao/estoque.py`**

```python
_METRICAS_CARD = ("recebimento", "transbordo", "esmagamento", "vendas",
                  "saldo", "capacidade", "excedente")


def _delta(atual, comparado):
    if comparado is None:
        return "novo"
    if comparado == 0:
        return 0.0 if atual == 0 else None
    return (atual - comparado) / comparado * 100


def _traduzir_filtros(filtros, cenario_id):
    """Re-resolve armazem_ids/fabrica_ids (ids de um cenário) para os ids dos
    armazéns/fábricas de mesmo NOME em `cenario_id` (clones têm ids novos, nomes
    iguais). Limitação conhecida (Fase 13 Ruling 8): sem unidade de mesmo nome no
    cenário comparado, a lista fica vazia = "sem filtro"."""
    if not filtros.get("armazem_ids") and not filtros.get("fabrica_ids"):
        return filtros
    traduzido = dict(filtros)
    if filtros.get("armazem_ids"):
        nomes = Armazem.objects.filter(id__in=filtros["armazem_ids"]).values_list("nome", flat=True)
        traduzido["armazem_ids"] = list(
            Armazem.objects.filter(cenario_id=cenario_id, nome__in=list(nomes)).values_list("id", flat=True))
    if filtros.get("fabrica_ids"):
        nomes = Fabrica.objects.filter(id__in=filtros["fabrica_ids"]).values_list("nome", flat=True)
        traduzido["fabrica_ids"] = list(
            Fabrica.objects.filter(cenario_id=cenario_id, nome__in=list(nomes)).values_list("id", flat=True))
    return traduzido


def card_de_pico(cenario_id, filtros):
    linhas = _agregar_sistema(cenario_id, filtros)
    card = {m: 0.0 for m in _METRICAS_CARD}
    card["saldo_min"] = 0.0
    card["mes_ruptura"] = None
    if not linhas:
        return card
    for linha in linhas:
        for m in ("recebimento", "transbordo", "esmagamento", "vendas"):
            card[m] += linha[m]
    card["saldo"] = max(linha["saldo"] for linha in linhas)
    card["excedente"] = max(linha["excedente"] for linha in linhas)
    card["capacidade"] = linhas[0]["capacidade"]
    pior = min(linhas, key=lambda linha: linha["saldo"])
    if pior["saldo"] < 0:
        card["saldo_min"] = pior["saldo"]
        card["mes_ruptura"] = _mes_ptbr(pior["mes"])
    return card


def card_com_delta(cenario_id, cenario_comparado_id, filtros):
    atual = card_de_pico(cenario_id, filtros)
    if cenario_comparado_id is None:
        atual["delta"] = None
        return atual
    comp = card_de_pico(cenario_comparado_id, _traduzir_filtros(filtros, cenario_comparado_id))
    atual["delta"] = {m: _delta(atual[m], comp[m]) for m in _METRICAS_CARD}
    return atual


def cenarios_comparaveis(cenario_id, cooperativa_id):
    com_estoque = set(
        ResumoMensalArmazem.objects.filter(cooperativa_id=cooperativa_id)
        .values_list("cenario_id", flat=True)) | set(
        ResumoMensalFabrica.objects.filter(cooperativa_id=cooperativa_id)
        .values_list("cenario_id", flat=True))
    qs = (Cenario.objects.filter(cooperativa_id=cooperativa_id, id__in=list(com_estoque))
          .exclude(id=cenario_id).order_by("-is_oficial", "nome"))
    return [{"id": c.id, "nome": c.nome} for c in qs]
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest apps/simulacao/tests/test_estoque_card.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/simulacao/estoque.py apps/simulacao/tests/test_estoque_card.py
git commit -m "feat(estoque): card_de_pico + card_com_delta + cenarios_comparaveis"
```

---

### Task 4: `aplicar_comparacao` + `dados_grafico`

**Files:**
- Modify: `apps/simulacao/estoque.py`
- Test: `apps/simulacao/tests/test_estoque_comparacao.py`, `apps/simulacao/tests/test_estoque_grafico.py`

**Interfaces:**
- Consumes: `agregar` (Task 2), `_agregar_sistema` (Task 2), `_delta` / `_traduzir_filtros` / `_mes_ptbr` (Tasks 2–3), `VISOES` (Task 1).
- Produces:
  - `aplicar_comparacao(dados: dict, cenario_comparado_id: int, visao: str, filtros: dict) -> dict` — recebe o retorno de `agregar(cenario_ATUAL, ...)` e devolve o mesmo dict alterado: roda `agregar(cenario_comparado_id, visao, _traduzir_filtros(filtros, cenario_comparado_id), pagina=None)`, indexa por `_chave`, grava `linha["<m>_delta"]` para cada coluna `comparavel` (`float | None | "novo"`), insere a coluna-Δ `{"key": f"{m}_delta", "label": "Δ%", "tipo": "delta"}` depois de cada coluna `comparavel`, e grava `dados["totais_delta"]`. **Vale para as 3 visões** (sem exclusão de "linha crua").
  - `dados_grafico(cenario_id: int, filtros: dict, cenario_comparado_id: int | None) -> dict` — **sempre** `{"tipo": "line", "labels": [meses MM/AAAA], "datasets": [...]}`. Datasets: `{"label": "Saldo total", "dados": [...], "eixo": "y"}` + `{"label": "Excedente total", "dados": [...], "eixo": "y"}`; se `cenario_comparado_id` → mais `"Saldo total (comparado)"` / `"Excedente total (comparado)"`, alinhados pelos meses do atual (mês ausente = 0).

- [ ] **Step 1: Write the failing tests**

```python
# apps/simulacao/tests/test_estoque_comparacao.py
from django.test import TestCase

from apps.core.models import Cooperativa
from apps.core.tenancy import definir_cooperativa_atual, resetar_cooperativa_atual
from apps.simulacao import estoque
from apps.simulacao.models import Armazem, Cenario, Fabrica, ResumoMensalArmazem

VAZIO = {"mes_de": "", "mes_ate": "", "armazem_ids": [], "fabrica_ids": []}


class ComparacaoTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome="C", slug="c")
        self._tok = definir_cooperativa_atual(self.coop.id)
        self.atual = self._cen("Atual", saldo=200)
        self.comp = self._cen("Comp", saldo=160)

    def tearDown(self):
        resetar_cooperativa_atual(self._tok)

    def _cen(self, nome, saldo):
        cen = Cenario.objects.create(cooperativa=self.coop, nome=nome)
        arm = Armazem.objects.create(
            cooperativa=self.coop, cenario=cen, nome="ARM",
            capacidade_estatica=1, capacidade_expedicao_diaria=1, estoque_inicial=0)
        ResumoMensalArmazem.objects.create(
            cooperativa=self.coop, cenario=cen, armazem=arm, mes="2026-01",
            rec_produtor=100, envio_transbordo=10, vendas=0, saldo_estoque=saldo,
            capacidade_estatica=300, excedente=0)
        return cen

    def test_sistema_recebe_delta_e_colunas(self):
        d = estoque.agregar(self.atual.id, "sistema", VAZIO)
        d = estoque.aplicar_comparacao(d, self.comp.id, "sistema", VAZIO)
        self.assertAlmostEqual(d["linhas"][0]["saldo_delta"], (200 - 160) / 160 * 100, places=6)
        keys = [c["key"] for c in d["colunas"]]
        self.assertIn("saldo_delta", keys)
        self.assertEqual(keys.index("saldo_delta"), keys.index("saldo") + 1)

    def test_armazem_recebe_delta(self):
        d = estoque.agregar(self.atual.id, "armazem", VAZIO)
        d = estoque.aplicar_comparacao(d, self.comp.id, "armazem", VAZIO)
        self.assertIn("saldo_delta", d["linhas"][0])

    def test_chave_sem_par_e_novo(self):
        arm = Armazem.objects.filter(cenario=self.atual).first()
        ResumoMensalArmazem.objects.create(
            cooperativa=self.coop, cenario=self.atual, armazem=arm, mes="2026-02",
            rec_produtor=5, envio_transbordo=0, vendas=0, saldo_estoque=5,
            capacidade_estatica=300, excedente=0)
        d = estoque.agregar(self.atual.id, "sistema", VAZIO)
        d = estoque.aplicar_comparacao(d, self.comp.id, "sistema", VAZIO)
        fev = [l for l in d["linhas"] if l["mes"] == "2026-02"][0]
        self.assertEqual(fev["saldo_delta"], "novo")

    def test_totais_delta(self):
        d = estoque.agregar(self.atual.id, "sistema", VAZIO)
        d = estoque.aplicar_comparacao(d, self.comp.id, "sistema", VAZIO)
        self.assertIn("saldo", d["totais_delta"])
```

```python
# apps/simulacao/tests/test_estoque_grafico.py
from django.test import TestCase

from apps.core.models import Cooperativa
from apps.core.tenancy import definir_cooperativa_atual, resetar_cooperativa_atual
from apps.simulacao import estoque
from apps.simulacao.models import Armazem, Cenario, ResumoMensalArmazem

VAZIO = {"mes_de": "", "mes_ate": "", "armazem_ids": [], "fabrica_ids": []}


class GraficoTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome="C", slug="c")
        self._tok = definir_cooperativa_atual(self.coop.id)
        self.cen = Cenario.objects.create(cooperativa=self.coop, nome="Cen")
        arm = Armazem.objects.create(
            cooperativa=self.coop, cenario=self.cen, nome="A",
            capacidade_estatica=1, capacidade_expedicao_diaria=1, estoque_inicial=0)
        for mes, saldo, exc in [("2026-01", 50, 0), ("2026-02", 250, 50)]:
            ResumoMensalArmazem.objects.create(
                cooperativa=self.coop, cenario=self.cen, armazem=arm, mes=mes,
                rec_produtor=1, envio_transbordo=0, vendas=0, saldo_estoque=saldo,
                capacidade_estatica=200, excedente=exc)

    def tearDown(self):
        resetar_cooperativa_atual(self._tok)

    def test_linha_saldo_excedente(self):
        g = estoque.dados_grafico(self.cen.id, VAZIO, None)
        self.assertEqual(g["tipo"], "line")
        self.assertEqual(g["labels"], ["01/2026", "02/2026"])
        saldo = [d for d in g["datasets"] if d["label"] == "Saldo total"][0]
        self.assertEqual(saldo["dados"], [50.0, 250.0])

    def test_comparado_adiciona_datasets(self):
        comp = Cenario.objects.create(cooperativa=self.coop, nome="Comp")
        g = estoque.dados_grafico(self.cen.id, VAZIO, comp.id)
        self.assertIn("Excedente total (comparado)", {d["label"] for d in g["datasets"]})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest apps/simulacao/tests/test_estoque_comparacao.py apps/simulacao/tests/test_estoque_grafico.py -v`
Expected: FAIL — `aplicar_comparacao` / `dados_grafico` não existem.

- [ ] **Step 3: Implement em `apps/simulacao/estoque.py`**

```python
def aplicar_comparacao(dados, cenario_comparado_id, visao, filtros):
    """Anota `dados` (retorno de `agregar` do cenário atual) com Δ% contra
    `cenario_comparado_id`: `*_delta` por linha, colunas Δ%, `totais_delta`."""
    visao = normalizar_visao(visao)
    comparaveis = [c["key"] for c in dados["colunas"] if c.get("comparavel")]

    comp = agregar(cenario_comparado_id, visao,
                   _traduzir_filtros(filtros, cenario_comparado_id), pagina=None)
    por_chave = {linha_c["_chave"]: linha_c for linha_c in comp["linhas"]}

    for linha in dados["linhas"]:
        alvo = por_chave.get(linha["_chave"])
        for m in comparaveis:
            linha[f"{m}_delta"] = _delta(linha[m], alvo[m] if alvo else None)

    novas_colunas = []
    for col in dados["colunas"]:
        novas_colunas.append(col)
        if col.get("comparavel"):
            novas_colunas.append(
                {"key": f'{col["key"]}_delta', "label": "Δ%", "tipo": "delta"})
    dados["colunas"] = novas_colunas

    dados["totais_delta"] = {
        m: _delta(dados["totais"][m], comp["totais"][m]) for m in comparaveis}
    return dados


def dados_grafico(cenario_id, filtros, cenario_comparado_id):
    linhas = _agregar_sistema(cenario_id, filtros)
    labels = [_mes_ptbr(linha["mes"]) for linha in linhas]
    datasets = [
        {"label": "Saldo total", "dados": [linha["saldo"] for linha in linhas], "eixo": "y"},
        {"label": "Excedente total", "dados": [linha["excedente"] for linha in linhas], "eixo": "y"},
    ]
    if cenario_comparado_id:
        comp = _agregar_sistema(
            cenario_comparado_id, _traduzir_filtros(filtros, cenario_comparado_id))
        m_saldo = {_mes_ptbr(linha["mes"]): linha["saldo"] for linha in comp}
        m_exc = {_mes_ptbr(linha["mes"]): linha["excedente"] for linha in comp}
        datasets += [
            {"label": "Saldo total (comparado)",
             "dados": [m_saldo.get(x, 0.0) for x in labels], "eixo": "y"},
            {"label": "Excedente total (comparado)",
             "dados": [m_exc.get(x, 0.0) for x in labels], "eixo": "y"},
        ]
    return {"tipo": "line", "labels": labels, "datasets": datasets}
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest apps/simulacao/tests/test_estoque_comparacao.py apps/simulacao/tests/test_estoque_grafico.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/simulacao/estoque.py apps/simulacao/tests/test_estoque_comparacao.py apps/simulacao/tests/test_estoque_grafico.py
git commit -m "feat(estoque): aplicar_comparacao (Δ% nas 3 visões) + dados_grafico"
```

---

### Task 5: rename `cenario_tem_resultado` → `cenario_tem_simulacao`

**Files:**
- Modify: `apps/simulacao/templatetags/simulacao_filters.py`, `templates/simulacao/_subnav.html`

**Interfaces:**
- Produces: `cenario_tem_simulacao(cenario) -> bool` (`@register.simple_tag`, comportamento idêntico ao antigo — `MovimentacaoDiaria.objects.filter(cenario_id=cenario.id).exists()`). No `_subnav.html` a variável de atribuição passa a ser `tem_simulacao` e serve à aba "Resultados" e (Task 6) à aba "Estoque".

- [ ] **Step 1: Confirmar que nada de teste referencia o nome antigo**

Run: `grep -rn "cenario_tem_resultado" apps/ templates/`
Expected: só `simulacao_filters.py:38` e `_subnav.html:3`. (Os testes de subnav em `test_views_resultados.py` checam o HTML renderizado `tab-disabled`, não o nome do tag.)

- [ ] **Step 2: Rename no templatetag** — em `apps/simulacao/templatetags/simulacao_filters.py`

```python
@register.simple_tag
def cenario_tem_simulacao(cenario):
    """True se o cenário tem ao menos uma `MovimentacaoDiaria` — i.e. rodou uma
    simulação com sucesso (o engine grava `MovimentacaoDiaria` e `ResumoMensal*`
    na mesma transação). Gate das abas Resultados e Estoque."""
    from apps.simulacao.models import MovimentacaoDiaria
    return MovimentacaoDiaria.objects.filter(cenario_id=cenario.id).exists()
```

- [ ] **Step 3: Rename no `_subnav.html`** — linha 3 e a aba "Resultados"

Trocar `{% cenario_tem_resultado cenario as tem_resultado %}` por `{% cenario_tem_simulacao cenario as tem_simulacao %}`; na aba "Resultados", trocar os 3 usos de `tem_resultado` por `tem_simulacao` (`{% if tem_resultado %}` → `{% if tem_simulacao %}` e `{% if not tem_resultado %}` → `{% if not tem_simulacao %}`).

> **Não** tocar `templates/simulacao/_resultados_content.html:4` (`{% if not tem_resultado %}`) — ali `tem_resultado` é a variável de **contexto** passada pela view `resultados_tab`, não a saída do templatetag.

- [ ] **Step 4: Run the affected tests**

Run: `python -m pytest apps/simulacao/tests/test_views_resultados.py apps/core/tests/test_render_smoke.py -q`
Expected: PASS (a aba Resultados continua habilitando/desabilitando igual).

- [ ] **Step 5: Commit**

```bash
git add apps/simulacao/templatetags/simulacao_filters.py templates/simulacao/_subnav.html
git commit -m "refactor(subnav): cenario_tem_resultado → cenario_tem_simulacao (serve às 2 abas)"
```

---

### Task 6: view `estoque_tab`, rotas, parciais, 9ª aba

**Files:**
- Modify: `apps/simulacao/views.py`, `apps/simulacao/urls.py`, `templates/simulacao/_subnav.html`, `apps/core/tests/test_render_smoke.py`
- Create: `templates/simulacao/estoque.html`, `_estoque_content.html`, `_estoque_area.html`, `_estoque_tabela.html`, `_estoque_grafico.html`
- Test: `apps/simulacao/tests/test_views_estoque.py`

**Interfaces:**
- Consumes: `estoque.agregar` / `aplicar_comparacao` / `card_com_delta` / `cenarios_comparaveis` / `dados_grafico` / `normalizar_visao` / `ROTULOS_VISAO` / `VISOES` / `RecorteGrandeDemais`; `EstoqueForm`; `requer_membro_organizacao`, `cooperativa_id_do_request`; `cenario_tem_simulacao` (Task 5).
- Produces:
  - URL `simulacao:estoque_tab` (`cenarios/<int:cenario_id>/estoque/`).
  - `views._estoque_params(request, cenario) -> (form, filtros, visao, comparar_id)` (irmão do `_resultados_params`; `comparar_id` int | None seguro).
  - `views._estoque_template(request, tem_dados) -> str` (dispatch por `request.htmx.target`: `estoque.html` / `_estoque_tabela.html` / `_estoque_area.html` / `_estoque_content.html`).
  - `views.estoque_tab(request, cenario_id)`.
  - Contexto do `_estoque_content.html`: `cenario`, `active='estoque'`, `tem_estoque`, `form`, `visao`, `comparar` (str), `dados`, `card`, `grafico`, `comparaveis`, `visoes` (= `ROTULOS_VISAO`), `querystring`.

- [ ] **Step 1: Write the failing test**

```python
# apps/simulacao/tests/test_views_estoque.py
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.models import Cooperativa
from apps.simulacao.models import (
    Armazem, Cenario, Fabrica, ResumoMensalArmazem, ResumoMensalFabrica,
)

User = get_user_model()


class EstoqueViewTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome="C", slug="c")
        self.user = User.objects.create_user(
            username="u", email="u@t.test", password="x",
            papel=User.PAPEL_ADMIN_COOPERATIVA, cooperativa=self.coop)
        self.cen = Cenario.all_cooperativas.create(cooperativa=self.coop, nome="Cen", is_oficial=True)
        self.url = reverse("simulacao:estoque_tab", kwargs={"cenario_id": self.cen.id})

    def _povoar(self, cenario=None, saldo=50, excedente=0):
        cenario = cenario or self.cen
        arm = Armazem.all_cooperativas.create(
            cooperativa=self.coop, cenario=cenario, nome="A",
            capacidade_estatica=1, capacidade_expedicao_diaria=1, estoque_inicial=0)
        fab = Fabrica.all_cooperativas.create(
            cooperativa=self.coop, cenario=cenario, nome="F",
            capacidade_estatica=1, capacidade_esmagamento_diaria=1,
            capacidade_recebimento_diaria=1, limite_caminhoes=1,
            carga_media_caminhao=1, estoque_inicial=0)
        ResumoMensalArmazem.all_cooperativas.create(
            cooperativa=self.coop, cenario=cenario, armazem=arm, mes="2026-01",
            rec_produtor=100, envio_transbordo=20, vendas=5, saldo_estoque=saldo,
            capacidade_estatica=200, excedente=excedente)
        ResumoMensalFabrica.all_cooperativas.create(
            cooperativa=self.coop, cenario=cenario, fabrica=fab, mes="2026-01",
            rec_produtor=0, rec_transbordo=20, esmagado=10, saldo_estoque=10,
            capacidade_estatica=300, excedente=0)
        return arm, fab

    def test_requer_login(self):
        self.assertIn("/accounts/login/", self.client.get(self.url).url)

    def test_admin_vector_sem_org_403(self):
        v = User.objects.create_user(username="v", email="v@t.test", password="x",
                                     papel=User.PAPEL_ADMIN_VECTOR)
        self.client.force_login(v)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_estado_vazio(self):
        self.client.force_login(self.user)
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Nenhum resultado de estoque")

    def test_pagina_completa(self):
        self._povoar()
        self.client.force_login(self.user)
        r = self.client.get(self.url)
        self.assertContains(r, "<html")
        self.assertContains(r, "Recebimento")   # coluna da visão Sistema (default)

    def test_parcial_htmx(self):
        self._povoar()
        self.client.force_login(self.user)
        r = self.client.get(self.url, HTTP_HX_REQUEST="true")
        self.assertNotContains(r, "<html")

    def test_troca_para_armazem_muda_colunas(self):
        self._povoar()
        self.client.force_login(self.user)
        r = self.client.get(self.url, {"visao": "armazem"}, HTTP_HX_REQUEST="true")
        self.assertContains(r, "Envio Transbordo")

    def test_comparacao_gera_colunas_delta(self):
        self._povoar()
        comp = Cenario.all_cooperativas.create(cooperativa=self.coop, nome="Comp")
        self._povoar(cenario=comp, saldo=30)
        self.client.force_login(self.user)
        r = self.client.get(self.url, {"visao": "sistema", "comparar": comp.id},
                            HTTP_HX_REQUEST="true")
        self.assertContains(r, "Δ%")

    def test_sinalizacao_excedente(self):
        self._povoar(excedente=40)
        self.client.force_login(self.user)
        r = self.client.get(self.url, {"visao": "armazem"}, HTTP_HX_REQUEST="true")
        self.assertContains(r, "bg-error/5")

    def test_cenario_de_outra_coop_404(self):
        outra = Cooperativa.objects.create(nome="D", slug="d")
        cen_b = Cenario.all_cooperativas.create(cooperativa=outra, nome="B")
        self.client.force_login(self.user)
        r = self.client.get(reverse("simulacao:estoque_tab", kwargs={"cenario_id": cen_b.id}))
        self.assertEqual(r.status_code, 404)

    def test_comparar_nao_numerico_nao_quebra(self):
        self._povoar()
        self.client.force_login(self.user)
        r = self.client.get(self.url, {"comparar": "xyz"}, HTTP_HX_REQUEST="true")
        self.assertEqual(r.status_code, 200)

    def test_aba_desabilitada_sem_simulacao(self):
        self.client.force_login(self.user)
        r = self.client.get(reverse("simulacao:simulacao_tab", kwargs={"cenario_id": self.cen.id}))
        self.assertContains(r, "tab-disabled")

    def test_aba_habilitada_com_movimentacao(self):
        from apps.simulacao.models import MovimentacaoDiaria
        import datetime
        arm, fab = self._povoar()
        MovimentacaoDiaria.all_cooperativas.create(
            cooperativa=self.coop, cenario=self.cen, data=datetime.date(2026, 1, 5),
            armazem=arm, fabrica=fab, quantidade_ton=1, custo_total=1)
        self.client.force_login(self.user)
        r = self.client.get(reverse("simulacao:simulacao_tab", kwargs={"cenario_id": self.cen.id}))
        # a aba Estoque só habilita quando há MovimentacaoDiaria (cenario_tem_simulacao)
        self.assertNotContains(r, 'title="Rode uma simulação"')
```

> **Nota:** `cenario_tem_simulacao` checa `MovimentacaoDiaria` (não `ResumoMensal*`), porque as duas tabelas saem da mesma transação e `MovimentacaoDiaria` é a checagem que já existia. Um cenário com `ResumoMensal*` mas sem `MovimentacaoDiaria` não acontece na prática (mesma transação), mas os testes de `estoque.agregar` populam só `ResumoMensal*` — então `test_estado_vazio` / `test_pagina_completa` da **view** dependem do check da própria view (`ResumoMensal*.objects.exists()`), não do templatetag. Ver Step 4.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest apps/simulacao/tests/test_views_estoque.py -v`
Expected: FAIL — `NoReverseMatch: 'estoque_tab'`.

- [ ] **Step 3: rota** — em `apps/simulacao/urls.py`, antes de `path('carga/', ...)` (junto das rotas de `resultados`):

```python
    path('cenarios/<int:cenario_id>/estoque/', views.estoque_tab, name='estoque_tab'),
```

- [ ] **Step 4: view** — em `apps/simulacao/views.py`. Adicionar aos imports: `estoque` em `from apps.simulacao import assistente, engine, resultados, services, tasks` → `... resultados, services, tasks` + `estoque`; `from apps.simulacao.forms import EstoqueForm, ResultadosForm`; `ResumoMensalArmazem, ResumoMensalFabrica` no bloco de models. Depois:

```python
def _estoque_params(request, cenario):
    """Parseia os parâmetros compartilhados por estoque_tab e estoque_export.
    `comparar_id` é int | None (parâmetro não-numérico é descartado)."""
    form = EstoqueForm(request.GET or None, cenario=cenario)
    form.is_valid()
    filtros = form.filtros_limpos() if form.is_bound else {
        "mes_de": "", "mes_ate": "", "armazem_ids": [], "fabrica_ids": []}
    visao = estoque.normalizar_visao(request.GET.get("visao"))
    comparar_raw = request.GET.get("comparar") or ""
    try:
        comparar_id = int(comparar_raw) if comparar_raw else None
    except (TypeError, ValueError):
        comparar_id = None
    return form, filtros, visao, comparar_id


def _estoque_template(request, tem_dados):
    """Escolhe a parcial a renderizar pelo header HX-Target (django-htmx)."""
    if not request.htmx:
        return 'simulacao/estoque.html'
    alvo = request.htmx.target
    if not tem_dados:
        return 'simulacao/_estoque_content.html'
    if alvo == 'estoque-tabela' or request.GET.get('parcial') == 'tabela':
        return 'simulacao/_estoque_tabela.html'
    if alvo == 'estoque-area':
        return 'simulacao/_estoque_area.html'
    return 'simulacao/_estoque_content.html'


@login_required
@requer_membro_organizacao
def estoque_tab(request, cenario_id):
    cenario = get_object_or_404(Cenario, id=cenario_id)
    tem_estoque = (
        ResumoMensalArmazem.objects.filter(cenario_id=cenario.id).exists()
        or ResumoMensalFabrica.objects.filter(cenario_id=cenario.id).exists())

    if not tem_estoque:
        ctx = {"cenario": cenario, "active": "estoque", "tem_estoque": False}
        return render(request, _estoque_template(request, tem_dados=False), ctx)

    coop_id = cooperativa_id_do_request(request)
    form, filtros, visao, comparar_id = _estoque_params(request, cenario)
    comparar = str(comparar_id) if comparar_id else ""
    try:
        pagina = max(1, int(request.GET.get("page", 1)))
    except (TypeError, ValueError):
        pagina = 1

    dados = estoque.agregar(cenario.id, visao, filtros, pagina=pagina)
    card = estoque.card_com_delta(cenario.id, comparar_id, filtros)
    grafico = estoque.dados_grafico(cenario.id, filtros, comparar_id)
    if comparar_id:
        dados = estoque.aplicar_comparacao(dados, comparar_id, visao, filtros)

    qs = request.GET.copy()
    qs.pop("page", None)
    qs.pop("parcial", None)
    ctx = {
        "cenario": cenario, "active": "estoque", "tem_estoque": True,
        "form": form, "visao": visao, "comparar": comparar,
        "dados": dados, "card": card, "grafico": grafico,
        "comparaveis": estoque.cenarios_comparaveis(cenario.id, coop_id),
        "visoes": estoque.ROTULOS_VISAO,
        "querystring": qs.urlencode(),
    }
    return render(request, _estoque_template(request, tem_dados=True), ctx)
```

- [ ] **Step 5: `_subnav.html`** — 9ª aba, entre "Resultados" e "Assistente" (usa `tem_simulacao` da Task 5):

```html
    <a href="{% url 'simulacao:estoque_tab' cenario_id=cenario.id %}"
       role="tab"
       {% if tem_simulacao %}
       hx-get="{% url 'simulacao:estoque_tab' cenario_id=cenario.id %}"
       hx-target="#cenario-content" hx-push-url="true"
       {% else %}aria-disabled="true" title="Rode uma simulação"{% endif %}
       class="tab {% if active == 'estoque' %}tab-active{% endif %}{% if not tem_simulacao %} tab-disabled opacity-50 pointer-events-none{% endif %}">Estoque</a>
```

- [ ] **Step 6: templates**

`templates/simulacao/estoque.html`:
```html
{% extends "base.html" %}
{% block content %}
<div id="cenario-content">
  {% include "simulacao/_estoque_content.html" %}
</div>
{% endblock %}
```

`templates/simulacao/_estoque_content.html`:
```html
{% load simulacao_filters %}
{% include "simulacao/_subnav.html" %}

{% if not tem_estoque %}
  <c-card>
    <p class="text-sm text-base-content/70">Nenhum resultado de estoque. Rode uma simulação na aba
      <a href="{% url 'simulacao:simulacao_tab' cenario_id=cenario.id %}" class="text-accent hover:underline">Simulação</a>.</p>
  </c-card>
{% else %}
<c-card>
  <form id="form-estoque"
        hx-get="{% url 'simulacao:estoque_tab' cenario.id %}"
        hx-target="#estoque-area" hx-swap="innerHTML" hx-push-url="true"
        hx-trigger="change from:#id_visao, change from:#id_comparar, submit"
        class="mb-4 flex flex-wrap items-end gap-3">
    <label class="flex flex-col text-sm">Visão
      <select id="id_visao" name="visao" class="select select-bordered select-sm">
        {% for valor, rotulo in visoes %}<option value="{{ valor }}" {% if valor == visao %}selected{% endif %}>{{ rotulo }}</option>{% endfor %}
      </select>
    </label>
    <label class="flex flex-col text-sm">Comparar com
      <select id="id_comparar" name="comparar" class="select select-bordered select-sm">
        <option value="">— sem comparação —</option>
        {% for c in comparaveis %}<option value="{{ c.id }}" {% if comparar == c.id|stringformat:'s' %}selected{% endif %}>{{ c.nome }}</option>{% endfor %}
      </select>
    </label>
    <label class="flex flex-col text-sm">Mês de {{ form.mes_de }}</label>
    <label class="flex flex-col text-sm">Mês até {{ form.mes_ate }}</label>
    <label class="flex flex-col text-sm">Armazéns {{ form.armazem_ids }}</label>
    <label class="flex flex-col text-sm">Fábricas {{ form.fabrica_ids }}</label>
    <button type="submit" class="btn btn-outline btn-sm">Aplicar</button>
    <a href="{% url 'simulacao:estoque_tab' cenario.id %}" class="btn btn-ghost btn-sm">Limpar</a>
  </form>

  {% if form.is_bound and form.errors %}
    <p class="mb-3 text-xs text-error">Alguns filtros têm formato inválido e foram ignorados.</p>
  {% endif %}

  <div id="estoque-area">
    {% include "simulacao/_estoque_area.html" %}
  </div>
</c-card>
{% endif %}
```

`templates/simulacao/_estoque_area.html`:
```html
{% load simulacao_filters %}
<c-resumo-numerico class="mb-4">
  <div class="stat"><div class="stat-title">Recebimento</div>
    <div class="stat-value text-base-content">{{ card.recebimento|volume }}</div>
    {% if card.delta %}<div class="stat-desc">{{ card.delta.recebimento|variacao }}</div>{% endif %}</div>
  <div class="stat"><div class="stat-title">Transbordo</div>
    <div class="stat-value text-base-content">{{ card.transbordo|volume }}</div>
    {% if card.delta %}<div class="stat-desc">{{ card.delta.transbordo|variacao }}</div>{% endif %}</div>
  <div class="stat"><div class="stat-title">Saldo (pico)</div>
    <div class="stat-value {% if card.mes_ruptura %}text-error{% else %}text-base-content{% endif %}">
      {% if card.mes_ruptura %}{{ card.saldo_min|volume }}{% else %}{{ card.saldo|volume }}{% endif %}</div>
    {% if card.mes_ruptura %}<div class="stat-desc text-error">ruptura em {{ card.mes_ruptura }}</div>
    {% elif card.delta %}<div class="stat-desc">{{ card.delta.saldo|variacao }}</div>{% endif %}</div>
  <div class="stat"><div class="stat-title">Cap. Estática</div>
    <div class="stat-value text-base-content">{{ card.capacidade|volume }}</div></div>
  <div class="stat"><div class="stat-title">Excedente (pico)</div>
    <div class="stat-value {% if card.excedente %}text-error{% else %}text-base-content{% endif %}">{{ card.excedente|volume }}</div>
    {% if card.delta %}<div class="stat-desc">{{ card.delta.excedente|variacao }}</div>{% endif %}</div>
</c-resumo-numerico>

<div class="mb-3 flex gap-2">
  {# botões de exportação: Task 7 #}
</div>

{% if grafico %}<div id="estoque-grafico" class="mb-4">{% include "simulacao/_estoque_grafico.html" %}</div>{% endif %}

<div id="estoque-tabela">{% include "simulacao/_estoque_tabela.html" %}</div>
```

`templates/simulacao/_estoque_tabela.html`:
```html
{% load simulacao_filters %}
<div class="overflow-x-auto">
  <table class="table table-sm">
    <thead><tr>{% for col in dados.colunas %}<th>{{ col.label }}</th>{% endfor %}</tr></thead>
    <tbody>
      {% for linha in dados.linhas %}
        <tr class="hover:bg-base-200{% if linha._alerta %} bg-error/5{% endif %}">
          {% for col in dados.colunas %}
            <td>
              {% if col.tipo == 'mes' %}{% if linha._alerta == 'ruptura' and forloop.first %}⚠ {% endif %}{{ linha.mes|slice:'5:7' }}/{{ linha.mes|slice:':4' }}
              {% elif col.tipo == 'texto' %}{{ linha|item:col.key }}
              {% elif col.tipo == 'delta' %}{{ linha|item:col.key|variacao }}
              {% elif col.tipo == 'num' %}<span class="{% if col.key == 'excedente' and linha.excedente > 0 %}text-error font-semibold{% elif col.key == 'saldo' and linha.saldo < 0 %}text-error font-semibold{% endif %}">{{ linha|item:col.key|volume }}</span>
              {% endif %}
            </td>
          {% endfor %}
        </tr>
      {% empty %}
        <tr><td colspan="{{ dados.colunas|length }}" class="py-3 text-sm text-base-content/50">Nenhuma movimentação de estoque no recorte.</td></tr>
      {% endfor %}
    </tbody>
    {% if visao == 'sistema' and dados.linhas %}
      <tfoot><tr class="font-semibold">
        {% for col in dados.colunas %}
          <td>{% if col.tipo == 'num' %}{{ dados.totais|item:col.key|volume }}{% elif forloop.first %}Total{% endif %}</td>
        {% endfor %}
      </tr></tfoot>
    {% endif %}
  </table>
</div>
{% if dados.paginacao %}
  <nav class="mt-3 flex items-center justify-between text-sm text-base-content/70">
    <span>Página {{ dados.paginacao.pagina }} de {{ dados.paginacao.num_paginas }} · {{ dados.paginacao.total }} linhas</span>
    <span class="join">
      {% if dados.paginacao.pagina > 1 %}<a class="join-item btn btn-sm btn-outline"
        hx-get="{% url 'simulacao:estoque_tab' cenario.id %}?{{ querystring }}&parcial=tabela&page={{ dados.paginacao.pagina|add:'-1' }}"
        hx-target="#estoque-tabela">←</a>{% endif %}
      {% if dados.paginacao.pagina < dados.paginacao.num_paginas %}<a class="join-item btn btn-sm btn-outline"
        hx-get="{% url 'simulacao:estoque_tab' cenario.id %}?{{ querystring }}&parcial=tabela&page={{ dados.paginacao.pagina|add:'1' }}"
        hx-target="#estoque-tabela">→</a>{% endif %}
    </span>
  </nav>
{% endif %}
```

> **Nota:** o `{{ linha|item:col.key }}` no ramo `texto` usa o filtro `item` da Fase 13 (`apps/simulacao/templatetags/simulacao_filters.py`) — dict lookup com chave variável. O `{{ dados.totais|item:col.key }}` idem. Já registrado; só `{% load simulacao_filters %}`.

`templates/simulacao/_estoque_grafico.html`:
```html
{{ grafico|json_script:"grafico-estoque-dados" }}
<canvas id="grafico-estoque" height="90"></canvas>
<script>
(function () {
  var VER = "4.4.7";
  function render() {
    var el = document.getElementById("grafico-estoque");
    var raw = document.getElementById("grafico-estoque-dados");
    if (!el || !raw || !window.Chart) return;
    var g = JSON.parse(raw.textContent);
    if (window._estoqueChart) window._estoqueChart.destroy();
    window._estoqueChart = new Chart(el, {
      type: g.tipo,
      data: {
        labels: g.labels,
        datasets: g.datasets.map(function (d) {
          return {label: d.label, data: d.dados, yAxisID: d.eixo};
        }),
      },
      options: {responsive: true, scales: {
        y: {position: "left", title: {display: true, text: "Toneladas"}},
      }},
    });
  }
  if (window.Chart) { render(); return; }
  var s = document.createElement("script");
  s.src = "https://cdn.jsdelivr.net/npm/chart.js@" + VER + "/dist/chart.umd.min.js";
  s.onload = render;
  document.head.appendChild(s);
})();
</script>
```

- [ ] **Step 7: render smoke** — em `apps/core/tests/test_render_smoke.py`, adicionar `"simulacao:estoque_tab"` a `ABAS_CENARIO_MEMBRO`:

```python
ABAS_CENARIO_MEMBRO = [
    "simulacao:rotas_grid", "simulacao:previsoes_grid", "simulacao:safras_grid",
    "simulacao:simulacao_tab", "simulacao:assistente_tab", "simulacao:resultados_tab",
    "simulacao:estoque_tab",
]
```

- [ ] **Step 8: Run tests**

Run: `python -m pytest apps/simulacao/tests/test_views_estoque.py apps/core/tests/test_render_smoke.py apps/simulacao/tests/test_views_resultados.py -q`
Expected: PASS. Depois `python manage.py check`.

- [ ] **Step 9: Commit**

```bash
git add apps/simulacao/views.py apps/simulacao/urls.py templates/simulacao/ apps/core/tests/test_render_smoke.py apps/simulacao/tests/test_views_estoque.py
git commit -m "feat(estoque): aba Estoque — view, parciais, 9ª aba HTMX, sinalização"
```

---

### Task 7: `estoque_export` — Excel + CSV

**Files:**
- Modify: `apps/simulacao/views.py`, `apps/simulacao/urls.py`, `templates/simulacao/_estoque_area.html`
- Test: `apps/simulacao/tests/test_estoque_export.py`

**Interfaces:**
- Consumes: `estoque.agregar` / `aplicar_comparacao` / `RecorteGrandeDemais` / `EXPORT_MAX`; `_estoque_params` (Task 6); `Workbook`, `csv`, `io`, `FileResponse`, `XLSX`, `timezone`, `HttpResponseBadRequest` (todos já importados em `views.py` pela Fase 13).
- Produces: URL `simulacao:estoque_export` (`cenarios/<int:cenario_id>/estoque/export/`); `views.estoque_export(request, cenario_id)`.

- [ ] **Step 1: Write the failing test**

```python
# apps/simulacao/tests/test_estoque_export.py
import io

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from openpyxl import load_workbook

from apps.core.models import Cooperativa
from apps.simulacao.models import Armazem, Cenario, ResumoMensalArmazem

User = get_user_model()


class ExportTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome="C", slug="c")
        self.user = User.objects.create_user(
            username="u", email="u@t.test", password="x",
            papel=User.PAPEL_ADMIN_COOPERATIVA, cooperativa=self.coop)
        self.cen = Cenario.all_cooperativas.create(cooperativa=self.coop, nome="Cen")
        arm = Armazem.all_cooperativas.create(
            cooperativa=self.coop, cenario=self.cen, nome="A",
            capacidade_estatica=1, capacidade_expedicao_diaria=1, estoque_inicial=0)
        for mes in ("2026-01", "2026-02", "2026-03"):
            ResumoMensalArmazem.all_cooperativas.create(
                cooperativa=self.coop, cenario=self.cen, armazem=arm, mes=mes,
                rec_produtor=10, envio_transbordo=2, vendas=1, saldo_estoque=5,
                capacidade_estatica=200, excedente=0)
        self.url = reverse("simulacao:estoque_export", kwargs={"cenario_id": self.cen.id})

    def test_xlsx_conteudo_e_headers(self):
        self.client.force_login(self.user)
        r = self.client.get(self.url, {"visao": "armazem", "formato": "xlsx"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("attachment", r["Content-Disposition"])
        conteudo = b"".join(r.streaming_content) if hasattr(r, "streaming_content") else r.content
        ws = load_workbook(io.BytesIO(conteudo)).active
        self.assertEqual(ws.cell(1, 1).value, "Mês")
        self.assertEqual(ws.max_row, 4)   # header + 3 meses
        self.assertIsInstance(ws.cell(2, 3).value, (int, float))   # rec_produtor numérico

    def test_csv_ponto_e_virgula_e_bom(self):
        self.client.force_login(self.user)
        r = self.client.get(self.url, {"visao": "sistema", "formato": "csv"})
        conteudo = b"".join(r.streaming_content) if hasattr(r, "streaming_content") else r.content
        self.assertTrue(conteudo.startswith(b"\xef\xbb\xbf"))
        self.assertIn(";", conteudo.decode("utf-8-sig").splitlines()[0])

    def test_formato_invalido_400(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.url, {"formato": "pdf"}).status_code, 400)

    def test_export_recorte_grande_400(self):
        from apps.simulacao import estoque
        orig = estoque.EXPORT_MAX
        estoque.EXPORT_MAX = 1
        try:
            self.client.force_login(self.user)
            r = self.client.get(self.url, {"visao": "armazem", "formato": "csv"})
            self.assertEqual(r.status_code, 400)
        finally:
            estoque.EXPORT_MAX = orig

    def test_gate_admin_vector_sem_org(self):
        v = User.objects.create_user(username="v", email="v@t.test", password="x",
                                     papel=User.PAPEL_ADMIN_VECTOR)
        self.client.force_login(v)
        self.assertEqual(self.client.get(self.url, {"formato": "csv"}).status_code, 403)

    def test_anonimo_redireciona_login(self):
        self.assertIn("/accounts/login/", self.client.get(self.url, {"formato": "csv"}).url)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest apps/simulacao/tests/test_estoque_export.py -v`
Expected: FAIL — `NoReverseMatch: 'estoque_export'`.

- [ ] **Step 3: rota** — em `apps/simulacao/urls.py`, logo após `estoque_tab`:

```python
    path('cenarios/<int:cenario_id>/estoque/export/', views.estoque_export, name='estoque_export'),
```

- [ ] **Step 4: view** — em `apps/simulacao/views.py` (junto de `estoque_tab`):

```python
@login_required
@requer_membro_organizacao
def estoque_export(request, cenario_id):
    cenario = get_object_or_404(Cenario, id=cenario_id)
    formato = request.GET.get("formato", "xlsx")
    if formato not in ("xlsx", "csv"):
        return HttpResponseBadRequest("Formato inválido.")

    _form, filtros, visao, comparar_id = _estoque_params(request, cenario)

    try:
        dados = estoque.agregar(cenario.id, visao, filtros,
                                pagina=None, limite=estoque.EXPORT_MAX)
    except estoque.RecorteGrandeDemais:
        return HttpResponseBadRequest("Refine os filtros para exportar.")
    if comparar_id:
        dados = estoque.aplicar_comparacao(dados, comparar_id, visao, filtros)

    colunas = dados["colunas"]

    def valor(linha, col):
        return linha.get(col["key"])

    nome = f'estoque-{cenario.id}-{visao}-{timezone.now():%Y%m%d}'
    if formato == "xlsx":
        wb = Workbook()
        ws = wb.active
        ws.append([c["label"] for c in colunas])
        for linha in dados["linhas"]:
            ws.append([valor(linha, c) for c in colunas])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return FileResponse(
            buf, as_attachment=True, filename=f'{nome}.xlsx', content_type=XLSX)

    buf = io.StringIO()
    buf.write("﻿")  # BOM UTF-8 (U+FEFF) — escape, não char literal
    w = csv.writer(buf, delimiter=";")
    w.writerow([c["label"] for c in colunas])
    for linha in dados["linhas"]:
        row = []
        for c in colunas:
            v = valor(linha, c)
            if isinstance(v, float):
                v = f"{v:.2f}".replace(".", ",")
            row.append(v)
        w.writerow(row)
    return FileResponse(
        io.BytesIO(buf.getvalue().encode("utf-8")),
        as_attachment=True, filename=f'{nome}.csv', content_type="text/csv")
```

- [ ] **Step 5: botões no `_estoque_area.html`** — trocar `{# botões de exportação: Task 7 #}` por:

```html
  <a href="{% url 'simulacao:estoque_export' cenario.id %}?{{ querystring }}&formato=xlsx" class="btn btn-outline btn-sm">Exportar (Excel)</a>
  <a href="{% url 'simulacao:estoque_export' cenario.id %}?{{ querystring }}&formato=csv" class="btn btn-outline btn-sm">CSV</a>
```

- [ ] **Step 6: Run tests**

Run: `python -m pytest apps/simulacao/tests/test_estoque_export.py apps/simulacao/tests/test_views_estoque.py -q`
Expected: PASS (o `_estoque_area.html` agora referencia `estoque_export`, que existe).

- [ ] **Step 7: Commit**

```bash
git add apps/simulacao/views.py apps/simulacao/urls.py templates/simulacao/_estoque_area.html apps/simulacao/tests/test_estoque_export.py
git commit -m "feat(estoque): exportação Excel + CSV do recorte"
```

---

### Task 8: docs, CLAUDE.md, CHANGELOG, VERSION, gate, tag

**Files:**
- Modify: `apps/simulacao/CLAUDE.md`, `CLAUDE.md` (raiz), `CHANGELOG.md`, `VERSION`

- [ ] **Step 1: `apps/simulacao/CLAUDE.md`** — acrescentar ao file map, no estilo terso das entradas existentes: `estoque.py` (**Fase 14**: motor de agregação por ORM da aba "Estoque" sobre `ResumoMensalArmazem` / `ResumoMensalFabrica` — `agregar` / `card_de_pico` / `card_com_delta` / `cenarios_comparaveis` / `aplicar_comparacao` / `dados_grafico`; três visões `sistema` / `armazem` / `fabrica`; `.objects` escopado, **não** `all_cooperativas`; **duplica de propósito** parte de `services.py::get_factories_summary` / `get_warehouses_summary` / `compare_*` — `services.py` congelado; ver a spec `docs/superpowers/specs/2026-09-02-fase14-painel-estoque-design.md`); `EstoqueForm` em `forms.py` (mês `type=month` + multi de unidade); a aba "Estoque" nas views (`estoque_tab` / `estoque_export` + `_estoque_params` / `_estoque_template`). Mencionar o rename `cenario_tem_resultado` → `cenario_tem_simulacao` (serve às abas Resultados e Estoque).

- [ ] **Step 2: `CLAUDE.md` raiz** — nova seção `## Fase 14 — Painel de Movimentação de Estoque (concluída)` no estilo da `## Fase 13`: aba "Estoque" por cenário (9ª, habilitada após a 1ª simulação), `apps/simulacao/estoque.py` + `EstoqueForm`, combo Visão (Sistema / Por armazém / Por fábrica), card de pico ("pior momento do sistema"), comparação Δ% nas 3 visões, filtros mês/armazém/fábrica, exportação Excel/CSV, gráfico de linha Saldo/Excedente, sinalização de excedente e ruptura. Sem migrations, sem ADR novo. `VERSION` → `1.3.0`. Roadmap Status → "Fases 1–14 concluídas".

- [ ] **Step 3: `VERSION`** → `1.3.0` (linha única + newline).

- [ ] **Step 4: `CHANGELOG.md`** — nova seção acima de `## [1.2.0]`, mesmo formato (parágrafo de prosa + `### Added` + `### Changed`):

```markdown
## [1.3.0] - 2026-09-02

Fase 14 — Painel de Movimentação de Estoque: aba "Estoque" por cenário sobre as tabelas de balanço mensal (`ResumoMensal*`), com a visão agregada do sistema que faltava. Nenhuma mudança de regra de negócio ou de model, sem migrations. Ver a spec 2026-09-02.

### Added
- Aba "Estoque" por cenário (habilitada após a 1ª simulação): três visões via combo — Sistema (totais mensais + rodapé), Por armazém, Por fábrica; card de pico do cenário ("pior momento do sistema"); comparação com um 2º cenário (colunas Δ% nas 3 visões, card com Δ); filtros de mês (`type=month`) / armazém / fábrica; exportação Excel e CSV; gráfico de linha Saldo total / Excedente total por mês; sinalização visual de excedente (`> 0`) e ruptura (`saldo < 0`).
- `apps/simulacao/estoque.py` (motor de agregação ORM sobre `ResumoMensal*`), `apps/simulacao/forms.py::EstoqueForm`.

### Changed
- `templates/simulacao/_subnav.html` ganha a 9ª aba "Estoque".
- Templatetag `cenario_tem_resultado` renomeado para `cenario_tem_simulacao` (a checagem serve às abas Resultados e Estoque).
```

- [ ] **Step 5: Verificação manual** — registrar (comentário no commit/PR): `runserver` + `procrastinate worker`; rodar uma simulação; abrir "Estoque"; percorrer as 3 visões; filtros de mês/unidade; cenário de comparação (Δ + card); exportar xlsx e csv e abrir; gráfico com e sem comparação; conferir destaque de excedente e de ruptura (célula vermelha + ícone + fundo de linha); paginação nas visões por unidade.

- [ ] **Step 6: Checks finais + commit + tag**

Run: `python manage.py check && python manage.py makemigrations --check --dry-run && python -m pytest -q`
Expected: limpo, "No changes detected", **todos verdes** (433 + ~45).

```bash
git add apps/simulacao/CLAUDE.md CLAUDE.md CHANGELOG.md VERSION
git commit -m "docs: release 1.3.0 (Fase 14 — Painel de Movimentação de Estoque)"
git tag -a v1.3.0 -m "Fase 14 — Painel de Movimentação de Estoque"
```

(Não pushar automaticamente — o dono decide. Merge fast-forward em `main` ao fim da revisão de todas as tarefas.)

---

## Self-Review

**1. Cobertura do SPEC:**

| Seção / requisito do SPEC | Task |
|---|---|
| `estoque.py` novo, ORM, `services.py` congelado (Decisão 1) | 1–4 |
| `EstoqueForm` (Decisão 3) | 1 |
| As 3 visões + colunas + card de pico (Decisão 2) | 1 (config), 2 (agregar), 3 (card) |
| `agregar` — merge "sistema", por unidade, `_alerta`, filtros, paginação, `limite`, tenancy (Decisão 3) | 2 |
| `card_de_pico` / `card_com_delta` / `cenarios_comparaveis` / `_traduzir_filtros` / `_delta` (Decisões 2–4) | 3 |
| `aplicar_comparacao` — Δ% nas 3 visões, colunas Δ, `totais_delta` (Decisão 4) | 4 |
| `dados_grafico` — linha Saldo/Excedente, comparado (Decisão 7) | 4 |
| Sinalização excedente + ruptura (Decisão 5) | 2 (`_alerta`), 6 (template) |
| rename `cenario_tem_resultado` → `cenario_tem_simulacao` (Decisões 6, 9) | 5 |
| view `estoque_tab`, `_estoque_params`, `_estoque_template`, rotas, 5 parciais, 9ª aba, estado vazio (Decisões 6, 9) | 6 |
| Gráfico `_estoque_grafico.html` lazy, ids próprios (Decisão 7) | 6 |
| `estoque_export` xlsx/csv, `EXPORT_MAX`, `formato` inválido, botões (Decisão 8) | 7 |
| render smoke + gate da suíte (Testes) | 6 (smoke), 8 (gate) |
| `apps/simulacao/CLAUDE.md`, `CLAUDE.md`, CHANGELOG, `VERSION` → 1.3.0, tag `v1.3.0` (Docs) | 8 |
| Sem migrations | todas (check no Step final de 1, 6, 8) |

**2. Placeholders:** a Task 6 `_estoque_area.html` tem `{# botões de exportação: Task 7 #}` — não é um buraco, é uma costura deliberada (a rota `estoque_export` só existe na Task 7; incluir os `{% url %}` antes daria `NoReverseMatch` nos testes da Task 6). A Task 7 Step 5 substitui o comentário. Nenhum outro `TODO`/`TBD`. Os `{...}` em `VISOES` / `colunas` do SPEC estão concretizados no código da Task 1.

**3. Consistência de tipos:**
- `agregar(cenario_id, visao, filtros, pagina=1, limite=None)` — assinatura idêntica em Tasks 2, 4 (`pagina=None`), 6, 7.
- `aplicar_comparacao(dados, cenario_comparado_id, visao, filtros)` — Tasks 4, 6, 7.
- `card_com_delta(cenario_id, cenario_comparado_id, filtros)` / `card_de_pico(cenario_id, filtros)` — Tasks 3, 6.
- `dados_grafico(cenario_id, filtros, cenario_comparado_id)` — Tasks 4, 6.
- `cenarios_comparaveis(cenario_id, cooperativa_id)` — Tasks 3, 6.
- `_estoque_params(request, cenario) -> (form, filtros, visao, comparar_id)` — Tasks 6, 7 (mesma ordem, `comparar_id` int|None).
- `_estoque_template(request, tem_dados)` — Task 6 (mesma lógica 4-vias do `_resultados_template`).
- chaves de `filtros`: `{mes_de, mes_ate, armazem_ids, fabrica_ids}` — Tasks 1 (`filtros_limpos`), 2, 3, 4, 6, 7.
- chaves de linha por visão: `sistema` → `{mes, recebimento, transbordo, esmagamento, vendas, saldo, capacidade, excedente}`; `armazem` → `{mes, unidade, rec_produtor, envio_transbordo, vendas, saldo, capacidade, excedente}`; `fabrica` → `{mes, unidade, rec_produtor, rec_transbordo, esmagado, saldo, capacidade, excedente}`. Consistente entre `VISOES["<v>"]["colunas"]` (Task 1) e o dict montado em `agregar` (Task 2), e o template lê `linha|item:col.key` (Task 6).
- `_alerta` ∈ `{None, "excedente", "ruptura"}` — Task 2 grava, Task 6 template lê (`linha._alerta`).
- `card` keys: `{recebimento, transbordo, esmagamento, vendas, saldo, capacidade, excedente, saldo_min, mes_ruptura, delta}` — Task 3 produz, Task 6 `_estoque_area.html` lê exatamente essas.
- coluna-Δ key = `f"{metrica}_delta"` (Task 4) e o template faz `linha|item:col.key|variacao` (Task 6) — batem.
- `RecorteGrandeDemais` definida em `estoque.py` (Task 1), levantada em `agregar` (Task 2), capturada em `estoque_export` (Task 7).

**Correções aplicadas inline durante a self-review:** (a) o `_estoque_tabela.html` da Task 6 usa `{% if visao == 'sistema' %}` para o `<tfoot>` (não `{% if dados.paginacao is None %}`) — mais direto e casa com a Decisão 2 (só a visão Sistema tem rodapé); (b) a nota da Task 3 sobre `capacidade` no `test_card_de_pico` deixa explícita a ambiguidade do fixture (jan tem ARM+FAB, fev só ARM) e manda o implementador escolher e registrar; (c) `_totais` (Task 2) trata `capacidade` como "último valor visto" (constante) e `saldo`/`excedente` como `max` — coerente com o card.

## Execution Handoff

**Plano completo e salvo em `docs/superpowers/plans/2026-09-02-fase14-painel-estoque.md`. Duas opções de execução:**

**1. Subagent-Driven (recomendado)** — um subagent novo por task, revisão em dois estágios entre tasks, iteração rápida. Casa com o rollout em ondas do SPEC.

**2. Inline Execution** — executo as tasks nesta sessão via `executing-plans`, em lotes com checkpoints.

**Qual abordagem?**
