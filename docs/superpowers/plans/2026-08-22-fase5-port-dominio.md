# Fase 5 — Port do Domínio Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the SQLAlchemy domain layer (`models.py`'s 11 tables, `calculations.py`'s OR-Tools engine, `logistics_services.py`'s read layer) to Django, with `cooperativa_id` on every tenant-scoped model and a formal, per-model tenant-isolation test — without touching the existing Streamlit/SQLAlchemy app, which keeps running unmodified until cutover (Fase 8).

**Architecture:** All new code lives in `apps/simulacao/` (registered, empty, since the Fundação plan). `apps/simulacao/models.py` gets two abstract mixins on top of Fase 5's Fundação-phase `apps.core.tenancy.CooperativaScopedModel`: `CenarioScopedModel` (adds a required `cenario` FK + a `clean()` invariant that `self.cenario.cooperativa_id == self.cooperativa_id` — the SQLAlchemy source never had this check because it never had a `cooperativa` concept; it's new, cheap insurance against the exact class of bug ADR 0001 already flags as an open write-path gap) for the 7 models that key off `cenario_id` directly, plus two narrower one-off `clean()` checks for the two `Previsao*` models, which key off `fabrica`/`armazem` instead. `apps/simulacao/engine.py` and `apps/simulacao/services.py` are the 1:1 ports of `calculations.py`/`logistics_services.py`: same public function names and business parameters (the SQLAlchemy `session` parameter is dropped — Django's ORM has no session object), same OR-Tools solver logic (untouched), Django ORM underneath. Every query in `engine.py`/`services.py` uses `Model.all_cooperativas` (the unscoped manager), never `Model.objects` (the fail-closed `TenantManager`) — documented as ADR 0006: these are backend domain functions that receive their tenant boundary explicitly via a `cenario_id`/`scenario_id` parameter (exactly how the pre-Fase-5 code already worked — there was never an implicit "current session's tenant" concept), and they must work correctly when called from contexts with no HTTP request at all (a future Procrastinate worker, a management command, a test) — relying on `CooperativaScopeMiddleware`-populated context here would silently return empty results the moment a caller forgets to also set it, which is a worse failure mode than requiring the explicit ID that was already being passed in anyway.

**Tech Stack:** Django 6 ORM (already installed, Fundação plan), `django.db.transaction.atomic()` for the delete+recompute+insert atomicity guarantee, `django.test.utils.CaptureQueriesContext`/`TestCase.assertNumQueries` for the query-count regression tests, OR-Tools (`ortools`, already installed) — solver logic itself is untouched.

**Spec:** `docs/superpowers/specs/2026-08-22-fase5-arquitetura-saas-django.md` (decision #1's `cooperativa_id` propagation, decision #2's engine.py/services.py port, migration phase 2 "Port do domínio")

## Global Constraints

- Multi-tenancy is schema compartilhado + `cooperativa_id` (FK, `on_delete=PROTECT`, via `apps.core.tenancy.CooperativaScopedModel`) on every model — never `django-tenants` (spec decision #1, already implemented in the Fundação plan).
- `TenantManager` (`Model.objects`) fails closed (`queryset.none()` with no cooperativa in context) — `Model.all_cooperativas` is the explicit, deliberate cross-tenant/no-context escape hatch (ADR 0003, Fundação plan). This plan's engine/services layer uses `all_cooperativas` throughout, per ADR 0006 below.
- All new development happens in the `Transbordo` repo (remote `origin`); never commit to the frozen `comigo` remote.
- Portuguese domain terms (`Cenario`, `Fabrica`, `Armazem`, `Rota`, `Safra`, `Cooperativa`, ...) are never translated.
- Documentation follows the APP_Vector convention: ADRs in `docs/decisions/`, numbered, `Status`/`Data`/`Contexto`/`Decisão`/`Consequências`. This plan continues the numbering from the Fundação plan's ADRs 0001-0004, starting at `0005`.
- The existing Streamlit/SQLAlchemy app (`app.py`, `models.py`, `calculations.py`, `logistics_services.py`, `data_loader.py`, ...) and its `tests/` suite must keep working unmodified — the two stacks coexist in the same repo until Fase 8 (Cutover). This plan only ever CREATES new files under `apps/simulacao/`; it never modifies a root-level `.py` file or anything under `tests/`.
- **Real business-rule correction found while planning, not from the spec**: `CLAUDE.md`'s "Key Business Rules" bullet ("Cenário oficial = `cenario_id IS NULL` (baseline)") is stale/incorrect as a general rule — verified by reading `models.py`, `scenarios.py`, `data_loader.py`, and `analise_mineiros.py`: the official scenario is a normal `Cenario` row with `is_oficial=True`, and every child table's `cenario_id` is a real, non-null FK to a `Cenario.id` (including the official one — see e.g. `analise_mineiros.py`'s `Fabrica.cenario_id == oficial.id`). The `cenario_id IS NULL` convention is real but scoped to exactly one table, `LogExecucao`, whose own in-code comment explains it: a `LogExecucao` row's `cenario_id` is `NULL` specifically when that execution ran against the official scenario, "diferente do padrão nas demais tabelas". This plan's Django models follow the verified, actual behavior (real `Cenario` FK everywhere, nullable only on `LogExecucao`), not the stale doc bullet. Task 8 fixes the `CLAUDE.md` bullet itself.
- No task in this plan modifies `pytest.ini`, migrations from the Fundação plan, or any shared config file outside what each task's own file list states — a Critical finding in the Fundação plan (Task 3) came from exactly this kind of unauthorized scope creep.

---

## File Structure

```
apps/simulacao/
  __init__.py                    # already exists (Fundação plan)
  apps.py                        # already exists (Fundação plan)
  migrations/
    __init__.py                  # already exists
    0001_initial.py               # Task 1 — CenarioScopedModel base fields land on first concrete subclass; Cenario, Fabrica, Armazem, Rota
    0002_*.py                     # Task 2 — PrevisaoFabrica, PrevisaoArmazem, SafraUnidade, MovimentacaoDiaria
    0003_*.py                     # Task 3 — LogExecucao, ResumoMensalFabrica, ResumoMensalArmazem
  models.py                       # Task 1 (foundation + 4 models) → Task 2 (append 4) → Task 3 (append 3)
  admin.py                        # Task 1 → Task 2 → Task 3 (append registrations)
  engine.py                       # Task 4 (safra window helpers) → Task 5 (otimizar_dia) → Task 6 (simular_periodo, obter_range_previsoes, JsonFormatter)
  services.py                     # Task 7 (list_scenarios, get_daily_movements, get_monthly_summary) → Task 8 (6 report functions)
  tests/
    __init__.py                   # Task 1
    test_models.py                # Task 1 → Task 2 → Task 3 (append — creation + cooperativa/cenario consistency + cross-tenant isolation per model)
    test_engine_safra.py          # Task 4
    test_engine_otimizar_dia.py   # Task 5
    test_engine_simular_periodo.py # Task 6
    test_services_movements.py    # Task 7
    test_services_reports.py      # Task 8
docs/decisions/
  0005-cenario-scoped-model-consistencia.md   # Task 1
  0006-engine-services-usam-all-cooperativas.md  # Task 4
CLAUDE.md                          # Task 8 — corrects the stale "cenario_id IS NULL" bullet, documents apps.simulacao in the File Map
```

---

### Task 1: `CenarioScopedModel` mixin + `Cenario`, `Fabrica`, `Armazem`, `Rota`

**Files:**
- Create: `apps/simulacao/models.py`, `apps/simulacao/admin.py`
- Create: `apps/simulacao/migrations/0001_initial.py` (generated, not hand-written)
- Create: `apps/simulacao/tests/__init__.py`, `apps/simulacao/tests/test_models.py`
- Create: `docs/decisions/0005-cenario-scoped-model-consistencia.md`

**Interfaces:**
- Consumes: `apps.core.tenancy.CooperativaScopedModel` / `TenantManager` (Fundação plan), `apps.core.models.Cooperativa` (Fundação plan), `apps.core.tenancy.definir_cooperativa_atual`/`resetar_cooperativa_atual` (for the isolation test).
- Produces: `apps.simulacao.models.CenarioScopedModel` (abstract — Tasks 2-3's `SafraUnidade`/`MovimentacaoDiaria`/`ResumoMensalFabrica`/`ResumoMensalArmazem` inherit it), `Cenario`, `Fabrica`, `Armazem`, `Rota`.

- [ ] **Step 1: Write the failing tests**

`apps/simulacao/tests/__init__.py` — empty.

`apps/simulacao/tests/test_models.py`:
```python
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.core.models import Cooperativa
from apps.core.tenancy import definir_cooperativa_atual, resetar_cooperativa_atual
from apps.simulacao.models import Armazem, Cenario, Fabrica, Rota


class CenarioTests(TestCase):
    def setUp(self):
        self.cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')

    def test_criacao_com_campos_minimos(self):
        cenario = Cenario.all_cooperativas.create(cooperativa=self.cooperativa, nome='Cenário Teste')

        self.assertFalse(cenario.is_oficial)
        self.assertIsNotNone(cenario.data_criacao)

    def test_str_retorna_nome(self):
        cenario = Cenario.all_cooperativas.create(cooperativa=self.cooperativa, nome='Cenário Teste')

        self.assertEqual(str(cenario), 'Cenário Teste')


class FabricaTests(TestCase):
    def setUp(self):
        self.cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.cenario = Cenario.all_cooperativas.create(cooperativa=self.cooperativa, nome='Cenário Teste')

    def _fabrica_valida(self, **overrides):
        dados = dict(
            cooperativa=self.cooperativa,
            cenario=self.cenario,
            nome='Fábrica Teste',
            capacidade_estatica=10000,
            capacidade_esmagamento_diaria=500,
            capacidade_recebimento_diaria=600,
            limite_caminhoes=20,
            carga_media_caminhao=30,
            estoque_inicial=1000,
        )
        dados.update(overrides)
        return Fabrica(**dados)

    def test_criacao_com_campos_validos(self):
        fabrica = self._fabrica_valida()
        fabrica.full_clean()
        fabrica.save()

        self.assertEqual(fabrica.cenario_id, self.cenario.id)

    def test_clean_rejeita_cooperativa_diferente_da_do_cenario(self):
        outra_cooperativa = Cooperativa.objects.create(nome='Coop B', slug='coop-b')
        fabrica = self._fabrica_valida(cooperativa=outra_cooperativa)

        with self.assertRaises(ValidationError):
            fabrica.full_clean()


class TenantIsolationRealModelsTests(TestCase):
    """Formal isolation proof against real, concrete models (not the throwaway
    Item from the Fundação plan's test_tenancy.py) -- required by the spec's
    'testes de isolamento de tenant' for this phase."""

    def setUp(self):
        self.coop_a = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.coop_b = Cooperativa.objects.create(nome='Coop B', slug='coop-b')
        self.cenario_a = Cenario.all_cooperativas.create(cooperativa=self.coop_a, nome='Cenário A')
        self.cenario_b = Cenario.all_cooperativas.create(cooperativa=self.coop_b, nome='Cenário B')
        Fabrica.all_cooperativas.create(
            cooperativa=self.coop_a, cenario=self.cenario_a, nome='Fábrica A',
            capacidade_estatica=1, capacidade_esmagamento_diaria=1,
            capacidade_recebimento_diaria=1, limite_caminhoes=1,
            carga_media_caminhao=1, estoque_inicial=0,
        )
        Fabrica.all_cooperativas.create(
            cooperativa=self.coop_b, cenario=self.cenario_b, nome='Fábrica B',
            capacidade_estatica=1, capacidade_esmagamento_diaria=1,
            capacidade_recebimento_diaria=1, limite_caminhoes=1,
            carga_media_caminhao=1, estoque_inicial=0,
        )

    def test_objects_manager_never_leaks_other_cooperativa(self):
        token = definir_cooperativa_atual(self.coop_a.id)
        try:
            nomes = list(Fabrica.objects.values_list('nome', flat=True))
            cenarios = list(Cenario.objects.values_list('nome', flat=True))
        finally:
            resetar_cooperativa_atual(token)

        self.assertEqual(nomes, ['Fábrica A'])
        self.assertEqual(cenarios, ['Cenário A'])

    def test_all_cooperativas_manager_sees_both(self):
        self.assertEqual(Fabrica.all_cooperativas.count(), 2)
        self.assertEqual(Cenario.all_cooperativas.count(), 2)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest apps/simulacao/tests/test_models.py -v`
Expected: FAIL/ERROR with `ModuleNotFoundError: No module named 'apps.simulacao.models'`.

- [ ] **Step 3: Write the models**

`apps/simulacao/models.py`:
```python
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.core.tenancy import CooperativaScopedModel


class CenarioScopedModel(CooperativaScopedModel):
    """Base abstrata para models que pertencem a um Cenario (a maioria do
    domínio de simulação). `cenario` é obrigatório (ao contrário de
    `LogExecucao`, que declara seu próprio FK nullable -- ver ADR 0005).

    `clean()` prova que `cooperativa` e `cenario.cooperativa` nunca divergem
    -- sem essa checagem, nada impede que alguém crie uma Fabrica apontando
    para um Cenario de outra cooperativa (o `TenantManager` só filtra
    leituras; ver ADR 0001 e ADR 0006).
    """

    cenario = models.ForeignKey('simulacao.Cenario', on_delete=models.CASCADE)

    class Meta:
        abstract = True

    def clean(self):
        super().clean()
        if self.cenario_id is not None and self.cenario.cooperativa_id != self.cooperativa_id:
            raise ValidationError(
                'cooperativa não corresponde à cooperativa do cenario.'
            )


class Cenario(CooperativaScopedModel):
    nome = models.CharField(max_length=100, unique=True)
    data_criacao = models.DateTimeField(default=timezone.now)
    is_oficial = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Cenário'
        verbose_name_plural = 'Cenários'
        ordering = ['nome']

    def __str__(self):
        return self.nome


class Fabrica(CenarioScopedModel):
    nome = models.CharField(max_length=100)
    capacidade_estatica = models.FloatField()
    capacidade_esmagamento_diaria = models.FloatField()
    capacidade_recebimento_diaria = models.FloatField()
    limite_caminhoes = models.IntegerField()
    carga_media_caminhao = models.FloatField()
    estoque_inicial = models.FloatField()

    class Meta:
        verbose_name = 'Fábrica'
        verbose_name_plural = 'Fábricas'
        ordering = ['nome']

    def __str__(self):
        return self.nome


class Armazem(CenarioScopedModel):
    nome = models.CharField(max_length=100)
    capacidade_estatica = models.FloatField()
    capacidade_expedicao_diaria = models.FloatField()
    estoque_inicial = models.FloatField()

    class Meta:
        verbose_name = 'Armazém'
        verbose_name_plural = 'Armazéns'
        ordering = ['nome']

    def __str__(self):
        return self.nome


class Rota(CenarioScopedModel):
    armazem = models.ForeignKey(Armazem, on_delete=models.CASCADE, related_name='rotas')
    fabrica = models.ForeignKey(Fabrica, on_delete=models.CASCADE, related_name='rotas')
    distancia_km = models.FloatField()
    custo_frete_ton = models.FloatField()
    custo_frete_entressafra = models.FloatField(default=0)

    class Meta:
        verbose_name = 'Rota'
        verbose_name_plural = 'Rotas'

    def __str__(self):
        return f'{self.armazem} → {self.fabrica}'
```

`apps/simulacao/admin.py`:
```python
from django.contrib import admin

from apps.simulacao.models import Armazem, Cenario, Fabrica, Rota


@admin.register(Cenario)
class CenarioAdmin(admin.ModelAdmin):
    list_display = ('nome', 'cooperativa', 'is_oficial', 'data_criacao')
    list_filter = ('cooperativa', 'is_oficial')


@admin.register(Fabrica)
class FabricaAdmin(admin.ModelAdmin):
    list_display = ('nome', 'cenario', 'cooperativa')
    list_filter = ('cooperativa', 'cenario')


@admin.register(Armazem)
class ArmazemAdmin(admin.ModelAdmin):
    list_display = ('nome', 'cenario', 'cooperativa')
    list_filter = ('cooperativa', 'cenario')


@admin.register(Rota)
class RotaAdmin(admin.ModelAdmin):
    list_display = ('armazem', 'fabrica', 'cenario', 'cooperativa')
    list_filter = ('cooperativa', 'cenario')
```

Run: `python manage.py makemigrations simulacao`
Expected: creates `apps/simulacao/migrations/0001_initial.py`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest apps/simulacao/tests/test_models.py -v`
Expected: PASS (6 passed)

Run: `python manage.py check`
Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 5: Document the decision**

`docs/decisions/0005-cenario-scoped-model-consistencia.md`:
```markdown
# ADR 0005 — CenarioScopedModel: consistência cooperativa/cenario via clean()

- Status: Aceito
- Data: 2026-08-22

## Contexto

`cooperativa_id` é propagado como coluna direta a `Cenario` e a todos os seus descendentes (ADR 0001),
em vez de ser derivado por JOIN via `cenario.cooperativa_id` a cada leitura. Nada no `TenantManager`
(que só filtra leituras — ver ADR 0001/0003) impede que um `cooperativa_id` divergente seja gravado
numa `Fabrica`/`Armazem`/`Rota` cujo `cenario` pertence a outra cooperativa.

## Decisão

- `apps.simulacao.models.CenarioScopedModel` (abstrata, estende `CooperativaScopedModel`) adiciona um
  FK `cenario` obrigatório e um `clean()` que levanta `ValidationError` se
  `self.cenario.cooperativa_id != self.cooperativa_id`.
- Usada por `Fabrica`, `Armazem`, `Rota` (Task 1), `SafraUnidade`, `MovimentacaoDiaria` (Task 2),
  `ResumoMensalFabrica`, `ResumoMensalArmazem` (Task 3) — os 7 models cujo vínculo primário com o
  cenário é um FK direto `cenario`.
- `PrevisaoFabrica`/`PrevisaoArmazem` (Task 2) não têm FK direto a `Cenario` (nunca tiveram, no
  SQLAlchemy original — o vínculo é via `fabrica`/`armazem`), então cada um implementa seu próprio
  `clean()` mais estreito (`self.fabrica.cooperativa_id`/`self.armazem.cooperativa_id`), sem herdar
  este mixin.
- `LogExecucao` (Task 3) não herda este mixin: seu `cenario` é nullable por design (ver o próprio
  comentário no `models.py` original — representa execução contra o cenário oficial), incompatível
  com a obrigatoriedade que `CenarioScopedModel` assume. Declara seu próprio FK nullable e seu próprio
  `clean()` que só valida a consistência quando `cenario` não é `None`.
- `clean()` não é chamado automaticamente por `save()` (convenção já usada por `apps.core.models.User`,
  Fase 5 Fundação) — é responsabilidade do código de escrita (a próxima fase, quando views/forms
  existirem) chamar `full_clean()` antes de `save()`, ou usar `Model.objects.create()` sempre com o
  `cooperativa` derivado do `cenario` já validado.

## Consequências

- Nenhuma proteção em nível de banco (`CheckConstraint`) ainda — `clean()` só pega o erro se o código
  de escrita chamar `full_clean()`. Uma futura fase (quando este código for exercitado por views reais)
  deve avaliar se vale a pena promover para `CheckConstraint`, como já foi feito para
  `User.papel`/`cooperativa` na Fase 5 Fundação (revisão final, finding Important #2).
- `clean()` acessa `self.cenario` (dispara uma query se ainda não estiver em cache) — aceitável, pois
  não é chamado no caminho quente de leitura (`engine.py`/`services.py` nunca chamam `clean()`).
```

- [ ] **Step 6: Commit**

```bash
git add apps/simulacao/models.py apps/simulacao/admin.py apps/simulacao/migrations/0001_initial.py apps/simulacao/tests/ docs/decisions/0005-cenario-scoped-model-consistencia.md
git commit -m "feat(fase5): port Cenario, Fabrica, Armazem, Rota with cooperativa_id"
```

---

### Task 2: `PrevisaoFabrica`, `PrevisaoArmazem`, `SafraUnidade`, `MovimentacaoDiaria`

**Files:**
- Modify: `apps/simulacao/models.py`, `apps/simulacao/admin.py`, `apps/simulacao/tests/test_models.py`
- Create: `apps/simulacao/migrations/0002_*.py` (generated, not hand-written)

**Interfaces:**
- Consumes: `CenarioScopedModel`, `Cenario`, `Fabrica`, `Armazem` (Task 1).
- Produces: `PrevisaoFabrica`, `PrevisaoArmazem`, `SafraUnidade`, `MovimentacaoDiaria` — `engine.py` (Tasks 4-6) queries all four directly.

- [ ] **Step 1: Write the failing tests**

Append to `apps/simulacao/tests/test_models.py`:
```python
import datetime

from apps.simulacao.models import MovimentacaoDiaria, PrevisaoArmazem, PrevisaoFabrica, SafraUnidade


class PrevisaoFabricaTests(TestCase):
    def setUp(self):
        self.cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.cenario = Cenario.all_cooperativas.create(cooperativa=self.cooperativa, nome='Cenário Teste')
        self.fabrica = Fabrica.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, nome='Fábrica Teste',
            capacidade_estatica=1, capacidade_esmagamento_diaria=1,
            capacidade_recebimento_diaria=1, limite_caminhoes=1,
            carga_media_caminhao=1, estoque_inicial=0,
        )

    def test_criacao_com_campos_validos(self):
        previsao = PrevisaoFabrica(
            cooperativa=self.cooperativa, fabrica=self.fabrica,
            mes_referencia=datetime.date(2026, 1, 1),
            recebimento_produtor=100, vendas=50,
        )
        previsao.full_clean()
        previsao.save()

        self.assertEqual(previsao.fabrica_id, self.fabrica.id)

    def test_clean_rejeita_cooperativa_diferente_da_da_fabrica(self):
        outra_cooperativa = Cooperativa.objects.create(nome='Coop B', slug='coop-b')
        previsao = PrevisaoFabrica(
            cooperativa=outra_cooperativa, fabrica=self.fabrica,
            mes_referencia=datetime.date(2026, 1, 1),
        )

        with self.assertRaises(ValidationError):
            previsao.full_clean()


class PrevisaoArmazemTests(TestCase):
    def setUp(self):
        self.cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.cenario = Cenario.all_cooperativas.create(cooperativa=self.cooperativa, nome='Cenário Teste')
        self.armazem = Armazem.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, nome='Armazém Teste',
            capacidade_estatica=1, capacidade_expedicao_diaria=1, estoque_inicial=0,
        )

    def test_criacao_com_campos_validos(self):
        previsao = PrevisaoArmazem(
            cooperativa=self.cooperativa, armazem=self.armazem,
            mes_referencia=datetime.date(2026, 1, 1),
            recebimento_produtor=100, vendas=50,
        )
        previsao.full_clean()
        previsao.save()

        self.assertEqual(previsao.armazem_id, self.armazem.id)

    def test_clean_rejeita_cooperativa_diferente_da_do_armazem(self):
        outra_cooperativa = Cooperativa.objects.create(nome='Coop B', slug='coop-b')
        previsao = PrevisaoArmazem(
            cooperativa=outra_cooperativa, armazem=self.armazem,
            mes_referencia=datetime.date(2026, 1, 1),
        )

        with self.assertRaises(ValidationError):
            previsao.full_clean()


class SafraUnidadeTests(TestCase):
    def setUp(self):
        self.cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.cenario = Cenario.all_cooperativas.create(cooperativa=self.cooperativa, nome='Cenário Teste')

    def test_criacao_com_campos_validos(self):
        safra = SafraUnidade(
            cooperativa=self.cooperativa, cenario=self.cenario,
            entidade_tipo='Armazém', entidade_id=1,
            data_inicio=datetime.date(2026, 2, 1), data_fim=datetime.date(2026, 3, 1),
        )
        safra.full_clean()
        safra.save()

        self.assertEqual(safra.entidade_tipo, 'Armazém')


class MovimentacaoDiariaTests(TestCase):
    def setUp(self):
        self.cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.cenario = Cenario.all_cooperativas.create(cooperativa=self.cooperativa, nome='Cenário Teste')
        self.armazem = Armazem.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, nome='Armazém Teste',
            capacidade_estatica=1, capacidade_expedicao_diaria=1, estoque_inicial=0,
        )
        self.fabrica = Fabrica.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, nome='Fábrica Teste',
            capacidade_estatica=1, capacidade_esmagamento_diaria=1,
            capacidade_recebimento_diaria=1, limite_caminhoes=1,
            carga_media_caminhao=1, estoque_inicial=0,
        )

    def test_criacao_com_campos_validos(self):
        mov = MovimentacaoDiaria(
            cooperativa=self.cooperativa, cenario=self.cenario,
            data=datetime.date(2026, 1, 1), armazem=self.armazem, fabrica=self.fabrica,
            quantidade_ton=10.5, custo_total=210.0,
        )
        mov.full_clean()
        mov.save()

        self.assertEqual(mov.quantidade_ton, 10.5)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest apps/simulacao/tests/test_models.py -v`
Expected: FAIL/ERROR with `ImportError: cannot import name 'MovimentacaoDiaria' from 'apps.simulacao.models'`.

- [ ] **Step 3: Write the models**

Append to `apps/simulacao/models.py`:
```python
class PrevisaoFabrica(CooperativaScopedModel):
    fabrica = models.ForeignKey(Fabrica, on_delete=models.CASCADE, related_name='previsoes')
    mes_referencia = models.DateField()
    recebimento_produtor = models.FloatField(default=0)
    vendas = models.FloatField(default=0)

    class Meta:
        verbose_name = 'Previsão de Fábrica'
        verbose_name_plural = 'Previsões de Fábrica'

    def __str__(self):
        return f'{self.fabrica} — {self.mes_referencia:%Y-%m}'

    def clean(self):
        super().clean()
        if self.fabrica_id is not None and self.fabrica.cooperativa_id != self.cooperativa_id:
            raise ValidationError('cooperativa não corresponde à cooperativa da fabrica.')


class PrevisaoArmazem(CooperativaScopedModel):
    armazem = models.ForeignKey(Armazem, on_delete=models.CASCADE, related_name='previsoes')
    mes_referencia = models.DateField()
    recebimento_produtor = models.FloatField(default=0)
    vendas = models.FloatField(default=0)

    class Meta:
        verbose_name = 'Previsão de Armazém'
        verbose_name_plural = 'Previsões de Armazém'

    def __str__(self):
        return f'{self.armazem} — {self.mes_referencia:%Y-%m}'

    def clean(self):
        super().clean()
        if self.armazem_id is not None and self.armazem.cooperativa_id != self.cooperativa_id:
            raise ValidationError('cooperativa não corresponde à cooperativa do armazem.')


class SafraUnidade(CenarioScopedModel):
    entidade_tipo = models.CharField(max_length=20)
    entidade_id = models.IntegerField()
    data_inicio = models.DateField()
    data_fim = models.DateField()

    class Meta:
        verbose_name = 'Safra da Unidade'
        verbose_name_plural = 'Safras das Unidades'

    def __str__(self):
        return f'{self.entidade_tipo} {self.entidade_id} ({self.data_inicio} a {self.data_fim})'


class MovimentacaoDiaria(CenarioScopedModel):
    data = models.DateField()
    armazem = models.ForeignKey(Armazem, on_delete=models.CASCADE)
    fabrica = models.ForeignKey(Fabrica, on_delete=models.CASCADE)
    quantidade_ton = models.FloatField()
    custo_total = models.FloatField()

    class Meta:
        verbose_name = 'Movimentação Diária'
        verbose_name_plural = 'Movimentações Diárias'
        ordering = ['data']

    def __str__(self):
        return f'{self.data} {self.armazem} → {self.fabrica}: {self.quantidade_ton}t'
```

Append to `apps/simulacao/admin.py`:
```python
from apps.simulacao.models import MovimentacaoDiaria, PrevisaoArmazem, PrevisaoFabrica, SafraUnidade


@admin.register(PrevisaoFabrica)
class PrevisaoFabricaAdmin(admin.ModelAdmin):
    list_display = ('fabrica', 'mes_referencia', 'cooperativa')
    list_filter = ('cooperativa',)


@admin.register(PrevisaoArmazem)
class PrevisaoArmazemAdmin(admin.ModelAdmin):
    list_display = ('armazem', 'mes_referencia', 'cooperativa')
    list_filter = ('cooperativa',)


@admin.register(SafraUnidade)
class SafraUnidadeAdmin(admin.ModelAdmin):
    list_display = ('entidade_tipo', 'entidade_id', 'data_inicio', 'data_fim', 'cooperativa')
    list_filter = ('cooperativa', 'entidade_tipo')


@admin.register(MovimentacaoDiaria)
class MovimentacaoDiariaAdmin(admin.ModelAdmin):
    list_display = ('data', 'armazem', 'fabrica', 'quantidade_ton', 'cooperativa')
    list_filter = ('cooperativa', 'cenario')
```

Run: `python manage.py makemigrations simulacao`
Expected: creates `apps/simulacao/migrations/0002_*.py`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest apps/simulacao/tests/test_models.py -v`
Expected: PASS (13 passed)

- [ ] **Step 5: Commit**

```bash
git add apps/simulacao/models.py apps/simulacao/admin.py apps/simulacao/migrations/0002_*.py apps/simulacao/tests/test_models.py
git commit -m "feat(fase5): port PrevisaoFabrica, PrevisaoArmazem, SafraUnidade, MovimentacaoDiaria"
```

---

### Task 3: `LogExecucao`, `ResumoMensalFabrica`, `ResumoMensalArmazem`

**Files:**
- Modify: `apps/simulacao/models.py`, `apps/simulacao/admin.py`, `apps/simulacao/tests/test_models.py`
- Create: `apps/simulacao/migrations/0003_*.py` (generated, not hand-written)

**Interfaces:**
- Consumes: `CooperativaScopedModel`, `CenarioScopedModel`, `Cenario`, `Fabrica`, `Armazem` (Tasks 1-2).
- Produces: `LogExecucao`, `ResumoMensalFabrica`, `ResumoMensalArmazem` — `engine.py` (Task 6) writes all three.

- [ ] **Step 1: Write the failing tests**

Append to `apps/simulacao/tests/test_models.py`:
```python
from apps.simulacao.models import LogExecucao, ResumoMensalArmazem, ResumoMensalFabrica


class LogExecucaoTests(TestCase):
    def setUp(self):
        self.cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.cenario = Cenario.all_cooperativas.create(cooperativa=self.cooperativa, nome='Cenário Teste')

    def test_criacao_com_cenario(self):
        log = LogExecucao(
            cooperativa=self.cooperativa, cenario=self.cenario,
            status='sucesso', mensagem='ok', duracao_segundos=1.5, dias_simulados=7,
        )
        log.full_clean()
        log.save()

        self.assertEqual(log.cenario_id, self.cenario.id)

    def test_criacao_sem_cenario_e_valida(self):
        """cenario=None representa execução contra o cenário oficial (ver ADR 0005)."""
        log = LogExecucao(
            cooperativa=self.cooperativa, cenario=None,
            status='sucesso', mensagem='ok', duracao_segundos=1.5, dias_simulados=7,
        )
        log.full_clean()
        log.save()

        self.assertIsNone(log.cenario_id)

    def test_clean_rejeita_cooperativa_diferente_da_do_cenario_quando_presente(self):
        outra_cooperativa = Cooperativa.objects.create(nome='Coop B', slug='coop-b')
        log = LogExecucao(cooperativa=outra_cooperativa, cenario=self.cenario, status='sucesso')

        with self.assertRaises(ValidationError):
            log.full_clean()


class ResumoMensalFabricaTests(TestCase):
    def setUp(self):
        self.cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.cenario = Cenario.all_cooperativas.create(cooperativa=self.cooperativa, nome='Cenário Teste')
        self.fabrica = Fabrica.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, nome='Fábrica Teste',
            capacidade_estatica=1, capacidade_esmagamento_diaria=1,
            capacidade_recebimento_diaria=1, limite_caminhoes=1,
            carga_media_caminhao=1, estoque_inicial=0,
        )

    def test_criacao_com_campos_validos(self):
        resumo = ResumoMensalFabrica(
            cooperativa=self.cooperativa, cenario=self.cenario, mes='2026-01', fabrica=self.fabrica,
        )
        resumo.full_clean()
        resumo.save()

        self.assertEqual(resumo.rec_produtor, 0)


class ResumoMensalArmazemTests(TestCase):
    def setUp(self):
        self.cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.cenario = Cenario.all_cooperativas.create(cooperativa=self.cooperativa, nome='Cenário Teste')
        self.armazem = Armazem.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, nome='Armazém Teste',
            capacidade_estatica=1, capacidade_expedicao_diaria=1, estoque_inicial=0,
        )

    def test_criacao_com_campos_validos(self):
        resumo = ResumoMensalArmazem(
            cooperativa=self.cooperativa, cenario=self.cenario, mes='2026-01', armazem=self.armazem,
        )
        resumo.full_clean()
        resumo.save()

        self.assertEqual(resumo.rec_produtor, 0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest apps/simulacao/tests/test_models.py -v`
Expected: FAIL/ERROR with `ImportError: cannot import name 'LogExecucao' from 'apps.simulacao.models'`.

- [ ] **Step 3: Write the models**

Append to `apps/simulacao/models.py`:
```python
class LogExecucao(CooperativaScopedModel):
    """`cenario` é nullable de propósito -- diferente de `CenarioScopedModel`
    (não herda dele). NULL representa uma execução rodada contra o cenário
    oficial. Ver ADR 0005."""

    cenario = models.ForeignKey(Cenario, on_delete=models.CASCADE, null=True, blank=True)
    data_execucao = models.DateTimeField(default=timezone.now)
    status = models.CharField(max_length=50, blank=True, default='')
    mensagem = models.CharField(max_length=500, blank=True, default='')
    duracao_segundos = models.FloatField(null=True, blank=True)
    dias_simulados = models.IntegerField(null=True, blank=True)

    class Meta:
        verbose_name = 'Log de Execução'
        verbose_name_plural = 'Logs de Execução'
        ordering = ['-data_execucao']

    def __str__(self):
        return f'{self.data_execucao:%Y-%m-%d %H:%M} — {self.status}'

    def clean(self):
        super().clean()
        if self.cenario_id is not None and self.cenario.cooperativa_id != self.cooperativa_id:
            raise ValidationError('cooperativa não corresponde à cooperativa do cenario.')


class ResumoMensalFabrica(CenarioScopedModel):
    mes = models.CharField(max_length=7)  # 'YYYY-MM'
    fabrica = models.ForeignKey(Fabrica, on_delete=models.CASCADE)
    rec_produtor = models.FloatField(default=0)
    rec_transbordo = models.FloatField(default=0)
    esmagado = models.FloatField(default=0)
    saldo_estoque = models.FloatField(default=0)
    capacidade_estatica = models.FloatField(default=0)
    excedente = models.FloatField(default=0)

    class Meta:
        verbose_name = 'Resumo Mensal de Fábrica'
        verbose_name_plural = 'Resumos Mensais de Fábrica'

    def __str__(self):
        return f'{self.fabrica} — {self.mes}'


class ResumoMensalArmazem(CenarioScopedModel):
    mes = models.CharField(max_length=7)  # 'YYYY-MM'
    armazem = models.ForeignKey(Armazem, on_delete=models.CASCADE)
    rec_produtor = models.FloatField(default=0)
    envio_transbordo = models.FloatField(default=0)
    vendas = models.FloatField(default=0)
    saldo_estoque = models.FloatField(default=0)
    capacidade_estatica = models.FloatField(default=0)
    excedente = models.FloatField(default=0)

    class Meta:
        verbose_name = 'Resumo Mensal de Armazém'
        verbose_name_plural = 'Resumos Mensais de Armazém'

    def __str__(self):
        return f'{self.armazem} — {self.mes}'
```

Append to `apps/simulacao/admin.py`:
```python
from apps.simulacao.models import LogExecucao, ResumoMensalArmazem, ResumoMensalFabrica


@admin.register(LogExecucao)
class LogExecucaoAdmin(admin.ModelAdmin):
    list_display = ('data_execucao', 'status', 'cenario', 'dias_simulados', 'cooperativa')
    list_filter = ('cooperativa', 'status')


@admin.register(ResumoMensalFabrica)
class ResumoMensalFabricaAdmin(admin.ModelAdmin):
    list_display = ('mes', 'fabrica', 'saldo_estoque', 'cooperativa')
    list_filter = ('cooperativa', 'cenario')


@admin.register(ResumoMensalArmazem)
class ResumoMensalArmazemAdmin(admin.ModelAdmin):
    list_display = ('mes', 'armazem', 'saldo_estoque', 'cooperativa')
    list_filter = ('cooperativa', 'cenario')
```

Run: `python manage.py makemigrations simulacao`
Expected: creates `apps/simulacao/migrations/0003_*.py`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest apps/simulacao/tests/test_models.py -v`
Expected: PASS (18 passed)

Run: `python manage.py check` and `python manage.py makemigrations --check --dry-run`
Expected: both clean.

- [ ] **Step 5: Commit**

```bash
git add apps/simulacao/models.py apps/simulacao/admin.py apps/simulacao/migrations/0003_*.py apps/simulacao/tests/test_models.py
git commit -m "feat(fase5): port LogExecucao, ResumoMensalFabrica, ResumoMensalArmazem"
```

---

### Task 4: `engine.py` — safra window helpers

**Files:**
- Create: `apps/simulacao/engine.py`
- Create: `apps/simulacao/tests/test_engine_safra.py`
- Create: `docs/decisions/0006-engine-services-usam-all-cooperativas.md`

**Interfaces:**
- Consumes: `SafraUnidade` (Task 2).
- Produces: `apps.simulacao.engine._janela_safra_de_registro(safra, data)`, `apps.simulacao.engine.obter_janela_safra(entidade_tipo, entidade_id, data, cenario_id)`, `apps.simulacao.engine._carregar_safras_por_armazem(cenario_id)` — all three consumed by Task 5's `otimizar_dia`. **Signature change from the SQLAlchemy source**: no `session` parameter (Django has no session object) — every other parameter name/order is unchanged.

- [ ] **Step 1: Write the failing tests**

`apps/simulacao/tests/test_engine_safra.py`:
```python
import datetime

from django.test import TestCase

from apps.core.models import Cooperativa
from apps.simulacao import engine
from apps.simulacao.models import Armazem, Cenario, SafraUnidade


class JanelaSafraDeRegistroTests(TestCase):
    def test_sem_registro_fallback_varia_por_ano(self):
        na_safra_2026, ini_2026, fim_2026 = engine._janela_safra_de_registro(None, datetime.date(2026, 2, 1))
        na_safra_2027, ini_2027, fim_2027 = engine._janela_safra_de_registro(None, datetime.date(2027, 2, 1))

        self.assertEqual((ini_2026, fim_2026), (datetime.date(2026, 1, 15), datetime.date(2026, 4, 15)))
        self.assertEqual((ini_2027, fim_2027), (datetime.date(2027, 1, 15), datetime.date(2027, 4, 15)))
        self.assertTrue(na_safra_2026)
        self.assertTrue(na_safra_2027)

    def test_com_registro_usa_datas_do_registro(self):
        cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        cenario = Cenario.all_cooperativas.create(cooperativa=cooperativa, nome='Cenário Teste')
        safra = SafraUnidade.all_cooperativas.create(
            cooperativa=cooperativa, cenario=cenario, entidade_tipo='Armazém', entidade_id=1,
            data_inicio=datetime.date(2026, 2, 1), data_fim=datetime.date(2026, 3, 1),
        )

        na_safra, ini, fim = engine._janela_safra_de_registro(safra, datetime.date(2026, 2, 15))

        self.assertTrue(na_safra)
        self.assertEqual((ini, fim), (datetime.date(2026, 2, 1), datetime.date(2026, 3, 1)))


class ObterJanelaSafraTests(TestCase):
    def setUp(self):
        self.cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.cenario = Cenario.all_cooperativas.create(cooperativa=self.cooperativa, nome='Cenário Teste')
        self.armazem = Armazem.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, nome='Armazém Teste',
            capacidade_estatica=1, capacidade_expedicao_diaria=1, estoque_inicial=0,
        )

    def test_com_registro_data_dentro(self):
        SafraUnidade.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, entidade_tipo='Armazém',
            entidade_id=self.armazem.id,
            data_inicio=datetime.date(2026, 2, 1), data_fim=datetime.date(2026, 3, 1),
        )

        na_safra, d_ini, d_fim = engine.obter_janela_safra(
            'Armazém', self.armazem.id, datetime.date(2026, 2, 15), self.cenario.id
        )

        self.assertTrue(na_safra)
        self.assertEqual((d_ini, d_fim), (datetime.date(2026, 2, 1), datetime.date(2026, 3, 1)))

    def test_com_registro_data_fora(self):
        SafraUnidade.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, entidade_tipo='Armazém',
            entidade_id=self.armazem.id,
            data_inicio=datetime.date(2026, 2, 1), data_fim=datetime.date(2026, 3, 1),
        )

        na_safra, d_ini, d_fim = engine.obter_janela_safra(
            'Armazém', self.armazem.id, datetime.date(2026, 3, 15), self.cenario.id
        )

        self.assertFalse(na_safra)
        self.assertEqual((d_ini, d_fim), (datetime.date(2026, 2, 1), datetime.date(2026, 3, 1)))

    def test_sem_registro_usa_padrao_15jan_15abr(self):
        na_safra_dentro, d_ini, d_fim = engine.obter_janela_safra(
            'Armazém', self.armazem.id, datetime.date(2026, 2, 1), self.cenario.id
        )
        self.assertEqual((d_ini, d_fim), (datetime.date(2026, 1, 15), datetime.date(2026, 4, 15)))
        self.assertTrue(na_safra_dentro)

        na_safra_fora, d_ini2, d_fim2 = engine.obter_janela_safra(
            'Armazém', self.armazem.id, datetime.date(2026, 5, 1), self.cenario.id
        )
        self.assertEqual((d_ini2, d_fim2), (datetime.date(2026, 1, 15), datetime.date(2026, 4, 15)))
        self.assertFalse(na_safra_fora)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest apps/simulacao/tests/test_engine_safra.py -v`
Expected: FAIL/ERROR with `ModuleNotFoundError: No module named 'apps.simulacao.engine'`.

- [ ] **Step 3: Write the engine module (part 1)**

`apps/simulacao/engine.py`:
```python
import datetime
import json
import logging

