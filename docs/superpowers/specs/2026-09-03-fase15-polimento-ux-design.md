# Fase 15 — Polimento UX Resultados + Estoque — Design

- Status: Em revisão (aguarda aprovação do dono do projeto)
- Data: 2026-09-03
- Roteiro: quarta fase de evolução pós-Cutover. Sucede a Fase 14 (Painel de Movimentação de
  Estoque, `docs/superpowers/specs/2026-09-02-fase14-painel-estoque-design.md`).

## Contexto e objetivo

As Fases 13 e 14 entregaram as abas **"Resultados"** (movimentações de transbordo) e **"Estoque"**
(balanço mensal). A aba Estoque foi construída como espelho ponto a ponto da Resultados. Uma revisão
de design com a app no ar (2026-09-02, prints em `.superpowers/` — não versionados) levantou ~14
achados P1/P2. A maioria dos itens compartilhados existe **idêntica** nas duas abas (são espelhos),
então corrigir só a Estoque faria as duas divergirem.

Objetivo desta fase: **polir a UX das duas abas juntas**, priorizando (a) os itens compartilhados e as
lacunas do guia normativo do design system (`docs/design-system/README.md` §7 — tema e paleta do
gráfico), e (b) os itens só da Estoque onde o card de pico entrega menos do que promete. Nenhuma
mudança de contrato de dado, de model, de comportamento de negócio ou de engine.

**Abordagem (decidida no brainstorming):** faseta única, ordem de execução "compartilhado primeiro"
— a fundação (`variacao`, tema do gráfico, §7 do DS) cai e fica testável antes de as mudanças visíveis
empilharem em cima. **Rejeitadas:** duas sub-fases (cerimônia demais para o volume); extrair os
parciais compartilhados num "framework de painel" antes de corrigir (abstração prematura — mesma razão
que a Fase 14 rejeitou o "mini-framework de painel").

## Escopo

**Dentro:**

- **`variacao`** (`apps/simulacao/templatetags/simulacao_filters.py`) — limiar neutro para Δ que
  arredonda para `0,0%`.
- **Gráfico** — tema (relê tokens, re-renderiza no toggle) + paleta AgroVector, nos dois parciais
  (`_resultados_grafico.html`, `_estoque_grafico.html`); evento `vector:themechange` na `base.html`;
  snippet compartilhado `_grafico_tokens.html`; emenda do §7 do DS.
- **Tabelas** dos dois pares de parciais — Δ da comparação **embutido na célula** (deixa de ser
  coluna); `aplicar_comparacao` (`resultados.py` + `estoque.py`) para de inserir colunas `_delta`;
  realce de linha de alerta visível nos dois temas (só Estoque); `<thead>` fixo + 1ª coluna fixa nas
  visões por unidade; coluna "Mês" sai das visões por unidade; legenda "Valores em toneladas"; ids
  dos selects hand-rolled prefixados; contêiner do gráfico `hidden sm:block`; rótulos dos botões de
  export uniformizados.
- **Barra de filtros** dos dois content partials — filtros avançados (mês/data + multi-selects) num
  `<details>` fechado por default, com contador.
- **Card de pico do Estoque** (`_estoque_area.html`) — barra de ocupação (saldo × capacidade ×
  excedente) + legenda "Pico do sistema · `<mês>`" + os 7 tiles (acrescenta Esmagamento e Vendas) com
  Saldo/Excedente coloridos por estado. `card_de_pico` devolve `mes_pico` / `ocupacao_pct` /
  `excedente_pct`.
- **Faixas de mês** nas visões por unidade da Estoque — cada mês vira uma faixa que carrega os totais
  do sistema daquele mês.
- `VERSION` → `1.4.0`, `CHANGELOG.md`, seções em `CLAUDE.md` / `apps/simulacao/CLAUDE.md`.
- Higiene: `.gitignore` += `.playwright-mcp/`; prints da revisão movidos para fora da raiz.

