# Fase 13 — Painel de Resultados de Simulação — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Uma aba "Resultados" dentro do cenário que mostra as movimentações e sumarizações de uma simulação (diárias e mensais), com filtros, comparação com um segundo cenário, exportação Excel/CSV e um gráfico — tudo resolvido no servidor via HTMX.

**Architecture:** Módulo novo `apps/simulacao/resultados.py` (funções puras, agregação por ORM sobre `MovimentacaoDiaria`), `apps/simulacao/forms.py` (`ResultadosForm`), views novas em `apps/simulacao/views.py` (`resultados_tab`, `resultados_export`), parciais HTMX, e Chart.js via CDN carregado só no parcial de gráfico. `apps/simulacao/services.py`, `engine.py`, `tasks.py`, `apps/integracoes` e `mcp_server.py` ficam intocados. Nenhum model muda — sem migrations.

**Tech Stack:** Django 6, HTMX, django-cotton, daisyUI, Chart.js 4.x (CDN, novo), openpyxl (já é dep), PostgreSQL, pytest.

**Spec:** `docs/superpowers/specs/2026-09-01-fase13-painel-resultados-design.md` — leia os dois.

## Global Constraints

Todo requisito de tarefa inclui implicitamente esta seção.

- **Sem migrations.** Nenhum model muda. `python manage.py makemigrations --check --dry-run` tem de sair "No changes detected".
- **TDD estrito** (red → green): teste que falha → confirma que falha pelo motivo certo → mínimo → verde. Testes em `apps/simulacao/tests/` (+ um em `apps/core/tests/test_render_smoke.py`).
- **Banco real:** PostgreSQL local via `DJANGO_DB_*` (`config.settings.dev`, default do `pytest.ini`). Suíte atual = **367 passed**; ao fim continua verde + os novos (~40).
- **Fonte única de dados:** tudo vem de `MovimentacaoDiaria` (`data`, `armazem` FK, `fabrica` FK, `quantidade_ton` FloatField, `custo_total` FloatField). `custo_total` **já embute** safra/entressafra — só exibir, nunca recalcular. As tabelas `ResumoMensal*` **não** são usadas nesta fase.
- **Sacas:** `ton * KG_PER_TON / KG_PER_SACA` — importar `KG_PER_TON` (1000) e `KG_PER_SACA` (60) de `apps.simulacao.services`. Nunca `1000/60` literal.
- **Tenancy:** `resultados.py` usa `MovimentacaoDiaria.objects` / `Cenario.objects` / `Armazem.objects` / `Fabrica.objects` (escopado pelo contextvar via `CooperativaScopeMiddleware`), **não** `all_cooperativas` (esse é só de `services.py`, ADR 0006). Testes de unidade setam o contextvar no `setUp` com `apps.core.tenancy.definir_cooperativa_atual(coop_id)` e resetam no `tearDown`.
- **Gate das views:** `@login_required` + `@requer_membro_organizacao` (de `apps.core.permissions`). Anônimo → redireciona login; Admin Vector sem organização → `PermissionDenied` (403); membro ou Admin Vector com organização → passa.
- **Formatação pt-BR:** filtros `moeda` / `volume` de `apps/simulacao/templatetags/simulacao_filters.py`. Nunca float/moeda cru na tela.
- **Identidade visual (Fase 12 / ADR 0012):** `text-accent` para link solto; `primary`/navy só para fundo preenchido ou borda; `text-error` (Δ maior) / `text-success` (Δ menor); componentes `<c-card>` / `<c-resumo-numerico>`; sinal de menos = U+2212 (`−`) nas variações.
- **Chart.js:** versão exata pinada, de `https://cdn.jsdelivr.net/npm/chart.js@<versão>/dist/chart.umd.min.js`. Carregado **só** no parcial `_resultados_grafico.html`, nunca no `base.html`.
- **`PAGE_SIZE = 100`**, `EXPORT_MAX = 50_000` — constantes em `apps/simulacao/resultados.py`.
- **`VERSION` → `1.2.0`** ao fim (minor, aditivo); tag `v1.2.0` anotada, local (não pushed automaticamente).

## Config das visões (referência — usada por várias tarefas)

O dict `VISOES` em `apps/simulacao/resultados.py` mapeia `(periodo, agrupar)` → definição. `periodo ∈ {'diario','mensal','total'}`, `agrupar ∈ {'fabrica_armazem','fabrica','armazem','nada'}` (ignorado quando `periodo='total'`).

| `(periodo, agrupar)` | `group_by` (campos `.values()`) | colunas de dimensão | pagina | requisito |
|---|---|---|---|---|
| `('diario','fabrica_armazem')` | `['data','armazem__nome','fabrica__nome']` | Dia, Origem, Destino | sim | #2 |
| `('diario','fabrica')` | `['data','fabrica__nome']` | Dia, Destino | sim | #3 |
| `('diario','armazem')` | `['data','armazem__nome']` | Dia, Origem | sim | #4 |
| `('diario','nada')` | `['data']` | Dia | não | #5 |
| `('mensal','fabrica_armazem')` | `[mes,'armazem__nome','fabrica__nome']` | Mês, Origem, Destino | não | #7 |
| `('mensal','fabrica')` | `[mes,'fabrica__nome']` | Mês, Destino | não | #8/#9 |
| `('mensal','armazem')` | `[mes,'armazem__nome']` | Mês, Origem | não | #9/#8 |
| `('mensal','nada')` | `[mes]` | Mês | não | #10 |
| `('total', *)` | `[]` (aggregate) | — | não | #11 |

`mes` = `TruncMonth('data')`. Colunas de métrica sempre no fim: `ton` (num), `sacas` (num), `custo` (moeda), todas `comparavel: True`. Default ao abrir: `('diario','fabrica_armazem')`.

---

### Task 1: `ResultadosForm` + `VISOES` (config das visões)

**Files:**
- Create: `apps/simulacao/forms.py`
- Modify: `apps/simulacao/resultados.py` (criar o arquivo, só com constantes + `VISOES` + helpers de validação)
- Test: `apps/simulacao/tests/test_resultados_config.py`

**Interfaces:**
- Produces:
  - `apps/simulacao/resultados.py`: `PAGE_SIZE = 100`, `EXPORT_MAX = 50_000`, `PERIODOS = ('diario','mensal','total')`, `AGRUPAMENTOS = ('fabrica_armazem','fabrica','armazem','nada')`, `VISOES: dict[tuple[str,str], dict]`, `normalizar_visao(periodo, agrupar) -> tuple[str,str]` (aplica defaults + valida contra `VISOES`; entrada inválida → `('diario','fabrica_armazem')`).
  - `apps/simulacao/forms.py`: `ResultadosForm(forms.Form)` com `__init__(self, *args, cenario=None, **kwargs)`; campos `data_de`/`data_ate` (`DateField`, `required=False`), `armazem_ids`/`fabrica_ids` (`ModelMultipleChoiceField`, `required=False`, queryset `Armazem.objects.filter(cenario=cenario)` / `Fabrica.objects.filter(cenario=cenario)`). `filtros_limpos(self) -> dict` → `{'data_de','data_ate','armazem_ids','fabrica_ids'}` (listas de ids para os multi, `None` para datas ausentes) após `is_valid()`.

- [ ] **Step 1: Write the failing test**

```python
# apps/simulacao/tests/test_resultados_config.py
import datetime

from django.test import TestCase

from apps.core.models import Cooperativa
from apps.core.tenancy import definir_cooperativa_atual, resetar_cooperativa_atual
from apps.simulacao import resultados
from apps.simulacao.forms import ResultadosForm
from apps.simulacao.models import Armazem, Cenario, Fabrica


class VisoesConfigTests(TestCase):
    def test_todas_as_combinacoes_validas_existem(self):
        for periodo in ("diario", "mensal"):
            for agrupar in ("fabrica_armazem", "fabrica", "armazem", "nada"):
                self.assertIn((periodo, agrupar), resultados.VISOES, (periodo, agrupar))
        self.assertIn(("total", "nada"), resultados.VISOES)

    def test_cada_visao_tem_colunas_de_metrica_comparaveis(self):
        for chave, visao in resultados.VISOES.items():
            metricas = [c for c in visao["colunas"] if c["key"] in ("ton", "sacas", "custo")]
            self.assertEqual(len(metricas), 3, chave)
            self.assertTrue(all(c.get("comparavel") for c in metricas), chave)

    def test_normalizar_visao_default_e_rejeita_invalida(self):
        self.assertEqual(resultados.normalizar_visao(None, None), ("diario", "fabrica_armazem"))
        self.assertEqual(resultados.normalizar_visao("mensal", "fabrica"), ("mensal", "fabrica"))
        self.assertEqual(resultados.normalizar_visao("xpto", "yz"), ("diario", "fabrica_armazem"))
        self.assertEqual(resultados.normalizar_visao("total", "fabrica"), ("total", "nada"))

    def test_paginacao_so_no_diario_agrupado(self):
        self.assertTrue(resultados.VISOES[("diario", "fabrica_armazem")]["pagina"])
        self.assertTrue(resultados.VISOES[("diario", "fabrica")]["pagina"])
        self.assertFalse(resultados.VISOES[("diario", "nada")]["pagina"])
        self.assertFalse(resultados.VISOES[("mensal", "fabrica_armazem")]["pagina"])


class ResultadosFormTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome="C", slug="c")
        self._tok = definir_cooperativa_atual(self.coop.id)
        self.cenario = Cenario.objects.create(cooperativa=self.coop, nome="Cen")
        self.arm = Armazem.objects.create(
            cooperativa=self.coop, cenario=self.cenario, nome="A1",
            capacidade_estatica=1, capacidade_expedicao_diaria=1, estoque_inicial=0,
        )

    def tearDown(self):
        resetar_cooperativa_atual(self._tok)

    def test_form_vazio_e_valido_e_devolve_filtros_none(self):
        form = ResultadosForm({}, cenario=self.cenario)
        self.assertTrue(form.is_valid())
        f = form.filtros_limpos()
        self.assertEqual(f, {"data_de": None, "data_ate": None, "armazem_ids": [], "fabrica_ids": []})

    def test_form_com_datas_e_armazem(self):
        form = ResultadosForm(
            {"data_de": "2026-01-01", "data_ate": "2026-01-31", "armazem_ids": [self.arm.id]},
            cenario=self.cenario,
        )
        self.assertTrue(form.is_valid(), form.errors)
        f = form.filtros_limpos()
        self.assertEqual(f["data_de"], datetime.date(2026, 1, 1))
        self.assertEqual(f["armazem_ids"], [self.arm.id])

    def test_armazem_de_outro_cenario_e_invalido(self):
        outro = Cenario.objects.create(cooperativa=self.coop, nome="Outro")
        arm2 = Armazem.objects.create(
            cooperativa=self.coop, cenario=outro, nome="A2",
            capacidade_estatica=1, capacidade_expedicao_diaria=1, estoque_inicial=0,
        )
        form = ResultadosForm({"armazem_ids": [arm2.id]}, cenario=self.cenario)
        self.assertFalse(form.is_valid())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest apps/simulacao/tests/test_resultados_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'apps.simulacao.resultados'` / `forms`.

- [ ] **Step 3: Create `apps/simulacao/resultados.py`** (só config nesta task)

