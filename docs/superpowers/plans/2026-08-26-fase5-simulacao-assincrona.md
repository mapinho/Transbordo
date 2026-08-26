# Fase 5.5 — Simulação Assíncrona (Procrastinate + Polling HTMX) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dar à aba de cenário um disparo assíncrono da simulação (`engine.simular_periodo`) via
Procrastinate, com acompanhamento de progresso por polling HTMX, sem alterar a lógica de otimização.

**Architecture:** `procrastinate.contrib.django` roda como app Django adicional, reaproveitando a
conexão Postgres já configurada. Uma task fina (`apps/simulacao/tasks.py`) envolve
`engine.simular_periodo` sem tocá-lo. `LogExecucao` (já existente) é a única fonte de verdade do status
de execução — tanto para o guard de concorrência quanto para o fragmento de polling. Uma nova 6ª aba
"Simulação" dispara a task e o navegador faz polling num endpoint HTMX até o status virar terminal.

**Tech Stack:** Django 6, `procrastinate` (`contrib.django`), HTMX (`django-htmx`, já instalado),
PostgreSQL (`DJANGO_DB_*`), pytest + `django.test.TestCase`.

**Spec:** `docs/superpowers/specs/2026-08-26-fase5-simulacao-assincrona-design.md`

## Global Constraints

- Integração via `procrastinate.contrib.django` (app Django oficial) — nunca um `procrastinate.App`
  avulso.
- `apps/simulacao/engine.py` e `calculations.py` NÃO são modificados por este plano — a task é um
  wrapper fino em torno de `engine.simular_periodo`.
- Progresso é indeterminado (spinner), não percentual por dia — decisão explícita da spec.
- `LogExecucao` é a única fonte de verdade do status; nenhuma view introspecta
  `procrastinate_jobs` diretamente.
- Concorrência: dois cadeados — guard de UX na view (checa `LogExecucao` `em_andamento`) e
  `lock`/`queueing_lock` dinâmico do Procrastinate por `cenario_id` (defesa em profundidade).
- Timeout de staleness: 30 minutos (`STALENESS_TIMEOUT = datetime.timedelta(minutes=30)`).
- Mensagem de erro truncada em 500 caracteres (`CharField(max_length=500)` de `LogExecucao.mensagem`).
- Estratégias válidas: exatamente `['Econômico', 'Expedição', 'Segurança']` — mesmas de
  `engine.py`/`calculations.py`.
- Toda query em view usa `Model.objects` (tenant-scoped); toda query dentro da task Procrastinate
  usa `Model.all_cooperativas` (a task roda fora do ciclo de request HTTP, sem o contextvar de
  cooperativa — ver ADR 0006).
- TDD: cada task abaixo tem teste escrito e visto falhar antes da implementação.

---

### Task 1: Instalar e configurar o Procrastinate no projeto Django

**Files:**
- Modify: `requirements.txt`
- Modify: `config/settings/base.py:16-30` (bloco `INSTALLED_APPS`)

**Interfaces:**
- Produces: app Django `procrastinate.contrib.django` registrado e migrado; nenhuma interface Python
  nova ainda (só infraestrutura). Tasks seguintes importam `from procrastinate.contrib.django import app`
  e `from procrastinate.contrib.django import procrastinate_app` (o segundo nome expõe
  `procrastinate_app.current_app`, usado nos testes para trocar o connector).

- [ ] **Step 1: Adicionar a dependência**

Edite `requirements.txt`, adicionando a nova linha logo após `crispy-tailwind>=1.0,<2.0`:

```
crispy-tailwind>=1.0,<2.0
procrastinate>=3.9,<4.0
```

- [ ] **Step 2: Instalar**

Run: `pip install -r requirements.txt`
Expected: `procrastinate` (>=3.9,<4.0) instalado sem erro.

- [ ] **Step 3: Registrar a app no Django**

Edite `config/settings/base.py`, no bloco `INSTALLED_APPS` (linhas 16-30). O app do Procrastinate entra
antes das apps próprias do projeto, como a documentação oficial recomenda:

```python
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django_htmx',
    'django_cotton',
    'crispy_forms',
    'crispy_tailwind',
    'procrastinate.contrib.django',
    'apps.core',
    'apps.simulacao',
    'apps.integracoes',
]
```

- [ ] **Step 4: Aplicar as migrations do Procrastinate**

Run: `python manage.py migrate`
Expected: novas migrations de `procrastinate` aplicadas (tabelas `procrastinate_jobs` e afins criadas no
banco `transbordo`), sem erro.

- [ ] **Step 5: Sanity check**

Run: `python manage.py check`
Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 6: Commit**

```bash
git add requirements.txt config/settings/base.py
git commit -m "feat(simulacao): instala e registra o Procrastinate no projeto Django"
```

---

### Task 2: Task `executar_simulacao` (wrapper assíncrono de `engine.simular_periodo`)