**Fora:**

- Qualquer mudança em `engine.py`, `tasks.py`, `services.py`, `apps/integracoes`, `mcp_server.py`.
- Migrations — **nenhum model muda**.
- ADR novo (Chart.js já é ADR 0013; a mudança é no guia §7, não na decisão).
- Extrair/generalizar os parciais compartilhados das duas abas num componente único.
- Overlap do seletor de organização com o e-mail do usuário no header no mobile — é `base.html`,
  pré-existente, não específico das duas abas.
- Toggle de unidade (sacas), ordenação por clique de coluna, "chips" nos multi-selects — todos já
  fora de escopo desde as Fases 13/14 (YAGNI).
- Renomear o badge "Simulação" / "Oficial" do `_cenario_header.html` (compartilhado por todas as abas
  — fora do foco).
- Snapshot visual automatizado.
- Deploy server-side.

## Decisões de arquitetura

### 1. `variacao` — limiar neutro

`apps/simulacao/templatetags/simulacao_filters.py::variacao(valor)`. Entrada inalterada
(`float | None | "novo" | ""`). Única mudança: **antes** dos ramos `valor > 0` / `valor < 0`, se
`isinstance(valor, (int, float))` e `abs(valor) < 0.05` (arredonda para `0,0%` com 1 decimal),
renderiza o neutro — `<span class="text-base-content/50">0,0%</span>` — sem seta e sem cor. É o mesmo
HTML do ramo do zero exato de hoje; o ramo do zero exato passa a ser coberto por este.

Motivação: com dados quase iguais entre cenários o Δ vem como `±3e-7`; hoje `valor > 0` (no float
cru) pinta `↑ +0,0%` em `text-error`, texto "0,0%" mas com seta e cor — ruído. `text-error` /
`text-success` já são tokens que adaptam nos dois temas; os ramos de valor não-nulo não mudam.
`"novo"` (badge), `None` (`—`) e não-número (`""`) inalterados.

### 2. Gráfico — tema e paleta (§7 do design system)

**Evento de tema.** `base.html`: a função `vectorApplyTheme(pref)` e o listener de
`matchMedia('(prefers-color-scheme: dark)')` disparam
`window.dispatchEvent(new CustomEvent('vector:themechange'))` **depois** de gravar o `data-theme` no
`<html>`. É a única linha nova no arquivo — não toca os dois blocos de `<style>` nem o script
anti-flash (o checklist de portabilidade do §8 proíbe só esses).

**Snippet de tokens.** `templates/simulacao/_grafico_tokens.html` — um `<script>` que define
`window.vectorChartTokens()` devolvendo `{text, grid, accent, error, primary, dashed(hex) -> "rgba(...)"}`
lendo `getComputedStyle(document.documentElement).getPropertyValue('--color-…')`. Incluído pelos dois
parciais de gráfico **antes** do bloco de `render()`. O loader do CDN e o `render()` continuam
por-parcial (padrão "duplica de propósito" já adotado para o loader IIFE).

**Cada parcial de gráfico** (`_resultados_grafico.html`, `_estoque_grafico.html`):
- `render()` chama `vectorChartTokens()` no início e usa os valores em `options.scales.*.ticks.color`
  / `.grid.color` / `.title.color` e `options.plugins.legend.labels.color` (`text` para
  texto/legenda, `grid` para as linhas de grade).
- Cores de série vêm dos tokens: **Estoque** — Saldo = `accent`, Excedente = `error`; **Resultados**
  — Toneladas = `accent`, Frete = `primary`. Série do cenário comparado: mesma cor,
  `borderDash: [5, 4]`, cor passada por `dashed(...)` (~0.55 de opacidade).