```python
"""Motor de agregação do painel de Resultados (Fase 13). Funções puras sobre
`MovimentacaoDiaria`, via ORM escopado (`objects`), não `all_cooperativas`
(diferente de `services.py` — ver ADR 0006 e a spec 2026-09-01)."""
from django.db.models.functions import TruncMonth

from apps.simulacao.services import KG_PER_SACA, KG_PER_TON  # noqa: F401  (usados nas tasks seguintes)

PAGE_SIZE = 100
EXPORT_MAX = 50_000

PERIODOS = ("diario", "mensal", "total")
AGRUPAMENTOS = ("fabrica_armazem", "fabrica", "armazem", "nada")

_COL_DIA = {"key": "dia", "label": "Dia", "tipo": "data_dia"}
_COL_MES = {"key": "dia", "label": "Mês", "tipo": "data_mes"}
_COL_ORIGEM = {"key": "origem", "label": "Origem", "tipo": "texto"}
_COL_DESTINO = {"key": "destino", "label": "Destino", "tipo": "texto"}
_COLS_METRICA = [
    {"key": "ton", "label": "Toneladas", "tipo": "num", "comparavel": True},
    {"key": "sacas", "label": "Sacas", "tipo": "num", "comparavel": True},
    {"key": "custo", "label": "Frete (R$)", "tipo": "moeda", "comparavel": True},
]


def _visao(group_by, dimensoes, pagina):
    return {"group_by": group_by, "colunas": [*dimensoes, *_COLS_METRICA], "pagina": pagina}


VISOES = {
    ("diario", "fabrica_armazem"): _visao(
        ["data", "armazem__nome", "fabrica__nome"], [_COL_DIA, _COL_ORIGEM, _COL_DESTINO], True),
    ("diario", "fabrica"): _visao(["data", "fabrica__nome"], [_COL_DIA, _COL_DESTINO], True),
    ("diario", "armazem"): _visao(["data", "armazem__nome"], [_COL_DIA, _COL_ORIGEM], True),
    ("diario", "nada"): _visao(["data"], [_COL_DIA], False),
    ("mensal", "fabrica_armazem"): _visao(
        ["mes", "armazem__nome", "fabrica__nome"], [_COL_MES, _COL_ORIGEM, _COL_DESTINO], False),
    ("mensal", "fabrica"): _visao(["mes", "fabrica__nome"], [_COL_MES, _COL_DESTINO], False),
    ("mensal", "armazem"): _visao(["mes", "armazem__nome"], [_COL_MES, _COL_ORIGEM], False),
    ("mensal", "nada"): _visao(["mes"], [_COL_MES], False),
    ("total", "nada"): _visao([], [], False),
}

# `TruncMonth` fica pronto para as tasks de agregação usarem no annotate.
TRUNC_MES = TruncMonth("data")


def normalizar_visao(periodo, agrupar):
    if periodo == "total":
        return ("total", "nada")
    if (periodo, agrupar) in VISOES:
        return (periodo, agrupar)
    return ("diario", "fabrica_armazem")
```

- [ ] **Step 4: Create `apps/simulacao/forms.py`**

```python
from django import forms

from apps.simulacao.models import Armazem, Fabrica


class ResultadosForm(forms.Form):
    data_de = forms.DateField(required=False)
    data_ate = forms.DateField(required=False)
    armazem_ids = forms.ModelMultipleChoiceField(queryset=Armazem.objects.none(), required=False)
    fabrica_ids = forms.ModelMultipleChoiceField(queryset=Fabrica.objects.none(), required=False)

    def __init__(self, *args, cenario=None, **kwargs):
        super().__init__(*args, **kwargs)
        if cenario is not None:
            self.fields["armazem_ids"].queryset = Armazem.objects.filter(cenario=cenario)
            self.fields["fabrica_ids"].queryset = Fabrica.objects.filter(cenario=cenario)

    def filtros_limpos(self):
        d = self.cleaned_data
        return {
            "data_de": d.get("data_de"),
            "data_ate": d.get("data_ate"),
            "armazem_ids": [a.id for a in d.get("armazem_ids", [])],
            "fabrica_ids": [f.id for f in d.get("fabrica_ids", [])],
        }
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest apps/simulacao/tests/test_resultados_config.py -v`
Expected: PASS (todos). Depois: `python manage.py check` limpo.

- [ ] **Step 6: Commit**

```bash
git add apps/simulacao/resultados.py apps/simulacao/forms.py apps/simulacao/tests/test_resultados_config.py
git commit -m "feat(resultados): config das visões + ResultadosForm (Fase 13)"
```

---

### Task 2: `resultados.agregar()` — o núcleo de agregação

**Files:**
- Modify: `apps/simulacao/resultados.py`
- Test: `apps/simulacao/tests/test_resultados_agregar.py`

**Interfaces:**
- Consumes: `VISOES`, `normalizar_visao`, `PAGE_SIZE` (Task 1); `KG_PER_TON`/`KG_PER_SACA` de `apps.simulacao.services`.
- Produces: `agregar(cenario_id: int, periodo: str, agrupar: str, filtros: dict, pagina: int | None = 1) -> dict` com o formato:
  ```python
  {
    "colunas": [ {"key","label","tipo",...}, ... ],       # == VISOES[(periodo,agrupar)]["colunas"]
    "linhas":  [ {"dia": date, "origem": str, "destino": str,
                  "ton": float, "sacas": float, "custo": float,
                  "_chave": tuple}, ... ],
    "totais":  {"ton": float, "sacas": float, "custo": float},   # recorte inteiro (todas as páginas)
    "paginacao": {"pagina": int, "num_paginas": int, "total": int} | None,
  }
  ```
  - `dia` é `datetime.date` (1º dia do mês no `mensal`). `origem`/`destino` só existem nas visões que têm essas colunas.
  - `_chave`: `total` → `("total",)`; senão a tupla das dimensões como strings (`data.isoformat()` ou `"AAAA-MM"`, depois origem, depois destino, conforme a visão).
  - `pagina=None` → sem paginação (`linhas` = recorte inteiro, `paginacao=None`).

- [ ] **Step 1: Write the failing test**

```python
# apps/simulacao/tests/test_resultados_agregar.py
import datetime

from django.test import TestCase

from apps.core.models import Cooperativa
from apps.core.tenancy import definir_cooperativa_atual, resetar_cooperativa_atual
from apps.simulacao import resultados
from apps.simulacao.models import Armazem, Cenario, Fabrica, MovimentacaoDiaria

D = datetime.date
VAZIO = {"data_de": None, "data_ate": None, "armazem_ids": [], "fabrica_ids": []}


class AgregarTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome="C", slug="c")
        self._tok = definir_cooperativa_atual(self.coop.id)
        self.cen = Cenario.objects.create(cooperativa=self.coop, nome="Cen")
        self.a1 = self._arm("ARM1"); self.a2 = self._arm("ARM2")
        self.f1 = self._fab("FAB1"); self.f2 = self._fab("FAB2")
        # jan: a1->f1 10t/100, a2->f1 5t/50 ; fev: a1->f2 20t/400
        self._mov(D(2026, 1, 5), self.a1, self.f1, 10, 100)
        self._mov(D(2026, 1, 5), self.a2, self.f1, 5, 50)
        self._mov(D(2026, 1, 6), self.a1, self.f1, 3, 30)
        self._mov(D(2026, 2, 10), self.a1, self.f2, 20, 400)

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

    def _mov(self, data, arm, fab, ton, custo):
        MovimentacaoDiaria.objects.create(
            cooperativa=self.coop, cenario=self.cen, data=data,
            armazem=arm, fabrica=fab, quantidade_ton=ton, custo_total=custo)

    def test_diario_linha_crua(self):
        d = resultados.agregar(self.cen.id, "diario", "fabrica_armazem", VAZIO)
        self.assertEqual(len(d["linhas"]), 4)
        l0 = d["linhas"][0]
        self.assertEqual(l0["dia"], D(2026, 1, 5))
        self.assertEqual({l["origem"] for l in d["linhas"]}, {"ARM1", "ARM2"})
        self.assertEqual(l0["sacas"], l0["ton"] * 1000 / 60)
        self.assertEqual(d["totais"], {"ton": 38.0, "sacas": 38.0 * 1000 / 60, "custo": 580.0})

    def test_diario_por_fabrica_soma_armazens(self):
        d = resultados.agregar(self.cen.id, "diario", "fabrica", VAZIO)
        jan5 = [l for l in d["linhas"] if l["dia"] == D(2026, 1, 5)]
        self.assertEqual(len(jan5), 1)
        self.assertEqual(jan5[0]["ton"], 15.0)
        self.assertEqual(jan5[0]["custo"], 150.0)
        self.assertNotIn("origem", d["linhas"][0])

    def test_mensal_total(self):
        d = resultados.agregar(self.cen.id, "mensal", "nada", VAZIO)
        self.assertEqual([l["dia"] for l in d["linhas"]], [D(2026, 1, 1), D(2026, 2, 1)])
        self.assertEqual(d["linhas"][0]["ton"], 18.0)
        self.assertEqual(d["linhas"][1]["custo"], 400.0)
        self.assertEqual(d["colunas"][0]["tipo"], "data_mes")

    def test_total_do_cenario_uma_linha(self):
        d = resultados.agregar(self.cen.id, "total", "nada", VAZIO)
        self.assertEqual(len(d["linhas"]), 1)
        self.assertEqual(d["linhas"][0]["custo"], 580.0)
        self.assertEqual(d["linhas"][0]["_chave"], ("total",))

    def test_filtro_data_estreita(self):
        f = {**VAZIO, "data_de": D(2026, 2, 1), "data_ate": D(2026, 2, 28)}
        d = resultados.agregar(self.cen.id, "diario", "fabrica_armazem", f)
        self.assertEqual(len(d["linhas"]), 1)
        self.assertEqual(d["totais"]["ton"], 20.0)

    def test_filtro_armazem(self):
        f = {**VAZIO, "armazem_ids": [self.a2.id]}
        d = resultados.agregar(self.cen.id, "diario", "fabrica_armazem", f)
        self.assertEqual(len(d["linhas"]), 1)
        self.assertEqual(d["linhas"][0]["origem"], "ARM2")

    def test_filtro_que_zera(self):
        f = {**VAZIO, "data_de": D(2030, 1, 1)}
        d = resultados.agregar(self.cen.id, "diario", "nada", f)
        self.assertEqual(d["linhas"], [])
        self.assertEqual(d["totais"], {"ton": 0.0, "sacas": 0.0, "custo": 0.0})

    def test_paginacao(self):
        for i in range(1, 151):
            self._mov(D(2026, 3, 1) + datetime.timedelta(days=i), self.a1, self.f1, 1, 1)
        d1 = resultados.agregar(self.cen.id, "diario", "fabrica_armazem", VAZIO, pagina=1)
        self.assertEqual(len(d1["linhas"]), 100)
        self.assertEqual(d1["paginacao"]["total"], 154)
        self.assertEqual(d1["paginacao"]["num_paginas"], 2)
        d2 = resultados.agregar(self.cen.id, "diario", "fabrica_armazem", VAZIO, pagina=2)
        self.assertEqual(len(d2["linhas"]), 54)

    def test_sem_paginacao_quando_pagina_none(self):
        for i in range(1, 151):
            self._mov(D(2026, 3, 1) + datetime.timedelta(days=i), self.a1, self.f1, 1, 1)
        d = resultados.agregar(self.cen.id, "diario", "fabrica_armazem", VAZIO, pagina=None)
        self.assertEqual(len(d["linhas"]), 154)
        self.assertIsNone(d["paginacao"])

    def test_nao_vaza_outro_cenario(self):
        outro = Cenario.objects.create(cooperativa=self.coop, nome="Outro")
        a = Armazem.objects.create(
            cooperativa=self.coop, cenario=outro, nome="X",
            capacidade_estatica=1, capacidade_expedicao_diaria=1, estoque_inicial=0)
        f = Fabrica.objects.create(
            cooperativa=self.coop, cenario=outro, nome="Y",
            capacidade_estatica=1, capacidade_esmagamento_diaria=1,
            capacidade_recebimento_diaria=1, limite_caminhoes=1,
            carga_media_caminhao=1, estoque_inicial=0)
        MovimentacaoDiaria.objects.create(
            cooperativa=self.coop, cenario=outro, data=D(2026, 1, 5),
            armazem=a, fabrica=f, quantidade_ton=999, custo_total=999)
        d = resultados.agregar(self.cen.id, "total", "nada", VAZIO)
        self.assertEqual(d["linhas"][0]["ton"], 38.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest apps/simulacao/tests/test_resultados_agregar.py -v`
