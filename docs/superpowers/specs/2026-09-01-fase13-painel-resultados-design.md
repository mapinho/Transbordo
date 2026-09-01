# Fase 13 — Painel de Resultados de Simulação — Design

- Status: Em revisão (aguarda aprovação do dono do projeto)
- Data: 2026-09-01
- Roteiro: segunda fase de evolução pós-Cutover; ver ADR 0011 e "Roadmap Status" no `CLAUDE.md` raiz. Sucede a Fase 12 (Evolução UX/UI, ADR 0012).

## Contexto e objetivo

Hoje, depois que uma simulação roda, o app Django/HTMX **não mostra nenhum resultado**. A aba
"Simulação" só exibe o **status da execução** (em andamento / "Concluída" + data / erro) via polling
HTMX. Os números gerados (movimentações diárias, custo de frete, sumarizações) só saem por: Face JSON
(`/api/v1/`), MCP server (`mcp_server.py`) e o Assistente de IA (`apps/simulacao/assistente.py`).

O motor grava, a cada execução bem-sucedida, três tabelas por cenário: `MovimentacaoDiaria`
(`data`, `armazem`, `fabrica`, `quantidade_ton`, `custo_total`), `ResumoMensalFabrica` e
`ResumoMensalArmazem`. As duas de resumo são de **saldo de estoque** (rec. produtor, esmagado,
saldo, excedente) — **não** de frete. Toda visão de frete/volume que esta fase entrega sai de
`MovimentacaoDiaria` agrupada de formas diferentes.

`MovimentacaoDiaria.custo_total` **já embute** o custo de frete correto: o engine grava
`quantidade_ton × (custo_frete_ton se na safra | custo_frete_entressafra fora)` — o painel só exibe,
não recalcula. O engine **apaga e reescreve** as três tabelas no início de cada run, então o conteúdo
atual de `MovimentacaoDiaria` de um cenário = resultado da **última** execução bem-sucedida dele.

Objetivo desta fase: **um painel de resultados dentro do cenário** — nova aba "Resultados" — com
listagens e sumarizações (diárias e mensais), filtros, comparação com um segundo cenário,
exportação (Excel/CSV) e um gráfico. Toda resolução de dados no servidor, via HTMX.

## Escopo

**Dentro:**

- Nova aba **"Resultados"** no subnav do cenário (8ª), habilitada só quando há `MovimentacaoDiaria`.
- Novo módulo **`apps/simulacao/resultados.py`** — motor de agregação por ORM (funções puras).
- Novo **`apps/simulacao/forms.py`** — `ResultadosForm` (Django `Form` puro) para parsear/validar o
  formulário de filtros. Não é `FilterSet` do django-filter: os filtros não filtram um queryset
  diretamente, alimentam `resultados.agregar()`; um `Form` é mais honesto.
- Views novas em `apps/simulacao/views.py`: `resultados_tab`, `resultados_export`. Rotas em
  `apps/simulacao/urls.py`.
- Parciais HTMX: `templates/simulacao/resultados.html`, `_resultados_content.html`,
  `_resultados_tabela.html`, `_resultados_grafico.html`.
- Seletor **Período × Agrupar por**, seletor de **cenário de comparação**, filtros (data de/até,
  armazéns multi, fábricas multi), card-resumo fixo no topo, gráfico condicional.
- **Chart.js 4.x** via CDN — padrão de gráfico da suíte AgroVector (ADR 0013).
- Exportação Excel (`openpyxl`) + CSV (stdlib) do recorte atual.
- `VERSION` → `1.2.0`, `CHANGELOG.md`, tag `v1.2.0` (não pushed automaticamente).
- ADR 0013 + seção nova em `docs/design-system/README.md`.

**Fora:**

- Qualquer mudança no motor de otimização (`engine.py`), nas tarefas assíncronas (`tasks.py`), nos
  serviços de relatório (`services.py`), na Face JSON (`apps/integracoes`) ou no `mcp_server.py`.
- Migrations de banco — **nenhum model muda** nesta fase.
- Ordenação por clique de coluna (YAGNI — ver Decisão 2).
- UI de "chips" para os multi-selects de armazém/fábrica (`<select multiple>` simples; upgrade futuro).
- Gráficos além do mensal (barras) e do diário-total (linha) — as visões agrupadas por
  fábrica/armazém e a linha crua não têm gráfico.
