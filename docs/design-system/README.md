# Design system AgroVector — guia normativo

Padrão de UX/UI da suíte **AgroVector** (Vector Consulting). Este documento é **normativo e portável**:
cada produto novo da suíte copia os arquivos de referência do Transbordo (`templates/base.html`,
`templates/cotton/*`, os overrides de template, `static/vector/*`) e segue as regras abaixo. Não há
pacote Python compartilhado — ver `docs/decisions/0012-design-system-agrovector.md`.

A implementação de referência atual é o **Transbordo** (`Transbordo.git`). A linhagem do padrão é
`ManAuto` (Sistema de Manutenção Automotiva) → `AppVector` (Sistema de Gestão de Projetos) → Transbordo.
O truque de cascata sem `@layer` (§2) vem da **ADR 0020 de `AppVector.git`**.

---

## 1. Tokens de cor

daisyUI 5 + Tailwind 4 (Play CDN). Dois temas: `vector` (claro, default) e `vector-dark`. O estado
"sistema" resolve para um dos dois via `prefers-color-scheme`.

Os **nomes** dos tokens são registrados no bloco `@theme` (faz `bg-primary`, `text-accent` etc.
existirem como utilities do Tailwind). Os **valores** vêm do bloco `:root` / `[data-theme="vector-dark"]`
**sem `@layer`** — essa é a fonte de verdade real (ver §2).

### Tema claro (`:root`, `data-theme="vector"`)

| Token | Valor | Uso |
|---|---|---|
| `--color-primary` | `#1F3060` | Navy Vector. Header, `btn-primary`, `badge-primary`, bordas de foco. **Sempre este valor, nos dois temas.** |
| `--color-primary-hover` | `#2a4080` | Hover de superfícies navy |
| `--color-primary-content` | `#ffffff` | Texto/ícone sobre navy |
| `--color-secondary` | `#B2B5B7` | Cinza neutro |
| `--color-secondary-content` | `#1a2540` | Texto sobre `secondary` |
| `--color-accent` | `#38bdf8` | Azul-céu. **Links soltos** (`text-accent`), destaques |
| `--color-accent-content` | `#06283d` | Texto sobre `accent` |
| `--color-neutral` | `#1F3060` | = navy |
| `--color-neutral-content` | `#ffffff` | Texto sobre `neutral` |
| `--color-base-100` | `#ffffff` | Superfície de cartão / conteúdo |
| `--color-base-200` | `#E8ECF2` | Fundo da página (`body`) |
| `--color-base-300` | `#dde3ec` | Bordas, divisores |
| `--color-base-content` | `#1a2540` | Texto principal |
| `--color-info` | `#38bdf8` | = accent |
| `--color-info-content` | `#06283d` | Texto sobre `info` |
| `--color-success` | `#27c27a` | Verde |
| `--color-success-content` | `#ffffff` | Texto sobre `success` |
| `--color-warning` | `#f59e0b` | Âmbar |
| `--color-warning-content` | `#1a1206` | Texto sobre `warning` |
| `--color-error` | `#ef4444` | Vermelho |
| `--color-error-content` | `#ffffff` | Texto sobre `error` |

### Tema escuro (`[data-theme="vector-dark"]` — só os tokens que mudam)

| Token | Valor |
|---|---|
| `color-scheme` | `dark` |
| `--color-base-100` | `#0d1530` |
| `--color-base-200` | `#060d1a` |
| `--color-base-300` | `#08111f` |
| `--color-base-content` | `#d4dff0` |
| `--color-secondary-content` | `#08111f` |
| `--color-neutral` | `#08111f` |
| `--color-neutral-content` | `#d4dff0` |
| `--color-success-content` | `#06140d` |
| `--color-error-content` | `#2a0a0a` |

Todo o resto (navy `primary`, `accent`, `success`/`warning`/`error` de fundo) é **herdado do `:root`** —
não redefinir no bloco escuro.

---

## 2. Anatomia da `base.html`

### Ordem obrigatória no `<head>`

1. `<script>` **anti-flash** inline (antes de qualquer CSS): lê `localStorage['vector-theme-pref']`
   (`'light'` / `'dark'` / `'system'`, default `'system'`), resolve `system` contra
   `window.matchMedia('(prefers-color-scheme: dark)')`, e aplica `data-theme="vector"` ou
   `"vector-dark"` no `<html>` **antes do primeiro paint**. Também grava
   `document.documentElement.dataset.themePref`.