Expected: FAIL — `AttributeError: module 'apps.simulacao.resultados' has no attribute 'agregar'`.

- [ ] **Step 3: Implement `agregar` em `apps/simulacao/resultados.py`**

```python
import datetime

from django.db.models import Sum

# (no topo do módulo, junto aos imports já existentes)
from apps.simulacao.models import MovimentacaoDiaria


def _queryset_filtrado(cenario_id, filtros):
    qs = MovimentacaoDiaria.objects.filter(cenario_id=cenario_id)
    if filtros.get("data_de"):
        qs = qs.filter(data__gte=filtros["data_de"])
    if filtros.get("data_ate"):
        qs = qs.filter(data__lte=filtros["data_ate"])
    if filtros.get("armazem_ids"):
        qs = qs.filter(armazem_id__in=filtros["armazem_ids"])
    if filtros.get("fabrica_ids"):
        qs = qs.filter(fabrica_id__in=filtros["fabrica_ids"])
    return qs


def _com_sacas(ton):
    return (ton or 0.0) * KG_PER_TON / KG_PER_SACA


def agregar(cenario_id, periodo, agrupar, filtros, pagina=1):
    periodo, agrupar = normalizar_visao(periodo, agrupar)
    visao = VISOES[(periodo, agrupar)]
    base = _queryset_filtrado(cenario_id, filtros)

    tot = base.aggregate(ton=Sum("quantidade_ton"), custo=Sum("custo_total"))
    totais = {
        "ton": tot["ton"] or 0.0,
        "sacas": _com_sacas(tot["ton"]),
        "custo": tot["custo"] or 0.0,
    }

    if periodo == "total":
        linha = {"ton": totais["ton"], "sacas": totais["sacas"], "custo": totais["custo"],
                 "_chave": ("total",)}
        return {"colunas": visao["colunas"], "linhas": [linha], "totais": totais, "paginacao": None}

    group_by = visao["group_by"]
    qs = base
    if "mes" in group_by:
        qs = qs.annotate(mes=TRUNC_MES)
    qs = (qs.values(*group_by)
            .annotate(ton=Sum("quantidade_ton"), custo=Sum("custo_total"))
            .order_by(*group_by))

    total_linhas = qs.count()
    paginacao = None
    if visao["pagina"] and pagina is not None:
        num_paginas = max(1, (total_linhas + PAGE_SIZE - 1) // PAGE_SIZE)
        pagina = min(max(1, pagina), num_paginas)
        ini = (pagina - 1) * PAGE_SIZE
        qs = qs[ini:ini + PAGE_SIZE]
        paginacao = {"pagina": pagina, "num_paginas": num_paginas, "total": total_linhas}

    linhas = []
    for row in qs:
        dia = row.get("mes") or row.get("data")
        if isinstance(dia, datetime.datetime):
            dia = dia.date()
        linha = {"dia": dia, "ton": row["ton"] or 0.0, "sacas": _com_sacas(row["ton"]),
                 "custo": row["custo"] or 0.0}
        if "armazem__nome" in group_by:
            linha["origem"] = row["armazem__nome"]
        if "fabrica__nome" in group_by:
            linha["destino"] = row["fabrica__nome"]
        chave = [dia.isoformat() if periodo == "diario" else dia.strftime("%Y-%m")]
        if "origem" in linha:
            chave.append(linha["origem"])
        if "destino" in linha:
            chave.append(linha["destino"])
        linha["_chave"] = tuple(chave)
        linhas.append(linha)

    return {"colunas": visao["colunas"], "linhas": linhas, "totais": totais, "paginacao": paginacao}
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest apps/simulacao/tests/test_resultados_agregar.py -v`
Expected: PASS (todos os 11).

- [ ] **Step 5: Commit**

```bash
git add apps/simulacao/resultados.py apps/simulacao/tests/test_resultados_agregar.py
git commit -m "feat(resultados): agregar() — núcleo de agregação por ORM"
```

---

### Task 3: `totais_do_recorte` + `cenarios_comparaveis`

**Files:**
- Modify: `apps/simulacao/resultados.py`
- Test: `apps/simulacao/tests/test_resultados_auxiliares.py`

**Interfaces:**
- Consumes: `_queryset_filtrado`, `_com_sacas` (Task 2).
- Produces:
  - `totais_do_recorte(cenario_id: int, filtros: dict) -> dict` → `{"ton": float, "sacas": float, "custo": float}` (mesmos números de `agregar(...)["totais"]`, mas função dedicada para o card do topo — não paga o custo de montar linhas).
  - `cenarios_comparaveis(cenario_id: int, cooperativa_id: int) -> list[dict]` → `[{"id": int, "nome": str}]`: cenários da cooperativa **com** pelo menos uma `MovimentacaoDiaria`, **exceto** `cenario_id`, ordenados `-is_oficial, nome`.

- [ ] **Step 1: Write the failing test**

```python
# apps/simulacao/tests/test_resultados_auxiliares.py
import datetime

from django.test import TestCase

from apps.core.models import Cooperativa
from apps.core.tenancy import definir_cooperativa_atual, resetar_cooperativa_atual
from apps.simulacao import resultados
from apps.simulacao.models import Armazem, Cenario, Fabrica, MovimentacaoDiaria

VAZIO = {"data_de": None, "data_ate": None, "armazem_ids": [], "fabrica_ids": []}


class AuxiliaresTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome="C", slug="c")
        self._tok = definir_cooperativa_atual(self.coop.id)
        self.cen = Cenario.objects.create(cooperativa=self.coop, nome="Atual", is_oficial=True)
        self.arm = Armazem.objects.create(
            cooperativa=self.coop, cenario=self.cen, nome="A",
            capacidade_estatica=1, capacidade_expedicao_diaria=1, estoque_inicial=0)
        self.fab = Fabrica.objects.create(
            cooperativa=self.coop, cenario=self.cen, nome="F",
            capacidade_estatica=1, capacidade_esmagamento_diaria=1,
            capacidade_recebimento_diaria=1, limite_caminhoes=1,
            carga_media_caminhao=1, estoque_inicial=0)
        MovimentacaoDiaria.objects.create(
            cooperativa=self.coop, cenario=self.cen, data=datetime.date(2026, 1, 1),
            armazem=self.arm, fabrica=self.fab, quantidade_ton=6, custo_total=60)

    def tearDown(self):
        resetar_cooperativa_atual(self._tok)

    def test_totais_do_recorte(self):
        t = resultados.totais_do_recorte(self.cen.id, VAZIO)
        self.assertEqual(t, {"ton": 6.0, "sacas": 6.0 * 1000 / 60, "custo": 60.0})

    def test_totais_recorte_vazio_zera(self):
        f = {**VAZIO, "data_de": datetime.date(2030, 1, 1)}
        self.assertEqual(resultados.totais_do_recorte(self.cen.id, f),
                         {"ton": 0.0, "sacas": 0.0, "custo": 0.0})

    def test_cenarios_comparaveis_so_com_movimentacao_exceto_atual(self):
        com_mov = Cenario.objects.create(cooperativa=self.coop, nome="Com Mov")
        MovimentacaoDiaria.objects.create(
            cooperativa=self.coop, cenario=com_mov, data=datetime.date(2026, 1, 1),
            armazem=self.arm, fabrica=self.fab, quantidade_ton=1, custo_total=1)
        Cenario.objects.create(cooperativa=self.coop, nome="Sem Mov")
        outra_coop = Cooperativa.objects.create(nome="D", slug="d")
        Cenario.objects.create(cooperativa=outra_coop, nome="De Outra")

        lista = resultados.cenarios_comparaveis(self.cen.id, self.coop.id)
        self.assertEqual([c["nome"] for c in lista], ["Com Mov"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest apps/simulacao/tests/test_resultados_auxiliares.py -v`
Expected: FAIL — `AttributeError: ... has no attribute 'totais_do_recorte'`.

- [ ] **Step 3: Implement**

```python
# apps/simulacao/resultados.py  (adicionar)
from apps.simulacao.models import Cenario


def totais_do_recorte(cenario_id, filtros):
    agg = _queryset_filtrado(cenario_id, filtros).aggregate(
        ton=Sum("quantidade_ton"), custo=Sum("custo_total"))
    return {"ton": agg["ton"] or 0.0, "sacas": _com_sacas(agg["ton"]), "custo": agg["custo"] or 0.0}


def cenarios_comparaveis(cenario_id, cooperativa_id):
    com_mov = (MovimentacaoDiaria.objects.filter(cooperativa_id=cooperativa_id)
               .values_list("cenario_id", flat=True).distinct())
    qs = (Cenario.objects.filter(cooperativa_id=cooperativa_id, id__in=list(com_mov))
          .exclude(id=cenario_id).order_by("-is_oficial", "nome"))
    return [{"id": c.id, "nome": c.nome} for c in qs]
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest apps/simulacao/tests/test_resultados_auxiliares.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/simulacao/resultados.py apps/simulacao/tests/test_resultados_auxiliares.py
git commit -m "feat(resultados): totais_do_recorte + cenarios_comparaveis"
```

---

### Task 4: templatetags `variacao` + `item`

**Files:**
- Modify: `apps/simulacao/templatetags/simulacao_filters.py`
- Test: `apps/simulacao/tests/test_templatetags.py` (estender)

**Interfaces:**
- Produces:
  - `variacao(valor) -> SafeString` — `valor` é `float | None | "novo"`:
    - `float > 0` → `<span class="text-error">↑&nbsp;+12,3%</span>`
    - `float < 0` → `<span class="text-success">↓&nbsp;−4,1%</span>` (menos = U+2212)
    - `float == 0` → `<span class="text-base-content/50">0,0%</span>`
    - `None` → `<span class="text-base-content/50">—</span>`
    - `"novo"` → `<span class="badge badge-ghost badge-sm">novo</span>`
    - qualquer outra coisa (`""`, não numérico) → `""`
  - `item(dicionario, chave)` — `dicionario.get(chave)` (lookup de dict com chave variável no template); se não for dict → `""`.

- [ ] **Step 1: Write the failing test** (adicionar a `apps/simulacao/tests/test_templatetags.py`)