- Predição de recebimento/venda, rename do model `Cooperativa`, parâmetros novos do motor — fases
  seguintes.
- Deploy server-side automatizado — segue manual.

## Decisões de arquitetura

### 1. Fronteira: `resultados.py` novo, ORM, `services.py` intocado

`apps/simulacao/resultados.py` é um módulo novo de funções puras que agregam `MovimentacaoDiaria`
via ORM (`.values(...).annotate(Sum(...))`). **Não** reusa nem altera `apps/simulacao/services.py`:
`services.py` é "porte 1:1" (pandas) das funções do Streamlit original, é o contrato consumido por
MCP / Face JSON / Assistente, e usa `all_cooperativas` por decisão explícita (ADR 0006). `resultados.py`
é a camada de UI, chamada de uma view onde o `CooperativaScopeMiddleware` já definiu o contextvar de
tenant, então usa **`MovimentacaoDiaria.objects`** (escopado, fail-closed) — igual aos grids editáveis.

Há sobreposição deliberada de lógica com `services.py::get_monthly_summary` / `get_daily_movements`.
É aceitável: são camadas diferentes com donos diferentes. `services.py` fica congelado.

Rejeitado: reusar `services.py` + django-tables2/filter (Abordagem 2 do brainstorming) — bendearia um
contrato de API e 9 formas de tabela × colunas Δ dinâmicas brigam com o django-tables2.

### 2. O seletor: Período × Agrupar por (uma tabela, nove formas)

Dois combos, não onze opções. Um dict de config em `resultados.py` mapeia `(periodo, agrupar)` →
`(campos do GROUP BY, definição de colunas)`. `agregar()` é **uma função**, não nove.

| Período | Agrupar por | GROUP BY | Colunas | Pagina? | Requisito do dono |
|---|---|---|---|---|---|
| `diario` | `fabrica_armazem` | — (linha crua de `MovimentacaoDiaria`) | Dia · Origem · Destino · Ton · Sacas · Frete | **sim** | #2 |
| `diario` | `fabrica` | `(data, fabrica)` | Dia · Destino · Ton · Sacas · Frete | sim | #3 |
| `diario` | `armazem` | `(data, armazem)` | Dia · Origem · Ton · Sacas · Frete | sim | #4 |
| `diario` | `nada` | `(data,)` | Dia · Ton · Sacas · Frete | não | #5 |
| `mensal` | `fabrica_armazem` | `(mês, armazem, fabrica)` | Mês · Origem · Destino · Ton · Sacas · Frete | não | #7 |
| `mensal` | `fabrica` | `(mês, fabrica)` | Mês · Destino · Ton · Sacas · Frete | não | #8 / #9 |
| `mensal` | `armazem` | `(mês, armazem)` | Mês · Origem · Ton · Sacas · Frete | não | #9 / #8 |
| `mensal` | `nada` | `(mês,)` | Mês · Ton · Sacas · Frete | não | #10 |
| `total` | (ignora o combo B) | — | Ton · Sacas · Frete (1 linha) | não | #11 |

- **Default ao abrir:** `diario × fabrica_armazem` (item #2 do dono).
- Mês = `TruncMonth('data')`, exibido `MM/AAAA`, ordenado pela data real.
- A linha crua já é 1 registro por `(data, armazem, fabrica)` (o `otimizar_dia` produz no máximo um
  `v_mov[(armazem, fabrica)]` por dia) — sem GROUP BY, é um queryset paginado.
- **Itens #8 e #9 do pedido têm rótulo ambíguo** ("mensal por armazém, mostrando fábrica" vs.
  "mensal por fábrica, mostrando armazém"). O modelo Período×Agrupar resolve os dois como
  `mensal × armazem` e `mensal × fabrica`; a coluna mostrada é a do agrupamento. Se o dono quiser a
  semântica invertida, é troca de rótulo no dict de config.
- **Sem ordenação por clique** (YAGNI). Ordem fixa: coluna de período → origem/destino.
- `PAGE_SIZE = 100`, fixo.

### 3. `resultados.py` — assinaturas e formato

```python
PAGE_SIZE = 100

def agregar(cenario_id: int, periodo: str, agrupar: str,
            filtros: dict, pagina: int | None = 1) -> dict   # pagina=None -> sem paginação (export)
def totais_do_recorte(cenario_id: int, filtros: dict) -> dict
def cenarios_comparaveis(cenario_id: int, cooperativa_id: int) -> list[dict]
def aplicar_comparacao(dados: dict, cenario_comparado_id: int, periodo: str,
                       agrupar: str, filtros: dict) -> dict
def dados_grafico(cenario_id: int, periodo: str, filtros: dict,
                  cenario_comparado_id: int | None) -> dict | None
```

