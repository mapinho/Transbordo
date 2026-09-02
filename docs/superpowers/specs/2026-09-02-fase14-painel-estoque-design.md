# Fase 14 — Painel de Movimentação de Estoque — Design

- Status: Em revisão (aguarda aprovação do dono do projeto)
- Data: 2026-09-02
- Roteiro: terceira fase de evolução pós-Cutover. Sucede a Fase 13 (Painel de Resultados de
  Transbordo, `docs/superpowers/specs/2026-09-01-fase13-painel-resultados-design.md`, ADR 0013).

## Contexto e objetivo

A Fase 13 entregou a aba **"Resultados"** por cenário — listagens e sumarizações das **movimentações
de transbordo** (`MovimentacaoDiaria`: frete e volume). O engine também grava, a cada execução
bem-sucedida e na **mesma transação**, duas tabelas de **balanço de estoque**:

- **`ResumoMensalFabrica`** (`cenario`, `fabrica`, `mes` `'YYYY-MM'`): `rec_produtor`, `rec_transbordo`,
  `esmagado`, `saldo_estoque`, `capacidade_estatica`, `excedente`.
- **`ResumoMensalArmazem`** (`cenario`, `armazem`, `mes`): `rec_produtor`, `envio_transbordo`,
  `vendas`, `saldo_estoque`, `capacidade_estatica`, `excedente`.

O engine inicializa **uma linha por (unidade, mês)** para todo mês do horizonte (mesmo meses sem
atividade) e grava, no fim de cada mês, o *snapshot* de `saldo_estoque` e o `excedente`
(`= max(0, saldo_estoque − capacidade_estatica)`).

Distinção de tipo dos campos:

- **Fluxos** (somáveis entre meses): `rec_produtor`, `rec_transbordo`, `esmagado`, `envio_transbordo`,
  `vendas`.
- **Níveis / snapshots de fim de mês** (não somáveis entre meses): `saldo_estoque`,
  `capacidade_estatica` (constante por unidade), `excedente`.

Hoje essas tabelas **não têm nenhuma UI** no app Django — só saem por `services.py`
(`get_factories_summary` / `get_warehouses_summary` / `compare_*` / `get_stock_excesses_report` /
`get_stock_ruptures_report`), consumido por MCP / Face JSON / Assistente de IA. As "listagens
separadas" de resumo mensal que existiam eram telas do Comigo/Streamlit (congelado).

Objetivo desta fase: **uma aba "Estoque" por cenário** com (a) as listagens por unidade (por armazém,
por fábrica) que faltam na UI Django, e (b) a **visão agregada do sistema** que hoje não existe em
lugar nenhum — recebimento, transbordo, esmagamento, vendas, saldo de estoque, capacidade estática e
excedente totais, por mês e num card de pico. Foco em **sinalizar excedente e ruptura**. Resolução de
dados no servidor, via HTMX.

## Escopo

**Dentro:**

- Nova aba **"Estoque"** no subnav do cenário (9ª), habilitada só quando há `ResumoMensal*`.
- Novo módulo **`apps/simulacao/estoque.py`** — motor de agregação por ORM sobre `ResumoMensalArmazem`
  / `ResumoMensalFabrica` (funções puras, `.objects` escopado).
- **`EstoqueForm`** em `apps/simulacao/forms.py` (`forms.Form` puro).
- Views novas em `apps/simulacao/views.py`: `estoque_tab`, `estoque_export`. Rotas em `urls.py`.
- Parciais HTMX: `templates/simulacao/estoque.html`, `_estoque_content.html`, `_estoque_area.html`,
  `_estoque_tabela.html`, `_estoque_grafico.html`.
- Combo **"Visão"** (`Sistema` · `Por armazém` · `Por fábrica`), combo de **cenário de comparação**,
  filtros (mês de/até, armazéns multi, fábricas multi), **card de pico** fixo no topo, gráfico de
  linha (Saldo total / Excedente total por mês).
- **Comparação** com um 2º cenário: colunas Δ% em todas as visões, e Δ no card.
- **Sinalização** de `excedente > 0` e `saldo_estoque < 0` (ruptura) — célula vermelha + fundo de
  linha tênue + ícone de alerta na ruptura.