```python
class VariacaoFilterTests(SimpleTestCase):
    def _render(self, valor):
        return Template("{% load simulacao_filters %}{{ valor|variacao }}").render(
            Context({"valor": valor}))

    def test_positivo_vermelho_seta_cima(self):
        out = self._render(12.34)
        self.assertIn("text-error", out)
        self.assertIn("+12,3%", out)
        self.assertIn("↑", out)

    def test_negativo_verde_seta_baixo_menos_unicode(self):
        out = self._render(-4.08)
        self.assertIn("text-success", out)
        self.assertIn("−4,1%", out)   # U+2212
        self.assertIn("↓", out)

    def test_zero(self):
        self.assertIn("0,0%", self._render(0.0))

    def test_none_travessao(self):
        self.assertIn("—", self._render(None))

    def test_novo_badge(self):
        self.assertIn("badge", self._render("novo"))

    def test_vazio(self):
        self.assertEqual(self._render("").strip(), "")


class ItemFilterTests(SimpleTestCase):
    def test_lookup(self):
        out = Template("{% load simulacao_filters %}{{ d|item:'x' }}").render(
            Context({"d": {"x": 42}}))
        self.assertEqual(out, "42")

    def test_nao_dict(self):
        out = Template("{% load simulacao_filters %}{{ d|item:'x' }}").render(Context({"d": 5}))
        self.assertEqual(out, "")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest apps/simulacao/tests/test_templatetags.py -v`
Expected: FAIL — `variacao`/`item` não são filtros registrados.

- [ ] **Step 3: Implement** (adicionar a `apps/simulacao/templatetags/simulacao_filters.py`)

```python
from django.utils.safestring import mark_safe


@register.filter
def item(dicionario, chave):
    if isinstance(dicionario, dict):
        return dicionario.get(chave)
    return ""


@register.filter
def variacao(valor):
    if valor == "novo":
        return mark_safe('<span class="badge badge-ghost badge-sm">novo</span>')
    if valor is None:
        return mark_safe('<span class="text-base-content/50">—</span>')
    if valor == "" or not isinstance(valor, (int, float)):
        return ""
    pct = _formatar_pt_br(abs(valor), 1)
    if valor > 0:
        return mark_safe(f'<span class="text-error">↑&nbsp;+{pct}%</span>')
    if valor < 0:
        return mark_safe(f'<span class="text-success">↓&nbsp;−{pct}%</span>')
    return mark_safe('<span class="text-base-content/50">0,0%</span>')
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest apps/simulacao/tests/test_templatetags.py -v`
Expected: PASS (os antigos + os novos).

- [ ] **Step 5: Commit**

```bash
git add apps/simulacao/templatetags/simulacao_filters.py apps/simulacao/tests/test_templatetags.py
git commit -m "feat(resultados): templatetags variacao + item"
```

---

### Task 5: `resultados.aplicar_comparacao()`

**Files:**
- Modify: `apps/simulacao/resultados.py`
- Test: `apps/simulacao/tests/test_resultados_comparacao.py`

**Interfaces:**
- Consumes: `agregar` (Task 2), `VISOES` (Task 1).
- Produces: `aplicar_comparacao(dados: dict, cenario_comparado_id: int, periodo: str, agrupar: str, filtros: dict) -> dict` — recebe o retorno de `agregar(cenario_ATUAL, ...)` e devolve o mesmo dict alterado:
  - Se `(periodo, agrupar) == ("diario", "fabrica_armazem")` → devolve `dados` **sem mudança** e com `dados["comparacao_ignorada"] = True`.
  - Senão: roda `agregar(cenario_comparado_id, periodo, agrupar, filtros, pagina=None)`, indexa por `_chave`, e para cada linha de `dados["linhas"]` grava `linha["ton_delta"] / linha["sacas_delta"] / linha["custo_delta"]` (`float | None | "novo"`):
    - sem par → `"novo"`
    - par existe, comparado `== 0`, atual `> 0` → `None`
    - comparado `== 0` e atual `== 0` → `0.0`
    - senão → `(atual - comparado) / comparado * 100`
  - Insere, logo após cada coluna de métrica em `dados["colunas"]`, a coluna-Δ `{"key": f"{m}_delta", "label": "Δ%", "tipo": "delta"}` (`m ∈ {ton,sacas,custo}`).
  - `dados["totais_delta"] = {"ton": .., "sacas": .., "custo": ..}` — Δ% dos totais dos dois recortes (mesma fórmula; `None`/`0.0` nos casos-limite).

- [ ] **Step 1: Write the failing test**

```python
# apps/simulacao/tests/test_resultados_comparacao.py
import datetime

from django.test import TestCase

from apps.core.models import Cooperativa
from apps.core.tenancy import definir_cooperativa_atual, resetar_cooperativa_atual
from apps.simulacao import resultados
from apps.simulacao.models import Armazem, Cenario, Fabrica, MovimentacaoDiaria

D = datetime.date
VAZIO = {"data_de": None, "data_ate": None, "armazem_ids": [], "fabrica_ids": []}


class ComparacaoTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome="C", slug="c")
        self._tok = definir_cooperativa_atual(self.coop.id)
        self.atual = self._cenario_com_mov("Atual", ton=10, custo=100)
        self.comp = self._cenario_com_mov("Comp", ton=8, custo=125)

    def tearDown(self):
        resetar_cooperativa_atual(self._tok)

    def _cenario_com_mov(self, nome, ton, custo):
        cen = Cenario.objects.create(cooperativa=self.coop, nome=nome)
        arm = Armazem.objects.create(
            cooperativa=self.coop, cenario=cen, nome="ARM",
            capacidade_estatica=1, capacidade_expedicao_diaria=1, estoque_inicial=0)
        fab = Fabrica.objects.create(
            cooperativa=self.coop, cenario=cen, nome="FAB",
            capacidade_estatica=1, capacidade_esmagamento_diaria=1,
            capacidade_recebimento_diaria=1, limite_caminhoes=1,
            carga_media_caminhao=1, estoque_inicial=0)
        MovimentacaoDiaria.objects.create(
            cooperativa=self.coop, cenario=cen, data=D(2026, 1, 5),
            armazem=arm, fabrica=fab, quantidade_ton=ton, custo_total=custo)
        return cen

    def test_linha_crua_nao_recebe_delta(self):
        d = resultados.agregar(self.atual.id, "diario", "fabrica_armazem", VAZIO)
        d = resultados.aplicar_comparacao(d, self.comp.id, "diario", "fabrica_armazem", VAZIO)
        self.assertTrue(d["comparacao_ignorada"])
        self.assertNotIn("ton_delta", d["linhas"][0])

    def test_mensal_recebe_delta_e_colunas(self):
        d = resultados.agregar(self.atual.id, "mensal", "nada", VAZIO)
        d = resultados.aplicar_comparacao(d, self.comp.id, "mensal", "nada", VAZIO)
        self.assertEqual(d["linhas"][0]["ton_delta"], (10 - 8) / 8 * 100)     # +25%
        self.assertEqual(d["linhas"][0]["custo_delta"], (100 - 125) / 125 * 100)  # -20%
        self.assertEqual(d["linhas"][0]["sacas_delta"], d["linhas"][0]["ton_delta"])
        keys = [c["key"] for c in d["colunas"]]
        self.assertEqual(keys, ["dia", "ton", "ton_delta", "sacas", "sacas_delta",
                                "custo", "custo_delta"])

    def test_chave_sem_par_e_novo(self):
        # comparado não tem fevereiro
        MovimentacaoDiaria.objects.create(
            cooperativa=self.coop, cenario=self.atual,
            data=D(2026, 2, 2), armazem=self.atual.simulacao_armazems.first(),
            fabrica=self.atual.simulacao_fabricas.first(), quantidade_ton=3, custo_total=9)
        d = resultados.agregar(self.atual.id, "mensal", "nada", VAZIO)
        d = resultados.aplicar_comparacao(d, self.comp.id, "mensal", "nada", VAZIO)
        fev = [l for l in d["linhas"] if l["dia"] == D(2026, 2, 1)][0]
        self.assertEqual(fev["ton_delta"], "novo")

    def test_totais_delta(self):
        d = resultados.agregar(self.atual.id, "total", "nada", VAZIO)
        d = resultados.aplicar_comparacao(d, self.comp.id, "total", "nada", VAZIO)
        self.assertEqual(d["totais_delta"]["custo"], (100 - 125) / 125 * 100)
```