from apps.simulacao.models import SafraUnidade

# Ver ADR 0006: engine.py e services.py consultam via `all_cooperativas`
# (nunca `objects`, o TenantManager fail-closed) porque recebem o limite de
# tenant explicitamente via `cenario_id`/`scenario_id` -- exatamente como o
# codigo SQLAlchemy original ja funcionava, sem nocao de "cooperativa da
# sessao corrente". Confiar no contexto implicito de middleware aqui
# quebraria silenciosamente (queryset vazio) toda chamada feita fora de uma
# requisicao HTTP -- um worker Procrastinate futuro, um management command,
# ou os proprios testes deste arquivo.

_RESERVED_LOG_RECORD_ATTRS = frozenset({
    'name', 'msg', 'args', 'levelname', 'levelno', 'pathname', 'filename',
    'module', 'exc_info', 'exc_text', 'stack_info', 'lineno', 'funcName',
    'created', 'msecs', 'relativeCreated', 'thread', 'threadName',
    'processName', 'process', 'taskName', 'message',
})


class JsonFormatter(logging.Formatter):
    """Formatter de logging que emite um objeto JSON por linha (structured
    logging). Porte 1:1 de `calculations.JsonFormatter` -- pura lógica de
    logging, sem dependência de ORM."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            'timestamp': self.formatTime(record, self.datefmt),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
        }

        for key, value in record.__dict__.items():
            if key not in _RESERVED_LOG_RECORD_ATTRS:
                payload[key] = value

        if record.exc_info:
            payload['exc_info'] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str, ensure_ascii=False)


_handler = logging.StreamHandler()
_handler.setFormatter(JsonFormatter())
logger = logging.getLogger(__name__)
logger.addHandler(_handler)
logger.setLevel(logging.INFO)
logger.propagate = False


def _janela_safra_de_registro(safra, data):
    """Versão pura de `obter_janela_safra`: recebe o registro SafraUnidade já
    buscado (ou None) e resolve (na_safra, data_inicio, data_fim) sem tocar
    o banco. Porte 1:1 de `calculations._janela_safra_de_registro`."""
    if safra:
        data_inicio, data_fim = safra.data_inicio, safra.data_fim
    else:
        ano = data.year
        data_inicio = datetime.date(ano, 1, 15)
        data_fim = datetime.date(ano, 4, 15)

    na_safra = data_inicio <= data <= data_fim
    return na_safra, data_inicio, data_fim


def obter_janela_safra(entidade_tipo, entidade_id, data, cenario_id):
    """Determina a janela de safra de uma unidade e se `data` está dentro
    dela. Porte de `calculations.obter_janela_safra` -- assinatura igual,
    menos o parâmetro `session` (Django não tem sessão)."""
    safra = SafraUnidade.all_cooperativas.filter(
        cenario_id=cenario_id,
        entidade_tipo=entidade_tipo,
        entidade_id=entidade_id,
    ).first()
    return _janela_safra_de_registro(safra, data)


def _carregar_safras_por_armazem(cenario_id):
    """Pré-carrega todos os SafraUnidade de armazéns do cenário, indexados
    por armazem_id. Porte de `calculations._carregar_safras_por_armazem`."""
    rows = SafraUnidade.all_cooperativas.filter(
        cenario_id=cenario_id,
        entidade_tipo='Armazém',
    )
    return {r.entidade_id: r for r in rows}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest apps/simulacao/tests/test_engine_safra.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Document the all_cooperativas decision**

`docs/decisions/0006-engine-services-usam-all-cooperativas.md`:
```markdown
# ADR 0006 — engine.py e services.py consultam via all_cooperativas, não objects

- Status: Aceito
- Data: 2026-08-22

## Contexto

`apps.simulacao.engine`/`apps.simulacao.services` são o porte 1:1 de `calculations.py`/
`logistics_services.py`: funções de domínio que recebem `cenario_id`/`scenario_id` como parâmetro
explícito. O código SQLAlchemy original nunca teve noção de "cooperativa da sessão corrente" —
o único limite de tenant sempre foi o `cenario_id` passado pelo chamador.

## Decisão

- Toda query em `engine.py`/`services.py` usa `Model.all_cooperativas` (manager sem escopo, ADR 0001/
  0003), nunca `Model.objects` (o `TenantManager` fail-closed, que depende de
  `CooperativaScopeMiddleware` ter rodado numa requisição HTTP).
- Justificativa: estas funções precisam funcionar corretamente quando chamadas fora de uma requisição
  HTTP — um worker Procrastinate (Fase 5, próxima etapa do roteiro), um management command, ou os
  próprios testes automatizados deste módulo. Depender do contexto implícito de middleware aqui faria
  qualquer uma dessas chamadas falhar silenciosamente (queryset vazio, não um erro) assim que alguém
  esquecesse de também chamar `definir_cooperativa_atual()` manualmente — pior que exigir o
  `cenario_id`/`scenario_id` explícito que o chamador já precisa fornecer de qualquer forma.
- O uso de `all_cooperativas` aqui é exatamente o caso de "consulta cross-tenant deliberada" que a
  ADR 0003 já previu como uso legítimo do escape hatch — a autorização (o usuário pode ver este
  `cenario_id`?) é responsabilidade de quem CHAMA `engine.py`/`services.py` (a próxima fase, quando
  views/Django Ninja existirem), não destas funções de domínio puro.

## Consequências

- `engine.py`/`services.py` não têm proteção própria contra um `cenario_id` de outra cooperativa sendo
  passado por engano — confiam inteiramente no chamador. Isso é aceitável para funções de domínio
  interno (não expostas diretamente a input de usuário sem uma camada de autorização na frente), mas
  a próxima fase (views/Django Ninja) precisa validar `cenario.cooperativa_id == request.user.cooperativa_id`
  antes de repassar um `cenario_id` vindo de fora para estas funções.
```

- [ ] **Step 6: Commit**

```bash
git add apps/simulacao/engine.py apps/simulacao/tests/test_engine_safra.py docs/decisions/0006-engine-services-usam-all-cooperativas.md
git commit -m "feat(fase5): port safra window helpers to engine.py"
```

---

### Task 5: `engine.py` — `otimizar_dia`

**Files:**
- Modify: `apps/simulacao/engine.py`
- Create: `apps/simulacao/tests/test_engine_otimizar_dia.py`

**Interfaces:**
- Consumes: `Fabrica`, `Armazem`, `Rota` (Task 1), `_janela_safra_de_registro`, `obter_janela_safra` (Task 4).
- Produces: `apps.simulacao.engine.otimizar_dia(data, estoques_atuais, estrategia='Econômico', cenario_id=None, fabricas=None, armazens=None, rotas=None, safra_cache=None) -> list[dict] | None` — consumed by Task 6's `simular_periodo`. **Signature change**: no `session` parameter.

- [ ] **Step 1: Write the failing tests**

`apps/simulacao/tests/test_engine_otimizar_dia.py`:
```python
import datetime
import logging

from django.test import TestCase
from ortools.linear_solver import pywraplp

from apps.core.models import Cooperativa
from apps.simulacao import engine
from apps.simulacao.models import Armazem, Cenario, Fabrica, Rota, SafraUnidade


class OtimizarDiaFixtureMixin:
    def setUp(self):
        self.cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.cenario = Cenario.all_cooperativas.create(cooperativa=self.cooperativa, nome='Cenário Teste')
        self.armazem = Armazem.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, nome='Armazém Teste',
            capacidade_estatica=5000, capacidade_expedicao_diaria=300, estoque_inicial=2000,
        )
        self.fabrica = Fabrica.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, nome='Fábrica Teste',
            capacidade_estatica=10000, capacidade_esmagamento_diaria=500,
            capacidade_recebimento_diaria=600, limite_caminhoes=20,
            carga_media_caminhao=30, estoque_inicial=1000,
        )
        self.rota = Rota.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario,
            armazem=self.armazem, fabrica=self.fabrica,
            distancia_km=50, custo_frete_ton=20.0, custo_frete_entressafra=15.0,
        )


class OtimizarDiaSolverTests(OtimizarDiaFixtureMixin, TestCase):
    def test_raises_when_no_solver_available(self):
        original_create_solver = pywraplp.Solver.CreateSolver
        pywraplp.Solver.CreateSolver = staticmethod(lambda *_args, **_kwargs: None)
        try:
            with self.assertRaises(RuntimeError):
                engine.otimizar_dia(
                    data=datetime.date(2026, 2, 1),
                    estoques_atuais={f'F_{self.fabrica.id}': 0, f'A_{self.armazem.id}': 1000},
                    cenario_id=self.cenario.id,
                )
        finally:
            pywraplp.Solver.CreateSolver = original_create_solver

    def test_logs_warning_when_status_not_optimal(self):
        original_solve = pywraplp.Solver.Solve
        pywraplp.Solver.Solve = lambda self: pywraplp.Solver.INFEASIBLE
        try:
            with self.assertLogs('apps.simulacao.engine', level='WARNING') as captured:
                resultado = engine.otimizar_dia(
                    data=datetime.date(2026, 2, 1),
                    estoques_atuais={f'F_{self.fabrica.id}': 0, f'A_{self.armazem.id}': 1000},
                    cenario_id=self.cenario.id,
                )
        finally:
            pywraplp.Solver.Solve = original_solve

        self.assertIsNone(resultado)
        self.assertTrue(any(record.levelno == logging.WARNING for record in captured.records))


class OtimizarDiaSafraTests(OtimizarDiaFixtureMixin, TestCase):
    def test_usa_custo_de_safra_quando_data_esta_na_janela(self):
        SafraUnidade.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, entidade_tipo='Armazém',
            entidade_id=self.armazem.id,
            data_inicio=datetime.date(2026, 2, 1), data_fim=datetime.date(2026, 3, 1),
        )

        resultados = engine.otimizar_dia(
            data=datetime.date(2026, 2, 15),
            estoques_atuais={f'A_{self.armazem.id}': 2000, f'F_{self.fabrica.id}': 0},
            cenario_id=self.cenario.id,
        )

        self.assertTrue(resultados)
        mov = resultados[0]
        self.assertEqual(mov['armazem_id'], self.armazem.id)
        self.assertEqual(mov['fabrica_id'], self.fabrica.id)
        self.assertEqual(mov['custo_total'], mov['quantidade_ton'] * self.rota.custo_frete_ton)

    def test_usa_custo_de_entressafra_quando_data_fora_da_janela(self):
        SafraUnidade.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, entidade_tipo='Armazém',
            entidade_id=self.armazem.id,
            data_inicio=datetime.date(2026, 2, 1), data_fim=datetime.date(2026, 3, 1),
        )

        resultados = engine.otimizar_dia(
            data=datetime.date(2026, 3, 15),
            estoques_atuais={f'A_{self.armazem.id}': 2000, f'F_{self.fabrica.id}': 0},
            cenario_id=self.cenario.id,
        )

        self.assertTrue(resultados)
        mov = resultados[0]
        self.assertEqual(mov['custo_total'], mov['quantidade_ton'] * self.rota.custo_frete_entressafra)


class OtimizarDiaPreCarregamentoTests(OtimizarDiaFixtureMixin, TestCase):
    def test_nao_consulta_banco_quando_dados_pre_carregados(self):
        from django.test.utils import CaptureQueriesContext
        from django.db import connection

        estoques = {f'F_{self.fabrica.id}': 0, f'A_{self.armazem.id}': 5000}

        with CaptureQueriesContext(connection) as ctx:
            engine.otimizar_dia(
                data=datetime.date(2026, 2, 1), estoques_atuais=estoques, cenario_id=self.cenario.id,
                fabricas=[self.fabrica], armazens=[self.armazem], rotas=[self.rota], safra_cache={},
            )

        self.assertEqual(len(ctx.captured_queries), 0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest apps/simulacao/tests/test_engine_otimizar_dia.py -v`
Expected: FAIL/ERROR with `AttributeError: module 'apps.simulacao.engine' has no attribute 'otimizar_dia'`.

- [ ] **Step 3: Write `otimizar_dia`**

Append to `apps/simulacao/engine.py` (add these imports at the top of the file, alongside the existing ones):
```python
from ortools.linear_solver import pywraplp

from apps.simulacao.models import Armazem, Fabrica, Rota
```

Then append the function itself:
```python
def otimizar_dia(data, estoques_atuais, estrategia='Econômico', cenario_id=None,
                  fabricas=None, armazens=None, rotas=None, safra_cache=None):
    """Otimiza a movimentação de soja para um dia específico. Porte 1:1 de
    `calculations.otimizar_dia` -- lógica do solver inalterada, só a camada
    de acesso a dados trocou de `session.query` para `Model.all_cooperativas`
    (ver ADR 0006). Assinatura igual, menos o parâmetro `session`."""
    solver = pywraplp.Solver.CreateSolver('SCIP')
    if not solver:
        solver = pywraplp.Solver.CreateSolver('GLOP')

    if not solver:
        logger.error("Nenhum solver (SCIP ou GLOP) disponível no OR-Tools.")
        raise RuntimeError("Nenhum solver OR-Tools disponivel (SCIP ou GLOP).")

    if fabricas is None:
        fabricas = list(Fabrica.all_cooperativas.filter(cenario_id=cenario_id))
    if armazens is None:
        armazens = list(Armazem.all_cooperativas.filter(cenario_id=cenario_id))
    if rotas is None:
        rotas = list(Rota.all_cooperativas.filter(cenario_id=cenario_id))

    if not rotas:
        return []

    v_mov = {}
    for r in rotas:
        v_mov[(r.armazem_id, r.fabrica_id)] = solver.NumVar(0, solver.infinity(), f'mov_{r.armazem_id}_{r.fabrica_id}')

    for a in armazens:
        movs_saindo = [v_mov[(a.id, f.id)] for f in fabricas if (a.id, f.id) in v_mov]
        if movs_saindo:
            solver.Add(solver.Sum(movs_saindo) <= a.capacidade_expedicao_diaria)
            solver.Add(solver.Sum(movs_saindo) <= max(0, estoques_atuais.get(f'A_{a.id}', 0)))

    for f in fabricas:
        movs_entrando = [v_mov[(a.id, f.id)] for a in armazens if (a.id, f.id) in v_mov]
        if not movs_entrando:
            continue

        recebimento_transbordo = solver.Sum(movs_entrando)
        solver.Add(recebimento_transbordo <= f.capacidade_recebimento_diaria)
        solver.Add(recebimento_transbordo <= f.limite_caminhoes * f.carga_media_caminhao)

    v_atendimento = {}
    for f in fabricas:
        demanda = max(0, f.capacidade_esmagamento_diaria - max(0, estoques_atuais.get(f'F_{f.id}', 0)))
        if demanda > 0:
            v_atendimento[f.id] = solver.NumVar(0, demanda, f'atend_{f.id}')
            movs_entrando = [v_mov[(a.id, f.id)] for a in armazens if (a.id, f.id) in v_mov]
            if movs_entrando:
                solver.Add(solver.Sum(movs_entrando) >= v_atendimento[f.id])

    p_atendimento = 10000000
    recompensa_base = 10000
    if estrategia == 'Econômico':
        recompensa_base = 100
    elif estrategia == 'Expedição':
        recompensa_base = 50000
    elif estrategia == 'Segurança':
        p_atendimento = 50000000

    objetivo = solver.Objective()
    for var in v_atendimento.values():
        objetivo.SetCoefficient(var, p_atendimento)

    for r in rotas:
        if safra_cache is not None:
            na_safra, d_ini, d_fim = _janela_safra_de_registro(safra_cache.get(r.armazem_id), data)
        else:
            na_safra, d_ini, _d_fim = obter_janela_safra('Armazém', r.armazem_id, data, cenario_id)

        if data < d_ini:
            solver.Add(v_mov[(r.armazem_id, r.fabrica_id)] == 0)
            continue

        custo_ton = r.custo_frete_ton if na_safra else r.custo_frete_entressafra
        incentivo_movimentar = recompensa_base + (1000 if na_safra else 0)
        objetivo.SetCoefficient(v_mov[(r.armazem_id, r.fabrica_id)], incentivo_movimentar - custo_ton)

    objetivo.SetMaximization()
    status = solver.Solve()

    if status == pywraplp.Solver.OPTIMAL or status == pywraplp.Solver.FEASIBLE:
        resultados = []
        for r in rotas:
            qtd = v_mov[(r.armazem_id, r.fabrica_id)].solution_value()
            if qtd > 0.001:
                if safra_cache is not None:
                    na_safra_real, _, _ = _janela_safra_de_registro(safra_cache.get(r.armazem_id), data)
                else:
                    na_safra_real, _, _ = obter_janela_safra('Armazém', r.armazem_id, data, cenario_id)
                custo_ton_real = r.custo_frete_ton if na_safra_real else r.custo_frete_entressafra

                resultados.append({
                    'armazem_id': r.armazem_id,
                    'fabrica_id': r.fabrica_id,
                    'quantidade_ton': qtd,
                    'custo_total': qtd * custo_ton_real,
                })
        return resultados

    logger.warning(
        "Otimização do dia %s (cenario_id=%s) não encontrou solução ótima/viável (status=%s).",
        data, cenario_id, status
    )
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest apps/simulacao/tests/test_engine_otimizar_dia.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add apps/simulacao/engine.py apps/simulacao/tests/test_engine_otimizar_dia.py
git commit -m "feat(fase5): port otimizar_dia to engine.py"
```

---

### Task 6: `engine.py` — `simular_periodo`, `obter_range_previsoes`

**Files:**
- Modify: `apps/simulacao/engine.py`
- Create: `apps/simulacao/tests/test_engine_simular_periodo.py`

**Interfaces:**
- Consumes: `Fabrica`, `Armazem`, `Rota`, `PrevisaoFabrica`, `PrevisaoArmazem`, `MovimentacaoDiaria`, `ResumoMensalFabrica`, `ResumoMensalArmazem`, `LogExecucao`, `Cenario` (Tasks 1-3), `otimizar_dia`, `_carregar_safras_por_armazem` (Tasks 4-5).
- Produces: `apps.simulacao.engine.simular_periodo(data_inicio, data_fim_previsao, cenario_id=None, estrategia='Econômico') -> None`, `apps.simulacao.engine.obter_range_previsoes(cenario_id=None) -> tuple[date | None, date | None]`. **Signature change**: no `session` parameter on either.

- [ ] **Step 1: Write the failing tests**

`apps/simulacao/tests/test_engine_simular_periodo.py`:
```python
import datetime

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from apps.core.models import Cooperativa
from apps.simulacao import engine
from apps.simulacao.models import (
    Armazem,
    Cenario,
    Fabrica,
    LogExecucao,
    MovimentacaoDiaria,
    PrevisaoArmazem,
    PrevisaoFabrica,
    ResumoMensalFabrica,
    Rota,
)


def _montar_cenario_zerado(cooperativa, cenario):
    fabrica = Fabrica.all_cooperativas.create(
        cooperativa=cooperativa, cenario=cenario, nome='Fábrica 1',
        capacidade_estatica=100000, capacidade_esmagamento_diaria=1000,
        capacidade_recebimento_diaria=1000, limite_caminhoes=50,
        carga_media_caminhao=30, estoque_inicial=0,
    )
    armazem = Armazem.all_cooperativas.create(
        cooperativa=cooperativa, cenario=cenario, nome='Armazém 1',
        capacidade_estatica=50000, capacidade_expedicao_diaria=1000, estoque_inicial=0,
    )
    rota = Rota.all_cooperativas.create(
        cooperativa=cooperativa, cenario=cenario, armazem=armazem, fabrica=fabrica,
        distancia_km=10, custo_frete_ton=5.0, custo_frete_entressafra=8.0,
    )
    return fabrica, armazem, rota


class SimularPeriodoAtomicidadeTests(TestCase):
    def setUp(self):
        self.cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.cenario = Cenario.all_cooperativas.create(cooperativa=self.cooperativa, nome='Cenário Teste')
        self.fabrica, self.armazem, self.rota = _montar_cenario_zerado(self.cooperativa, self.cenario)

    def test_nao_perde_dados_em_falha_no_meio_do_loop(self):
        mov_existente = MovimentacaoDiaria.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario,
            data=datetime.date(2026, 1, 20), armazem=self.armazem, fabrica=self.fabrica,
            quantidade_ton=123.45, custo_total=999.99,
        )
        self.assertEqual(
            MovimentacaoDiaria.all_cooperativas.filter(cenario_id=self.cenario.id).count(), 1
        )

        original_otimizar_dia = engine.otimizar_dia

        def _falha_forcada(*args, **kwargs):
            raise RuntimeError('forced failure')

        engine.otimizar_dia = _falha_forcada
        try:
            with self.assertRaisesMessage(RuntimeError, 'forced failure'):
                engine.simular_periodo(
                    data_inicio=datetime.date(2026, 1, 20),
                    data_fim_previsao=datetime.date(2026, 1, 25),
                    cenario_id=self.cenario.id,
                )
        finally:
            engine.otimizar_dia = original_otimizar_dia

        count_apos_falha = MovimentacaoDiaria.all_cooperativas.filter(cenario_id=self.cenario.id).count()
        self.assertGreaterEqual(count_apos_falha, 1, 'MovimentacaoDiaria anterior foi perdida após falha (bug C1).')

        logs = LogExecucao.all_cooperativas.filter(cenario_id=self.cenario.id).count()
        self.assertEqual(logs, 0, 'Nenhum LogExecucao de sucesso deve sobreviver a uma execução que falhou.')


class SimularPeriodoObservabilidadeTests(TestCase):
    def setUp(self):
        self.cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.cenario = Cenario.all_cooperativas.create(cooperativa=self.cooperativa, nome='Cenário Fase4')
        _montar_cenario_zerado(self.cooperativa, self.cenario)

    def test_sucesso_grava_log_execucao(self):
        dias = 7
        data_inicio = datetime.date(2026, 1, 1)
        data_fim = data_inicio + datetime.timedelta(days=dias - 1)

        engine.simular_periodo(data_inicio, data_fim, cenario_id=self.cenario.id)

        logs = list(LogExecucao.all_cooperativas.filter(cenario_id=self.cenario.id))
        self.assertEqual(len(logs), 1)

        log = logs[0]
        self.assertEqual(log.status, 'sucesso')
        self.assertEqual(log.cenario_id, self.cenario.id)
        self.assertIsNotNone(log.duracao_segundos)
        self.assertGreaterEqual(log.duracao_segundos, 0)
        self.assertEqual(log.dias_simulados, dias)


class SimularPeriodoPerformanceTests(TestCase):
    def _run(self, dias, sufixo):
        cooperativa = Cooperativa.objects.create(nome=f'Coop {sufixo}', slug=f'coop-{sufixo}')
        cenario = Cenario.all_cooperativas.create(cooperativa=cooperativa, nome=f'C{sufixo}')
        _montar_cenario_zerado(cooperativa, cenario)

        data_inicio = datetime.date(2026, 1, 1)
        data_fim = data_inicio + datetime.timedelta(days=dias - 1)

        with CaptureQueriesContext(connection) as ctx:
            engine.simular_periodo(data_inicio, data_fim, cenario_id=cenario.id)
        return len(ctx.captured_queries)

    def test_contagem_de_queries_nao_escala_com_dias(self):
        queries_10_dias = self._run(10, '10d')
        queries_40_dias = self._run(40, '40d')

        delta = queries_40_dias - queries_10_dias
        self.assertLess(
            delta, 10,
            f'contagem de queries cresceu {delta} entre 10 e 40 dias simulados '
            '(esperado: crescimento praticamente nulo)',
        )

    def test_usa_previsoes_pre_carregadas_e_mantem_resultado(self):
        cooperativa = Cooperativa.objects.create(nome='Coop Prev', slug='coop-prev')
        cenario = Cenario.all_cooperativas.create(cooperativa=cooperativa, nome='C Prev')
        fabrica, armazem, rota = _montar_cenario_zerado(cooperativa, cenario)

        PrevisaoFabrica.all_cooperativas.create(
            cooperativa=cooperativa, fabrica=fabrica,
            mes_referencia=datetime.date(2026, 1, 1), recebimento_produtor=3100, vendas=0,
        )
        PrevisaoArmazem.all_cooperativas.create(
            cooperativa=cooperativa, armazem=armazem,
            mes_referencia=datetime.date(2026, 1, 1), recebimento_produtor=0, vendas=0,
        )

        data_inicio = datetime.date(2026, 1, 1)
        data_fim = data_inicio + datetime.timedelta(days=14)
        engine.simular_periodo(data_inicio, data_fim, cenario_id=cenario.id)

        resumo = ResumoMensalFabrica.all_cooperativas.filter(
            cenario_id=cenario.id, fabrica_id=fabrica.id
        ).first()
        self.assertIsNotNone(resumo)
        self.assertAlmostEqual(resumo.rec_produtor, 3100 / 31 * 15, places=2)


class ObterRangePrevisoesTests(TestCase):
    def test_sem_previsoes_retorna_none_none(self):
        cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        cenario = Cenario.all_cooperativas.create(cooperativa=cooperativa, nome='Cenário Teste')

        start, end = engine.obter_range_previsoes(cenario_id=cenario.id)

        self.assertIsNone(start)
        self.assertIsNone(end)

    def test_com_previsoes_retorna_range_correto(self):
        cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        cenario = Cenario.all_cooperativas.create(cooperativa=cooperativa, nome='Cenário Teste')
        fabrica, armazem, _rota = _montar_cenario_zerado(cooperativa, cenario)

        PrevisaoFabrica.all_cooperativas.create(
            cooperativa=cooperativa, fabrica=fabrica,
            mes_referencia=datetime.date(2026, 1, 1), recebimento_produtor=100, vendas=0,
        )
        PrevisaoFabrica.all_cooperativas.create(
            cooperativa=cooperativa, fabrica=fabrica,
            mes_referencia=datetime.date(2026, 3, 1), recebimento_produtor=100, vendas=0,
        )

        start, end = engine.obter_range_previsoes(cenario_id=cenario.id)

        self.assertEqual(start, datetime.date(2026, 1, 1))
        self.assertEqual(end, datetime.date(2026, 3, 31))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest apps/simulacao/tests/test_engine_simular_periodo.py -v`
Expected: FAIL/ERROR with `AttributeError: module 'apps.simulacao.engine' has no attribute 'simular_periodo'`.

- [ ] **Step 3: Write `simular_periodo` and `obter_range_previsoes`**

Append to `apps/simulacao/engine.py` (add these imports at the top of the file, alongside the existing ones):
```python
import time

import pandas as pd
from django.db import transaction
from django.db.models import Max, Min

from apps.simulacao.models import (
    Cenario,
    LogExecucao,
    MovimentacaoDiaria,
    PrevisaoArmazem,
    PrevisaoFabrica,
    ResumoMensalArmazem,
    ResumoMensalFabrica,
)
```

Then append the two functions:
```python
def simular_periodo(data_inicio, data_fim_previsao, cenario_id=None, estrategia='Econômico'):
    """Porte 1:1 de `calculations.simular_periodo`. A garantia de
    atomicidade (delete+recompute+insert) usa `transaction.atomic()` em vez
    de `session.commit()`/`session.rollback()` explícitos -- o efeito é o
    mesmo: uma exceção dentro do bloco reverte tudo dentro dele (até o
    savepoint mais próximo) e se repropaga. O registro de LogExecucao de
    sucesso fica FORA desse bloco, num segundo `.create()` autônomo, para
    preservar a mesma garantia do original ("commit separado, estritamente
    posterior ao principal")."""
    c_id = int(cenario_id) if cenario_id is not None else None
    inicio_execucao = time.monotonic()
    cenario = Cenario.all_cooperativas.get(id=c_id)
    cooperativa_id = cenario.cooperativa_id

    try:
        with transaction.atomic():
            MovimentacaoDiaria.all_cooperativas.filter(cenario_id=c_id).delete()
            ResumoMensalFabrica.all_cooperativas.filter(cenario_id=c_id).delete()
            ResumoMensalArmazem.all_cooperativas.filter(cenario_id=c_id).delete()

            data_inicio_ajustada = pd.to_datetime(data_inicio).date().replace(day=1)

            fabricas = list(Fabrica.all_cooperativas.filter(cenario_id=c_id))
            armazens = list(Armazem.all_cooperativas.filter(cenario_id=c_id))
            rotas = list(Rota.all_cooperativas.filter(cenario_id=c_id))
            safra_cache = _carregar_safras_por_armazem(c_id)

            fabrica_ids = [f.id for f in fabricas]
            armazem_ids = [a.id for a in armazens]
            previsoes_fab = {
                (p.fabrica_id, p.mes_referencia): p
                for p in PrevisaoFabrica.all_cooperativas.filter(fabrica_id__in=fabrica_ids)
            }
            previsoes_arm = {
                (p.armazem_id, p.mes_referencia): p
                for p in PrevisaoArmazem.all_cooperativas.filter(armazem_id__in=armazem_ids)
            }

            estoques_atuais = {}
            for f in fabricas:
                estoques_atuais[f'F_{f.id}'] = f.estoque_inicial
            for a in armazens:
                estoques_atuais[f'A_{a.id}'] = a.estoque_inicial

            data_atual = data_inicio_ajustada
            d_fim_p = pd.to_datetime(data_fim_previsao).date()

            resumos_fab = {}
            resumos_arm = {}
            dias_executados = 0
            max_dias = 730

            while True:
                mes_str = data_atual.strftime('%Y-%m')

                if mes_str not in resumos_fab:
                    resumos_fab[mes_str] = {f.id: {'rec_produtor': 0, 'rec_transbordo': 0, 'esmagado': 0, 'cap_estatica': f.capacidade_estatica} for f in fabricas}
                if mes_str not in resumos_arm:
                    resumos_arm[mes_str] = {a.id: {'rec_produtor': 0, 'envio_transbordo': 0, 'vendas': 0, 'cap_estatica': a.capacidade_estatica} for a in armazens}

                mes_atual_date = datetime.date(data_atual.year, data_atual.month, 1)
                dias_no_mes = pd.Period(data_atual.strftime('%Y-%m-%d')).days_in_month

                for f in fabricas:
                    prev = previsoes_fab.get((f.id, mes_atual_date))
                    if prev:
                        rec_diario = (prev.recebimento_produtor or 0) / dias_no_mes
                        vend_diario = (prev.vendas or 0) / dias_no_mes
                        estoques_atuais[f'F_{f.id}'] += (rec_diario - vend_diario)
                        resumos_fab[mes_str][f.id]['rec_produtor'] += rec_diario

                for a in armazens:
                    prev = previsoes_arm.get((a.id, mes_atual_date))
                    if prev:
                        rec_diario = (prev.recebimento_produtor or 0) / dias_no_mes
                        vend_diario = (prev.vendas or 0) / dias_no_mes
                        estoques_atuais[f'A_{a.id}'] += (rec_diario - vend_diario)
                        resumos_arm[mes_str][a.id]['rec_produtor'] += rec_diario
                        resumos_arm[mes_str][a.id]['vendas'] += vend_diario

                movimentacoes = otimizar_dia(
                    data_atual, estoques_atuais, estrategia=estrategia, cenario_id=c_id,
                    fabricas=fabricas, armazens=armazens, rotas=rotas, safra_cache=safra_cache,
                )

                if movimentacoes:
                    for mov in movimentacoes:
                        MovimentacaoDiaria.all_cooperativas.create(
                            cooperativa_id=cooperativa_id,
                            cenario_id=c_id,
                            data=data_atual,
                            armazem_id=mov['armazem_id'],
                            fabrica_id=mov['fabrica_id'],
                            quantidade_ton=mov['quantidade_ton'],
                            custo_total=mov['custo_total'],
                        )
                        estoques_atuais[f'A_{mov["armazem_id"]}'] -= mov['quantidade_ton']
                        estoques_atuais[f'F_{mov["fabrica_id"]}'] += mov['quantidade_ton']
                        resumos_arm[mes_str][mov['armazem_id']]['envio_transbordo'] += mov['quantidade_ton']
                        resumos_fab[mes_str][mov['fabrica_id']]['rec_transbordo'] += mov['quantidade_ton']

                for f in fabricas:
                    esmagado_real = min(max(0, estoques_atuais[f'F_{f.id}']), f.capacidade_esmagamento_diaria)
                    estoques_atuais[f'F_{f.id}'] -= esmagado_real
                    resumos_fab[mes_str][f.id]['esmagado'] += esmagado_real

                total_estoque_arm = sum(max(0, estoques_atuais[f'A_{a.id}']) for a in armazens)
                acabaram_previsoes = data_atual >= d_fim_p
                armazens_vazios = total_estoque_arm < 1.0

                eh_ultimo_dia_simulacao = (acabaram_previsoes and armazens_vazios) or dias_executados >= max_dias
                eh_ultimo_dia_mes = (data_atual + datetime.timedelta(days=1)).month != data_atual.month

                if eh_ultimo_dia_mes or eh_ultimo_dia_simulacao:
                    for f in fabricas:
                        resumos_fab[mes_str][f.id]['saldo_estoque'] = estoques_atuais[f'F_{f.id}']
                        resumos_fab[mes_str][f.id]['excedente'] = max(0, estoques_atuais[f'F_{f.id}'] - resumos_fab[mes_str][f.id]['cap_estatica'])
                    for a in armazens:
                        resumos_arm[mes_str][a.id]['saldo_estoque'] = estoques_atuais[f'A_{a.id}']
                        resumos_arm[mes_str][a.id]['excedente'] = max(0, estoques_atuais[f'A_{a.id}'] - resumos_arm[mes_str][a.id]['cap_estatica'])

                if eh_ultimo_dia_simulacao:
                    break

                data_atual += datetime.timedelta(days=1)
                dias_executados += 1

            for mes, fab_dict in resumos_fab.items():
                for f_id, dados in fab_dict.items():
                    ResumoMensalFabrica.all_cooperativas.create(
                        cooperativa_id=cooperativa_id, cenario_id=c_id, mes=mes, fabrica_id=f_id,
                        rec_produtor=dados['rec_produtor'], rec_transbordo=dados['rec_transbordo'],
                        esmagado=dados['esmagado'], saldo_estoque=dados.get('saldo_estoque', 0),
                        capacidade_estatica=dados['cap_estatica'], excedente=dados.get('excedente', 0),
                    )

            for mes, arm_dict in resumos_arm.items():
                for a_id, dados in arm_dict.items():
                    ResumoMensalArmazem.all_cooperativas.create(
                        cooperativa_id=cooperativa_id, cenario_id=c_id, mes=mes, armazem_id=a_id,
                        rec_produtor=dados['rec_produtor'], envio_transbordo=dados['envio_transbordo'],
                        vendas=dados['vendas'], saldo_estoque=dados.get('saldo_estoque', 0),
                        capacidade_estatica=dados['cap_estatica'], excedente=dados.get('excedente', 0),
                    )

        duracao_segundos = time.monotonic() - inicio_execucao
        dias_simulados = dias_executados + 1
        LogExecucao.all_cooperativas.create(
            cooperativa_id=cooperativa_id,
            cenario_id=c_id,
            status='sucesso',
            mensagem=f"Simulação concluída para cenario_id={c_id} em {dias_simulados} dia(s).",
            duracao_segundos=duracao_segundos,
            dias_simulados=dias_simulados,
        )

        logger.info(
            "Simulação concluída",
            extra={
                'cenario_id': c_id,
                'duracao_segundos': duracao_segundos,
                'dias_simulados': dias_simulados,
            },
        )
    except Exception:
        logger.error(
            "Falha na simulação",
            extra={'cenario_id': c_id},
            exc_info=True,
        )
        raise


def obter_range_previsoes(cenario_id=None):
    """Porte 1:1 de `calculations.obter_range_previsoes`."""
    min_f = PrevisaoFabrica.all_cooperativas.filter(fabrica__cenario_id=cenario_id).aggregate(Min('mes_referencia'))['mes_referencia__min']
    max_f = PrevisaoFabrica.all_cooperativas.filter(fabrica__cenario_id=cenario_id).aggregate(Max('mes_referencia'))['mes_referencia__max']
    min_a = PrevisaoArmazem.all_cooperativas.filter(armazem__cenario_id=cenario_id).aggregate(Min('mes_referencia'))['mes_referencia__min']
    max_a = PrevisaoArmazem.all_cooperativas.filter(armazem__cenario_id=cenario_id).aggregate(Max('mes_referencia'))['mes_referencia__max']

    dates = [d for d in [min_f, max_f, min_a, max_a] if d is not None]
    if not dates:
        return None, None

    start_date = min(dates)
    end_date_start_month = max(dates)
    end_date = (pd.Timestamp(end_date_start_month) + pd.offsets.MonthEnd(0)).date()

    return start_date, end_date
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest apps/simulacao/tests/test_engine_simular_periodo.py -v`
Expected: PASS (6 passed)

Run: `pytest apps/simulacao/ -v` (full app suite so far)
Expected: all passing.

- [ ] **Step 5: Commit**

```bash
git add apps/simulacao/engine.py apps/simulacao/tests/test_engine_simular_periodo.py
git commit -m "feat(fase5): port simular_periodo and obter_range_previsoes to engine.py"
```

---

### Task 7: `services.py` — `list_scenarios`, `get_daily_movements`, `get_monthly_summary`

**Files:**
- Create: `apps/simulacao/services.py`
- Create: `apps/simulacao/tests/test_services_movements.py`

**Interfaces:**
- Consumes: `Cenario`, `Armazem`, `Fabrica`, `MovimentacaoDiaria` (Tasks 1-2).
- Produces: `apps.simulacao.services.list_scenarios() -> list[dict]`, `apps.simulacao.services.get_daily_movements(scenario_id, start_date=None, end_date=None, origin_id=None, destination_id=None, limit=150) -> list[dict]`, `apps.simulacao.services.get_monthly_summary(scenario_id, start_date=None, end_date=None) -> dict`, `apps.simulacao.services.MAX_LIMIT`, `apps.simulacao.services.KG_PER_TON`, `apps.simulacao.services.KG_PER_SACA`. **Signature change**: no `session`/`init_db()` — Django manages connections automatically.

- [ ] **Step 1: Write the failing tests**

`apps/simulacao/tests/test_services_movements.py`:
```python
import datetime

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from apps.core.models import Cooperativa
from apps.simulacao import services
from apps.simulacao.models import Armazem, Cenario, Fabrica, MovimentacaoDiaria


class ListScenariosTests(TestCase):
    def test_lista_ordenada_por_oficial_depois_nome(self):
        cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        Cenario.all_cooperativas.create(cooperativa=cooperativa, nome='Zebra', is_oficial=False)
        Cenario.all_cooperativas.create(cooperativa=cooperativa, nome='Oficial', is_oficial=True)
        Cenario.all_cooperativas.create(cooperativa=cooperativa, nome='Alfa', is_oficial=False)

        resultado = services.list_scenarios()

        self.assertEqual([r['nome'] for r in resultado], ['Oficial', 'Alfa', 'Zebra'])
        self.assertTrue(resultado[0]['is_oficial'])


class GetDailyMovementsTests(TestCase):
    def setUp(self):
        self.cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.cenario = Cenario.all_cooperativas.create(cooperativa=self.cooperativa, nome='Cenário Teste')
        self.armazem = Armazem.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, nome='Armazém Teste',
            capacidade_estatica=1, capacidade_expedicao_diaria=1, estoque_inicial=0,
        )
        self.fabrica = Fabrica.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, nome='Fábrica Teste',
            capacidade_estatica=1, capacidade_esmagamento_diaria=1,
            capacidade_recebimento_diaria=1, limite_caminhoes=1,
            carga_media_caminhao=1, estoque_inicial=0,
        )

    def test_retorna_movimentacoes_com_nomes_e_conversao_para_sacas(self):
        MovimentacaoDiaria.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario,
            data=datetime.date(2026, 1, 1), armazem=self.armazem, fabrica=self.fabrica,
            quantidade_ton=6.0, custo_total=120.0,
        )

        resultado = services.get_daily_movements(scenario_id=self.cenario.id)

        self.assertEqual(len(resultado), 1)
        mov = resultado[0]
        self.assertEqual(mov['origem'], 'Armazém Teste')
        self.assertEqual(mov['destino'], 'Fábrica Teste')
        self.assertEqual(mov['quantidade_sc'], 100.0)  # 6 Ton * 1000 / 60

    def test_bulk_lookup_de_entidades_nao_escala_com_numero_de_linhas(self):
        for i in range(10):
            MovimentacaoDiaria.all_cooperativas.create(
                cooperativa=self.cooperativa, cenario=self.cenario,
                data=datetime.date(2026, 1, 1) + datetime.timedelta(days=i),
                armazem=self.armazem, fabrica=self.fabrica,
                quantidade_ton=10.0, custo_total=100.0,
            )

        with CaptureQueriesContext(connection) as ctx:
            resultado = services.get_daily_movements(scenario_id=self.cenario.id)

        self.assertEqual(len(resultado), 10)
        self.assertLess(
            len(ctx.captured_queries), 10,
            f'{len(ctx.captured_queries)} queries para 10 linhas -- parece N+1 (bug A3).',
        )

    def test_clamps_excessive_limit(self):
        MovimentacaoDiaria.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario,
            data=datetime.date(2026, 1, 1), armazem=self.armazem, fabrica=self.fabrica,
            quantidade_ton=10.0, custo_total=100.0,
        )

        resultado = services.get_daily_movements(scenario_id=self.cenario.id, limit=999999)

        self.assertEqual(len(resultado), 1)
        self.assertLessEqual(services.MAX_LIMIT, 1000)

    def test_raises_clear_error_on_malformed_start_date(self):
        with self.assertRaises(ValueError) as ctx:
            services.get_daily_movements(scenario_id=self.cenario.id, start_date='not-a-date')

        msg = str(ctx.exception)
        self.assertIn('not-a-date', msg)
        self.assertNotIn('does not match format', msg)
        self.assertIn('AAAA-MM-DD', msg)