- Exportação **Excel (openpyxl) + CSV (stdlib)** do recorte atual.
- **Renomear `cenario_tem_resultado` → `cenario_tem_simulacao`** (a checagem serve às duas abas).
- `VERSION` → `1.3.0`, `CHANGELOG.md`, tag `v1.3.0` (não pushed automaticamente).
- Seções novas em `CLAUDE.md` / `apps/simulacao/CLAUDE.md`.

**Fora:**

- Qualquer mudança em `engine.py`, `tasks.py`, `services.py`, `apps/integracoes`, `mcp_server.py`.
- Migrations — **nenhum model muda**.
- Refatorar / generalizar o scaffolding da Fase 13 num "mini-framework de painel" (Abordagem 2 do
  brainstorming, rejeitada — abstração prematura; a Fase 13 acabou de subir e nem passou por
  verificação manual).
- Colunas de **sacas** (só toneladas nesta fase; toggle de unidade fica pra depois).
- Ordenação por clique de coluna (YAGNI, igual Fase 13).
- UI de "chips" nos multi-selects (`<select multiple size="4">` simples).
- Uma visão "Por unidade" combinando armazém + fábrica numa tabela só (colunas incompatíveis).
- ADR novo (Chart.js já é ADR 0013; a arquitetura é o padrão da Fase 13).
- Novo conteúdo no `docs/design-system/README.md`.
- Deploy server-side automatizado.

## Decisões de arquitetura

### 1. Fronteira: `estoque.py` novo, ORM, `services.py` congelado

Mesma decisão da Fase 13 (Decisão 1 de lá). `apps/simulacao/estoque.py` é um módulo novo de funções
puras que agregam `ResumoMensal*` via ORM (`.values(...).annotate(Sum(...))`). **Não** reusa nem
altera `services.py` — que é "porte 1:1" (pandas), contrato de MCP / Face JSON / Assistente, e usa
`all_cooperativas` por decisão explícita (ADR 0006). `estoque.py` é camada de UI, chamada de uma view
onde o `CooperativaScopeMiddleware` já definiu o contextvar de tenant → usa **`Model.objects`**
(escopado, fail-closed), igual `resultados.py` e os grids editáveis.

Sobreposição deliberada de lógica com `services.py::get_factories_summary` /
`get_warehouses_summary` / `compare_*`. Aceitável: camadas diferentes, donos diferentes.

**Abordagem escolhida (Abordagem 1 do brainstorming):** módulo irmão paralelo. Reaproveita os
*padrões já provados* da Fase 13 — dispatch de parcial por `HX-Target`, templatetags `variacao` /
`item`, casamento por nome do `_chave`, parcial Chart.js lazy (ADR 0013) — mas como código próprio.
Aceita ~200–300 linhas de eco estrutural (dispatch 4-vias, helper de parse, esqueleto do export view)
em troca de: Fase 13 intocada, cada módulo legível sozinho, e os dois conjuntos de dados (que quase
não compartilham colunas) sem forçar uma abstração comum.

### 2. As três visões e o card de pico

**Combo "Visão"** (`ROTULOS_VISAO = (("sistema","Sistema"), ("armazem","Por armazém"),
("fabrica","Por fábrica"))`). O **card de pico** aparece sempre no topo, independente da visão.

**Card de pico — "o pior momento do sistema":**

| Métrica | Cálculo |
|---|---|
| Recebimento | Σ `rec_produtor` de **todas** as unidades (armazéns + fábricas), todos os meses (fluxo) |
| Transbordo | Σ `envio_transbordo` (armazéns), todos os meses — ≡ Σ `rec_transbordo` das fábricas por construção do engine |
| Esmagamento | Σ `esmagado` (fábricas), todos os meses |
| Vendas | Σ `vendas` (armazéns), todos os meses |
| Saldo de estoque | **máx** mensal de (Σ `saldo_estoque` de todas as unidades) — o mês de pico |
| Capacidade estática | Σ `capacidade_estatica` das unidades (constante entre meses) |
| Excedente | **máx** mensal de (Σ `excedente` de todas as unidades) — o pior mês |
| `saldo_min` (só interno) | **mín** mensal de (Σ `saldo_estoque`); se `< 0` → o card mostra "Saldo" como esse mínimo em vermelho, rótulo "ruptura em MM/AAAA" |