2. `<link href="https://cdn.jsdelivr.net/npm/daisyui@5" rel="stylesheet">`
3. `<script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4">`
4. `<style type="text/tailwindcss">` — **bloco 1**: `@theme { --color-*: ... }` (só registra nomes)
   + `@layer base { ... }` (estilos de `input`/`select`/`textarea`/`label` e o separador
   `.c-breadcrumb > *:not(:first-child)::before { content: "/" }`).
5. `<style>` — **bloco 2**, **sem `@layer`**: `:root { --color-*: ... }` +
   `[data-theme="vector-dark"] { ... }`. **Esta é a fonte de verdade real das cores.**
6. CSS do Tabulator (`tabulator-tables@6`) + `static/vector/css/tabulator-vector.css`.
7. `htmx.org@2` + `{% django_htmx_script %}`.
8. libs de grid: `luxon@3`, `tabulator-tables@6` (js), `imask@7`, `static/simulacao/js/grid_editor.js`.
9. `{% block extra_head %}`.

### Por que dois blocos de style (o truque de cascata)

Qualquer regra CSS **dentro de uma `@layer`** perde na cascata para qualquer regra **fora de `@layer`**,
independentemente de especificidade ou ordem de declaração. O daisyUI define seus temas dentro de
`@layer`. Portanto:

- o `@theme` (bloco 1) serve só para o Tailwind **gerar as utilities** `bg-primary`, `text-accent` etc.;
- o `:root` **sem `@layer`** (bloco 2) é o que **de fato pinta a tela**, sobrescrevendo o daisyUI.

Não mover o bloco 2 para dentro de uma `@layer`, não removê-lo. Comentário verbatim no arquivo cita a
ADR 0020 de AppVector.

### `<body>`

```html
<body class="min-h-screen bg-base-200 text-base-content antialiased"
      hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'>
```

O `hx-headers` global manda o CSRF em toda requisição HTMX. `django_htmx` segue carregado para o resto.

### Os dois `<dialog>` compartilhados (fim do `<body>`)

- `#vector-modal` — `<div id="vector-modal-body">` vazio; um script escuta `htmx:afterSwap`: quando o
  alvo do swap é `#vector-modal-body` e há conteúdo, chama `modal.showModal()`. Serve para abrir
  formulários/telas em modal via `hx-target="#vector-modal-body"`.
- `#vector-confirm` — diálogo de confirmação. `window.vectorConfirm(form, texto)` para uso manual;
  e um listener de `htmx:confirm` que intercepta `hx-confirm` e troca o `confirm()` nativo pelo
  diálogo daisyUI (`evt.detail.issueRequest(true)` no OK).

### Tema (tri-estado)

- Chave: `localStorage['vector-theme-pref']` — `'light'` | `'dark'` | `'system'`.
- `vectorApplyTheme(pref)` grava a preferência, resolve e aplica `data-theme`, e sincroniza o ícone.
- `vectorSyncThemeIcon()` mostra ☀️ / 🌙 / 🖥️ conforme a preferência ativa.
- Um listener de `matchMedia('(prefers-color-scheme: dark)')` reaplica quando a pref é `'system'`.
- **Prefixo `vector-*`** em toda a suíte (não `av-*`, não `<produto>-*`).

### `messages` e erros

- `messages` do Django → `alert` daisyUI (`alert-error` / `alert-success` / `alert-info`) no topo do
  `<main>`.
- Erro de rede HTMX (`htmx:responseError`) → toast `#htmx-error-toast` (`alert alert-error`, canto
  superior direito, some em 5 s).

---

## 3. Componentes cotton (`templates/cotton/`)

### `<c-card>`

Contêiner de superfície. Atributos: `class` (extra), `id` (opcional).

```html
<div class="rounded-lg border border-base-300 bg-base-100 p-8 {{ class }}"{% if id %} id="{{ id }}"{% endif %}>
  {{ slot }}
</div>
```

```html
<c-card class="max-w-xl">
  <h1 class="text-lg font-semibold">Título</h1>
  <p class="text-sm text-base-content/70">Conteúdo…</p>
</c-card>
```

### `<c-lista-cartao titulo="…">`