**Files:**
- Create: `apps/simulacao/tasks.py`
- Test: `apps/simulacao/tests/test_tasks_executar_simulacao.py`

**Interfaces:**
- Consumes: `apps.simulacao.engine.simular_periodo(data_inicio, data_fim_previsao, cenario_id=None, estrategia='Econômico')`
  (já existe, não é modificada); `apps.simulacao.models.LogExecucao` (já existe, campos `status`,
  `mensagem`, `cenario_id`, `cooperativa_id`, `dias_simulados`, `duracao_segundos`).
- Produces: `apps.simulacao.tasks.executar_simulacao` — task Procrastinate com assinatura
  `executar_simulacao(log_id, cenario_id, data_inicio, data_fim, estrategia)`. Ao terminar com sucesso,
  apaga o `LogExecucao` de `id=log_id` (o marcador de "em andamento" criado por quem chamou `.defer()`
  — a própria `engine.simular_periodo` já cria seu próprio `LogExecucao(status='sucesso')` ao final,
  então o marcador vira redundante e é removido). Ao falhar, atualiza esse mesmo `LogExecucao` para
  `status='erro'`, `mensagem=str(exc)[:500]`, e relança a exceção.

- [ ] **Step 1: Escrever os testes (falhando)**

Crie `apps/simulacao/tests/test_tasks_executar_simulacao.py`:

```python
from django.test import TestCase
from procrastinate import testing
from procrastinate.contrib.django import procrastinate_app

from apps.core.models import Cooperativa
from apps.simulacao import tasks
from apps.simulacao.models import Armazem, Cenario, Fabrica, LogExecucao, Rota


def _montar_cenario_zerado(cooperativa, cenario):
    fabrica = Fabrica.all_cooperativas.create(
        cooperativa=cooperativa, cenario=cenario, nome='Fábrica 1',
        capacidade_estatica=100000, capacidade_esmagamento_diaria=1000,
        capacidade_recebimento_diaria=1000, limite_caminhoes=50,
        carga_media_caminhao=30, estoque_inicial=0,
    )
    armazem = Armazem.all_cooperativas.create(
        cooperativa=cooperativa, cenario=cenario, nome='Armazém 1',
        capacidade_estatica=50000, capacidade_expedicao_diaria=1000,
        estoque_inicial=500,
    )
    rota = Rota.all_cooperativas.create(
        cooperativa=cooperativa, cenario=cenario, armazem=armazem, fabrica=fabrica,
        distancia_km=10, custo_frete_ton=5.0, custo_frete_entressafra=8.0,
    )
    return fabrica, armazem, rota


class ExecutarSimulacaoTaskTests(TestCase):
    def setUp(self):
        self.cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.cenario = Cenario.all_cooperativas.create(
            cooperativa=self.cooperativa, nome='Cenário Teste',
        )
        _montar_cenario_zerado(self.cooperativa, self.cenario)

        self._connector = testing.InMemoryConnector()
        self._ctx = procrastinate_app.current_app.replace_connector(self._connector)
        self.app = self._ctx.__enter__()
        self.addCleanup(self._ctx.__exit__, None, None, None)

    def test_sucesso_apaga_o_marcador_e_engine_ja_criou_o_log_de_sucesso(self):
        log = LogExecucao.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, status='em_andamento',
        )

        tasks.executar_simulacao.defer(
            log_id=log.id, cenario_id=self.cenario.id,
            data_inicio='2026-01-01', data_fim='2026-01-05', estrategia='Econômico',
        )
        self.app.run_worker(wait=False)

        self.assertFalse(LogExecucao.all_cooperativas.filter(id=log.id).exists())
        log_sucesso = LogExecucao.all_cooperativas.filter(
            cenario_id=self.cenario.id, status='sucesso',
        ).latest('id')
        self.assertIsNotNone(log_sucesso.dias_simulados)

    def test_falha_atualiza_o_marcador_para_erro_com_mensagem_truncada(self):
        log = LogExecucao.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, status='em_andamento',
        )
        cenario_inexistente_id = self.cenario.id + 999999

        tasks.executar_simulacao.defer(
            log_id=log.id, cenario_id=cenario_inexistente_id,
            data_inicio='2026-01-01', data_fim='2026-01-05', estrategia='Econômico',
        )
        self.app.run_worker(wait=False)

        log.refresh_from_db()
        self.assertEqual(log.status, 'erro')
        self.assertIn('Cenario matching query does not exist', log.mensagem)

    def test_queueing_lock_impede_dois_disparos_para_o_mesmo_cenario(self):
        log_a = LogExecucao.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, status='em_andamento',
        )
        log_b = LogExecucao.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, status='em_andamento',
        )
        lock = f'simulacao-cenario-{self.cenario.id}'

        tasks.executar_simulacao.configure(lock=lock, queueing_lock=lock).defer(
            log_id=log_a.id, cenario_id=self.cenario.id,
            data_inicio='2026-01-01', data_fim='2026-01-05', estrategia='Econômico',
        )

        from procrastinate.exceptions import AlreadyEnqueued
        with self.assertRaises(AlreadyEnqueued):
            tasks.executar_simulacao.configure(lock=lock, queueing_lock=lock).defer(
                log_id=log_b.id, cenario_id=self.cenario.id,
                data_inicio='2026-01-01', data_fim='2026-01-05', estrategia='Econômico',
            )
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `pytest apps/simulacao/tests/test_tasks_executar_simulacao.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'apps.simulacao.tasks'` (o módulo ainda não
existe).

- [ ] **Step 3: Implementar a task**

Crie `apps/simulacao/tasks.py`:

```python
from procrastinate.contrib.django import app