**Visão "Sistema" — 1 linha por mês** (célula = Σ de todas as unidades naquele mês):
`Mês · Recebimento · Transbordo · Esmagamento · Vendas · Saldo · Cap. Estática · Excedente`.
Rodapé (`<tfoot>`) com o fecho da coluna (Σ dos fluxos; pico de Saldo e Excedente; Cap. Estática
constante). Não pagina (≤ 12 meses).

**Visão "Por armazém" — 1 linha por (armazém, mês):**
`Armazém · Mês · Rec. Produtor · Envio Transbordo · Vendas · Saldo · Cap. Estática · Excedente`.

**Visão "Por fábrica" — 1 linha por (fábrica, mês):**
`Fábrica · Mês · Rec. Produtor · Rec. Transbordo · Esmagado · Saldo · Cap. Estática · Excedente`.

Visões por unidade: ordem fixa mês → nome da unidade; paginam (`PAGE_SIZE = 100`); **sem `<tfoot>`**
(o card de pico no topo já carrega o fecho do sistema — mesma decisão da Fase 13, Ruling 7). Só a
visão "Sistema" tem rodapé.

Todas as colunas são **toneladas** (`tipo: "num"`, formatação `volume`). Sem `moeda`, sem sacas.

### 3. `estoque.py` — assinaturas e formato

```python
PAGE_SIZE = 100
EXPORT_MAX = 50_000
ROTULOS_VISAO = (("sistema", "Sistema"), ("armazem", "Por armazém"), ("fabrica", "Por fábrica"))
VISOES = { "sistema": {...}, "armazem": {...}, "fabrica": {...} }   # colunas + fonte + pagina

class RecorteGrandeDemais(Exception): ...

def normalizar_visao(visao: str) -> str                         # inválido → "sistema"
def agregar(cenario_id: int, visao: str, filtros: dict,
            pagina: int | None = 1, limite: int | None = None) -> dict
def card_de_pico(cenario_id: int, filtros: dict) -> dict
def card_com_delta(cenario_id: int, cenario_comparado_id: int | None, filtros: dict) -> dict
def cenarios_comparaveis(cenario_id: int, cooperativa_id: int) -> list[dict]
def aplicar_comparacao(dados: dict, cenario_comparado_id: int, visao: str, filtros: dict) -> dict
def dados_grafico(cenario_id: int, filtros: dict, cenario_comparado_id: int | None) -> dict
def _traduzir_filtros(filtros: dict, cenario_id: int) -> dict    # id→nome→id, igual Fase 13
def _delta(atual, comparado)                                     # 5 linhas, duplicado (sem acoplar)
```

**`filtros`** = `EstoqueForm(request.GET, cenario=cenario).filtros_limpos()` (após `is_valid()`):
`{mes_de, mes_ate, armazem_ids, fabrica_ids}`. `mes_de` / `mes_ate` são strings `'YYYY-MM'`
(`<input type="month">`; filtro é comparação lexical de string, que ordena certo para `YYYY-MM`).
Chaves vazias = cenário inteiro. Na visão "Por fábrica" o `armazem_ids` é ignorado (e vice-versa);
na "Sistema" os dois filtram quais unidades entram nas somas.

`EstoqueForm` (`apps/simulacao/forms.py`, `Form` puro): `mes_de` / `mes_ate` = `CharField` com
`widget=forms.TextInput(attrs={"type": "month", ...})` e validação de formato `YYYY-MM`;
`armazem_ids` / `fabrica_ids` = `ModelMultipleChoiceField` com queryset
`Armazem.objects.filter(cenario=cenario)` / `Fabrica.objects.filter(cenario=cenario)`, `required=False`,
mesmos atributos de widget dos multi-selects da Fase 13 (`rounded-lg border border-base-300 bg-base-100
p-1 text-sm`, `size="4"` — **não** `.select` do daisyUI, que achata `<select multiple>`).
`filtros_limpos()` → dict com listas de ids e strings de mês (`None`/`""` ausentes).

**Retorno de `agregar()`:**