class GetMonthlySummaryTests(TestCase):
    def setUp(self):
        self.cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.cenario = Cenario.all_cooperativas.create(cooperativa=self.cooperativa, nome='Cenário Teste')
        self.armazem = Armazem.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, nome='Armazém Teste',
            capacidade_estatica=1, capacidade_expedicao_diaria=1, estoque_inicial=0,
        )
        self.fabrica = Fabrica.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, nome='Fábrica Teste',
            capacidade_estatica=1, capacidade_esmagamento_diaria=1,
            capacidade_recebimento_diaria=1, limite_caminhoes=1,
            carga_media_caminhao=1, estoque_inicial=0,
        )

    def test_sem_movimentacoes_retorna_listas_vazias(self):
        resultado = services.get_monthly_summary(scenario_id=self.cenario.id)

        self.assertEqual(resultado, {'meses': [], 'rotas': []})

    def test_agrega_por_mes_e_por_rota(self):
        MovimentacaoDiaria.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario,
            data=datetime.date(2026, 1, 5), armazem=self.armazem, fabrica=self.fabrica,
            quantidade_ton=10.0, custo_total=100.0,
        )
        MovimentacaoDiaria.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario,
            data=datetime.date(2026, 1, 20), armazem=self.armazem, fabrica=self.fabrica,
            quantidade_ton=5.0, custo_total=50.0,
        )

        resultado = services.get_monthly_summary(scenario_id=self.cenario.id)

        self.assertEqual(len(resultado['resumo_mensal']), 1)
        self.assertEqual(resultado['resumo_mensal'][0]['quantidade_ton'], 15.0)
        self.assertEqual(len(resultado['detalhe_rotas']), 1)

    def test_raises_clear_error_on_malformed_end_date(self):
        with self.assertRaises(ValueError) as ctx:
            services.get_monthly_summary(scenario_id=self.cenario.id, end_date='31/12/2026')

        msg = str(ctx.exception)
        self.assertIn('31/12/2026', msg)
        self.assertNotIn('does not match format', msg)
        self.assertIn('AAAA-MM-DD', msg)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest apps/simulacao/tests/test_services_movements.py -v`
Expected: FAIL/ERROR with `ModuleNotFoundError: No module named 'apps.simulacao.services'`.

- [ ] **Step 3: Write the services module (part 1)**

`apps/simulacao/services.py`:
```python
import datetime