(Nota: os `related_name` reversos de `CenarioScopedModel` são `simulacao_armazems` / `simulacao_fabricas` — de `%(app_label)s_%(class)ss`. Se o teste precisar do armazém/fábrica, use `Armazem.objects.filter(cenario=...).first()`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest apps/simulacao/tests/test_resultados_comparacao.py -v`
Expected: FAIL — `aplicar_comparacao` não existe.

- [ ] **Step 3: Implement**

```python
# apps/simulacao/resultados.py  (adicionar)
_METRICAS = ("ton", "sacas", "custo")


def _delta(atual, comparado):
    if comparado is None:
        return "novo"
    if comparado == 0:
        return 0.0 if atual == 0 else None
    return (atual - comparado) / comparado * 100


def aplicar_comparacao(dados, cenario_comparado_id, periodo, agrupar, filtros):
    periodo, agrupar = normalizar_visao(periodo, agrupar)
    if (periodo, agrupar) == ("diario", "fabrica_armazem"):
        dados["comparacao_ignorada"] = True
        return dados
    dados["comparacao_ignorada"] = False

    comp = agregar(cenario_comparado_id, periodo, agrupar, filtros, pagina=None)
    por_chave = {l["_chave"]: l for l in comp["linhas"]}

    for linha in dados["linhas"]:
        alvo = por_chave.get(linha["_chave"])
        for m in _METRICAS:
            linha[f"{m}_delta"] = _delta(linha[m], alvo[m] if alvo else None)

    novas_colunas = []
    for col in dados["colunas"]:
        novas_colunas.append(col)
        if col["key"] in _METRICAS:
            novas_colunas.append(
                {"key": f'{col["key"]}_delta', "label": "Δ%", "tipo": "delta"})
    dados["colunas"] = novas_colunas

    dados["totais_delta"] = {
        m: _delta(dados["totais"][m], comp["totais"][m]) for m in _METRICAS}
    return dados
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest apps/simulacao/tests/test_resultados_comparacao.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/simulacao/resultados.py apps/simulacao/tests/test_resultados_comparacao.py
git commit -m "feat(resultados): aplicar_comparacao — colunas Δ% entre cenários"
```

---

### Task 6: `resultados.dados_grafico()`

**Files:**
- Modify: `apps/simulacao/resultados.py`
- Test: `apps/simulacao/tests/test_resultados_grafico.py`

**Interfaces:**
- Consumes: `agregar` (Task 2).
- Produces: `dados_grafico(cenario_id: int, periodo: str, filtros: dict, cenario_comparado_id: int | None) -> dict | None`:
  - `None` quando NÃO (`periodo == "mensal"` OU `(periodo == "diario" e o combo B for "nada")`). **Assinatura recebe só `periodo`** — a regra do diário depende também do agrupamento; portanto a assinatura real é `dados_grafico(cenario_id, periodo, agrupar, filtros, cenario_comparado_id)`. `mostra_grafico = periodo == "mensal" or (periodo == "diario" and agrupar == "nada")`.
  - `periodo == "mensal"` → `{"tipo": "bar", "labels": ["01/2026", "02/2026", ...], "datasets": [...]}`.
  - `periodo == "diario"` (+ `agrupar == "nada"`) → `{"tipo": "line", "labels": ["05/01", ...], "datasets": [...]}`.
  - datasets sempre: `{"label": "Toneladas", "dados": [...], "eixo": "y"}` + `{"label": "Frete (R$)", "dados": [...], "eixo": "y2"}`; se `cenario_comparado_id` → mais dois datasets `"Toneladas (comparado)"` / `"Frete (comparado)"`.
  - O gráfico usa sempre os **totais do período** (roda `agregar(..., agrupar="nada", ...)` internamente, ignorando o combo B da tabela).

- [ ] **Step 1: Write the failing test**

```python
# apps/simulacao/tests/test_resultados_grafico.py
import datetime

from django.test import TestCase

from apps.core.models import Cooperativa
from apps.core.tenancy import definir_cooperativa_atual, resetar_cooperativa_atual
from apps.simulacao import resultados
from apps.simulacao.models import Armazem, Cenario, Fabrica, MovimentacaoDiaria

D = datetime.date
VAZIO = {"data_de": None, "data_ate": None, "armazem_ids": [], "fabrica_ids": []}


class GraficoTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome="C", slug="c")
        self._tok = definir_cooperativa_atual(self.coop.id)
        self.cen = Cenario.objects.create(cooperativa=self.coop, nome="Cen")
        arm = Armazem.objects.create(
            cooperativa=self.coop, cenario=self.cen, nome="A",
            capacidade_estatica=1, capacidade_expedicao_diaria=1, estoque_inicial=0)
        fab = Fabrica.objects.create(
            cooperativa=self.coop, cenario=self.cen, nome="F",
            capacidade_estatica=1, capacidade_esmagamento_diaria=1,
            capacidade_recebimento_diaria=1, limite_caminhoes=1,
            carga_media_caminhao=1, estoque_inicial=0)
        for data, ton, custo in [(D(2026, 1, 5), 10, 100), (D(2026, 2, 3), 20, 250)]:
            MovimentacaoDiaria.objects.create(
                cooperativa=self.coop, cenario=self.cen, data=data,
                armazem=arm, fabrica=fab, quantidade_ton=ton, custo_total=custo)

    def tearDown(self):
        resetar_cooperativa_atual(self._tok)

    def test_mensal_barras(self):
        g = resultados.dados_grafico(self.cen.id, "mensal", "fabrica", VAZIO, None)
        self.assertEqual(g["tipo"], "bar")
        self.assertEqual(len(g["labels"]), 2)
        ton = [d for d in g["datasets"] if d["label"] == "Toneladas"][0]
        self.assertEqual(ton["dados"], [10.0, 20.0])

    def test_diario_total_linha(self):
        g = resultados.dados_grafico(self.cen.id, "diario", "nada", VAZIO, None)
        self.assertEqual(g["tipo"], "line")

    def test_diario_agrupado_sem_grafico(self):
        self.assertIsNone(resultados.dados_grafico(self.cen.id, "diario", "fabrica", VAZIO, None))

    def test_total_sem_grafico(self):
        self.assertIsNone(resultados.dados_grafico(self.cen.id, "total", "nada", VAZIO, None))

    def test_comparado_adiciona_datasets(self):
        comp = Cenario.objects.create(cooperativa=self.coop, nome="Comp")
        g = resultados.dados_grafico(self.cen.id, "mensal", "nada", VAZIO, comp.id)
        rotulos = {d["label"] for d in g["datasets"]}
        self.assertIn("Toneladas (comparado)", rotulos)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest apps/simulacao/tests/test_resultados_grafico.py -v`
Expected: FAIL — `dados_grafico` não existe.

- [ ] **Step 3: Implement**

```python
# apps/simulacao/resultados.py  (adicionar)
def _serie_periodo(cenario_id, periodo, filtros):
    d = agregar(cenario_id, periodo, "nada", filtros, pagina=None)
    labels_fmt = "%m/%Y" if periodo == "mensal" else "%d/%m"
    return (
        [l["dia"].strftime(labels_fmt) for l in d["linhas"]],
        [l["ton"] for l in d["linhas"]],
        [l["custo"] for l in d["linhas"]],
    )


def dados_grafico(cenario_id, periodo, agrupar, filtros, cenario_comparado_id):
    periodo, agrupar = normalizar_visao(periodo, agrupar)
    mostra = periodo == "mensal" or (periodo == "diario" and agrupar == "nada")
    if not mostra:
        return None
    labels, ton, custo = _serie_periodo(cenario_id, periodo, filtros)
    datasets = [
        {"label": "Toneladas", "dados": ton, "eixo": "y"},
        {"label": "Frete (R$)", "dados": custo, "eixo": "y2"},
    ]
    if cenario_comparado_id:
        _lab, ton_c, custo_c = _serie_periodo(cenario_comparado_id, periodo, filtros)
        # alinha pelo label do cenário atual; mês/dia ausente no comparado = 0
        mapa_ton = dict(zip(_lab, ton_c))
        mapa_custo = dict(zip(_lab, custo_c))
        datasets += [
            {"label": "Toneladas (comparado)",
             "dados": [mapa_ton.get(x, 0.0) for x in labels], "eixo": "y"},
            {"label": "Frete (comparado)",
             "dados": [mapa_custo.get(x, 0.0) for x in labels], "eixo": "y2"},
        ]
    return {"tipo": "bar" if periodo == "mensal" else "line", "labels": labels, "datasets": datasets}
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest apps/simulacao/tests/test_resultados_grafico.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/simulacao/resultados.py apps/simulacao/tests/test_resultados_grafico.py
git commit -m "feat(resultados): dados_grafico — série mensal/diária p/ Chart.js"
```

---

### Task 7: view `resultados_tab`, rotas, parciais, 8ª aba

**Files:**
- Modify: `apps/simulacao/views.py`, `apps/simulacao/urls.py`, `templates/simulacao/_subnav.html`, `apps/simulacao/templatetags/simulacao_filters.py`
- Create: `templates/simulacao/resultados.html`, `templates/simulacao/_resultados_content.html`, `templates/simulacao/_resultados_tabela.html`
- Test: `apps/simulacao/tests/test_views_resultados.py`

**Interfaces:**
- Consumes: `resultados.agregar` / `aplicar_comparacao` / `totais_do_recorte` / `cenarios_comparaveis` / `dados_grafico` / `normalizar_visao` / `PERIODOS` / `AGRUPAMENTOS`; `ResultadosForm`; `requer_membro_organizacao`, `cooperativa_id_do_request`.
- Produces:
  - URL names `simulacao:resultados_tab` (path `cenarios/<int:cenario_id>/resultados/`).
  - `views.resultados_tab(request, cenario_id)`.
  - templatetag `cenario_tem_resultado(cenario) -> bool` (assignment/simple tag: `MovimentacaoDiaria.objects.filter(cenario_id=cenario.id).exists()`).
  - Contexto do `_resultados_content.html`: `cenario`, `active='resultados'`, `tem_resultado`, `form` (ResultadosForm), `periodo`, `agrupar`, `comparar` (id ou `""`), `dados`, `card` (`{ton,sacas,custo, delta}`), `grafico` (dict|None), `comparaveis` (list), `periodos`/`agrupamentos` (para os `<select>`), `querystring` (a query atual sem `page`/`parcial`, para os links de export e paginação).

- [ ] **Step 1: Write the failing test**

```python
# apps/simulacao/tests/test_views_resultados.py
import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.models import Cooperativa
from apps.simulacao.models import Armazem, Cenario, Fabrica, MovimentacaoDiaria

User = get_user_model()


class ResultadosViewTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome="C", slug="c")
        self.user = User.objects.create_user(
            username="u", email="u@t.test", password="x",
            papel=User.PAPEL_ADMIN_COOPERATIVA, cooperativa=self.coop)
        self.cen = Cenario.all_cooperativas.create(cooperativa=self.coop, nome="Cen", is_oficial=True)
        self.url = reverse("simulacao:resultados_tab", kwargs={"cenario_id": self.cen.id})

    def _povoar(self):
        arm = Armazem.all_cooperativas.create(
            cooperativa=self.coop, cenario=self.cen, nome="A",
            capacidade_estatica=1, capacidade_expedicao_diaria=1, estoque_inicial=0)
        fab = Fabrica.all_cooperativas.create(
            cooperativa=self.coop, cenario=self.cen, nome="F",
            capacidade_estatica=1, capacidade_esmagamento_diaria=1,
            capacidade_recebimento_diaria=1, limite_caminhoes=1,
            carga_media_caminhao=1, estoque_inicial=0)
        MovimentacaoDiaria.all_cooperativas.create(
            cooperativa=self.coop, cenario=self.cen, data=datetime.date(2026, 1, 5),
            armazem=arm, fabrica=fab, quantidade_ton=10, custo_total=100)

    def test_requer_login(self):
        self.assertIn("/accounts/login/", self.client.get(self.url).url)

    def test_admin_vector_sem_org_403(self):
        v = User.objects.create_user(username="v", email="v@t.test", password="x",
                                     papel=User.PAPEL_ADMIN_VECTOR)
        self.client.force_login(v)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_estado_vazio_sem_simulacao(self):
        self.client.force_login(self.user)
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Nenhum resultado")

    def test_pagina_completa_com_dados(self):
        self._povoar()
        self.client.force_login(self.user)
        r = self.client.get(self.url)
        self.assertContains(r, "<html")
        self.assertContains(r, "ARM".replace("ARM", "A"))  # nome do armazém na linha crua

    def test_parcial_htmx(self):
        self._povoar()
        self.client.force_login(self.user)
        r = self.client.get(self.url, HTTP_HX_REQUEST="true")
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, "<html")

    def test_troca_para_mensal_muda_colunas(self):
        self._povoar()
        self.client.force_login(self.user)
        r = self.client.get(self.url, {"periodo": "mensal", "agrupar": "nada"},
                            HTTP_HX_REQUEST="true")
        self.assertContains(r, "Mês")

    def test_comparacao_gera_colunas_delta(self):
        self._povoar()
        comp = Cenario.all_cooperativas.create(cooperativa=self.coop, nome="Comp")
        a = Armazem.all_cooperativas.create(
            cooperativa=self.coop, cenario=comp, nome="A",
            capacidade_estatica=1, capacidade_expedicao_diaria=1, estoque_inicial=0)
        f = Fabrica.all_cooperativas.create(
            cooperativa=self.coop, cenario=comp, nome="F",
            capacidade_estatica=1, capacidade_esmagamento_diaria=1,
            capacidade_recebimento_diaria=1, limite_caminhoes=1,
            carga_media_caminhao=1, estoque_inicial=0)
        MovimentacaoDiaria.all_cooperativas.create(
            cooperativa=self.coop, cenario=comp, data=datetime.date(2026, 1, 5),
            armazem=a, fabrica=f, quantidade_ton=8, custo_total=125)
        self.client.force_login(self.user)
        r = self.client.get(self.url, {"periodo": "mensal", "agrupar": "nada",
                                       "comparar": comp.id}, HTTP_HX_REQUEST="true")
        self.assertContains(r, "Δ%")

    def test_cenario_de_outra_coop_404(self):
        outra = Cooperativa.objects.create(nome="D", slug="d")
        cen_b = Cenario.all_cooperativas.create(cooperativa=outra, nome="B")
        self.client.force_login(self.user)
        r = self.client.get(reverse("simulacao:resultados_tab", kwargs={"cenario_id": cen_b.id}))
        self.assertEqual(r.status_code, 404)

    def test_paginacao_parcial_tabela(self):
        self._povoar()
        arm = Armazem.all_cooperativas.filter(cenario=self.cen).first()
        fab = Fabrica.all_cooperativas.filter(cenario=self.cen).first()
        for i in range(1, 151):
            MovimentacaoDiaria.all_cooperativas.create(
                cooperativa=self.coop, cenario=self.cen,
                data=datetime.date(2026, 3, 1) + datetime.timedelta(days=i),
                armazem=arm, fabrica=fab, quantidade_ton=1, custo_total=1)
        self.client.force_login(self.user)
        r = self.client.get(self.url, {"parcial": "tabela", "page": 2}, HTTP_HX_REQUEST="true")
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, "resultados-area")  # só a tabela

    def test_aba_desabilitada_no_subnav_sem_resultado(self):
        self.client.force_login(self.user)
        r = self.client.get(reverse("simulacao:simulacao_tab", kwargs={"cenario_id": self.cen.id}))
        self.assertContains(r, "tab-disabled")

    def test_aba_habilitada_com_resultado(self):
        self._povoar()
        self.client.force_login(self.user)
        r = self.client.get(reverse("simulacao:simulacao_tab", kwargs={"cenario_id": self.cen.id}))
        self.assertNotContains(r, "tab-disabled")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest apps/simulacao/tests/test_views_resultados.py -v`
Expected: FAIL — `NoReverseMatch: 'resultados_tab'`.

- [ ] **Step 3: rota** — em `apps/simulacao/urls.py`, antes de `path('carga/', ...)`:

```python
    path('cenarios/<int:cenario_id>/resultados/', views.resultados_tab, name='resultados_tab'),