```python
{
  "colunas": [
    {"key": "mes",     "label": "Mês",        "tipo": "mes"},
    {"key": "unidade",  "label": "Armazém",    "tipo": "texto"},     # só nas visões por unidade
    {"key": "rec_produtor", "label": "Rec. Produtor", "tipo": "num", "comparavel": True},
    ...
    {"key": "excedente", "label": "Excedente", "tipo": "num", "comparavel": True},
  ],
  "linhas": [
    {"mes": "2026-01", "unidade": "ARM X",
     "rec_produtor": 100.0, ..., "saldo": 1200.0, "excedente": 0.0,
     "_chave": ("2026-01", "ARM X"), "_alerta": None},
    ...
  ],
  "totais": {"rec_produtor": ..., "saldo": <pico>, "excedente": <pico>, "capacidade": <const>, ...},
  "paginacao": {"pagina": 2, "num_paginas": 3, "total": 240} | None,
}
```

- **Agregação "sistema":** duas queries — `ResumoMensalArmazem.objects.filter(cenario_id=..., <filtros>)
  .values("mes").annotate(...)` e a irmã de fábrica — depois **merge por `mes` em Python** (os nomes
  de coluna diferem: armazém tem `envio_transbordo`/`vendas`, fábrica tem `rec_transbordo`/`esmagado`).
  `Recebimento` = Σ `rec_produtor` das duas; `Transbordo` = Σ `envio_transbordo` (armazéns).
- **Agregação "armazem" / "fabrica":** queryset `.filter(cenario_id=..., <filtros>)` ordenado por
  `mes, <unidade>__nome`. Uma linha já é 1 registro por (unidade, mês) — passa por
  `.values(...).annotate(Sum(...))` uniformemente (agrupamento no-op) por consistência.
- **`_chave`** = tupla por **nome** (não id): `("sistema" → (mes,); unidade → (mes, nome_unidade))`.
  Cenários clonados têm ids novos, nomes iguais — casar por nome faz a comparação entre clones
  funcionar (mesma lógica do `_chave` da Fase 13).
- **`_alerta`** ∈ `{None, "excedente", "ruptura"}`: `"ruptura"` se a linha tem `saldo < 0` (prioridade),
  senão `"excedente"` se tem `excedente > 0`, senão `None`.
- **`totais`**: fluxos = Σ das linhas do recorte inteiro; `saldo` e `excedente` = **pico** (máx
  mensal de Σ das unidades); `capacidade` = constante. Renderizado só no `<tfoot>` da visão
  "Sistema" (as por unidade não têm rodapé — o card carrega o fecho).
- **`limite`**: se não-nulo e o total de linhas do recorte exceder `limite` → levanta
  `RecorteGrandeDemais` **antes** de materializar as linhas (guard do export; conta com `.count()`).
- **`pagina=None`** → sem paginação (`linhas` = recorte inteiro, `paginacao=None`).

**`card_de_pico`** = agregações baratas (`aggregate(Sum(...))` para fluxos; `.values("mes")
.annotate(saldo=Sum(...), excedente=Sum(...))` e `max`/`min` em Python para os níveis) — não monta
linhas. **`card_com_delta`** roda `card_de_pico` nos dois cenários (comparado com `_traduzir_filtros`)
→ `delta` por métrica via `_delta`.

**`cenarios_comparaveis`** = cenários da cooperativa com pelo menos um `ResumoMensalArmazem` **ou**
`ResumoMensalFabrica`, exceto o atual, ordenados `-is_oficial, nome`.

### 4. Comparação entre cenários

Idêntico ao padrão da Fase 13 (Decisão 4 de lá):

**`aplicar_comparacao(dados, cenario_comparado_id, visao, filtros)`:**

1. Roda `agregar(cenario_comparado_id, visao, _traduzir_filtros(filtros, cenario_comparado_id),
   pagina=None)` e indexa por `_chave`.
2. Para cada linha do cenário atual, para cada coluna `comparavel` `m`:
   - sem par no comparado → `linha[f"{m}_delta"] = "novo"`.
   - par existe, `comparado[m] == 0`, atual `> 0` → `None`.
   - `comparado[m] == 0` e atual `== 0` → `0.0`.
   - senão → `(atual − comparado) / comparado * 100`.