- Registra `window.addEventListener('vector:themechange', render)` **uma vez** — guarda contra bind
  duplo nos swaps HTMX (ex.: `if (!window.__estoqueThemeBound) { window.__estoqueThemeBound = true;
  addEventListener(...) }`). No swap, o `render()` inline reexecuta e re-lê os tokens de qualquer
  forma; o listener cobre o toggle de tema puro (sem swap).

**§7 do DS** ganha:
- bullet **"Tema"**: o gráfico relê `--color-*` a cada `render()` e re-renderiza no
  `vector:themechange` (disparado por `vectorApplyTheme`); cores de série vêm dos tokens
  (`accent` / `error` / `primary`), nunca das cores default do Chart.js; série comparada = mesma cor
  com `borderDash` + opacidade ~0.55; eixos/legenda em `--color-base-content`, grade em
  `--color-base-300`.
- terceira "forma padronizada": **linha mensal, 2 séries no mesmo eixo `y`** (Saldo total / Excedente
  total — a forma da Estoque), ao lado das duas que já estão documentadas (barras mensais de dois
  eixos; linha diária de série única).

### 3. Comparação — Δ embutido na célula

**`aplicar_comparacao`** nos dois módulos (`resultados.py`, `estoque.py`): **para de reconstruir
`dados["colunas"]`** (deixa de inserir os dicts `{"key": f"{m}_delta", "tipo": "delta"}`). Continua
gravando `linha[f"{m}_delta"]` (`float | None | "novo"`) para cada coluna `comparavel` e
`dados["totais_delta"]`. Efeito colateral positivo: some o rebuild da lista `colunas` — e com ele o
risco de mutação do `VISOES` global que os revisores das Fases 13/14 vigiaram (`agregar` devolve
`cfg["colunas"]`, que **é** `VISOES[visao]["colunas"]`).

A linha crua do Resultados (`("diario", "fabrica_armazem")`) continua com `comparacao_ignorada = True`
e retorno antecipado — sem Δ, com o `<p>` de aviso já existente.

**`_resultados_tabela.html` / `_estoque_tabela.html`**, ramo de célula `num` / `moeda`: renderiza o
valor e, quando `dados.totais_delta` existe (comparação ativa) e a linha tem a chave
`{{ col.key }}_delta`, um `<span class="block text-xs leading-tight">{{ linha|item:dk|variacao }}</span>`
logo abaixo (`{% with dk=col.key|add:'_delta' %}` — o filtro `add` do Django concatena strings). O
`<tfoot>` faz o mesmo lendo `dados.totais_delta|item:col.key` — o que também preenche os `<td>` que
antes ficavam vazios sob as colunas Δ.

Sem coluna de dimensão `tipo == "delta"` mais — o ramo pode ser removido dos dois parciais.

### 4. Barra de filtros — `<details>` para os avançados

`_resultados_content.html` e `_estoque_content.html`:

- **Linha principal** (sempre visível): Visão (Estoque) ou Período + Agrupar (Resultados) ·
  Comparar com · botão Aplicar · link Limpar.
- **`<details>` "Filtros"** (elemento nativo, sem JS): dentro, os inputs de mês/data (de + até) e os
  dois `<select multiple>` num grid limpo. No `<summary>`, um `badge badge-sm` com a contagem de
  filtros avançados preenchidos (`0` → sem badge). `<details {% if filtros_avancados_ativos %}open{% endif %}>`
  — abre sozinho quando há filtro em uso.
- **A view passa `filtros_avancados_ativos`** ao contexto — `True` quando qualquer um de `mes_de` /
  `mes_ate` / `data_de` / `data_ate` / `armazem_ids` / `fabrica_ids` do `filtros` limpo é não-vazio.
  E `filtros_avancados_count` (int) para o badge. Helpers pequenos em `_estoque_params` /
  `_resultados_params` (ambas já devolvem `filtros`).
- `hx-trigger` do form **inalterado**: auto-submete em `change` de Visão/Período/Agrupar/Comparar;
  mês/data/unidade continuam exigindo "Aplicar". Os seletores `from:#...` do `hx-trigger` acompanham
  o rename de id da Decisão 5.