from apps.simulacao import engine
from apps.simulacao.models import LogExecucao


@app.task
def executar_simulacao(log_id, cenario_id, data_inicio, data_fim, estrategia):
    """Wrapper assíncrono de `engine.simular_periodo` -- a lógica de
    otimização não é tocada. `log_id` referencia o `LogExecucao` marcador
    de "em andamento" criado por quem chamou `.defer()` (a view); em caso
    de sucesso ele é descartado porque `simular_periodo` já cria seu
    próprio `LogExecucao(status='sucesso')` ao final. Em caso de falha,
    esse mesmo marcador vira o registro de erro -- `simular_periodo` não
    grava nada no caminho de exceção."""
    try:
        engine.simular_periodo(data_inicio, data_fim, cenario_id=cenario_id, estrategia=estrategia)
    except Exception as exc:
        LogExecucao.all_cooperativas.filter(id=log_id).update(
            status='erro', mensagem=str(exc)[:500],
        )
        raise
    else:
        LogExecucao.all_cooperativas.filter(id=log_id).delete()
```

- [ ] **Step 4: Rodar os testes e confirmar que passam**

Run: `pytest apps/simulacao/tests/test_tasks_executar_simulacao.py -v`
Expected: PASS (3 testes).

- [ ] **Step 5: Commit**

```bash
git add apps/simulacao/tasks.py apps/simulacao/tests/test_tasks_executar_simulacao.py
git commit -m "feat(simulacao): task Procrastinate executar_simulacao envolve engine.simular_periodo"
```

---

### Task 3: Aba "Simulação" — views, URLs, templates e subnav

**Files:**
- Modify: `apps/simulacao/views.py` (imports no topo + 3 views novas ao final do arquivo)
- Modify: `apps/simulacao/urls.py:7-17`
- Modify: `templates/simulacao/_subnav.html`
- Create: `templates/simulacao/_simulacao_content.html`
- Create: `templates/simulacao/_simulacao_status.html`
- Create: `templates/simulacao/simulacao.html`
- Test: `apps/simulacao/tests/test_views_simulacao.py`

**Interfaces:**
- Consumes: `apps.simulacao.tasks.executar_simulacao` (Task 2, assinatura
  `executar_simulacao(log_id, cenario_id, data_inicio, data_fim, estrategia)`);
  `apps.simulacao.engine.obter_range_previsoes(cenario_id=None)` (já existe, retorna
  `(start_date, end_date)` ou `(None, None)`); `apps.simulacao.models.LogExecucao`,
  `apps.simulacao.models.Cenario`.
- Produces: rotas nomeadas `simulacao:simulacao_tab`, `simulacao:simulacao_executar`,
  `simulacao:simulacao_status`, todas com `cenario_id` na URL.

- [ ] **Step 1: Escrever os testes (falhando)**

Crie `apps/simulacao/tests/test_views_simulacao.py`:

```python
import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from procrastinate import testing
from procrastinate.contrib.django import procrastinate_app

from apps.core.models import Cooperativa
from apps.simulacao.models import Cenario, LogExecucao

User = get_user_model()