3. Insere no `colunas` uma coluna-Δ **ao lado** de cada coluna `comparavel`:
   `{"key": f"{m}_delta", "label": "Δ%", "tipo": "delta"}`.
4. Linhas do comparado sem par no atual **não aparecem** — a tabela é sempre a do cenário atual.
5. **Comparação vale para as 3 visões** — não há exclusão de "linha crua" como na Fase 13 (todas as
   linhas aqui são agregados mensais que casam por `(mes, nome)`).
6. Card: `card_com_delta` → `{<métricas>, delta: {<métricas>} | None}`.

**Cores/sinais**: reaproveita o templatetag `variacao` da Fase 13 (`text-error` ↑ quando maior,
`text-success` ↓ quando menor, sinal U+2212, `—` neutro, badge "novo"). `estoque.py` devolve só os
números crus.

**Limitação herdada (Fase 13 Ruling 8):** `_traduzir_filtros` resolve `armazem_ids` / `fabrica_ids`
por nome. Se o cenário comparado **não tem** unidade de mesmo nome, a lista traduzida fica vazia e o
filtro é tratado como "sem filtro" — a comparação passa a cobrir o cenário comparado inteiro. Caso
raro (nomes disjuntos, contrário ao uso de clones); documentado, não tratado nesta fase.

**`dados_grafico`** ignora o filtro de unidade na parte comparada da mesma forma — mas como o gráfico
usa só os totais "Sistema", o efeito é o mesmo já descrito.

### 5. Sinalização de excedente e ruptura

Sem templatetag novo — condicionais no `_estoque_tabela.html`, dirigidas por `linha._alerta` e pelo
valor da célula:

| Condição | Render |
|---|---|
| célula **Excedente** com valor `> 0` | `class="text-error font-semibold"` |
| célula **Saldo** com valor `< 0` (ruptura) | `class="text-error font-semibold"` + ícone `<c-icon name="alert">` / ⚠ no início da linha |
| linha com `_alerta` não-nulo | `<tr class="bg-error/5">` (fundo tênue, varredura rápida) |
| card: `saldo_min < 0` | "Saldo" no card = `saldo_min` em `text-error`, rótulo "ruptura em MM/AAAA" |

O par (`excedente > 0`, `saldo < 0`) é exatamente o que `get_stock_excesses_report` /
`get_stock_ruptures_report` já detectam.

### 6. View, parciais e ligação HTMX

Espelha a Fase 13 (Decisão 5 de lá) ponto a ponto.

**Rotas** (`apps/simulacao/urls.py`, antes de `path('carga/', ...)`):

```python
path('cenarios/<int:cenario_id>/estoque/', views.estoque_tab, name='estoque_tab'),
path('cenarios/<int:cenario_id>/estoque/export/', views.estoque_export, name='estoque_export'),
```

**`estoque_tab(request, cenario_id)`** — `@login_required @requer_membro_organizacao`:

- `cenario = get_object_or_404(Cenario, id=cenario_id)` (via `objects` escopado → outra coop = 404).
- Se `not ResumoMensalArmazem.objects.filter(cenario_id=cenario_id).exists()` **e** idem fábrica →
  estado vazio ("Nenhum resultado de estoque. Rode uma simulação na aba Simulação."), 200.
- Senão: helper de módulo `_estoque_params(request, cenario) -> (form, filtros, visao, comparar_id)`
  (irmão do `_resultados_params`: `form.is_valid()`; `filtros = form.filtros_limpos()`; `visao` de
  `request.GET` validado por `estoque.normalizar_visao`; `comparar_id` = `int` seguro ou `None`).
- `dados = estoque.agregar(...)`; se `comparar_id` → `estoque.aplicar_comparacao(...)`;
  `card = estoque.card_com_delta(cenario.id, comparar_id, filtros)`;
  `grafico = estoque.dados_grafico(cenario.id, filtros, comparar_id)`.
- Render, dispatch de parcial por `request.htmx` + `request.htmx.target` (mesma lógica 4-vias do
  `_resultados_template`):
  - sem `request.htmx` → `estoque.html`
  - `request.htmx.target == 'estoque-tabela'` (ou `?parcial=tabela`) → `_estoque_tabela.html`
  - `request.htmx.target == 'estoque-area'` → `_estoque_area.html`
  - senão → `_estoque_content.html`