import pandas as pd

from apps.simulacao.models import Armazem, Cenario, Fabrica, MovimentacaoDiaria

# Ver ADR 0006: services.py consulta via `all_cooperativas`, não `objects`.

MAX_LIMIT = 1000
KG_PER_TON = 1000
KG_PER_SACA = 60


def _parse_date(value: str, field_name: str) -> datetime.date:
    """Porte 1:1 de `logistics_services._parse_date`."""
    try:
        return datetime.datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(
            f"Data invalida para '{field_name}': '{value}'. Use o formato AAAA-MM-DD."
        )


def list_scenarios() -> list[dict]:
    """Porte 1:1 de `logistics_services.list_scenarios`."""
    scenarios_list = Cenario.all_cooperativas.order_by('-is_oficial', 'nome')
    return [
        {
            "id": c.id,
            "nome": c.nome,
            "is_oficial": bool(c.is_oficial),
            "data_criacao": c.data_criacao.strftime("%Y-%m-%d %H:%M:%S") if c.data_criacao else None,
        }
        for c in scenarios_list
    ]


def get_daily_movements(
    scenario_id: int,
    start_date: str | None = None,
    end_date: str | None = None,
    origin_id: int | None = None,
    destination_id: int | None = None,
    limit: int = 150,
) -> list[dict]:
    """Porte 1:1 de `logistics_services.get_daily_movements`."""
    limit = min(limit, MAX_LIMIT)
    query = MovimentacaoDiaria.all_cooperativas.filter(cenario_id=scenario_id)

    if start_date:
        d_ini = _parse_date(start_date, "start_date")
        query = query.filter(data__gte=d_ini)
    if end_date:
        d_fim = _parse_date(end_date, "end_date")
        query = query.filter(data__lte=d_fim)
    if origin_id:
        query = query.filter(armazem_id=origin_id)
    if destination_id:
        query = query.filter(fabrica_id=destination_id)

    movements = list(query.order_by('data')[:limit])

    armazem_ids = {m.armazem_id for m in movements}
    fabrica_ids = {m.fabrica_id for m in movements}
    armazens_map = {
        a.id: a.nome for a in Armazem.all_cooperativas.filter(id__in=armazem_ids)
    } if armazem_ids else {}
    fabricas_map = {
        f.id: f.nome for f in Fabrica.all_cooperativas.filter(id__in=fabrica_ids)
    } if fabrica_ids else {}

    results = []
    for m in movements:
        results.append({
            "id": m.id,
            "data": m.data.strftime("%Y-%m-%d"),
            "origem_id": m.armazem_id,
            "origem": armazens_map.get(m.armazem_id, "N/A"),
            "destino_id": m.fabrica_id,
            "destino": fabricas_map.get(m.fabrica_id, "N/A"),
            "quantidade_ton": m.quantidade_ton,
            "quantidade_sc": m.quantidade_ton * KG_PER_TON / KG_PER_SACA,
            "custo_total_r$": m.custo_total,
        })
    return results