### 5. Ajustes de tabela e diversos

- **`<thead>` fixo + 1ª coluna fixa — só nas visões por unidade** (as longas). O contêiner
  (`_estoque_tabela.html`, ramo `visao in {"armazem","fabrica"}`) vira
  `<div class="max-h-[70vh] overflow-auto …">`; `<thead class="sticky top-0 z-10 bg-base-100">`; a
  1ª `<td>`/`<th>` de cada linha `sticky left-0 bg-base-100 z-10` (na banda, `z` acima do resto). A
  visão Sistema (≤ 14 linhas) e as tabelas do Resultados ficam como estão.
- **Coluna "Mês" sai das visões por unidade** da Estoque. `estoque.py`:
  `VISOES["armazem"]["colunas"]` e `VISOES["fabrica"]["colunas"]` perdem o `_COL_MES` inicial; a 1ª
  coluna passa a ser `{"key": "unidade", …}`. `linha["mes"]` **continua** no dict de cada linha (para
  `{% ifchanged %}` e para o `_chave = (mes, unidade)`). A visão Sistema mantém a coluna "Mês".
- **Realce de alerta** (`_estoque_tabela.html`): a linha com `_alerta` passa de `bg-error/5` para
  `bg-error/10` + `border-l-4 border-error`; a de `_alerta == "ruptura"` fica `bg-error/20` + `⚠` no
  início da 1ª coluna. Célula de Excedente `> 0` e de Saldo `< 0` continuam `text-error font-semibold`
  (o SPEC da Fase 14 §5 já pede isso). Verificar contraste nos dois temas.
- **Legenda de unidade**: `<p class="mb-2 text-xs text-base-content/60">Valores em toneladas</p>`
  acima de cada tabela das duas abas (substitui a ideia de `(t)` nos headers).
- **IDs dos selects hand-rolled**: `id_visao` → `estoque-visao`; `id_comparar` (Estoque) →
  `estoque-comparar`; `id_periodo` / `id_agrupar` / `id_comparar` (Resultados) → `resultados-periodo`
  / `resultados-agrupar` / `resultados-comparar`. Ajustar os `hx-trigger` correspondentes. Os campos
  do `Form` (`{{ form.mes_de }}` etc.) mantêm os ids gerados pelo Django (`id_mes_de`, …) — só os
  `<select>` escritos à mão mudam.
- **Gráfico no mobile**: o contêiner (`{% if grafico %}<div id="…-grafico" …>`) ganha
  `hidden sm:block`. O §7 do DS já estabelece "o gráfico é complemento, nunca a única via ao dado".
- **Botões de export**: "Exportar (Excel)" / "CSV" → **"Excel" / "CSV"** (os dois nus), `btn-outline
  btn-sm` inalterado, nas duas abas.

### 6. Card de pico do Estoque

`_estoque_area.html` (só Estoque):

- **Legenda** `Pico do sistema · {{ card.mes_pico }}` (`text-xs text-base-content/60 uppercase`)
  acima da barra.
- **Barra de ocupação** — um `<div class="relative h-6 rounded bg-base-200 border border-base-300
  overflow-hidden">` com:
  - preenchido: `<div style="width: {{ card.ocupacao_pct }}%">` em `bg-accent` (= `min(saldo,
    capacidade) / capacidade`);
  - marca de 100%: `<div class="absolute … w-0.5 bg-primary">` em `left: 100%` (borda direita do
    trilho — ou um tick que transborda levemente);
  - excedente: um segmento hachurado `bg-error` à direita do trilho, largura
    `min(card.excedente_pct, 100)%` — o contêiner externo do card permite o overflow à direita (o
    trilho tem `overflow-hidden`, o segmento de excedente vive **fora** do trilho, num wrapper
    irmão). Quando `excedente_pct > 100`, o segmento fica saturado em +100% e o número
    (`+{{ card.excedente|volume }} t ({{ card.excedente_pct }}%)`) é a fonte de verdade.
  - ruptura (`card.saldo_min < 0`): sem preenchimento à direita; um recuo `bg-error` **antes** do
    zero (à esquerda do trilho) + `<span class="text-error">Ruptura em {{ card.mes_ruptura }}</span>`.