**Três alvos de swap, um endpoint** (aba → `#cenario-content`; form de filtros → `#estoque-area`;
paginação → `#estoque-tabela`).

**DOM (`_estoque_content.html`):**

```
{% include "simulacao/_subnav.html" %}
<c-card>
  <form id="form-estoque" hx-get=".../estoque/" hx-target="#estoque-area" hx-swap="innerHTML"
        hx-push-url="true" hx-trigger="change from:#id_visao, change from:#id_comparar, submit">
     [Visão ▾]  [Comparar com ▾]      [Mês de |month|] [Mês até |month|]
     [Armazéns ▾▾] [Fábricas ▾▾]      [Aplicar] [Limpar]
  </form>
  <div id="estoque-area">{% include "simulacao/_estoque_area.html" %}</div>
</c-card>
```

**`_estoque_area.html`**: card de pico (`<c-resumo-numerico>`) + Δ; botões de export
(`?<querystring>&formato=xlsx|csv`); `{% if grafico %}<div id="estoque-grafico">{% include
"simulacao/_estoque_grafico.html" %}</div>{% endif %}`; `<div id="estoque-tabela">{% include
"simulacao/_estoque_tabela.html" %}</div>`.

**`_estoque_tabela.html`** — burro: `<thead>` de `dados.colunas`, `<tbody>` de `dados.linhas`, célula
despachada por `col.tipo` (`mes` → `MM/AAAA`; `texto` → `{{ linha|item:col.key }}`; `num` →
`|volume` + classe de alerta condicional; `delta` → `{{ linha|item:col.key|variacao }}`).
`<tfoot>` com `dados.totais` **só na visão "Sistema"**. `{% empty %}` → "Nenhuma movimentação de
estoque no recorte."

**`estoque.html`** = `{% extends "base.html" %}{% block content %}<div id="cenario-content">{% include
"simulacao/_estoque_content.html" %}</div>{% endblock %}`.

**`_subnav.html`** — 9ª aba "Estoque", entre "Resultados" e "Assistente":

```html
<a href="{% url 'simulacao:estoque_tab' cenario_id=cenario.id %}" role="tab"
   {% if tem_simulacao %}hx-get="..." hx-target="#cenario-content" hx-push-url="true"
   {% else %}aria-disabled="true" title="Rode uma simulação"{% endif %}
   class="tab {% if active == 'estoque' %}tab-active{% endif %}
   {% if not tem_simulacao %}tab-disabled opacity-50 pointer-events-none{% endif %}">Estoque</a>
```

**Habilitação — rename `cenario_tem_resultado` → `cenario_tem_simulacao`:** `ResumoMensal*` e
`MovimentacaoDiaria` saem da mesma transação do engine, então a checagem "rodou uma simulação com
sucesso" serve às duas abas. O assignment tag em `_subnav.html` vira
`{% cenario_tem_simulacao cenario as tem_simulacao %}` e as abas "Resultados" e "Estoque" usam a
mesma variável. É 1 tag renomeada, 1 uso de template ajustado, 1 linha no smoke — uma `.exists()`
por render de subnav (não duas). `cenario_tem_simulacao` continua fazendo
`MovimentacaoDiaria.objects.filter(cenario_id=...).exists()` (é a tabela sempre escrita primeiro).

### 7. Gráfico (Chart.js) — padrão ADR 0013

`dados_grafico(cenario_id, filtros, cenario_comparado_id) -> {"tipo": "line", "labels": [...],
"datasets": [...]}` — **sempre linha**, sempre os números da visão "Sistema" (ignora o combo Visão,
igual a Fase 13). `labels` = meses `MM/AAAA`. `datasets`: `"Saldo total"` + `"Excedente total"`;
comparando → mais `"Saldo total (comparado)"` + `"Excedente total (comparado)"`, alinhados pelos
meses do cenário atual (mês ausente no comparado = 0).