def get_monthly_summary(
    scenario_id: int,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    """Porte 1:1 de `logistics_services.get_monthly_summary`."""
    query = MovimentacaoDiaria.all_cooperativas.filter(cenario_id=scenario_id)
    if start_date:
        d_ini = _parse_date(start_date, "start_date")
        query = query.filter(data__gte=d_ini)
    if end_date:
        d_fim = _parse_date(end_date, "end_date")
        query = query.filter(data__lte=d_fim)

    movements = list(query)
    if not movements:
        return {"meses": [], "rotas": []}

    armazem_ids = {m.armazem_id for m in movements}
    fabrica_ids = {m.fabrica_id for m in movements}
    armazens_map = {
        a.id: a.nome for a in Armazem.all_cooperativas.filter(id__in=armazem_ids)
    } if armazem_ids else {}
    fabricas_map = {
        f.id: f.nome for f in Fabrica.all_cooperativas.filter(id__in=fabrica_ids)
    } if fabrica_ids else {}

    df = pd.DataFrame([{
        "data": m.data,
        "origem": armazens_map.get(m.armazem_id, "N/A"),
        "destino": fabricas_map.get(m.fabrica_id, "N/A"),
        "quantidade_ton": m.quantidade_ton,
        "quantidade_sc": m.quantidade_ton * KG_PER_TON / KG_PER_SACA,
        "custo_total": m.custo_total,
    } for m in movements])

    df["mes"] = pd.to_datetime(df["data"]).dt.strftime("%Y-%m")

    df_mes = df.groupby("mes").agg({
        "quantidade_ton": "sum",
        "quantidade_sc": "sum",
        "custo_total": "sum",
    }).reset_index()

    df_rotas = df.groupby(["mes", "origem", "destino"]).agg({
        "quantidade_ton": "sum",
        "quantidade_sc": "sum",
        "custo_total": "sum",
    }).reset_index()

    return {
        "resumo_mensal": df_mes.to_dict(orient="records"),
        "detalhe_rotas": df_rotas.to_dict(orient="records"),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest apps/simulacao/tests/test_services_movements.py -v`
Expected: PASS (9 passed)

- [ ] **Step 5: Commit**

```bash
git add apps/simulacao/services.py apps/simulacao/tests/test_services_movements.py
git commit -m "feat(fase5): port list_scenarios, get_daily_movements, get_monthly_summary to services.py"
```

---

### Task 8: `services.py` — report/comparison functions + `CLAUDE.md` correction

**Files:**
- Modify: `apps/simulacao/services.py`, `CLAUDE.md`
- Create: `apps/simulacao/tests/test_services_reports.py`

**Interfaces:**
- Consumes: `ResumoMensalFabrica`, `ResumoMensalArmazem`, `Fabrica`, `Armazem` (Tasks 1-3).
- Produces: `apps.simulacao.services.get_factories_summary`, `get_warehouses_summary`, `compare_factories`, `compare_warehouses`, `get_stock_excesses_report`, `get_stock_ruptures_report` (all `(scenario_id: int) -> list[dict]`).

- [ ] **Step 1: Write the failing tests**

`apps/simulacao/tests/test_services_reports.py`:
```python
from django.test import TestCase

from apps.core.models import Cooperativa
from apps.simulacao import services
from apps.simulacao.models import Armazem, Cenario, Fabrica, ResumoMensalArmazem, ResumoMensalFabrica


class ReportsFixtureMixin:
    def setUp(self):
        self.cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.cenario = Cenario.all_cooperativas.create(cooperativa=self.cooperativa, nome='Cenário Teste')
        self.fabrica = Fabrica.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, nome='Fábrica Teste',
            capacidade_estatica=10000, capacidade_esmagamento_diaria=1,
            capacidade_recebimento_diaria=1, limite_caminhoes=1,
            carga_media_caminhao=1, estoque_inicial=0,
        )
        self.armazem = Armazem.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, nome='Armazém Teste',
            capacidade_estatica=5000, capacidade_expedicao_diaria=1, estoque_inicial=0,
        )