`filtros` = `ResultadosForm(request.GET, cenario=cenario).cleaned_data` (após `is_valid()`):
`{data_de, data_ate, armazem_ids, fabrica_ids}`, todos opcionais. Chaves vazias = cenário inteiro.
`ResultadosForm` (`apps/simulacao/forms.py`, `Form` puro): `data_de`/`data_ate` = `DateField`;
`armazem_ids`/`fabrica_ids` = `ModelMultipleChoiceField` com queryset
`Armazem.objects.filter(cenario_id=...)` / `Fabrica.objects.filter(cenario_id=...)`.

**Retorno de `agregar()`:**

```python
{
  "colunas": [
    {"key": "dia",    "label": "Dia",        "tipo": "data_dia"},   # ou "data_mes"
    {"key": "origem",  "label": "Origem",     "tipo": "texto"},
    {"key": "destino", "label": "Destino",    "tipo": "texto"},
    {"key": "ton",     "label": "Toneladas",  "tipo": "num",   "comparavel": True},
    {"key": "sacas",   "label": "Sacas",      "tipo": "num",   "comparavel": True},
    {"key": "custo",   "label": "Frete (R$)", "tipo": "moeda", "comparavel": True},
  ],
  "linhas": [
    {"dia": date(2026,1,5), "origem": "ARM X", "destino": "FAB Y",
     "ton": 123.4, "sacas": 2056.67, "custo": 4200.0,
     "_chave": ("2026-01-05", "ARM X", "FAB Y")},
    ...
  ],
  "totais": {"ton": 5000.0, "sacas": 83333.33, "custo": 210000.0},   # soma de TODAS as páginas do recorte
  "paginacao": {"pagina": 2, "num_paginas": 7, "total": 1380} | None,
}
```

- **Agregação por ORM.** `MovimentacaoDiaria.objects.filter(cenario_id=..., <filtros>)
  .values(*campos).annotate(ton=Sum('quantidade_ton'), custo=Sum('custo_total')).order_by(*campos)`.
  Nomes de armazém/fábrica resolvidos com um `.values('armazem__nome', 'fabrica__nome')` ou um
  `select_related`/map, conforme a visão.
- **Sacas = `ton * KG_PER_TON / KG_PER_SACA` calculada em Python** em cada linha (um único caminho
  de fórmula; `KG_PER_TON`/`KG_PER_SACA` importados de `apps.simulacao.services`).
- `custo` = `Sum('custo_total')` puro — safra/entressafra já embutida pelo engine.
- `_chave` = tupla **por nome** (não id): `(periodo_str, origem_nome?, destino_nome?)`. Cenários
  clonados têm ids novos e nomes iguais — casar por nome é o que faz a comparação entre clones
  funcionar.
- `totais_do_recorte` = um `aggregate(Sum('quantidade_ton'), Sum('custo_total'))` no recorte
  filtrado — barato, roda sempre (alimenta o card do topo).
- `cenarios_comparaveis` = cenários da cooperativa com `MovimentacaoDiaria`, exceto o atual,
  ordenados `-is_oficial, nome`.

**Filtros e semântica:**