- Abaixo da barra, uma linha `text-xs`: `Saldo {{ card.saldo|volume }} t · Capacidade
  {{ card.capacidade|volume }} t · Excedente <span class="text-error">+{{ card.excedente|volume }} t
  ({{ card.excedente_pct }}%)</span>` (o trecho de excedente só quando `> 0`).
- **`<c-resumo-numerico>`** (o componente do DS, **sem alteração**) com **7 tiles**: Recebimento,
  Transbordo, Esmagamento, Vendas, Saldo (pico), Cap. Estática, Excedente (pico). O tile de Saldo
  fica `text-error` quando `card.mes_ruptura` (mostrando `saldo_min`) ou `card.saldo >
  card.capacidade`; o de Excedente `text-error` quando `card.excedente > 0`. Os `stat-desc` de Δ
  (comparação) ficam nos 7 tiles — inclusive Cap. Estática, cujo Δ vai renderizar o neutro `0,0%`
  via Decisão 1 (capacidade ~constante entre cenários). Consistente com a tabela, que também tem Δ
  inline em todas as métricas `comparavel`.

**`estoque.py::card_de_pico`** devolve, além das chaves atuais:
- `mes_pico` — `_mes_ptbr` do mês de maior `saldo` (o mesmo mês cujo `saldo` já é devolvido em
  `card["saldo"]`); `""` para recorte vazio.
- `ocupacao_pct` — `round(min(saldo, capacidade) / capacidade * 100, 1)` se `capacidade > 0`, senão
  `0.0`.
- `excedente_pct` — `round(excedente / capacidade * 100, 1)` se `capacidade > 0`, senão `0.0`.

`card_com_delta` repassa as três (não calcula delta delas — são derivadas). Sem filtro de template
novo — os percentuais já vêm prontos.

### 7. Faixas de mês nas visões por unidade

`estoque.py::agregar`, ramo `visao in {"armazem", "fabrica"}`: acrescenta ao retorno
`dados["faixas"]` — um `dict` `{mes: linha_do_sistema}` onde `linha_do_sistema` é o item de
`_agregar_sistema(cenario_id, filtros)` daquele mês (as 7 métricas + `_alerta`). Só os meses
presentes nas `linhas` do recorte entram (não paga cálculo para meses filtrados fora). A visão
Sistema **não** recebe `faixas` (`None` ou ausente).

`_estoque_tabela.html`, ramo por unidade: dentro do `{% for linha in dados.linhas %}`, um
`{% ifchanged linha.mes %}` emite antes da linha um `<tr class="band bg-base-200 font-medium">`, com
exatamente duas `<td>`:
- **1ª** — `<td class="sticky left-0 bg-base-200 z-20">{{ linha.mes|mes_extenso }}</td>` (ocupa a
  coluna de dimensão "unidade"; fica fixa junto com a 1ª coluna das linhas normais). `mes_extenso`
  é um filtro novo em `simulacao_filters.py` — `"2026-02" -> "Fevereiro 2026"` (`MESES_PT` tuple, ~6
  linhas); mais limpo que formatar no `estoque.py`.
- **2ª** — `<td colspan="{{ dados.colunas|length|add:'-1' }}" class="text-right text-xs">` —
  `sistema — saldo {{ f.saldo|volume }} · cap {{ f.capacidade|volume }} · excedente
  <span class="{% if f.excedente %}text-error{% endif %}">{{ f.excedente|volume }}</span>`, onde
  `f = dados.faixas|item:linha.mes`.
