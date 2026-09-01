# ADR 0013 — Chart.js como padrão de gráfico da suíte AgroVector

- Status: Aceito
- Data: 2026-09-01

## Contexto

A Fase 13 (Painel de Resultados) introduz o **primeiro gráfico** do stack Django: a aba "Resultados"
de um cenário passa a mostrar, além da tabela, uma visão gráfica dos totais do recorte (barras mensais
de dois eixos — Toneladas à esquerda, Frete R$ à direita — e linha diária).

O produto original (Comigo/Streamlit) usava Plotly, que foi **removido no Cutover (Fase 11)** junto com
todo o stack Streamlit. A suíte AgroVector (ADR 0012) padronizou a fundação visual (daisyUI 5 +
Tailwind 4 via Play CDN, componentes cotton, header/menu), mas **não tinha padrão de gráfico** — nem
biblioteca, nem convenção de carregamento, nem contrato de dados servidor→cliente.

A `base.html` da suíte já carrega tudo por CDN (`cdn.jsdelivr.net`), sem build step e sem assets
locais. As telas são server-rendered e trocadas por HTMX (swaps parciais), o que impõe cuidado com
qualquer JS que instancie objetos com ciclo de vida (um `<canvas>` reinjetado precisa destruir a
instância anterior).

## Decisão

**Chart.js 4.x é o padrão de gráfico da suíte AgroVector**, com as seguintes regras:

- **CDN e versão**: carregado de
  `https://cdn.jsdelivr.net/npm/chart.js@<versão exata>/dist/chart.umd.min.js` (build UMD, mesmo CDN de
  daisyUI/htmx/Tailwind). A versão é **pinada exata** no template (`4.4.7` na Fase 13), nunca um range.
- **Carregamento preguiçoso — NÃO entra no `base.html`**. Um loader curto vive na parcial que desenha o
  gráfico (`templates/simulacao/_resultados_grafico.html`): se `window.Chart` já existe, chama o render
  direto; senão injeta o `<script src>` uma vez e chama o render no `onload`. Páginas sem gráfico não
  baixam a biblioteca.
- **Contrato de dados servidor→cliente**: a view põe no contexto um dict
  `{"tipo": "bar"|"line", "labels": [...], "datasets": [{"label", "dados", "eixo"}]}`. O template o
  serializa com `{{ grafico|json_script:"grafico-dados" }}` (tag nativa do Django — escapa com
  segurança dentro de um `<script type="application/json">`). O JS lê `.textContent` desse elemento,
  faz `JSON.parse` e monta a config do Chart.
- **Sobreviver aos swaps HTMX**: antes de recriar, o render faz
  `window._resultadosChart?.destroy()` e reatribui a instância nova. Cada swap parcial reexecuta o
  script inline da parcial, então o `destroy()` + recriação é o ciclo normal, não exceção.
- **Duas formas de gráfico** padronizadas: (1) **barras mensais de dois eixos** — eixo `y` à esquerda
  (Toneladas), eixo `y2` à direita (Frete R$), série do eixo `y2` renderizada como linha sobre as
  barras; (2) **linha diária** — série única no eixo `y`.

### Alternativas rejeitadas

- **Plotly** — removido no Cutover (Fase 11); bundle pesado (~1 MB+), desproporcional para dois tipos
  de gráfico simples.
- **ApexCharts** — boa opção, mas Chart.js é menor, mais onipresente (mais exemplos, mais estável) e
  cobre o que a suíte precisa.
- **Barras em CSS puro** (sem biblioteca) — resolve a linha/barra simples, mas não dá eixo secundário
  nem tooltip para a comparação mensal de dois eixos, que é o caso principal da Fase 13.

## Consequências

- **Positivas**: biblioteca leve, sem build step, no mesmo CDN já usado; contrato de dados explícito e
  testável no servidor (a parcial verifica `id="grafico-resultados"`, `id="grafico-dados"` e
  `chart.umd.min.js`); nenhuma dependência Python nova; nenhum model muda — a Fase 13 **não cria
  migrations**.
- **Ressalvas honestas**: em ambiente **offline ou com CSP restritivo** o `<script src>` do CDN não
  carrega e o gráfico não renderiza — a tabela, os totais e o resto da página continuam funcionando
  (degradação graciosa, o gráfico é complemento). A migração **CDN → assets locais** fica para quando a
  ADR 0012 fizer a dela (daisyUI/Tailwind/htmx), no mesmo movimento.
- O guia `docs/design-system/README.md` ganha a seção "Gráficos (Chart.js)"; cada produto futuro da
  suíte copia a parcial e segue as regras acima.
- Renumeração: esta é a ADR 0013; as ADRs vão de 0001 a 0013.