Parcial `_estoque_grafico.html` com **ids próprios** (`#grafico-estoque`, `#grafico-estoque-dados`,
`window._estoqueChart`), mesmo loader lazy Chart.js do `_resultados_grafico.html` (injeta o `<script
src>` do CDN só quando há gráfico, `destroy()` antes de recriar). Retorno `None` só quando não há
`ResumoMensal*` — mas nesse caso a aba já está no estado vazio, então na prática `dados_grafico`
sempre devolve dict aqui. Um eixo só (toneladas); Saldo e Excedente na mesma escala.

### 8. Exportação

**`estoque_export(request, cenario_id)`** — `@login_required @requer_membro_organizacao`, reusa
`_estoque_params`:

- `formato` (`xlsx` | `csv`, default `xlsx`); inválido → 400.
- Chama o **mesmo** `estoque.agregar(..., pagina=None, limite=estoque.EXPORT_MAX)` dentro de
  `try/except estoque.RecorteGrandeDemais → HttpResponseBadRequest("Refine os filtros para
  exportar.")`. Depois `aplicar_comparacao` se `comparar_id`.
- **xlsx** (openpyxl): uma aba, cabeçalho dos `colunas` (labels, com as `Δ%` se comparando), **números
  crus** (mês como string `YYYY-MM`, métricas como `float`) — não strings pt-BR.
- **csv** (stdlib): `delimiter=';'`, BOM UTF-8 (`"﻿"` — escape, não char literal), decimal com
  vírgula.
- `Content-Disposition: attachment; filename="estoque-<cenario.id>-<visao>-AAAAMMDD.<ext>"`.
  Padrão `FileResponse`.

`RecorteGrandeDemais` é definida em `estoque.py` (2 linhas duplicadas — não acopla ao `resultados`).

### 9. Aba, contexto e tenancy

- `_subnav.html` renderiza a aba "Estoque" sempre; desabilitada quando `not tem_simulacao`.
- `estoque_tab` / `estoque_export` usam `ResumoMensal*.objects` / `Cenario.objects` (escopo do
  contextvar via `CooperativaScopeMiddleware`). Admin Vector com organização selecionada vê como
  super-membro (herdado da Fase 12). Cenário de outra coop → 404.
- `estoque.py` recebe `cenario_id` já validado pela view; usa `.objects` internamente. Testes de
  unidade setam o contextvar no `setUp` (`apps.core.tenancy.definir_cooperativa_atual`).

## Testes

TDD (red → green), testes em `apps/simulacao/tests/`, PostgreSQL local via `DJANGO_DB_*`.

- **`test_estoque_agregar.py`** — as 3 visões (fixture: 2 meses × 2 armazéns × 2 fábricas); somas por
  mês na "Sistema" (Σ das duas tabelas, `Recebimento` = Σ `rec_produtor` das duas, `Transbordo` = Σ
  `envio_transbordo`); 1 linha por (unidade, mês) nas por unidade; `colunas` por visão; `_chave`;
  `_alerta` (`excedente` / `ruptura` / prioridade da ruptura); filtros (`mes_de`/`mes_ate` lexical,
  `__in` de unidade, combinados, vazio, filtro que zera); paginação (>100 linhas → pág. 1 = 100, pág.
  2 = resto; "sistema" nunca pagina); `limite` → `RecorteGrandeDemais`; **tenancy** (`agregar(A)`
  nunca traz linha de B).
- **`test_estoque_card.py`** — `card_de_pico` (fluxos somados; `saldo`/`excedente` = máx mensal;
  `saldo_min` negativo → presente); `card_com_delta` (Δ por métrica, `None` sem comparado);
  `cenarios_comparaveis` (só cenários com `ResumoMensal*`, exceto o atual, ordem `-is_oficial, nome`).
- **`test_estoque_comparacao.py`** — Δ% por visão; casar por nome; `"novo"` / `None` / `0.0`; linha do
  comparado sem par não aparece; `_traduzir_filtros` entre clones (filtro de unidade + comparação →
  Δ numérico, não `"novo"`).
- **`test_estoque_grafico.py`** — `tipo == "line"`; `labels` = meses; datasets "Saldo total" /
  "Excedente total"; comparado adiciona 2 datasets.