Cartão com cabeçalho (título + slot `acoes`) e corpo rolável (`max-h-96 overflow-y-auto`). Para listas
(`<ul class="divide-y divide-base-300">`) e tabelas curtas.

```html
<c-lista-cartao titulo="Cenários recentes">
  <c-slot name="acoes">
    <a href="…" class="btn btn-primary btn-xs"><c-icon name="plus" /> Novo</a>
  </c-slot>
  <ul class="divide-y divide-base-300">
    <li class="px-4 py-2.5"><a href="…" class="text-sm hover:text-accent hover:underline">Safra 24/25</a></li>
  </ul>
</c-lista-cartao>
```

### `<c-resumo-numerico>`

Faixa de KPIs. Envolve `stats` do daisyUI (vertical no mobile, horizontal a partir de `sm`). Cada
filho é um `<div class="stat">`. Atributo `class` (extra).

```html
<c-resumo-numerico class="mb-6">
  <div class="stat"><div class="stat-title">Fábricas</div><div class="stat-value text-base-content">12</div></div>
  <div class="stat"><div class="stat-title">Armazéns</div><div class="stat-value text-base-content">34</div></div>
</c-resumo-numerico>
```

Valores numéricos sempre em formatação pt-BR (filtros `volume` / `moeda` de
`apps/simulacao/templatetags/simulacao_filters.py`).

### `<c-breadcrumb>`

Trilha de navegação. "Início" (link para `core:home`) é sempre o primeiro item; o slot traz o resto.
Separador `/` injetado por CSS (`.c-breadcrumb > *:not(:first-child)::before`).

```html
<c-breadcrumb>
  <a href="{% url 'gestao:cooperativas' %}" class="text-base-content/60 hover:text-accent hover:underline">Organizações</a>
  <span class="text-base-content/60">Nova organização</span>
</c-breadcrumb>
```

Renderizado no `{% block breadcrumb %}` da `base.html` (ver §4). A home deixa o bloco vazio.

### `<c-icon name="…">`

SVG inline estilo Lucide, `stroke="currentColor"` (herda cor e tamanho). Atributo `class` (extra).
Catálogo atual: `home`, `git-branch`, `upload`, `plus`, `arrow-right`, `building`, `users`, `external`.
Ampliar o catálogo = adicionar um `{% elif name == "…" %}` com o path do ícone Lucide correspondente.

```html
<c-icon name="upload" class="text-accent" /> Carga de Dados
```

---

## 4. Header e navegação

### Header (dois níveis, sempre navy)

`<header class="sticky top-0 z-40 bg-primary text-primary-content shadow-sm">`, conteúdo em
`mx-auto max-w-7xl`.

**Nível 1 — `navbar`:**

- **`navbar-start`**: logo Vector (`static/vector/img/logo-vector.png`, `h-9`, link para `core:home`)
  + coluna "Nome do Sistema" (semibold) / "AgroVector" (uppercase, `text-[10px]`, opacidade 60%)
  + separador + **indicador de organização**:
  - `organizacoes_disponiveis is not None` (Admin Vector) → `<select>` com "— Consolidado —" + as
    organizações ativas; `onchange` faz `POST` para `core:selecionar_organizacao`.
  - senão, se `org` → `<span>{{ org.nome }}</span>` estático.
- **`navbar-end`** (exatamente três elementos):
  1. Nome do usuário + `dropdown dropdown-end` com itens gated por papel: **Minha conta** (qualquer
     autenticado) · **Minha organização** (`menu_admin_cooperativa`) · **Usuários**
     (`menu_gerir_usuarios`) · **Organizações** (`menu_admin_vector`) · **Admin Django**
     (`user.is_staff`).
  2. Ícone de aparência + `dropdown` (☀️ Claro / 🌙 Escuro / 🖥️ Sistema → `vectorApplyTheme(...)`).
  3. Ícone de sair — `<form method="post" action="{% url 'account_logout' %}">` isolado (sem dropdown).

**Nível 2 — faixa de módulos** (`{% if mostra_modulos %}`): `<nav class="border-t border-white/10
bg-black/10">`. Cada item é um `<a>` com `<c-icon>` + label. Estado ativo:
`border-b-2 border-white font-semibold text-white`; inativo:
`border-b-2 border-transparent text-primary-content/70 hover:text-white`.