- `{% ifchanged %}` é built-in do Django e acerta o primeiro item de cada página na paginação (sempre
  "mudou" na primeira iteração).

## Testes

TDD (red → green), testes em `apps/simulacao/tests/` e `apps/core/tests/`, PostgreSQL local.

- **`test_templatetags_variacao.py`** (novo) — `variacao(0.03)` / `variacao(-0.04)` → span neutro sem
  seta/cor; `variacao(0.0)` → idem; `variacao(0.06)` → `↓`/`text-success`; `variacao(120.0)` →
  `↑ +120,0%` / `text-error`; `variacao("novo")` → badge; `variacao(None)` → `—`; `variacao("")` →
  `""`.
- **`test_resultados_comparacao.py` / `test_estoque_comparacao.py`** — `aplicar_comparacao` **não**
  altera `dados["colunas"]` (nenhuma coluna com `tipo == "delta"` ou `key` terminando em `_delta`);
  `linha["<m>_delta"]` e `dados["totais_delta"]` presentes; casar por `_chave`; `"novo"` para chave
  sem par. **Atualizar** as asserções da Fase 13/14 que hoje verificam a inserção da coluna
  (`"saldo_delta" in [c["key"] …]`, `keys.index("saldo_delta") == keys.index("saldo") + 1`) — passam
  a verificar a **ausência**.
- **`test_estoque_card.py`** — `card_de_pico` devolve `mes_pico` (mês do saldo máximo),
  `ocupacao_pct`, `excedente_pct` (com `capacidade == 0` → `0.0`, sem `ZeroDivisionError`);
  `card_com_delta` repassa as três.
- **`test_estoque_agregar.py`** — visão por unidade: `dados["faixas"]` é `dict` keyed por mês, cada
  valor com as 7 métricas do sistema; só meses do recorte; visão Sistema sem `faixas`. `"mes"` **não**
  está em `[c["key"] for c in dados["colunas"]]` nas visões por unidade; **está** na Sistema.
- **`test_estoque_config.py`** — `VISOES["armazem"]["colunas"][0]["key"] == "unidade"` (era
  `["mes","unidade"]`); Sistema mantém `"mes"` primeiro.
- **`test_templatetags_*` / render** — `mes_extenso("2026-02") == "Fevereiro 2026"`.
- **`test_views_estoque.py` / `test_views_resultados.py`** — contêiner do gráfico com classe
  `hidden sm:block`; `<details` no HTML da barra de filtros, **fechado** sem filtro avançado e com
  `open` quando `?armazem_ids=` (ou `?mes_de=`) na querystring; badge de contagem correto;
  `sticky` (thead) e `left-0` presentes na visão por unidade e ausentes na Sistema; `<tr class="band`
  quando visão por unidade, com e sem comparação; ids `estoque-visao` / `resultados-periodo` no HTML
  (atualizar asserções que citam `id_visao` / `id_periodo`); modo comparação → não há `<th>Δ%` no
  `<thead>`, e o Δ aparece dentro do `<td>` da métrica.
- **`test_base_template.py`** — a `base.html` contém `vector:themechange` e o `dispatchEvent` dentro
  de `vectorApplyTheme`.
- **`test_render_smoke.py`** — segue verde (as duas abas, todos os papéis de membro).
- Meta: suíte continua verde (hoje **490**) + os novos/ajustados (~20). Sem snapshot visual.

## Verificação manual (a registrar no fim da fase)

- `python manage.py runserver` + `python manage.py procrastinate worker`; um cenário com simulação.
- **As duas abas** × **os dois temas** × **mobile (~390px)**: layout limpo, sem quebra da barra de
  filtros, gráfico escondido no mobile, tabela rola na horizontal com 1ª coluna/thead fixos nas
  visões por unidade.
- **Toggle de tema com o gráfico na tela** — eixos, grade e legenda re-tematizam na hora; cores de
  série seguem a paleta (não as default do Chart.js).