class GetFactoriesSummaryTests(ReportsFixtureMixin, TestCase):
    def test_retorna_resumo_com_nome_da_fabrica(self):
        ResumoMensalFabrica.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, mes='2026-01', fabrica=self.fabrica,
            rec_produtor=100, rec_transbordo=50, esmagado=120, saldo_estoque=30,
            capacidade_estatica=10000, excedente=0,
        )

        resultado = services.get_factories_summary(self.cenario.id)

        self.assertEqual(len(resultado), 1)
        self.assertEqual(resultado[0]['fabrica'], 'Fábrica Teste')
        self.assertEqual(resultado[0]['recebimento_produtor_ton'], 100)


class GetWarehousesSummaryTests(ReportsFixtureMixin, TestCase):
    def test_retorna_resumo_com_nome_do_armazem(self):
        ResumoMensalArmazem.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, mes='2026-01', armazem=self.armazem,
            rec_produtor=200, envio_transbordo=150, vendas=10, saldo_estoque=40,
            capacidade_estatica=5000, excedente=0,
        )

        resultado = services.get_warehouses_summary(self.cenario.id)

        self.assertEqual(len(resultado), 1)
        self.assertEqual(resultado[0]['armazem'], 'Armazém Teste')
        self.assertEqual(resultado[0]['envio_transbordo_ton'], 150)