class SimulacaoViewsTests(TestCase):
    def setUp(self):
        self.cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.user = User.objects.create_user(
            username='usuaria', password='senha-forte-123',
            cooperativa=self.cooperativa, papel=User.PAPEL_ADMIN_COOPERATIVA,
        )
        self.cenario = Cenario.all_cooperativas.create(
            cooperativa=self.cooperativa, nome='Cenário Teste',
        )
        self.url_tab = reverse('simulacao:simulacao_tab', kwargs={'cenario_id': self.cenario.id})
        self.url_executar = reverse(
            'simulacao:simulacao_executar', kwargs={'cenario_id': self.cenario.id},
        )
        self.url_status = reverse('simulacao:simulacao_status', kwargs={'cenario_id': self.cenario.id})

        self._connector = testing.InMemoryConnector()
        self._ctx = procrastinate_app.current_app.replace_connector(self._connector)
        self.app = self._ctx.__enter__()
        self.addCleanup(self._ctx.__exit__, None, None, None)

    def test_requer_login(self):
        response = self.client.get(self.url_tab)
        self.assertEqual(response.status_code, 302)

    def test_pagina_completa_sem_htmx(self):
        self.client.force_login(self.user)

        response = self.client.get(self.url_tab)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<html')

    def test_partial_com_htmx(self):
        self.client.force_login(self.user)

        response = self.client.get(self.url_tab, HTTP_HX_REQUEST='true')

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '<html')

    def test_cenario_de_outra_cooperativa_404(self):
        outra_cooperativa = Cooperativa.objects.create(nome='Coop B', slug='coop-b')
        cenario_b = Cenario.all_cooperativas.create(cooperativa=outra_cooperativa, nome='Cenário B')
        self.client.force_login(self.user)

        response = self.client.get(
            reverse('simulacao:simulacao_tab', kwargs={'cenario_id': cenario_b.id})
        )

        self.assertEqual(response.status_code, 404)

    def test_executar_dispara_a_task_e_cria_log_em_andamento(self):
        self.client.force_login(self.user)

        response = self.client.post(self.url_executar, {
            'data_inicio': '2026-01-01', 'data_fim': '2026-01-05', 'estrategia': 'Econômico',
        })

        self.assertEqual(response.status_code, 200)
        log = LogExecucao.all_cooperativas.get(cenario_id=self.cenario.id)
        self.assertEqual(log.status, 'em_andamento')
        self.assertEqual(len(self.app.connector.jobs), 1)

    def test_executar_bloqueia_quando_ja_em_andamento_recente(self):
        LogExecucao.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, status='em_andamento',
        )
        self.client.force_login(self.user)

        response = self.client.post(self.url_executar, {
            'data_inicio': '2026-01-01', 'data_fim': '2026-01-05', 'estrategia': 'Econômico',
        })

        self.assertEqual(response.status_code, 400)
        self.assertEqual(len(self.app.connector.jobs), 0)

    def test_executar_permite_quando_em_andamento_e_orfao(self):
        antigo = LogExecucao.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, status='em_andamento',
        )
        antigo.data_execucao = timezone.now() - datetime.timedelta(minutes=31)
        antigo.save(update_fields=['data_execucao'])
        self.client.force_login(self.user)

        response = self.client.post(self.url_executar, {
            'data_inicio': '2026-01-01', 'data_fim': '2026-01-05', 'estrategia': 'Econômico',
        })

        self.assertEqual(response.status_code, 200)
        antigo.refresh_from_db()
        self.assertEqual(antigo.status, 'erro')
        self.assertEqual(len(self.app.connector.jobs), 1)

    def test_executar_rejeita_periodo_vazio(self):
        self.client.force_login(self.user)

        response = self.client.post(self.url_executar, {'data_inicio': '', 'data_fim': '', 'estrategia': 'Econômico'})

        self.assertEqual(response.status_code, 400)

    def test_executar_rejeita_estrategia_invalida(self):
        self.client.force_login(self.user)

        response = self.client.post(self.url_executar, {
            'data_inicio': '2026-01-01', 'data_fim': '2026-01-05', 'estrategia': 'Chuta e Reza',
        })

        self.assertEqual(response.status_code, 400)

    def test_status_mostra_nenhuma_execucao_quando_log_nao_existe(self):
        self.client.force_login(self.user)

        response = self.client.get(self.url_status)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Nenhuma simulação')

    def test_status_apos_execucao_completa_mostra_sucesso_e_para_o_polling(self):
        self.client.force_login(self.user)
        self.client.post(self.url_executar, {
            'data_inicio': '2026-01-01', 'data_fim': '2026-01-05', 'estrategia': 'Econômico',
        })
        self.app.run_worker(wait=False)

        response = self.client.get(self.url_status)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Concluída')
        self.assertNotContains(response, 'hx-trigger')
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `pytest apps/simulacao/tests/test_views_simulacao.py -v`
Expected: FAIL — `NoReverseMatch: Reverse for 'simulacao_tab' not found` (as rotas ainda não existem).

- [ ] **Step 3: Adicionar as views**

Edite `apps/simulacao/views.py`. No bloco de imports do topo (linhas 1-30), adicione:

```python
import datetime
import json
import secrets

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.db import transaction
from django.http import FileResponse, Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from procrastinate.exceptions import AlreadyEnqueued

from apps.simulacao import engine, services, tasks
from apps.simulacao.columns import (
    ARMAZEM_COLUMNS,
    FABRICA_COLUMNS,
    PREVISAO_ARMAZEM_COLUMNS,
    PREVISAO_FABRICA_COLUMNS,
    ROTA_COLUMNS,
    SAFRA_COLUMNS,
)
from apps.simulacao.models import (
    Armazem,
    Cenario,
    Fabrica,
    LogExecucao,
    PrevisaoArmazem,
    PrevisaoFabrica,
    Rota,
    SafraUnidade,
)
from apps.simulacao.planilha import ABAS_NA_ORDEM, analisar, aplicar, gerar_template

XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
ESTRATEGIAS = ['Econômico', 'Expedição', 'Segurança']
STALENESS_TIMEOUT = datetime.timedelta(minutes=30)
```