Gestão (Organizações, Usuários, Minha organização, Conta) **não** entra na faixa — vive no dropdown do
usuário.

### Contexto do header

O context processor (`apps/gestao/context_processors.menu`, mais `apps/core/context_processors`)
devolve, além dos flags de papel (`menu_admin_vector`, `menu_admin_cooperativa`, `menu_gerir_usuarios`,
`menu_membro_cooperativa`):

- `org` — a `Cooperativa` corrente resolvida, ou `None`.
- `organizacoes_disponiveis` — queryset de `Cooperativa.objects.filter(ativo=True)` **só** para Admin
  Vector; `None` para os demais (é o discriminador que troca `<select>` por texto no header).
- `mostra_modulos` — `True` para membro, ou Admin Vector com organização selecionada.

### Breadcrumb

`{% block breadcrumb %}` fica na `base.html`, logo antes de `{% block content %}`. Telas que têm uma
base intermediária (ex. `base_gestao.html`) re-expõem via um bloco aninhado
(`{% block breadcrumb %}{% block gestao_breadcrumb %}{% endblock %}{% endblock %}`).

### Subnav (contexto de cenário / entidade)

Abas internas (`tabs tabs-bordered` do daisyUI) com swap HTMX em um alvo de conteúdo
(`hx-target="#...-content"`, `hx-push-url="true"`). Acima das abas, um cabeçalho da entidade dentro de
`<c-card>` (nome + `badge`).

---

## 5. Regras de uso

- **`text-accent` para link solto** — qualquer link fora de um contêiner de navegação usa
  `text-accent hover:underline` (no tema claro é o azul-céu `#38bdf8`). Nunca navy para texto de link.
- **`primary`/navy só para fundo preenchido ou borda** — `btn btn-primary`, `badge badge-primary`,
  `border-primary` (foco de input), e o header. Navy **não** é cor de texto de corpo nem de link.
- **Header sempre navy nos dois temas** — `bg-primary text-primary-content`. O `primary` não é
  redefinido no bloco escuro justamente para isso.
- **Tri-estado de tema com prefixo `vector-*`** — chave `vector-theme-pref`, funções `vectorApplyTheme`
  / `vectorSyncThemeIcon`. Três estados: claro, escuro, sistema (nunca só um toggle binário).
- **Superfícies**: página = `bg-base-200`; cartão/conteúdo = `bg-base-100`; bordas/divisores =
  `base-300`. Texto = `base-content` (com `/70`, `/60`, `/40` para hierarquia).
- **Números** sempre em pt-BR via os filtros de template — nunca um `float`/moeda cru.
- **Estados**: `alert-success` / `alert-warning` / `alert-error` / `alert-info`; `badge` para rótulos
  curtos; `progress` para andamento.

---

## 6. Overrides de template esperados

| Arquivo | O que é |
|---|---|
| `templates/django_tables2/tailwind.html` | Template de `django-tables2` re-tematizado: `table table-sm`, cabeçalho `text-base-content/70`, linha `hover:bg-base-200`, paginação `join` + `btn btn-sm btn-outline`. `DJANGO_TABLES2_TEMPLATE` aponta para ele. |
| `templates/tailwind/field.html` | Campo do `crispy-tailwind`: `<label>` com asterisco `text-error` para obrigatório, `help_text` em `text-xs text-base-content/60`, erros em `text-xs text-error`. |
| `templates/cotton/card.html` | `<c-card>` re-estilizado para os tokens daisyUI (mantém a assinatura `class` + `id`). |
| `static/vector/css/tabulator-vector.css` | Mapeia as classes do Tabulator para `--color-base-*` nos dois temas (carregado depois do CSS oficial do Tabulator). |

Formulários usam `crispy-tailwind` (`CRISPY_TEMPLATE_PACK = 'tailwind'`) dentro de `<c-card>`.
Listagens read-only usam `django-tables2` + `django-filter`. Grids editáveis seguem em Tabulator.
`/admin/` usa `django-unfold` (`unfold` + `unfold.contrib.filters` + `unfold.contrib.forms` antes de
`django.contrib.admin`; branding em `UNFOLD = {...}`).

---

## 7. Gráficos (Chart.js)

Padrão da suíte para qualquer gráfico (ADR 0013). Biblioteca: **Chart.js 4.x**.