class CompareFactoriesTests(ReportsFixtureMixin, TestCase):
    def test_agrega_pico_de_estoque_e_totais(self):
        ResumoMensalFabrica.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, mes='2026-01', fabrica=self.fabrica,
            rec_produtor=100, rec_transbordo=0, esmagado=50, saldo_estoque=200,
            capacidade_estatica=10000, excedente=0,
        )
        ResumoMensalFabrica.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, mes='2026-02', fabrica=self.fabrica,
            rec_produtor=100, rec_transbordo=0, esmagado=50, saldo_estoque=300,
            capacidade_estatica=10000, excedente=0,
        )

        resultado = services.compare_factories(self.cenario.id)

        self.assertEqual(len(resultado), 1)
        linha = resultado[0]
        self.assertEqual(linha['recebimento_produtor_total_ton'], 200)
        self.assertEqual(linha['pico_estoque_mensal_ton'], 300)

    def test_sem_resumos_retorna_lista_vazia(self):
        self.assertEqual(services.compare_factories(self.cenario.id), [])


class CompareWarehousesTests(ReportsFixtureMixin, TestCase):
    def test_agrega_pico_de_estoque_e_totais(self):
        ResumoMensalArmazem.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, mes='2026-01', armazem=self.armazem,
            rec_produtor=100, envio_transbordo=0, vendas=0, saldo_estoque=100,
            capacidade_estatica=5000, excedente=0,
        )
        ResumoMensalArmazem.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, mes='2026-02', armazem=self.armazem,
            rec_produtor=100, envio_transbordo=0, vendas=0, saldo_estoque=50,
            capacidade_estatica=5000, excedente=0,
        )

        resultado = services.compare_warehouses(self.cenario.id)

        self.assertEqual(len(resultado), 1)
        linha = resultado[0]
        self.assertEqual(linha['recebimento_produtor_total_ton'], 200)
        self.assertEqual(linha['pico_estoque_mensal_ton'], 100)

    def test_sem_resumos_retorna_lista_vazia(self):
        self.assertEqual(services.compare_warehouses(self.cenario.id), [])