Isso substitui o bloco de imports original (linhas 1-32) — adiciona `django.utils.timezone`,
`django.views.decorators.http.require_POST`, `procrastinate.exceptions.AlreadyEnqueued`, os módulos
`engine`/`tasks` e o model `LogExecucao`, e define as duas constantes novas.

Ao final do arquivo (depois de `carga_preview`), adicione as três views novas:

```python
@login_required
def simulacao_tab(request, cenario_id):
    cenario = get_object_or_404(Cenario, id=cenario_id)
    inicio_sugerido, fim_sugerido = engine.obter_range_previsoes(cenario_id=cenario.id)
    log_atual = LogExecucao.objects.filter(cenario_id=cenario.id).order_by('-id').first()
    context = {
        "cenario": cenario, "active": "simulacao",
        "inicio_sugerido": inicio_sugerido, "fim_sugerido": fim_sugerido,
        "estrategias": ESTRATEGIAS, "log_atual": log_atual,
    }
    template = 'simulacao/_simulacao_content.html' if request.htmx else 'simulacao/simulacao.html'
    return render(request, template, context)


@login_required
@require_POST
def simulacao_executar(request, cenario_id):
    cenario = get_object_or_404(Cenario, id=cenario_id)

    em_andamento = (
        LogExecucao.objects.filter(cenario_id=cenario.id, status='em_andamento')
        .order_by('-id').first()
    )
    if em_andamento is not None:
        if timezone.now() - em_andamento.data_execucao < STALENESS_TIMEOUT:
            return HttpResponseBadRequest(
                'Já existe uma simulação em andamento para este cenário.'
            )
        em_andamento.status = 'erro'
        em_andamento.mensagem = 'Execução interrompida — worker inativo.'
        em_andamento.save(update_fields=['status', 'mensagem'])

    data_inicio = request.POST.get('data_inicio', '')
    data_fim = request.POST.get('data_fim', '')
    estrategia = request.POST.get('estrategia', '')
    if not data_inicio or not data_fim:
        return HttpResponseBadRequest('Informe o período da simulação.')
    if estrategia not in ESTRATEGIAS:
        return HttpResponseBadRequest('Estratégia inválida.')

    log = LogExecucao.objects.create(
        cooperativa_id=cenario.cooperativa_id, cenario_id=cenario.id, status='em_andamento',
    )
    lock = f'simulacao-cenario-{cenario.id}'
    try:
        tasks.executar_simulacao.configure(lock=lock, queueing_lock=lock).defer(
            log_id=log.id, cenario_id=cenario.id,
            data_inicio=data_inicio, data_fim=data_fim, estrategia=estrategia,
        )
    except AlreadyEnqueued:
        log.delete()
        return HttpResponseBadRequest('Já existe uma simulação em andamento para este cenário.')

    return simulacao_status(request, cenario_id)


@login_required
def simulacao_status(request, cenario_id):
    cenario = get_object_or_404(Cenario, id=cenario_id)
    log_atual = LogExecucao.objects.filter(cenario_id=cenario.id).order_by('-id').first()
    context = {"cenario": cenario, "log_atual": log_atual}
    return render(request, 'simulacao/_simulacao_status.html', context)
```

- [ ] **Step 4: Adicionar as URLs**

Edite `apps/simulacao/urls.py`, adicionando as três rotas novas antes de `carga/`:

```python
from django.urls import path

from apps.simulacao import views

app_name = 'simulacao'

urlpatterns = [
    path('cenarios/', views.cenarios_list, name='cenarios_list'),
    path('cenarios/<int:cenario_id>/fabricas/', views.fabricas_grid, name='fabricas_grid'),
    path('cenarios/<int:cenario_id>/armazens/', views.armazens_grid, name='armazens_grid'),
    path('cenarios/<int:cenario_id>/rotas/', views.rotas_grid, name='rotas_grid'),
    path('cenarios/<int:cenario_id>/previsoes/', views.previsoes_grid, name='previsoes_grid'),
    path('cenarios/<int:cenario_id>/safras/', views.safras_grid, name='safras_grid'),
    path('cenarios/<int:cenario_id>/simulacao/', views.simulacao_tab, name='simulacao_tab'),
    path(
        'cenarios/<int:cenario_id>/simulacao/executar/',
        views.simulacao_executar, name='simulacao_executar',
    ),
    path(
        'cenarios/<int:cenario_id>/simulacao/status/',
        views.simulacao_status, name='simulacao_status',
    ),
    path('carga/', views.carga_upload, name='carga'),
    path('carga/template/', views.carga_template, name='carga_template'),
    path('carga/<str:token>/', views.carga_preview, name='carga_preview'),
]
```