- **Nunca no `base.html`** — carregamento preguiçoso. Um loader curto vive na parcial que desenha o
  gráfico: se `window.Chart` já existe, chama o render direto; senão injeta uma vez
  `<script src="https://cdn.jsdelivr.net/npm/chart.js@<versão exata>/dist/chart.umd.min.js">` e chama o
  render no `onload`. Páginas sem gráfico não baixam nada.
- **Versão pinada exata** no `src` (mesmo CDN de daisyUI/htmx/Tailwind) — nunca um range.
- **Contrato servidor→cliente**: a view põe no contexto um dict
  `{"tipo": "bar"|"line", "labels": [...], "datasets": [{"label", "dados", "eixo"}]}`. O template
  serializa com `{{ grafico|json_script:"grafico-dados" }}` (tag nativa do Django). O JS lê
  `.textContent` do `<script type="application/json">`, faz `JSON.parse` e monta a config.
- **Sobreviver aos swaps HTMX**: o `render()` roda a cada swap (o script inline da parcial reexecuta);
  antes de recriar faz `window._resultadosChart?.destroy()` e reatribui a instância nova.
- **Duas formas padronizadas**: (1) **barras mensais de dois eixos** — `y` à esquerda (Toneladas), `y2`
  à direita (Frete R$), a série de `y2` desenhada como linha sobre as barras; (2) **linha diária** —
  série única em `y`.
- **Degradação graciosa**: offline ou CSP restritivo → o CDN não carrega e o gráfico não aparece; a
  tabela e o resto da página continuam. O gráfico é complemento, nunca a única via ao dado.
- Implementação de referência: `templates/simulacao/_resultados_grafico.html`.

---

## 8. Portando para um novo produto da suíte

- [ ] Copiar `templates/base.html` e trocar só: `<title>`, o nome do sistema no header, e a lista de
      módulos do nível 2. **Não** tocar os dois blocos de `<style>` nem o script anti-flash.
- [ ] Copiar `templates/cotton/` (`card`, `lista_cartao`, `resumo_numerico`, `breadcrumb`, `icon`).
      Ampliar o catálogo de `<c-icon>` conforme necessário.
- [ ] Copiar os overrides: `templates/django_tables2/tailwind.html`, `templates/tailwind/field.html`.
- [ ] Copiar `static/vector/css/tabulator-vector.css` (só se o produto usa Tabulator) e
      `static/vector/img/logo-vector.png`.
- [ ] `INSTALLED_APPS`: `django_cotton`, `django_tables2`, `django_filters`, `django-crispy-forms` +
      `crispy_tailwind`, e `unfold` + `unfold.contrib.filters` + `unfold.contrib.forms` **antes** de
      `django.contrib.admin`.
- [ ] `settings`: `DJANGO_TABLES2_TEMPLATE = 'django_tables2/tailwind.html'`,
      `CRISPY_TEMPLATE_PACK = 'tailwind'`, `UNFOLD = {...}` (título + cor primária navy),
      `LOGIN_REDIRECT_URL = '/'`.
- [ ] `<body hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'>` e os dois `<dialog>` (`#vector-modal`,
      `#vector-confirm`) — portar 1:1.
- [ ] Header: context processor que devolva `org`, `organizacoes_disponiveis`, `mostra_modulos` e os
      flags de papel do produto.
- [ ] Rota `/` com a home (dashboard consolidado / home da organização, ou o equivalente do produto)
      como `LOGIN_REDIRECT_URL`.
- [ ] Multi-tenant: se houver um papel cross-tenant (tipo Admin Vector), resolver a organização
      corrente por sessão (Abordagem A da ADR 0012) — `obter_organizacao_corrente(request)` no
      middleware de escopo, view `selecionar_organizacao`, decorator `requer_membro_organizacao`.
- [ ] Gráficos: Chart.js por CDN, versão exata, carregamento preguiçoso na parcial (nunca no
      `base.html`), contrato `{{ grafico|json_script:"…" }}` + `render()`/`destroy()` a cada swap —
      ver seção 7 e a ADR 0013.
- [ ] `pyproject.toml` (PEP 621, `pip`) — sem `requirements*.txt`, sem resolvedor novo.
- [ ] Registrar as decisões próprias do produto e apontar de volta para este guia + a ADR 0012.