```

- [ ] **Step 4: templatetag** `cenario_tem_resultado` — em `apps/simulacao/templatetags/simulacao_filters.py`:

```python
@register.simple_tag
def cenario_tem_resultado(cenario):
    from apps.simulacao.models import MovimentacaoDiaria
    return MovimentacaoDiaria.objects.filter(cenario_id=cenario.id).exists()
```

- [ ] **Step 5: `_subnav.html`** — no topo, depois do `{% include _cenario_header %}`:

```html
{% load simulacao_filters %}
{% cenario_tem_resultado cenario as tem_resultado %}
```
E a 8ª aba, entre "Simulação" e "Assistente":
```html
    <a href="{% url 'simulacao:resultados_tab' cenario_id=cenario.id %}"
       role="tab"
       {% if tem_resultado %}
       hx-get="{% url 'simulacao:resultados_tab' cenario_id=cenario.id %}"
       hx-target="#cenario-content" hx-push-url="true"
       {% else %}aria-disabled="true" title="Rode uma simulação"{% endif %}
       class="tab {% if active == 'resultados' %}tab-active{% endif %}{% if not tem_resultado %} tab-disabled opacity-50 pointer-events-none{% endif %}">Resultados</a>
```

- [ ] **Step 6: view** — em `apps/simulacao/views.py`, adicionar import `from apps.simulacao import resultados`, `from apps.simulacao.forms import ResultadosForm`, `MovimentacaoDiaria` na lista de models, e:

```python
@login_required
@requer_membro_organizacao
def resultados_tab(request, cenario_id):
    cenario = get_object_or_404(Cenario, id=cenario_id)
    tem_resultado = MovimentacaoDiaria.objects.filter(cenario_id=cenario.id).exists()
    if not tem_resultado:
        ctx = {"cenario": cenario, "active": "resultados", "tem_resultado": False}
        template = 'simulacao/_resultados_content.html' if request.htmx else 'simulacao/resultados.html'
        return render(request, template, ctx)

    coop_id = cooperativa_id_do_request(request)
    form = ResultadosForm(request.GET or None, cenario=cenario)
    form.is_valid()
    filtros = form.filtros_limpos() if form.is_bound else {
        "data_de": None, "data_ate": None, "armazem_ids": [], "fabrica_ids": []}

    periodo, agrupar = resultados.normalizar_visao(
        request.GET.get("periodo"), request.GET.get("agrupar"))
    comparar = request.GET.get("comparar") or ""
    try:
        pagina = max(1, int(request.GET.get("page", 1)))
    except ValueError:
        pagina = 1

    dados = resultados.agregar(cenario.id, periodo, agrupar, filtros, pagina=pagina)
    card = resultados.totais_do_recorte(cenario.id, filtros)
    grafico = resultados.dados_grafico(cenario.id, periodo, agrupar, filtros,
                                       int(comparar) if comparar else None)
    if comparar:
        dados = resultados.aplicar_comparacao(dados, int(comparar), periodo, agrupar, filtros)
        comp_tot = resultados.totais_do_recorte(int(comparar), filtros)
        card["delta"] = {m: resultados._delta(card[m], comp_tot[m])
                         for m in ("ton", "sacas", "custo")}
    else:
        card["delta"] = None

    qs = request.GET.copy()
    qs.pop("page", None); qs.pop("parcial", None)
    ctx = {
        "cenario": cenario, "active": "resultados", "tem_resultado": True,
        "form": form, "periodo": periodo, "agrupar": agrupar, "comparar": comparar,
        "dados": dados, "card": card, "grafico": grafico,
        "comparaveis": resultados.cenarios_comparaveis(cenario.id, coop_id),
        "periodos": resultados.PERIODOS, "agrupamentos": resultados.AGRUPAMENTOS,
        "querystring": qs.urlencode(),
    }
    if request.htmx and request.GET.get("parcial") == "tabela":
        return render(request, 'simulacao/_resultados_tabela.html', ctx)
    template = 'simulacao/_resultados_content.html' if request.htmx else 'simulacao/resultados.html'
    return render(request, template, ctx)
```

- [ ] **Step 7: templates**

`templates/simulacao/resultados.html`:
```html
{% extends "base.html" %}
{% block content %}
<div id="cenario-content">
  {% include "simulacao/_resultados_content.html" %}
</div>
{% endblock %}
```

`templates/simulacao/_resultados_content.html`:
```html
{% load simulacao_filters %}
{% include "simulacao/_subnav.html" %}

{% if not tem_resultado %}
  <c-card>
    <p class="text-sm text-base-content/70">Nenhum resultado. Rode uma simulação na aba
      <a href="{% url 'simulacao:simulacao_tab' cenario_id=cenario.id %}" class="text-accent hover:underline">Simulação</a>.</p>
  </c-card>
{% else %}
<c-card>
  <form id="form-resultados"
        hx-get="{% url 'simulacao:resultados_tab' cenario.id %}"
        hx-target="#resultados-area" hx-swap="innerHTML" hx-push-url="true"
        hx-trigger="change from:(#id_periodo,#id_agrupar,#id_comparar), submit"
        class="mb-4 flex flex-wrap items-end gap-3">
    <label>Período
      <select id="id_periodo" name="periodo">
        {% for p in periodos %}<option value="{{ p }}" {% if p == periodo %}selected{% endif %}>{{ p|capfirst }}</option>{% endfor %}
      </select>
    </label>
    <label>Agrupar por
      <select id="id_agrupar" name="agrupar" {% if periodo == 'total' %}disabled{% endif %}>
        {% for a in agrupamentos %}<option value="{{ a }}" {% if a == agrupar %}selected{% endif %}>{{ a }}</option>{% endfor %}
      </select>
    </label>
    <label>Comparar com
      <select id="id_comparar" name="comparar">
        <option value="">— sem comparação —</option>
        {% for c in comparaveis %}<option value="{{ c.id }}" {% if comparar == c.id|stringformat:'s' %}selected{% endif %}>{{ c.nome }}</option>{% endfor %}
      </select>
    </label>
    <label>Data de {{ form.data_de }}</label>
    <label>Data até {{ form.data_ate }}</label>
    <label>Armazéns {{ form.armazem_ids }}</label>
    <label>Fábricas {{ form.fabrica_ids }}</label>
    <button type="submit" class="btn btn-outline btn-sm">Aplicar</button>
    <a href="{% url 'simulacao:resultados_tab' cenario.id %}" class="btn btn-ghost btn-sm">Limpar</a>
  </form>

  <div id="resultados-area">
    {% include "simulacao/_resultados_area.html" %}
  </div>
</c-card>
{% endif %}
```

`templates/simulacao/_resultados_area.html` (novo — o miolo re-swappável):
```html
{% load simulacao_filters %}
<c-resumo-numerico class="mb-4">
  <div class="stat"><div class="stat-title">Toneladas</div>
    <div class="stat-value text-base-content">{{ card.ton|volume }}</div>
    {% if card.delta %}<div class="stat-desc">{{ card.delta.ton|variacao }}</div>{% endif %}</div>
  <div class="stat"><div class="stat-title">Sacas</div>
    <div class="stat-value text-base-content">{{ card.sacas|volume }}</div>
    {% if card.delta %}<div class="stat-desc">{{ card.delta.sacas|variacao }}</div>{% endif %}</div>
  <div class="stat"><div class="stat-title">Frete (R$)</div>
    <div class="stat-value text-base-content">{{ card.custo|moeda }}</div>
    {% if card.delta %}<div class="stat-desc">{{ card.delta.custo|variacao }}</div>{% endif %}</div>
</c-resumo-numerico>

<div class="mb-3 flex gap-2">
  <a href="{% url 'simulacao:resultados_export' cenario.id %}?{{ querystring }}&formato=xlsx" class="btn btn-outline btn-sm">Exportar (Excel)</a>
  <a href="{% url 'simulacao:resultados_export' cenario.id %}?{{ querystring }}&formato=csv" class="btn btn-outline btn-sm">CSV</a>
</div>

{% if grafico %}<div id="resultados-grafico" class="mb-4">{% include "simulacao/_resultados_grafico.html" %}</div>{% endif %}