- [ ] **Step 5: Adicionar a 6ª aba na subnav**

Edite `templates/simulacao/_subnav.html`, adicionando o link antes do `</div>` final:

```html
<div class="tabs tabs-boxed mb-4">
    <a href="{% url 'simulacao:fabricas_grid' cenario_id=cenario.id %}"
       hx-get="{% url 'simulacao:fabricas_grid' cenario_id=cenario.id %}"
       hx-target="#cenario-content" hx-push-url="true"
       class="tab {% if active == 'fabricas' %}tab-active{% endif %}">Fábricas</a>
    <a href="{% url 'simulacao:armazens_grid' cenario_id=cenario.id %}"
       hx-get="{% url 'simulacao:armazens_grid' cenario_id=cenario.id %}"
       hx-target="#cenario-content" hx-push-url="true"
       class="tab {% if active == 'armazens' %}tab-active{% endif %}">Armazéns</a>
    <a href="{% url 'simulacao:rotas_grid' cenario_id=cenario.id %}"
       hx-get="{% url 'simulacao:rotas_grid' cenario_id=cenario.id %}"
       hx-target="#cenario-content" hx-push-url="true"
       class="tab {% if active == 'rotas' %}tab-active{% endif %}">Rotas</a>
    <a href="{% url 'simulacao:previsoes_grid' cenario_id=cenario.id %}"
       hx-get="{% url 'simulacao:previsoes_grid' cenario_id=cenario.id %}"
       hx-target="#cenario-content" hx-push-url="true"
       class="tab {% if active == 'previsoes' %}tab-active{% endif %}">Previsões</a>
    <a href="{% url 'simulacao:safras_grid' cenario_id=cenario.id %}"
       hx-get="{% url 'simulacao:safras_grid' cenario_id=cenario.id %}"
       hx-target="#cenario-content" hx-push-url="true"
       class="tab {% if active == 'safras' %}tab-active{% endif %}">Datas de Safra</a>
    <a href="{% url 'simulacao:simulacao_tab' cenario_id=cenario.id %}"
       hx-get="{% url 'simulacao:simulacao_tab' cenario_id=cenario.id %}"
       hx-target="#cenario-content" hx-push-url="true"
       class="tab {% if active == 'simulacao' %}tab-active{% endif %}">Simulação</a>
</div>
```

- [ ] **Step 6: Criar os templates**

Crie `templates/simulacao/_simulacao_status.html` (o fragmento de polling — nota: `hx-swap="outerHTML"`
aqui é seguro porque o alvo é este próprio `<div id="simulacao-status">`, não um contêiner
compartilhado com a navegação por abas; é exatamente essa distinção que evitou repetir o bug de
`hx-swap="outerHTML"` nos formulários de grid, corrigido na etapa anterior):

```html
<div id="simulacao-status"
     {% if log_atual.status == 'em_andamento' %}
     hx-get="{% url 'simulacao:simulacao_status' cenario_id=cenario.id %}"
     hx-trigger="every 2s" hx-swap="outerHTML"
     {% endif %}>
    {% if not log_atual %}
        <p>Nenhuma simulação executada ainda para este cenário.</p>
    {% elif log_atual.status == 'em_andamento' %}
        <p class="flex items-center gap-2">
            <span class="loading loading-spinner"></span>
            Simulação em andamento…
        </p>
    {% elif log_atual.status == 'sucesso' %}
        <p class="text-success">
            Concluída: {{ log_atual.dias_simulados }} dia(s) simulado(s) em
            {{ log_atual.duracao_segundos|floatformat:1 }}s.
        </p>
    {% elif log_atual.status == 'erro' %}
        <p class="text-error">Erro: {{ log_atual.mensagem }}</p>
    {% endif %}
</div>
```

Crie `templates/simulacao/_simulacao_content.html` (a aba completa):

```html
{% include "simulacao/_subnav.html" %}

<form hx-post="{% url 'simulacao:simulacao_executar' cenario_id=cenario.id %}"
      hx-target="#simulacao-status" hx-swap="outerHTML"
      class="mb-4">
    {% csrf_token %}
    <div class="flex flex-wrap gap-4 items-end">
        <label class="flex flex-col">
            <span class="text-sm">Data início</span>
            <input type="date" name="data_inicio"
                   value="{{ inicio_sugerido|date:'Y-m-d' }}" class="input input-bordered">
        </label>
        <label class="flex flex-col">
            <span class="text-sm">Data fim</span>
            <input type="date" name="data_fim"
                   value="{{ fim_sugerido|date:'Y-m-d' }}" class="input input-bordered">
        </label>
        <label class="flex flex-col">
            <span class="text-sm">Estratégia</span>
            <select name="estrategia" class="select select-bordered">
                {% for e in estrategias %}
                <option value="{{ e }}">{{ e }}</option>
                {% endfor %}
            </select>
        </label>
        <button type="submit"
                class="rounded bg-[var(--cor-primaria)] hover:bg-[var(--cor-primaria-hover)] text-white px-4 py-2">
            Executar
        </button>
    </div>
</form>

{% include "simulacao/_simulacao_status.html" %}
```