class GetStockExcessesReportTests(ReportsFixtureMixin, TestCase):
    def test_detecta_excedente_positivo_em_fabrica_e_armazem(self):
        ResumoMensalFabrica.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, mes='2026-01', fabrica=self.fabrica,
            rec_produtor=0, rec_transbordo=0, esmagado=0, saldo_estoque=12000,
            capacidade_estatica=10000, excedente=2000,
        )
        ResumoMensalArmazem.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, mes='2026-01', armazem=self.armazem,
            rec_produtor=0, envio_transbordo=0, vendas=0, saldo_estoque=0,
            capacidade_estatica=5000, excedente=0,
        )

        alertas = services.get_stock_excesses_report(self.cenario.id)

        self.assertEqual(len(alertas), 1)
        self.assertEqual(alertas[0]['entidade_tipo'], 'Fabrica')
        self.assertEqual(alertas[0]['entidade_nome'], 'Fábrica Teste')
        self.assertEqual(alertas[0]['excedente_estouro_ton'], 2000)


class GetStockRupturesReportTests(ReportsFixtureMixin, TestCase):
    def test_detecta_saldo_negativo(self):
        ResumoMensalFabrica.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, mes='2026-01', fabrica=self.fabrica,
            rec_produtor=100, rec_transbordo=0, esmagado=200, saldo_estoque=-50.0,
            capacidade_estatica=10000, excedente=0,
        )

        alertas = services.get_stock_ruptures_report(self.cenario.id)

        self.assertEqual(len(alertas), 1)
        alerta = alertas[0]
        self.assertEqual(alerta['entidade_nome'], 'Fábrica Teste')
        self.assertEqual(alerta['entidade_tipo'], 'Fabrica')
        self.assertAlmostEqual(alerta['deficit_ton'], 50.0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest apps/simulacao/tests/test_services_reports.py -v`
Expected: FAIL/ERROR with `AttributeError: module 'apps.simulacao.services' has no attribute 'get_factories_summary'`.

- [ ] **Step 3: Write the report functions**

Append to `apps/simulacao/services.py` (add `ResumoMensalArmazem, ResumoMensalFabrica` to the existing `from apps.simulacao.models import ...` line at the top of the file):
```python
def get_factories_summary(scenario_id: int) -> list[dict]:
    """Porte 1:1 de `logistics_services.get_factories_summary`."""
    resumos = ResumoMensalFabrica.all_cooperativas.filter(cenario_id=scenario_id)
    results = []
    for r in resumos:
        fab = Fabrica.all_cooperativas.filter(id=r.fabrica_id).first()
        results.append({
            "mes": r.mes,
            "fabrica_id": r.fabrica_id,
            "fabrica": fab.nome if fab else "N/A",
            "recebimento_produtor_ton": r.rec_produtor,
            "recebimento_transbordo_ton": r.rec_transbordo,
            "esmagado_ton": r.esmagado,
            "saldo_estoque_ton": r.saldo_estoque,
            "capacidade_estatica_ton": r.capacidade_estatica,
            "excedente_estoque_ton": r.excedente,
        })
    return sorted(results, key=lambda x: (x["mes"], x["fabrica"]))


def get_warehouses_summary(scenario_id: int) -> list[dict]:
    """Porte 1:1 de `logistics_services.get_warehouses_summary`."""
    resumos = ResumoMensalArmazem.all_cooperativas.filter(cenario_id=scenario_id)
    results = []
    for r in resumos:
        arm = Armazem.all_cooperativas.filter(id=r.armazem_id).first()
        results.append({
            "mes": r.mes,
            "armazem_id": r.armazem_id,
            "armazem": arm.nome if arm else "N/A",
            "recebimento_produtor_ton": r.rec_produtor,
            "envio_transbordo_ton": r.envio_transbordo,
            "vendas_ton": r.vendas,
            "saldo_estoque_ton": r.saldo_estoque,
            "capacidade_estatica_ton": r.capacidade_estatica,
            "excedente_estoque_ton": r.excedente,
        })
    return sorted(results, key=lambda x: (x["mes"], x["armazem"]))


def compare_factories(scenario_id: int) -> list[dict]:
    """Porte 1:1 de `logistics_services.compare_factories`."""
    resumos = list(ResumoMensalFabrica.all_cooperativas.filter(cenario_id=scenario_id))
    if not resumos:
        return []

    fabrica_ids = {r.fabrica_id for r in resumos}
    fabricas_map = {
        f.id: f.nome for f in Fabrica.all_cooperativas.filter(id__in=fabrica_ids)
    }

    df = pd.DataFrame([{
        "fabrica_id": r.fabrica_id,
        "fabrica": fabricas_map.get(r.fabrica_id, "N/A"),
        "rec_produtor": r.rec_produtor,
        "rec_transbordo": r.rec_transbordo,
        "esmagado": r.esmagado,
        "saldo_estoque": r.saldo_estoque,
        "excedente": r.excedente,
    } for r in resumos])

    comp = df.groupby(["fabrica_id", "fabrica"]).agg({
        "rec_produtor": "sum",
        "rec_transbordo": "sum",
        "esmagado": "sum",
        "saldo_estoque": "max",
        "excedente": "sum",
    }).reset_index()

    comp.rename(columns={
        "rec_produtor": "recebimento_produtor_total_ton",
        "rec_transbordo": "recebimento_transbordo_total_ton",
        "esmagado": "esmagado_total_ton",
        "saldo_estoque": "pico_estoque_mensal_ton",
        "excedente": "excedente_total_acumulado_ton",
    }, inplace=True)

    return comp.to_dict(orient="records")


def compare_warehouses(scenario_id: int) -> list[dict]:
    """Porte 1:1 de `logistics_services.compare_warehouses`."""
    resumos = list(ResumoMensalArmazem.all_cooperativas.filter(cenario_id=scenario_id))
    if not resumos:
        return []

    armazem_ids = {r.armazem_id for r in resumos}
    armazens_map = {
        a.id: a.nome for a in Armazem.all_cooperativas.filter(id__in=armazem_ids)
    }

    df = pd.DataFrame([{
        "armazem_id": r.armazem_id,
        "armazem": armazens_map.get(r.armazem_id, "N/A"),
        "rec_produtor": r.rec_produtor,
        "envio_transbordo": r.envio_transbordo,
        "vendas": r.vendas,
        "saldo_estoque": r.saldo_estoque,
        "excedente": r.excedente,
    } for r in resumos])

    comp = df.groupby(["armazem_id", "armazem"]).agg({
        "rec_produtor": "sum",
        "envio_transbordo": "sum",
        "vendas": "sum",
        "saldo_estoque": "max",
        "excedente": "sum",
    }).reset_index()

    comp.rename(columns={
        "rec_produtor": "recebimento_produtor_total_ton",
        "envio_transbordo": "envio_transbordo_total_ton",
        "vendas": "vendas_total_ton",
        "saldo_estoque": "pico_estoque_mensal_ton",
        "excedente": "excedente_total_acumulado_ton",
    }, inplace=True)

    return comp.to_dict(orient="records")


def get_stock_excesses_report(scenario_id: int) -> list[dict]:
    """Porte 1:1 de `logistics_services.get_stock_excesses_report`."""
    alertas = []

    res_fab = ResumoMensalFabrica.all_cooperativas.filter(cenario_id=scenario_id, excedente__gt=0)
    for r in res_fab:
        fab = Fabrica.all_cooperativas.filter(id=r.fabrica_id).first()
        alertas.append({
            "mes": r.mes,
            "entidade_tipo": "Fabrica",
            "entidade_id": r.fabrica_id,
            "entidade_nome": fab.nome if fab else "N/A",
            "estoque_final_ton": r.saldo_estoque,
            "capacidade_estatica_ton": r.capacidade_estatica,
            "excedente_estouro_ton": r.excedente,
        })

    res_arm = ResumoMensalArmazem.all_cooperativas.filter(cenario_id=scenario_id, excedente__gt=0)
    for r in res_arm:
        arm = Armazem.all_cooperativas.filter(id=r.armazem_id).first()
        alertas.append({
            "mes": r.mes,
            "entidade_tipo": "Armazem",
            "entidade_id": r.armazem_id,
            "entidade_nome": arm.nome if arm else "N/A",
            "estoque_final_ton": r.saldo_estoque,
            "capacidade_estatica_ton": r.capacidade_estatica,
            "excedente_estouro_ton": r.excedente,
        })

    return sorted(alertas, key=lambda x: (x["mes"], x["entidade_tipo"], x["entidade_nome"]))


def get_stock_ruptures_report(scenario_id: int) -> list[dict]:
    """Porte 1:1 de `logistics_services.get_stock_ruptures_report`."""
    alertas = []

    res_fab = ResumoMensalFabrica.all_cooperativas.filter(cenario_id=scenario_id, saldo_estoque__lt=0)
    for r in res_fab:
        fab = Fabrica.all_cooperativas.filter(id=r.fabrica_id).first()
        alertas.append({
            "mes": r.mes,
            "entidade_tipo": "Fabrica",
            "entidade_id": r.fabrica_id,
            "entidade_nome": fab.nome if fab else "N/A",
            "estoque_final_ton": r.saldo_estoque,
            "capacidade_estatica_ton": r.capacidade_estatica,
            "deficit_ton": abs(r.saldo_estoque),
        })

    res_arm = ResumoMensalArmazem.all_cooperativas.filter(cenario_id=scenario_id, saldo_estoque__lt=0)
    for r in res_arm:
        arm = Armazem.all_cooperativas.filter(id=r.armazem_id).first()
        alertas.append({
            "mes": r.mes,
            "entidade_tipo": "Armazem",
            "entidade_id": r.armazem_id,
            "entidade_nome": arm.nome if arm else "N/A",
            "estoque_final_ton": r.saldo_estoque,
            "capacidade_estatica_ton": r.capacidade_estatica,
            "deficit_ton": abs(r.saldo_estoque),
        })

    return sorted(alertas, key=lambda x: (x["mes"], x["entidade_tipo"], x["entidade_nome"]))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest apps/simulacao/tests/test_services_reports.py -v`
Expected: PASS (8 passed)

Run: `pytest apps/simulacao/ -v` (full app suite)
Expected: all passing (should be 52: 18 model + 6 safra + 5 otimizar_dia + 6 simular_periodo + 9 services_movements + 8 services_reports).

- [ ] **Step 5: Correct the stale CLAUDE.md business rule and extend the File Map**

In `CLAUDE.md`, under "## Key Business Rules", replace the line:
```markdown
- Cenário oficial = `cenario_id IS NULL` (baseline). Simulations are deep clones of it with a real `cenario_id`.
```
with:
```markdown
- Cenário oficial = a `Cenario` row with `is_oficial=True` (a real row, like any other). Every descendant table's `cenario_id` is a real, non-null FK to a `Cenario.id`, including the official one. The single exception is `LogExecucao.cenario_id`, which is nullable specifically to mean "this execution ran against the official scenario" (see the field's own comment in `models.py`) — that convention does NOT apply to any other table.
```

Add a bullet to "## Architecture / File Map", after the existing `config/`, `apps/core|simulacao|integracoes/` bullet added by the Fundação plan:
```markdown
- `apps/simulacao/models.py` — Django port of `models.py`'s 11 tables, every one with `cooperativa_id` (Fase 5, Port do Domínio). `apps/simulacao/engine.py` — port of `calculations.py`. `apps/simulacao/services.py` — port of `logistics_services.py`. All three use `Model.all_cooperativas` internally, not `Model.objects` — see `docs/decisions/0006-...`.
```

- [ ] **Step 6: Commit**

```bash
git add apps/simulacao/services.py apps/simulacao/tests/test_services_reports.py CLAUDE.md
git commit -m "feat(fase5): port report/comparison functions to services.py, fix stale CLAUDE.md rule"
```

---

## Self-Review Notes

- **Spec coverage:** spec's Phase 2 "Port do domínio" — "engine.py, services.py, os 9 models com cooperativa_id, testes de isolamento de tenant" — is covered: models across Tasks 1-3 (11 models, all with `cooperativa_id`), formal isolation test in Task 1 (`TenantIsolationRealModelsTests`, against real `Cenario`/`Fabrica`, not a throwaway model), `engine.py` across Tasks 4-6, `services.py` across Tasks 7-8. Spec decision #2's "mesmas assinaturas... trocando session.query por Model.objects.filter" is honored except for the necessarily-dropped `session` parameter (documented explicitly in every affected task) and the deliberate `all_cooperativas` (not `objects`) choice (ADR 0006, ADR 0003 already anticipated this exact escape-hatch use case).
- **Real bug found during investigation, fixed in-plan:** `CLAUDE.md`'s stale "cenario_id IS NULL" business rule (Task 8) — verified against actual code behavior across four files before concluding it was wrong, not guessed.
- **Ordering/consistency check applied during drafting:** `CenarioScopedModel` (Task 1) is the base for 7 of 11 models; `PrevisaoFabrica`/`PrevisaoArmazem` (Task 2) get their own narrower `clean()` (they never had a direct `cenario` FK, even in the SQLAlchemy original); `LogExecucao` (Task 3) deliberately does NOT inherit `CenarioScopedModel` (its `cenario` is nullable, incompatible with the mixin's required-FK assumption) and instead declares its own nullable FK + its own `clean()`. All three variants are documented in ADR 0005 so a future reader doesn't "fix" the asymmetry.
- **No placeholders:** every step shows complete file contents/diffs; no "port the rest" or "add appropriate tests" hand-waves — every test in this plan is a direct, faithful adaptation of an existing, already-passing SQLAlchemy test (`tests/test_calculations_*.py`, `tests/test_logistics_services_a2_a3_a4.py`), cited by name in this plan's investigation.