- **`test_views_estoque.py`** — aba habilitada/desabilitada; full vs htmx vs `?parcial=tabela` (+
  `HX-Target`); troca de visão → cabeçalhos certos; comparação → colunas Δ; filtros estreitam; estado
  vazio (200, não 404); gate (anon→login, admin_vector sem org→403, com org→200); cenário de outra
  coop→404; paginação alvo `#estoque-tabela`; sinalização (linha `bg-error/5` + `text-error` quando há
  excedente/ruptura); `estoque_export` xlsx (aba, cabeçalho, números numéricos, `Content-Disposition`)
  / csv (`;`, BOM, vírgula) / `formato` inválido→400 / `EXPORT_MAX`→400 / anon→login / `?comparar`
  não-numérico→200.
- **`test_templatetags.py`** (ajuste) — `cenario_tem_resultado` → `cenario_tem_simulacao` (renomear o
  teste existente; comportamento idêntico).
- **Render smoke** (`apps/core/tests/test_render_smoke.py`) — adiciona `simulacao:estoque_tab` à
  matriz por papel; 200 p/ todos os papéis de membro no estado vazio.
- Meta: suíte continua verde (hoje **433**) + os novos (~45). Sem snapshot visual automatizado.

## Verificação manual (a registrar no fim da fase)

- `python manage.py runserver` + `python manage.py procrastinate worker`.
- Rodar uma simulação; abrir a aba "Estoque"; percorrer as 3 visões (Sistema / Por armazém / Por
  fábrica); aplicar filtros de mês e de unidade; selecionar um cenário de comparação e conferir as
  colunas Δ (cores/setas) e o card; conferir o destaque de **excedente** (célula vermelha) e de
  **ruptura** (célula vermelha + ícone + fundo de linha); exportar Excel e CSV e abrir os arquivos;
  ver o gráfico de linha (Saldo / Excedente), com e sem comparação; paginação nas visões por unidade.
- `python manage.py check` e `python manage.py makemigrations --check --dry-run` limpos — esta fase
  **não cria migrations**.

## Docs

- Este SPEC.
- **Sem ADR novo.** Sem conteúdo novo no `docs/design-system/README.md`.
- `apps/simulacao/CLAUDE.md` — entradas de `estoque.py` (motor de agregação ORM sobre `ResumoMensal*`;
  `.objects` escopado; duplica de propósito parte de `services.py::get_factories_summary` /
  `get_warehouses_summary` / `compare_*`), `EstoqueForm`, e a aba "Estoque" nas views (`estoque_tab`,
  `estoque_export`).
- `CLAUDE.md` raiz — nova seção `## Fase 14 — Painel de Movimentação de Estoque (concluída)`; Roadmap
  Status → "Fases 1–14 concluídas", `1.3.0`.
- `CHANGELOG.md` + `VERSION` → `1.3.0`; tag `v1.3.0` (anotada, local — não pushed automaticamente).

## Rollout

Branch única `fase14-painel-estoque`. Execução subagent-driven em ondas, review por onda:

1. **Motor** — `estoque.py` (`VISOES` + `agregar` + filtros + paginação + `_alerta` + `RecorteGrandeDemais`),
   `EstoqueForm`, testes `test_estoque_agregar.py`.
2. **Card + comparação** — `card_de_pico` / `card_com_delta`, `cenarios_comparaveis`,
   `aplicar_comparacao`, `_traduzir_filtros`, `_delta`, `dados_grafico`; testes `test_estoque_card.py`
   / `test_estoque_comparacao.py` / `test_estoque_grafico.py`.
3. **View + parciais** — rename `cenario_tem_resultado` → `cenario_tem_simulacao`, `estoque_tab`,
   `_estoque_params`, rotas, 5 parciais, 9ª aba, estado vazio, sinalização; `test_views_estoque.py`,
   render smoke, ajuste de `test_templatetags.py`.
4. **Gráfico + exportação** — `_estoque_grafico.html` (loader lazy, ids próprios), `estoque_export`,
   botões.
5. **Docs + gate** — `CLAUDE.md` / `apps/simulacao/CLAUDE.md` / `CHANGELOG` / `VERSION` → `1.3.0`,
   suíte completa, tag `v1.3.0`.

Merge fast-forward em `main` ao fim. Sem deploy server-side automático.