Crie `templates/simulacao/simulacao.html` (fallback de página cheia, mesmo padrão de `fabricas.html`):

```html
{% extends "base.html" %}
{% block content %}
<div id="cenario-content">
    {% include "simulacao/_simulacao_content.html" %}
</div>
{% endblock %}
```

- [ ] **Step 7: Rodar os testes e confirmar que passam**

Run: `pytest apps/simulacao/tests/test_views_simulacao.py -v`
Expected: PASS (10 testes).

- [ ] **Step 8: Rodar a suíte completa**

Run: `python manage.py check && pytest`
Expected: check sem erros; suíte inteira (SQLAlchemy + Django) verde, incluindo os testes das grades
existentes (nenhuma regressão).

- [ ] **Step 9: Commit**

```bash
git add apps/simulacao/views.py apps/simulacao/urls.py templates/simulacao/_subnav.html \
    templates/simulacao/_simulacao_content.html templates/simulacao/_simulacao_status.html \
    templates/simulacao/simulacao.html apps/simulacao/tests/test_views_simulacao.py
git commit -m "feat(simulacao): aba Simulação com disparo assíncrono e polling HTMX de status"
```

---

### Task 4: ADR e documentação

**Files:**
- Create: `docs/decisions/0007-procrastinate-integracao-django-e-status-por-logexecucao.md`
- Modify: `CLAUDE.md` (seção "Fase 5 — Fundação Django (em progresso)" e "Architecture / File Map")

**Interfaces:** nenhuma — task de documentação, sem código.

- [ ] **Step 1: Escrever a ADR**

Crie `docs/decisions/0007-procrastinate-integracao-django-e-status-por-logexecucao.md`:

```markdown
# ADR 0007 — Procrastinate via contrib.django, LogExecucao como fonte de status, lock duplo

- Status: Aceito
- Data: 2026-08-26

## Contexto

A Fase 5.5 do roteiro (`docs/superpowers/specs/2026-08-26-fase5-simulacao-assincrona-design.md`) precisa
disparar `engine.simular_periodo` de forma assíncrona, com uma UI de acompanhamento de status via HTMX,
sem modificar a lógica de otimização em si e sem que duas execuções simultâneas do mesmo cenário corrompam
`MovimentacaoDiaria`/`ResumoMensal*` (apagados e reescritos por completo a cada execução).

## Decisão

- Integração via `procrastinate.contrib.django` (app Django oficial) — reaproveita a conexão já
  configurada em `DJANGO_DB_*`, entra no `manage.py migrate` normal, e expõe fixtures de teste prontas
  (`procrastinate.testing.InMemoryConnector` via `procrastinate_app.current_app.replace_connector(...)`).
  Um `procrastinate.App` avulso não traria vantagem nenhuma e duplicaria configuração que o Django já
  tem.
- `LogExecucao` (já existente, tabela de auditoria de execuções) é a única fonte de verdade do status de
  uma execução em andamento — nenhuma view introspecta o schema interno do Procrastinate
  (`procrastinate_jobs`). A view que dispara cria um `LogExecucao(status='em_andamento')` como marcador
  *antes* de enfileirar a task; a task, ao terminar, apaga esse marcador em caso de sucesso (porque
  `engine.simular_periodo` já cria seu próprio `LogExecucao(status='sucesso')` de forma autônoma ao
  final — não modificado por esta fase) ou o atualiza para `status='erro'` em caso de falha (porque
  `simular_periodo` não grava nada no caminho de exceção).
- Concorrência: dois cadeados com propósitos diferentes. A view rejeita um novo disparo na hora,
  sem enfileirar, se já existe um `LogExecucao(status='em_andamento')` para aquele cenário — a menos que
  seja "órfão" (mais velho que 30 minutos, o que indica um worker morto no meio da execução; nesse caso
  o antigo é marcado `erro` e o disparo é permitido). Como defesa em profundidade contra a corrida entre
  dois POSTs quase simultâneos, `.configure(lock=f"simulacao-cenario-{id}",
  queueing_lock=f"simulacao-cenario-{id}").defer(...)` serializa tanto o enfileiramento quanto a
  execução por cenário no próprio Procrastinate.
- A task usa `Model.all_cooperativas` (nunca `Model.objects`) para toda query, incluindo a atualização do
  próprio `LogExecucao` marcador — consistente com a ADR 0006: um worker Procrastinate roda fora do
  ciclo de request HTTP, sem o contextvar de cooperativa que o `TenantManager` exige.

## Consequências

- Uma execução bem-sucedida deixa exatamente um `LogExecucao(status='sucesso')` na auditoria (o marcador
  é descartado) — o histórico de execuções não duplica linhas por causa do disparo assíncrono.
- O timeout de staleness (30 min) é um valor fixo, não configurável por variável de ambiente ainda —
  reavaliar se cenários de produção mostrarem execuções legitimamente mais longas (ver "Decisões em
  aberto" da spec).
- Rodar a aba "Simulação" localmente exige dois processos: `python manage.py runserver` e
  `python manage.py procrastinate worker` — nenhum dos dois sozinho é suficiente.
```