- `data_de`/`data_ate` filtram sempre a coluna `data` das linhas diárias **antes** do agrupamento —
  inclusive no Mensal (um mês aparece se algum dia dele está no range) e no Total ("total do
  recorte").
- `armazem_ids`/`fabrica_ids`: `__in`. Opções de `Armazem.objects.filter(cenario_id=...)` /
  `Fabrica.objects.filter(cenario_id=...)` do cenário atual.

### 4. Comparação entre cenários

**`aplicar_comparacao(dados, cenario_comparado_id, periodo, agrupar, filtros)`:**

1. Se a visão é a **linha crua** (`periodo=diario` **e** `agrupar=fabrica_armazem`): não aplica. O
   parcial mostra a nota *"A comparação não se aplica à listagem de movimentações — troque o
   agrupamento ou o período."* As outras 8 visões (inclusive `mensal × fabrica_armazem`) recebem Δ.
2. Roda `agregar(cenario_comparado_id, periodo, agrupar, filtros)` — mesma forma, mesmos filtros —
   e indexa as linhas por `_chave`. Os filtros de armazém/fábrica são **traduzidos por NOME** para o
   cenário comparado antes de rodar (`_traduzir_filtros`): os ids não transferem entre clones, mas os
   nomes sim, consistente com a lógica de `_chave`. O mesmo vale para `dados_grafico` e para o card do
   topo (`totais_com_delta`).
3. Para cada linha do cenário atual, para `ton` / `sacas` / `custo`:
   - sem par no comparado → `_delta[key] = "novo"`.
   - par existe, `comparado[key] == 0`, atual `> 0` → `_delta[key] = None`.
   - senão → `_delta[key] = (atual[key] - comparado[key]) / comparado[key] * 100` (float).
   - `comparado[key] == 0` e `atual[key] == 0` → `_delta[key] = 0.0`.
4. **Linhas do comparado sem par no atual não aparecem** — a tabela é sempre a do cenário atual.
5. Grava cada Δ plano na linha: `linha["ton_delta"] / linha["sacas_delta"] / linha["custo_delta"]`
   (float | `None` | `"novo"`). Insere no `colunas` uma coluna-Δ **ao lado** de cada coluna
   `comparavel`: `Ton · Δ% · Sacas · Δ% · Frete · Δ%`, cada uma
   `{"key": "ton_delta", "label": "Δ%", "tipo": "delta"}`. `Δ%(sacas) ≡ Δ%(ton)` matematicamente,
   mas mantém-se a coluna para bater 1:1 com o pedido; sem special-case.
6. **Card do topo:** `totais_do_recorte` roda para os dois cenários → `delta` por métrica, mesma
   fórmula. `{ton, sacas, custo, delta: {ton, sacas, custo} | None}`.

**Cores e sinais** — templatetag novo `variacao` (junto de `moeda`/`volume` em
`apps/simulacao/templatetags/simulacao_filters.py`):

| Situação | Render |
|---|---|
| `Δ > 0` (atual **maior**) | `text-error` · `↑` · `+12,3%` |
| `Δ < 0` (atual **menor**) | `text-success` · `↓` · `−4,1%` (sinal de menos U+2212) |
| `Δ == 0` | `text-base-content/50` · `0,0%` |
| `_delta is None` (comparado = 0) | `—` neutro |
| `_delta == "novo"` | `badge badge-ghost badge-sm` "novo" |

`resultados.py` devolve só os números crus (`_delta`); a formatação/cor mora no templatetag.

### 5. View, parciais e ligação HTMX

**Rotas** (`apps/simulacao/urls.py`):

```python
path('cenarios/<int:cenario_id>/resultados/', views.resultados_tab, name='resultados_tab'),
path('cenarios/<int:cenario_id>/resultados/export/', views.resultados_export, name='resultados_export'),
```

**`resultados_tab(request, cenario_id)`** — `@login_required @requer_membro_organizacao`:

- `cenario = get_object_or_404(Cenario, id=cenario_id)` (via `objects` escopado → cenário de outra
  coop = 404).
- Se `not MovimentacaoDiaria.objects.filter(cenario_id=cenario_id).exists()` → renderiza estado
  vazio (`<c-card>` "Nenhum resultado. Rode uma simulação na aba Simulação.", sem combos), 200.
- Senão: `form = ResultadosForm(request.GET, cenario=cenario)`; `form.is_valid()`;
  `filtros = form.cleaned_data`; `periodo`/`agrupar`/`comparar`
  de `request.GET` (defaults `diario`/`fabrica_armazem`/`""`, validados contra o dict de config);
  `pagina` de `?page`.
- `dados = resultados.agregar(...)`; se `comparar` → `resultados.aplicar_comparacao(...)`;
  `card = resultados.totais_do_recorte(...)` (+ delta se comparar); `grafico = resultados.dados_grafico(...)`.
- Render:
  - sem `request.htmx` → `resultados.html`
  - `request.htmx` e `?parcial=tabela` → `_resultados_tabela.html`
  - `request.htmx` → `_resultados_content.html`

**Três alvos de swap, um endpoint:**

| Ação | `hx-get` | `hx-target` | Template |
|---|---|---|---|
| Clica na aba "Resultados" (no `_subnav`) | `…/resultados/` | `#cenario-content` | `_resultados_content.html` |
| Muda combo (Período/Agrupar/Comparar) ou "Aplicar" nos filtros | `…/resultados/?<form>` | `#resultados-area` | `_resultados_content.html` (do `#resultados-area`) |
| Clica numa página | `…/resultados/?<form>&page=N&parcial=tabela` | `#resultados-tabela` | `_resultados_tabela.html` |

**DOM do painel (`_resultados_content.html`):**

```
{% include "simulacao/_subnav.html" %}
<c-card>
  <form id="form-resultados"
        hx-get="{% url 'simulacao:resultados_tab' cenario.id %}"
        hx-target="#resultados-area" hx-swap="innerHTML" hx-push-url="true"
        hx-trigger="change from:(#id_periodo,#id_agrupar,#id_comparar), submit">
     linha 1: [Período ▾]  [Agrupar por ▾]                  [Comparar com ▾]
     linha 2: [Data de] [Data até] [Armazéns ▾▾] [Fábricas ▾▾]   [Aplicar] [Limpar]
  </form>
  <div id="resultados-area">
     <c-resumo-numerico>  Toneladas · Sacas · Frete (R$)   {# + Δ vs. comparado se houver #}
     <div class="flex gap-2">
       <a href="…/resultados/export/?<mesma query>&formato=xlsx" class="btn btn-outline btn-sm">Exportar (Excel)</a>
       <a href="…&formato=csv" class="btn btn-outline btn-sm">CSV</a>
     </div>
     {% if grafico %}<div id="resultados-grafico">{% include "simulacao/_resultados_grafico.html" %}</div>{% endif %}
     <div id="resultados-tabela">{% include "simulacao/_resultados_tabela.html" %}</div>
  </div>
</c-card>
```

- Combos disparam `change` → re-resolve tudo. Datas + multi-selects esperam **"Aplicar"** (`submit`).
  **"Limpar"** = link para a URL sem query.
- Filtros multi: `<select multiple size="4">` (o `ModelMultipleChoiceField` do `ResultadosForm`).
- Paginação: alvo `#resultados-tabela` (card e gráfico não mudam entre páginas).

**`_resultados_tabela.html`** — burro: `<thead>` de `dados.colunas`, `<tbody>` de `dados.linhas`,
célula despachada por `col.tipo` (`data_dia`→`|date:"d/m/Y"`, `data_mes`→`|date:"m/Y"`, `texto`→`{{ v }}`,
`num`→`|volume`, `moeda`→`|moeda`, `delta`→`{{ linha|item:col.key|variacao }}`).
`<tfoot>` com `dados.totais` aparece nas visões **não-paginadas**; nas 3 visões diárias paginadas o
card-resumo do topo já carrega os totais do recorte inteiro (um `<tfoot>` ali só duplicaria o card).
`{% empty %}` → "Nenhuma movimentação no recorte selecionado."

Django template não faz `linha[col.key]` com chave variável → **filtro novo `item`** (lookup de
dict, 3 linhas) junto de `variacao`. `aplicar_comparacao` grava cada Δ plano na linha sob a chave da
coluna-Δ (ex.: `linha["ton_delta"] = <float|None|"novo">`), e a coluna-Δ tem `{"key": "ton_delta",
"tipo": "delta"}` — o template faz `{{ linha|item:"ton_delta"|variacao }}`.

**`resultados.html`** = `{% extends "base.html" %}{% block content %}<div id="cenario-content">{% include "simulacao/_resultados_content.html" %}</div>{% endblock %}` — padrão das outras abas.

**`_subnav.html`** — 8ª aba, entre "Simulação" e "Assistente":

```html
<a href="{% url 'simulacao:resultados_tab' cenario_id=cenario.id %}"
   role="tab"
   {% if tem_resultado %}hx-get="{% url 'simulacao:resultados_tab' cenario_id=cenario.id %}"
   hx-target="#cenario-content" hx-push-url="true"{% else %}aria-disabled="true"
   title="Rode uma simulação"{% endif %}
   class="tab {% if active == 'resultados' %}tab-active{% endif %}
   {% if not tem_resultado %}tab-disabled opacity-50 pointer-events-none{% endif %}">Resultados</a>
```

`tem_resultado` vem de um **assignment tag** `{% cenario_tem_resultado cenario as tem_resultado %}`
no topo de `_subnav.html` (em `simulacao_filters.py`, faz o `.exists()` uma vez). Assim **nenhuma
das 7 views de aba existentes precisa mudar** — só o `_subnav.html` e o `resultados_tab` novo.
Uma query `.exists()` por render de subnav é barata.

### 6. Gráfico (Chart.js) — ADR 0013

- **Chart.js 4.x** via `cdn.jsdelivr.net/npm/chart.js@<versão exata>/dist/chart.umd.min.js` (mesmo
  CDN de daisyUI/htmx/Tabulator). Padrão de gráfico da suíte AgroVector.
- **Carregamento preguiçoso** — Chart.js **não** entra no `base.html`. Loader curto em
  `_resultados_grafico.html`: se `!window.Chart`, injeta o `<script src>` e chama
  `renderResultadosChart()` no `onload`; senão chama direto. `renderResultadosChart()` lê um
  `<script type="application/json" id="grafico-dados">`, destrói a instância anterior
  (`window._resultadosChart?.destroy()`) e recria.
- **Quando aparece** (`grafico is not None`):
  - `periodo == 'mensal'` (qualquer agrupar) → **barras por mês**: Toneladas (eixo esq.) + Frete R$
    (eixo dir.). Comparando: barra adjacente mais clara p/ Toneladas do comparado + linha tracejada
    p/ Frete do comparado.
  - `periodo == 'diario'` **e** `agrupar == 'nada'` → **linha** de Toneladas/dia (+ linha do
    comparado).
  - Todas as outras visões → sem gráfico.
- O gráfico usa **totais do período** (ignora o "Agrupar por" da tabela): `dados_grafico` roda seu
  próprio `agregar(periodo, 'nada', filtros)`. Retorno:
  `{"tipo": "bar"|"line", "labels": [...], "datasets": [{"label", "dados", "eixo"}]}` → serializado
  como JSON no `<script type="application/json">`.
- Rejeitados: Plotly (removido no Cutover, pesado), ApexCharts (ok, Chart.js menor/mais onipresente),
  barras CSS puras (sem eixo/tooltip para a comparação mensal).

### 7. Exportação

**`resultados_export(request, cenario_id)`** — `@login_required @requer_membro_organizacao`, reusa
`ResultadosForm`:

- Lê os mesmos params (`periodo`, `agrupar`, `comparar`, filtros) + `formato` (`xlsx`|`csv`, default
  `xlsx`). `formato` inválido → 400.
- Chama o **mesmo** `agregar()` + `aplicar_comparacao()`, **sem paginação** (`pagina=None` / recorte
  inteiro). Guard-rail: se o recorte tiver mais de `EXPORT_MAX = 50_000` linhas, 400 com mensagem
  "Refine os filtros para exportar."
- **xlsx** (`openpyxl`, já é dependência): uma aba, cabeçalho dos `colunas` (labels, com as `Δ%` se
  comparando), **números crus** — data como `datetime.date`, ton/sacas/custo/Δ como `float` — não
  strings pt-BR.
- **csv** (`csv` da stdlib): `delimiter=';'`, BOM UTF-8 (`﻿`), decimal com vírgula. (O dono pode
  trocar para ponto/`,` se quiser reimport.)
- `Content-Disposition: attachment; filename="resultados-<cenario-slug>-<periodo>-<agrupar>-AAAAMMDD.<ext>"`.
  Padrão `FileResponse` do `carga_template`.

### 8. Aba, contexto e tenancy

- `_subnav.html` renderiza a aba "Resultados" sempre; desabilitada quando `not tem_resultado`.
- `resultados_tab` e `resultados_export` usam `MovimentacaoDiaria.objects` / `Cenario.objects`
  (escopo do contextvar via `CooperativaScopeMiddleware`). Admin Vector com organização selecionada
  vê como super-membro (herdado da Fase 12). Cenário de outra coop → 404.
- `resultados.py` recebe `cenario_id` já validado pela view; usa `.objects` internamente.
  `test_resultados.py` seta o contextvar no `setUp` (`apps.core.tenancy.definir_cooperativa_atual`).

## Testes

TDD (red → green), testes em `apps/simulacao/tests/`, PostgreSQL local via `DJANGO_DB_*`.

- **`test_resultados.py`** — `agregar` para cada `(periodo, agrupar)` (cenário pequeno cruzando 2
  meses; somas por grupo, `colunas`, `sacas == ton*1000/60`, contagem, ordem); filtros (range,
  `__in`, combinados, vazio, filtro que zera); paginação (>100 linhas → pág. 1 = 100, pág. 2 =
  resto, `paginacao` dict; visões não-paginadas → `None`); `totais_do_recorte`;
  `cenarios_comparaveis`; `TruncMonth` na virada de mês; **tenancy** (`agregar(A)` nunca traz linha
  de B).
- **`test_resultados_comparacao.py`** — fórmula Δ%, casar por nome, `"novo"` / `None` / `0.0`, linha
  do comparado sem par não aparece, linha crua não ganha Δ, card `delta`.
- **`test_views_resultados.py`** — aba habilitada/desabilitada; full vs htmx vs `?parcial=tabela`;
  troca de combo → cabeçalhos certos; comparação → colunas Δ (e nota na crua); filtros estreitam;
  estado vazio (200, não 404); gate (anon→login, admin_vector sem org→403, com org→200); cenário de
  outra coop→404; paginação alvo `#resultados-tabela`, `page=2`.
- **`test_resultados_export.py`** — xlsx (aba, cabeçalho, contagem = recorte inteiro, números
  numéricos, `Content-Disposition`, `EXPORT_MAX`); csv (`;`, BOM, vírgula); respeita filtros +
  comparação; gate; `formato` inválido → 400.
- **`test_templatetags.py`** (estende) — `variacao`: `+12,3%`/`text-error`/↑, `−4,1%`/`text-success`/↓,
  `0,0%`, `None`→"—", `"novo"`→badge.
- **Render smoke** (`apps/core/tests/test_render_smoke.py`) — adiciona `simulacao:resultados_tab` à
  matriz por papel; 200 p/ todos os papéis de membro.
- Meta: suíte continua verde (hoje **367**) + os novos (~40). Sem snapshot visual automatizado.

## Verificação manual (a registrar no fim da fase)

- `python manage.py runserver` + `python manage.py procrastinate worker`.
- Rodar uma simulação; abrir a aba "Resultados"; percorrer os dois combos (todas as 9 formas);
  aplicar filtros de data/armazém/fábrica; selecionar um cenário de comparação e conferir as colunas
  Δ (cores/setas) e o card; exportar Excel e CSV e abrir os arquivos; ver o gráfico mensal e o
  diário-total, com e sem comparação; paginação na visão crua.
- `python manage.py check` e `python manage.py makemigrations --check --dry-run` limpos — esta fase
  **não cria migrations**.

## Docs (skill `sync-specs-skills` aplicável)

- Este SPEC.
- ADR `docs/decisions/0013-chartjs-padrao-grafico-agrovector.md` — Chart.js via CDN, lazy-load,
  contrato JSON + init-on-swap; rejeitados Plotly/ApexCharts/CSS.
- `docs/design-system/README.md` — nova seção "Gráficos (Chart.js)".
- `apps/simulacao/CLAUDE.md` — `resultados.py`, `forms.py`, a aba Resultados; nota sobre a
  duplicação deliberada com `services.py`.
- `CLAUDE.md` raiz — Tech Stack (+ Chart.js), seção `## Fase 13 — Painel de Resultados`, Roadmap →
  Fases 1–13.
- `CHANGELOG.md` + `VERSION` → `1.2.0`; tag `v1.2.0` (anotada, local — não pushed automaticamente).

## Rollout

Branch única `fase13-painel-resultados`. Execução subagent-driven em ondas, review por onda:

1. **Motor** — `resultados.py` (`agregar` + dict de config + filtros + paginação),
   `ResultadosForm` (`forms.py`), `columns` das visões, templatetags `variacao` + `item`, testes
   `test_resultados.py` + `test_templatetags.py`.
2. **Comparação** — `aplicar_comparacao`, `totais_do_recorte` com delta, `cenarios_comparaveis`,
   `test_resultados_comparacao.py`.
3. **View + parciais** — `resultados_tab`, rotas, `resultados.html` / `_resultados_content.html` /
   `_resultados_tabela.html`, a 8ª aba no `_subnav` + assignment tag `cenario_tem_resultado`, estado
   vazio, `test_views_resultados.py`, render smoke.
4. **Gráfico** — `dados_grafico`, `_resultados_grafico.html`, loader Chart.js, ADR 0013.
5. **Exportação** — `resultados_export`, botões, `test_resultados_export.py`.
6. **Docs** — ADR, guia, CLAUDE.md, CHANGELOG, VERSION, tag.

Merge fast-forward em `main` ao fim, tag `v1.2.0`. Sem deploy server-side automático.