- **Comparação** — Δ embutido nas células (métrica + variação juntas); sem ruído `↑ +0,0%`; `<tfoot>`
  sem `<td>` vazios.
- **Estoque / card** — barra de ocupação com saldo abaixo e acima da capacidade; caso de ruptura
  (recuo vermelho + rótulo); os 7 tiles; Saldo/Excedente coloridos quando fora do lugar.
- **Estoque / faixas de mês** — nas visões por armazém e por fábrica; totais do sistema corretos por
  mês; paginação preserva a faixa no topo da página.
- **Filtros** — `<details>` fechado por default, abre com contador quando há filtro; "Aplicar" e
  "Limpar" funcionam.
- `python manage.py check` + `makemigrations --check --dry-run` limpos — **sem migrations**.

## Docs

- Este SPEC.
- **`docs/design-system/README.md` §7** — bullet "Tema" + terceira "forma padronizada" (Decisão 2).
  **Sem ADR novo.**
- **`CLAUDE.md` raiz** — nova seção `## Fase 15 — Polimento UX Resultados + Estoque (concluída)`;
  Roadmap Status → "Fases 1–15 concluídas", `1.4.0`.
- **`apps/simulacao/CLAUDE.md`** — `aplicar_comparacao` não insere mais colunas Δ (embutido na
  célula); `card_de_pico` +`mes_pico`/`ocupacao_pct`/`excedente_pct`; `agregar` por unidade +`faixas`
  e sem coluna "Mês"; `_estoque_area.html` com barra de ocupação; `variacao` com limiar neutro;
  novo `mes_extenso`.
- **`CHANGELOG.md`** + **`VERSION`** → `1.4.0`; tag `v1.4.0` (anotada, local — não pushed
  automaticamente).
- **`.gitignore`** += `.playwright-mcp/`.

## Rollout

Branch única `fase15-polimento-ux`. Execução subagent-driven, review por onda:

1. **Fundação** — `variacao` (Decisão 1) + `_grafico_tokens.html` + evento `vector:themechange` na
   `base.html` + tema/paleta nos dois parciais de gráfico (Decisão 2); emenda do §7 do DS; testes
   `test_templatetags_variacao.py`, ajuste de `test_base_template.py`.
2. **Comparação embutida** — `aplicar_comparacao` nos dois módulos deixa de inserir colunas; os dois
   parciais de tabela renderizam Δ inline + `<tfoot>`; testes de comparação (Resultados + Estoque)
   atualizados.
3. **Barra de filtros** — `<details>` nos dois content partials + rename de ids + `hx-trigger`;
   ajustes de `test_views_*`.
4. **Ajustes de tabela** — `<thead>`/1ª coluna fixos nas visões por unidade, realce de alerta,
   legenda "Valores em toneladas", gráfico `hidden sm:block`, rótulos de export; `test_views_*`.
5. **Card do Estoque** — `card_de_pico` +3 chaves, barra de ocupação + 7 tiles no `_estoque_area.html`;
   `test_estoque_card.py`.
6. **Faixas de mês** — `agregar` por unidade +`faixas` **e** remoção do `_COL_MES` de
   `VISOES["armazem"]`/`["fabrica"]`, filtro `mes_extenso`, `{% ifchanged %}` no
   `_estoque_tabela.html`; `test_estoque_config.py` / `test_estoque_agregar.py` /
   `test_views_estoque.py`. (A coluna "Mês" só sai junto com as faixas que a substituem.)
7. **Docs + gate** — `CLAUDE.md` / `apps/simulacao/CLAUDE.md` / `CHANGELOG` / `VERSION` → `1.4.0`,
   `.gitignore`, suíte completa, tag `v1.4.0`.

Ondas 2 e 4 podem ser uma task cada por aba se o diff ficar grande. Merge fast-forward em `main` ao
fim. Sem deploy server-side automático.