- [ ] **Step 2: Atualizar CLAUDE.md — comandos**

No arquivo `CLAUDE.md`, dentro da seção `## Fase 5 — Fundação Django (em progresso)`, o bloco de
comandos atual é:

```markdown
- `python manage.py check` — sanity check do projeto Django.
- `pytest` — roda tanto os testes SQLAlchemy (`tests/`) quanto os testes Django (`apps/*/tests/`). Os
  testes Django (`apps/*/tests/`) precisam de um PostgreSQL local alcançável via `DJANGO_DB_*` (crie o
  banco/role antes de rodar `pytest` pela primeira vez — ver `docs/decisions/0002-...`); os testes
  SQLAlchemy (`tests/`) continuam usando SQLite em memória, sem essa dependência.
- O `.env` do stack Django usa variáveis `DJANGO_DB_*` (deliberadamente distintas de `DB_*`, que
  continuam servindo o stack Streamlit/SQLAlchemy) — ver `.env.example`.
- ADRs desta fase em `docs/decisions/`, começando em `0001`.
```

Adicione uma linha nova ao final desse bloco:

```markdown
- `python manage.py check` — sanity check do projeto Django.
- `pytest` — roda tanto os testes SQLAlchemy (`tests/`) quanto os testes Django (`apps/*/tests/`). Os
  testes Django (`apps/*/tests/`) precisam de um PostgreSQL local alcançável via `DJANGO_DB_*` (crie o
  banco/role antes de rodar `pytest` pela primeira vez — ver `docs/decisions/0002-...`); os testes
  SQLAlchemy (`tests/`) continuam usando SQLite em memória, sem essa dependência.
- O `.env` do stack Django usa variáveis `DJANGO_DB_*` (deliberadamente distintas de `DB_*`, que
  continuam servindo o stack Streamlit/SQLAlchemy) — ver `.env.example`.
- ADRs desta fase em `docs/decisions/`, começando em `0001`.
- `python manage.py procrastinate worker` — worker assíncrono (Procrastinate); precisa estar rodando,
  junto com `runserver`, para a aba "Simulação" executar de fato (ver ADR 0007).
```

- [ ] **Step 3: Atualizar CLAUDE.md — mapa de arquivos**

Na seção `## Architecture / File Map`, logo após a linha que descreve `apps/simulacao/legado.py`,
adicione uma linha nova:

```markdown
- `apps/simulacao/tasks.py` — task assíncrona Procrastinate `executar_simulacao`, disparada pela aba
  "Simulação" (views `simulacao_tab`/`simulacao_executar`/`simulacao_status` em
  `apps/simulacao/views.py`); envolve `engine.simular_periodo` sem alterar sua lógica. `LogExecucao` é a
  fonte de verdade do status (`em_andamento`/`sucesso`/`erro`) consultada pelo polling HTMX. Ver ADR 0007
  e `docs/superpowers/specs/2026-08-26-fase5-simulacao-assincrona-design.md`.
```

- [ ] **Step 4: Verificar**

Run: `python manage.py check && pytest`
Expected: sem erros (task de documentação não altera comportamento).

- [ ] **Step 5: Commit**

```bash
git add docs/decisions/0007-procrastinate-integracao-django-e-status-por-logexecucao.md CLAUDE.md
git commit -m "docs: ADR 0007 e atualização do CLAUDE.md para a simulação assíncrona"
```

---

## Verificação manual final (fora do escopo dos testes automatizados)

Depois da Task 4, com `python manage.py runserver` e `python manage.py procrastinate worker` rodando em
paralelo: abrir a aba "Simulação" de um cenário real (ex.: o cenário oficial espelhado do banco legado,
ver `docs/superpowers/specs/2026-08-24-espelhamento-dados-legado-design.md`), disparar uma execução,
confirmar que o polling mostra o spinner e depois o resumo de sucesso sem reload manual da página, e que
`MovimentacaoDiaria`/`ResumoMensal*` foram de fato gerados no banco.