<div id="resultados-tabela">{% include "simulacao/_resultados_tabela.html" %}</div>
```

`templates/simulacao/_resultados_tabela.html`:
```html
{% load simulacao_filters %}
{% if dados.comparacao_ignorada %}
  <p class="mb-2 text-xs text-base-content/60">A comparação não se aplica à listagem de movimentações — troque o agrupamento ou o período.</p>
{% endif %}
<div class="overflow-x-auto">
  <table class="table table-sm">
    <thead><tr>{% for col in dados.colunas %}<th>{{ col.label }}</th>{% endfor %}</tr></thead>
    <tbody>
      {% for linha in dados.linhas %}
        <tr class="hover:bg-base-200">
          {% for col in dados.colunas %}
            <td>
              {% if col.tipo == 'data_dia' %}{{ linha.dia|date:'d/m/Y' }}
              {% elif col.tipo == 'data_mes' %}{{ linha.dia|date:'m/Y' }}
              {% elif col.tipo == 'texto' %}{{ linha|item:col.key }}
              {% elif col.tipo == 'num' %}{{ linha|item:col.key|volume }}
              {% elif col.tipo == 'moeda' %}{{ linha|item:col.key|moeda }}
              {% elif col.tipo == 'delta' %}{{ linha|item:col.key|variacao }}
              {% endif %}
            </td>
          {% endfor %}
        </tr>
      {% empty %}
        <tr><td colspan="{{ dados.colunas|length }}" class="py-3 text-sm text-base-content/50">Nenhuma movimentação no recorte selecionado.</td></tr>
      {% endfor %}
    </tbody>
    {% if dados.paginacao is None and dados.linhas %}
      <tfoot><tr class="font-semibold">
        {% for col in dados.colunas %}
          <td>{% if col.key == 'ton' %}{{ dados.totais.ton|volume }}{% elif col.key == 'sacas' %}{{ dados.totais.sacas|volume }}{% elif col.key == 'custo' %}{{ dados.totais.custo|moeda }}{% elif forloop.first %}Total{% endif %}</td>
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
        hx-get="{% url 'simulacao:resultados_tab' cenario.id %}?{{ querystring }}&parcial=tabela&page={{ dados.paginacao.pagina|add:'-1' }}"
        hx-target="#resultados-tabela">←</a>{% endif %}
      {% if dados.paginacao.pagina < dados.paginacao.num_paginas %}<a class="join-item btn btn-sm btn-outline"
        hx-get="{% url 'simulacao:resultados_tab' cenario.id %}?{{ querystring }}&parcial=tabela&page={{ dados.paginacao.pagina|add:'1' }}"
        hx-target="#resultados-tabela">→</a>{% endif %}
    </span>
  </nav>
{% endif %}
```

(Ajuste na view: quando `?parcial=tabela`, renderizar `_resultados_tabela.html`; senão, `_resultados_content.html` renderiza tudo. O `_resultados_area.html` é incluído pelo `_resultados_content.html`; quando a troca é de combo, o `hx-target="#resultados-area"` recebe o `_resultados_content.html` inteiro — **corrigir**: o `hx-get` do form deve ter `hx-select="#resultados-area"` ou a view detecta htmx-sem-parcial e devolve `_resultados_area.html`. **Decisão para o implementador:** a view, quando `request.htmx and not parcial`, renderiza `_resultados_area.html` (o miolo); quando `not htmx`, renderiza `resultados.html`; quando aba clicada (htmx, sem query de combo), também precisa do `_resultados_content.html` com subnav. Distinção: a aba do `_subnav` aponta para `#cenario-content` → devolve `_resultados_content.html`; o form aponta para `#resultados-area` → devolve `_resultados_area.html`. Usar o header `HX-Target` (`request.headers.get('HX-Target')`) para decidir: `== 'resultados-area'` → área; `== 'resultados-tabela'` → tabela; senão → content.)

- [ ] **Step 8: Run tests**

Run: `python -m pytest apps/simulacao/tests/test_views_resultados.py -v`
Expected: PASS. Depois: `python -m pytest apps/simulacao/tests/test_login.py apps/simulacao/tests/test_views_simulacao.py -q` (o `_subnav` agora tem a aba nova — nenhum teste existente quebra porque a aba a mais é aditiva; se algum contar tabs, ajustar).

- [ ] **Step 9: Commit**

```bash
git add apps/simulacao/views.py apps/simulacao/urls.py apps/simulacao/templatetags/simulacao_filters.py templates/simulacao/ apps/simulacao/tests/test_views_resultados.py
git commit -m "feat(resultados): aba Resultados — view, parciais, 8ª aba HTMX"
```

---

### Task 8: gráfico Chart.js — parcial + loader + ADR 0013

**Files:**
- Create: `templates/simulacao/_resultados_grafico.html`, `docs/decisions/0013-chartjs-padrao-grafico-agrovector.md`
- Modify: `docs/design-system/README.md`
- Test: `apps/simulacao/tests/test_views_resultados.py` (estender)

**Interfaces:**
- Consumes: `grafico` no contexto (Task 7) — `{"tipo","labels","datasets":[{"label","dados","eixo"}]}`.
- Produces: `_resultados_grafico.html` — um `<canvas id="grafico-resultados">` + um `<script type="application/json" id="grafico-dados">{{ grafico|json_script_inline }}</script>` (na verdade usar `{{ grafico|json_script:"grafico-dados" }}` do Django) + o loader.

- [ ] **Step 1: Write the failing test** (adicionar a `test_views_resultados.py`)

```python
    def test_grafico_mensal_tem_canvas_e_dados(self):
        self._povoar()
        self.client.force_login(self.user)
        r = self.client.get(self.url, {"periodo": "mensal", "agrupar": "nada"},
                            HTTP_HX_REQUEST="true", HTTP_HX_TARGET="resultados-area")
        self.assertContains(r, 'id="grafico-resultados"')
        self.assertContains(r, 'id="grafico-dados"')
        self.assertContains(r, "chart.umd.min.js")

    def test_visao_crua_sem_grafico(self):
        self._povoar()
        self.client.force_login(self.user)
        r = self.client.get(self.url, HTTP_HX_REQUEST="true", HTTP_HX_TARGET="resultados-area")
        self.assertNotContains(r, 'id="grafico-resultados"')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest apps/simulacao/tests/test_views_resultados.py -k grafico -v`
Expected: FAIL.

- [ ] **Step 3: `_resultados_grafico.html`**

```html
{{ grafico|json_script:"grafico-dados" }}
<canvas id="grafico-resultados" height="90"></canvas>
<script>
(function () {
  var VER = "4.4.7";
  function render() {
    var el = document.getElementById("grafico-resultados");
    var raw = document.getElementById("grafico-dados");
    if (!el || !raw || !window.Chart) return;
    var g = JSON.parse(raw.textContent);
    if (window._resultadosChart) window._resultadosChart.destroy();
    window._resultadosChart = new Chart(el, {
      type: g.tipo,
      data: {
        labels: g.labels,
        datasets: g.datasets.map(function (d) {
          return {label: d.label, data: d.dados, yAxisID: d.eixo,
                  type: d.eixo === "y2" ? "line" : g.tipo};
        }),
      },
      options: {responsive: true, scales: {
        y: {position: "left", title: {display: true, text: "Toneladas"}},
        y2: {position: "right", grid: {drawOnChartArea: false},
             title: {display: true, text: "Frete (R$)"}},
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

- [ ] **Step 4: ADR 0013** `docs/decisions/0013-chartjs-padrao-grafico-agrovector.md` — formato dos ADRs 0001–0012 (`# ADR 0013 — …`, `- Status: Aceito`, `- Data: 2026-09-01`, `## Contexto`, `## Decisão`, `## Consequências`). Conteúdo: Chart.js 4.x via `cdn.jsdelivr.net`, versão exata pinada, carregado só onde há gráfico (não no `base.html`), servidor manda `{tipo, labels, datasets}` como JSON via `{{ ...|json_script }}`, init/destroy a cada swap HTMX. Rejeitados: Plotly (removido no Cutover, pesado), ApexCharts (ok mas Chart.js menor/mais onipresente), barras CSS puras (sem eixo/tooltip). Padrão da suíte AgroVector.

- [ ] **Step 5: `docs/design-system/README.md`** — nova seção "## Gráficos (Chart.js)": a regra do lazy-load, o contrato `{{ grafico|json_script:"..." }}` + `renderChart()` que roda no swap, os dois tipos (barras mensais dois-eixos, linha diária).

- [ ] **Step 6: Run tests**

Run: `python -m pytest apps/simulacao/tests/test_views_resultados.py -v && python manage.py check`
Expected: PASS + check limpo.

- [ ] **Step 7: Commit**

```bash
git add templates/simulacao/_resultados_grafico.html docs/decisions/0013-chartjs-padrao-grafico-agrovector.md docs/design-system/README.md apps/simulacao/tests/test_views_resultados.py
git commit -m "feat(resultados): gráfico Chart.js (lazy CDN) + ADR 0013"
```

---

### Task 9: `resultados_export` — Excel + CSV

**Files:**
- Modify: `apps/simulacao/views.py`, `apps/simulacao/urls.py`
- Test: `apps/simulacao/tests/test_resultados_export.py`

**Interfaces:**
- Consumes: `resultados.agregar` / `aplicar_comparacao` / `normalizar_visao` / `EXPORT_MAX`; `ResultadosForm`.
- Produces: URL `simulacao:resultados_export` (`cenarios/<int:cenario_id>/resultados/export/`); `views.resultados_export(request, cenario_id)`.

- [ ] **Step 1: Write the failing test**

```python
# apps/simulacao/tests/test_resultados_export.py
import csv
import datetime
import io

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from openpyxl import load_workbook

from apps.core.models import Cooperativa
from apps.simulacao.models import Armazem, Cenario, Fabrica, MovimentacaoDiaria

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
        fab = Fabrica.all_cooperativas.create(
            cooperativa=self.coop, cenario=self.cen, nome="F",
            capacidade_estatica=1, capacidade_esmagamento_diaria=1,
            capacidade_recebimento_diaria=1, limite_caminhoes=1,
            carga_media_caminhao=1, estoque_inicial=0)
        for i in range(3):
            MovimentacaoDiaria.all_cooperativas.create(
                cooperativa=self.coop, cenario=self.cen,
                data=datetime.date(2026, 1, 5 + i), armazem=arm, fabrica=fab,
                quantidade_ton=10, custo_total=100)
        self.url = reverse("simulacao:resultados_export", kwargs={"cenario_id": self.cen.id})

    def test_xlsx_conteudo_e_headers(self):
        self.client.force_login(self.user)
        r = self.client.get(self.url, {"periodo": "diario", "agrupar": "fabrica_armazem",
                                       "formato": "xlsx"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("attachment", r["Content-Disposition"])
        self.assertIn(".xlsx", r["Content-Disposition"])
        wb = load_workbook(io.BytesIO(b"".join(r.streaming_content) if hasattr(r, "streaming_content") else r.content))
        ws = wb.active
        self.assertEqual(ws.cell(1, 1).value, "Dia")
        self.assertEqual(ws.max_row, 4)  # 1 header + 3 linhas
        self.assertIsInstance(ws.cell(2, 4).value, (int, float))  # ton = número

    def test_csv_ponto_e_virgula_e_bom(self):
        self.client.force_login(self.user)
        r = self.client.get(self.url, {"formato": "csv"})
        conteudo = (b"".join(r.streaming_content) if hasattr(r, "streaming_content") else r.content)
        self.assertTrue(conteudo.startswith(b"\xef\xbb\xbf"))
        texto = conteudo.decode("utf-8-sig")
        self.assertIn(";", texto.splitlines()[0])

    def test_formato_invalido_400(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.url, {"formato": "pdf"}).status_code, 400)

    def test_respeita_filtro(self):
        self.client.force_login(self.user)
        r = self.client.get(self.url, {"formato": "csv", "data_de": "2026-01-06"})
        conteudo = (b"".join(r.streaming_content) if hasattr(r, "streaming_content") else r.content)
        self.assertEqual(len(conteudo.decode("utf-8-sig").strip().splitlines()), 3)  # header + 2

    def test_gate_admin_vector_sem_org(self):
        v = User.objects.create_user(username="v", email="v@t.test", password="x",
                                     papel=User.PAPEL_ADMIN_VECTOR)
        self.client.force_login(v)
        self.assertEqual(self.client.get(self.url, {"formato": "csv"}).status_code, 403)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest apps/simulacao/tests/test_resultados_export.py -v`
Expected: FAIL — `NoReverseMatch: 'resultados_export'`.

- [ ] **Step 3: rota** — em `apps/simulacao/urls.py`, logo após `resultados_tab`:

```python
    path('cenarios/<int:cenario_id>/resultados/export/', views.resultados_export, name='resultados_export'),
```

- [ ] **Step 4: view** — em `apps/simulacao/views.py`:

```python
import csv as _csv
import io as _io

from openpyxl import Workbook


@login_required
@requer_membro_organizacao
def resultados_export(request, cenario_id):
    cenario = get_object_or_404(Cenario, id=cenario_id)
    formato = request.GET.get("formato", "xlsx")
    if formato not in ("xlsx", "csv"):
        return HttpResponseBadRequest("Formato inválido.")

    form = ResultadosForm(request.GET or None, cenario=cenario)
    form.is_valid()
    filtros = form.filtros_limpos() if form.is_bound else {
        "data_de": None, "data_ate": None, "armazem_ids": [], "fabrica_ids": []}
    periodo, agrupar = resultados.normalizar_visao(
        request.GET.get("periodo"), request.GET.get("agrupar"))
    comparar = request.GET.get("comparar") or ""

    dados = resultados.agregar(cenario.id, periodo, agrupar, filtros, pagina=None)
    if len(dados["linhas"]) > resultados.EXPORT_MAX:
        return HttpResponseBadRequest("Refine os filtros para exportar.")
    if comparar:
        dados = resultados.aplicar_comparacao(dados, int(comparar), periodo, agrupar, filtros)

    colunas = dados["colunas"]
    def valor(linha, col):
        v = linha.get(col["key"])
        if col["tipo"] in ("data_dia", "data_mes"):
            return linha.get("dia")
        return v

    nome = f'resultados-{cenario.id}-{periodo}-{agrupar}-{timezone.now():%Y%m%d}'
    if formato == "xlsx":
        wb = Workbook(); ws = wb.active
        ws.append([c["label"] for c in colunas])
        for linha in dados["linhas"]:
            ws.append([valor(linha, c) for c in colunas])
        buf = _io.BytesIO(); wb.save(buf); buf.seek(0)
        resp = FileResponse(buf, as_attachment=True, filename=f'{nome}.xlsx', content_type=XLSX)
        return resp

    buf = _io.StringIO(); buf.write("﻿")
    w = _csv.writer(buf, delimiter=";")
    w.writerow([c["label"] for c in colunas])
    for linha in dados["linhas"]:
        row = []
        for c in colunas:
            v = valor(linha, c)
            if isinstance(v, float):
                v = f"{v:.2f}".replace(".", ",")
            row.append(v)
        w.writerow(row)
    resp = FileResponse(_io.BytesIO(buf.getvalue().encode("utf-8")),
                        as_attachment=True, filename=f'{nome}.csv', content_type="text/csv")
    return resp
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest apps/simulacao/tests/test_resultados_export.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/simulacao/views.py apps/simulacao/urls.py apps/simulacao/tests/test_resultados_export.py
git commit -m "feat(resultados): exportação Excel + CSV do recorte"
```

---

### Task 10: gate — render smoke + suíte completa

**Files:**
- Modify: `apps/core/tests/test_render_smoke.py`

- [ ] **Step 1: adicionar `simulacao:resultados_tab` ao smoke**

Em `ABAS_CENARIO_MEMBRO` de `apps/core/tests/test_render_smoke.py`, acrescentar `"simulacao:resultados_tab"`. A aba responde 200 mesmo sem `MovimentacaoDiaria` (estado vazio) para qualquer papel de membro — que é o que `test_abas_comuns_do_cenario` já exige.

```python
ABAS_CENARIO_MEMBRO = [
    "simulacao:rotas_grid", "simulacao:previsoes_grid", "simulacao:safras_grid",
    "simulacao:simulacao_tab", "simulacao:assistente_tab", "simulacao:resultados_tab",
]
```

- [ ] **Step 2: Run the smoke**

Run: `python -m pytest apps/core/tests/test_render_smoke.py -v`
Expected: PASS.

- [ ] **Step 3: Suíte completa + checks**

Run: `python manage.py check && python manage.py makemigrations --check --dry-run && python -m pytest -q`
Expected: check limpo, "No changes detected", **todos verdes** (367 + ~40).

- [ ] **Step 4: Commit**

```bash
git add apps/core/tests/test_render_smoke.py
git commit -m "test(resultados): smoke da aba Resultados + gate da suíte"
```

---

### Task 11: docs, CLAUDE.md, CHANGELOG, VERSION, tag

**Files:**
- Modify: `apps/simulacao/CLAUDE.md`, `CLAUDE.md` (raiz), `CHANGELOG.md`, `VERSION`

- [ ] **Step 1: `apps/simulacao/CLAUDE.md`** — adicionar ao file map: `resultados.py` (motor de agregação ORM da UI — `agregar` / `totais_do_recorte` / `cenarios_comparaveis` / `aplicar_comparacao` / `dados_grafico`; usa `.objects` escopado, **não** `all_cooperativas`; **duplica de propósito** parte de `services.py::get_monthly_summary`/`get_daily_movements` — `services.py` é porte 1:1 congelado que alimenta MCP/API), `forms.py` (`ResultadosForm`), e a aba "Resultados" nas views (`resultados_tab`, `resultados_export`).

- [ ] **Step 2: `CLAUDE.md` raiz** — Tech Stack: `+ Chart.js 4 (CDN) — gráficos (ADR 0013)`. Nova seção `## Fase 13 — Painel de Resultados (concluída)` no estilo das seções de fase existentes: aba Resultados por cenário, `apps/simulacao/resultados.py` + `forms.py`, dois combos (Período × Agrupar), comparação entre cenários (Δ%), exportação Excel/CSV, gráfico Chart.js, ADR 0013. Roadmap Status → "Fases 1–13 concluídas", `1.2.0`.

- [ ] **Step 3: `VERSION`** → `1.2.0` (linha única + newline).

- [ ] **Step 4: `CHANGELOG.md`** — nova seção no topo da lista de versões:

```markdown
## [1.2.0] - 2026-09-01

### Added
- Fase 13 — Painel de Resultados: aba "Resultados" por cenário (habilitada após a 1ª simulação) com listagem de movimentações diárias e sumarizações (diárias e mensais) via dois combos Período × Agrupar por; card-resumo do cenário; comparação com um segundo cenário (colunas Δ%, vermelho ↑ / verde ↓); filtros de data / armazém / fábrica; exportação Excel e CSV do recorte; gráfico de barras mensal / linha diária.
- `apps/simulacao/resultados.py` (motor de agregação ORM), `apps/simulacao/forms.py` (`ResultadosForm`), templatetags `variacao` / `item` / `cenario_tem_resultado`.
- Chart.js 4.x via CDN como padrão de gráfico da suíte AgroVector (ADR 0013), carregado sob demanda.

### Changed
- `templates/simulacao/_subnav.html` ganha a 8ª aba "Resultados".
```

- [ ] **Step 5: Verificação manual** — registrar o resultado (comentário no commit/PR): `runserver` + `procrastinate worker`; rodar uma simulação; abrir "Resultados"; percorrer as 9 formas dos dois combos; aplicar filtros; selecionar cenário de comparação (conferir cores/setas Δ e o card); exportar xlsx e csv e abrir; ver o gráfico mensal e o diário-total, com e sem comparação; paginação na visão crua.

- [ ] **Step 6: Checks finais + commit + tag**

Run: `python manage.py check && python manage.py makemigrations --check --dry-run && python -m pytest -q`
Expected: limpo, sem migrations, verde.

```bash
git add apps/simulacao/CLAUDE.md CLAUDE.md CHANGELOG.md VERSION
git commit -m "docs: release 1.2.0 (Fase 13 — Painel de Resultados)"
git tag -a v1.2.0 -m "Fase 13 — Painel de Resultados de Simulação"
```
(Não pushar automaticamente — o dono decide. Merge fast-forward em `main` ao fim da revisão de todas as tarefas.)

---

## Self-Review

**1. Cobertura do SPEC:**

| Seção / requisito do SPEC | Task |
|---|---|
| `resultados.py` config das visões (Decisão 2) | 1 |
| `ResultadosForm` (Decisão 3) | 1 |
| `agregar()` + ORM + sacas + filtros + paginação + tenancy (Decisão 3) | 2 |
| `totais_do_recorte`, `cenarios_comparaveis` (Decisão 3) | 3 |
| templatetag `variacao` + `item` (Decisão 4) | 4 |
| `aplicar_comparacao` — Δ%, casos-limite, colunas Δ, card delta (Decisão 4) | 5 |
| `dados_grafico` (Decisão 6) | 6 |
| view `resultados_tab`, rotas, 3 alvos de swap, parciais, estado vazio, 8ª aba, `cenario_tem_resultado` (Decisões 5, 8) | 7 |
| Chart.js lazy-load, `_resultados_grafico.html`, ADR 0013, design-system README (Decisão 6) | 8 |
| `resultados_export` xlsx/csv, `EXPORT_MAX`, `formato` inválido (Decisão 7) | 9 |
| render smoke + gate da suíte (Testes) | 10 |
| `apps/simulacao/CLAUDE.md`, `CLAUDE.md`, CHANGELOG, `VERSION` → 1.2.0, tag `v1.2.0` (Docs) | 11 |
| Sem migrations | todas (check no Step final de 2, 7, 10, 11) |

**2. Placeholders:** a Task 7 Step 7 tem uma nota "**Decisão para o implementador**" sobre qual parcial devolver por `HX-Target` — não é um buraco, é a regra concreta (usar `request.headers.get('HX-Target')`: `resultados-area` → `_resultados_area.html`; `resultados-tabela` → `_resultados_tabela.html`; senão → `_resultados_content.html`). O `_resultados_area.html` é criado nessa mesma task (Step 7). Nenhum outro `TODO`/`TBD`.

**3. Consistência de tipos:**
- `agregar(cenario_id, periodo, agrupar, filtros, pagina=1)` — assinatura idêntica em Tasks 2, 5 (`pagina=None`), 6, 7, 9.
- `aplicar_comparacao(dados, cenario_comparado_id, periodo, agrupar, filtros)` — Tasks 5, 7, 9.
- `dados_grafico(cenario_id, periodo, agrupar, filtros, cenario_comparado_id)` — a Task 6 corrige a assinatura do SPEC (que só listava `periodo`) para incluir `agrupar`; Task 7 chama com 5 args posicionais coerentes.
- chaves de `filtros`: `{data_de, data_ate, armazem_ids, fabrica_ids}` — Tasks 1 (`filtros_limpos`), 2, 3, 5, 6, 7, 9.
- `_delta(atual, comparado)` — helper interno de `resultados.py`, usado em Task 5 e referenciado na Task 7 (`resultados._delta`) para o card. Consistente.
- coluna-Δ key = `f"{metrica}_delta"` (Task 5) e o template lê `linha|item:col.key` (Task 7) — batem.
- `VISOES[(periodo,agrupar)]["colunas"] / ["group_by"] / ["pagina"]` — Task 1 define, Tasks 2/5 consomem exatamente essas chaves.

**Correções aplicadas inline durante a self-review:** (a) a Task 7 introduz `_resultados_area.html` (o SPEC falava em `_resultados_content.html` re-swappável a partir de um `<div id="resultados-area">` — separar o miolo num parcial próprio é mais limpo e evita re-renderizar o subnav a cada troca de combo); (b) `dados_grafico` ganha `agrupar` na assinatura (o SPEC listava só `periodo` mas a própria regra `mostra_grafico` depende de `agrupar == 'nada'`).

## Execution Handoff

**Plano completo e salvo em `docs/superpowers/plans/2026-09-01-fase13-painel-resultados.md`. Duas opções de execução:**

**1. Subagent-Driven (recomendado)** — um subagent novo por task, revisão em dois estágios entre tasks, iteração rápida. Casa com o rollout em ondas do SPEC.

**2. Inline Execution** — executo as tasks nesta sessão via `executing-plans`, em lotes com checkpoints.

**Qual abordagem?**
