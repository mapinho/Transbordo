# Fase 15 — Polimento UX Resultados + Estoque — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Polir a UX das abas "Resultados" e "Estoque" juntas — tema/paleta do gráfico, Δ da comparação embutido na célula, barra de filtros recolhível, card de pico do Estoque com barra de ocupação, faixas de mês nas visões por unidade — sem tocar contrato de dado, model ou engine.

**Architecture:** Ordem "compartilhado primeiro": a fundação (`variacao`, tema do gráfico, snippet de tokens, §7 do design system) cai e fica testável antes das mudanças visíveis empilharem. Correções compartilhadas vão nos dois pares de parciais; correções só-de-Estoque (card, faixas de mês) ficam lá. Nenhuma extração de componente comum (abstração prematura — a Fase 14 já rejeitou "mini-framework de painel").

**Tech Stack:** Django 6, HTMX + django-htmx, django-cotton, daisyUI 5 + Tailwind 4 (Play CDN), Chart.js 4.4.7 (CDN, lazy), pytest, PostgreSQL local.

**Spec:** `docs/superpowers/specs/2026-09-03-fase15-polimento-ux-design.md` — leia os dois.

## Global Constraints

Todo requisito de tarefa inclui implicitamente esta seção.

- **Sem migrations.** Nenhum model muda. `python manage.py makemigrations --check --dry-run` tem de sair "No changes detected".
- **TDD estrito** (red → green): teste que falha → confirma que falha pelo motivo certo → mínimo → verde. Testes em `apps/simulacao/tests/` e `apps/core/tests/`.
- **Banco real:** PostgreSQL local via `DJANGO_DB_*` (`config.settings.dev`, default do `pytest.ini`). Suíte atual = **490 passed**; ao fim continua verde + os novos/ajustados (~20).
- **Sem ADR novo.** A mudança do gráfico entra no §7 do `docs/design-system/README.md`, não numa ADR.
- **`VERSION` → `1.4.0`** ao fim (minor, aditivo); tag `v1.4.0` anotada, local (não pushed automaticamente).
- **`variacao` é filtro compartilhado** — mudá-lo muda a renderização das duas abas. É de propósito.
- **`vector:themechange`** — o gráfico re-renderiza nesse evento (disparado por `vectorApplyTheme` na `base.html`). Cores de série vêm dos tokens `--color-*` (Estoque: Saldo=`accent`, Excedente=`error`; Resultados: Toneladas=`accent`, Frete=`primary`); série comparada = mesma cor, `borderDash: [5, 4]`, opacidade ~0.55; eixos/legenda = `--color-base-content`, grade = `--color-base-300`.
- **Não tocar** os dois blocos de `<style>` da `base.html` nem o script anti-flash (checklist §8 do DS). A única mudança na `base.html` é uma linha `dispatchEvent` dentro de `vectorApplyTheme`.
- **Line endings por arquivo:** alguns parciais estão em CRLF (Fase 13), outros em LF (Fase 14). A ferramenta de edição preserva o que está no arquivo — não normalizar.
- **pt-BR** em toda célula numérica via os filtros `volume` / `moeda`. Toneladas na aba Estoque (sem `moeda`, sem sacas).
- Escopo fechado do SPEC: **fora** — `engine.py` / `tasks.py` / `services.py` / `apps/integracoes` / `mcp_server.py`, migrations, ADR novo, extração de componente comum, header mobile (`base.html`), badge do `_cenario_header.html`, toggle de sacas, ordenação por clique, "chips".

---

### Task 1: `variacao` — limiar neutro

**Files:**
- Modify: `apps/simulacao/templatetags/simulacao_filters.py:46-60`
- Test: `apps/simulacao/tests/test_templatetags_variacao.py` (criar)

**Interfaces:**
- Produces: `variacao(valor: float | None | "novo" | "")` — HTML `str` (marcado safe). Comportamento novo: `isinstance(valor, (int, float))` e `abs(valor) < 0.05` → `<span class="text-base-content/50">0,0%</span>` (sem seta, sem cor). Resto inalterado.

- [ ] **Step 1: Write the failing test**

```python
# apps/simulacao/tests/test_templatetags_variacao.py
from django.test import SimpleTestCase

from apps.simulacao.templatetags.simulacao_filters import variacao


class VariacaoTests(SimpleTestCase):
    def test_novo(self):
        html = variacao("novo")
        self.assertIn("novo", html)
        self.assertIn("badge", html)

    def test_none_e_nao_numero(self):
        self.assertIn("—", variacao(None))
        self.assertEqual(variacao(""), "")
        self.assertEqual(variacao("qualquer"), "")

    def test_quase_zero_e_neutro(self):
        for v in (0.0, 0.03, -0.04, 0.049, -0.049):
            html = variacao(v)
            self.assertIn("0,0%", html)
            self.assertIn("text-base-content/50", html)
            self.assertNotIn("↑", html)
            self.assertNotIn("↓", html)
            self.assertNotIn("text-error", html)
            self.assertNotIn("text-success", html)

    def test_positivo_acima_do_limiar(self):
        html = variacao(25.0)
        self.assertIn("↑", html)
        self.assertIn("+25,0%", html)
        self.assertIn("text-error", html)

    def test_negativo_acima_do_limiar(self):
        html = variacao(-20.0)
        self.assertIn("↓", html)
        self.assertIn("−", html)   # U+2212 MINUS SIGN
        self.assertIn("20,0%", html)
        self.assertIn("text-success", html)

    def test_bordas_do_limiar(self):
        self.assertIn("text-base-content/50", variacao(0.04))
        self.assertIn("↑", variacao(0.06))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest apps/simulacao/tests/test_templatetags_variacao.py -v`
Expected: FAIL — `test_quase_zero_e_neutro` falha em `0.03` (hoje renderiza `↑ +0,0%` com `text-error`).

- [ ] **Step 3: Implement**

Substituir a função `variacao` (linhas 46-60) por:

```python
@register.filter
def variacao(valor):
    """Renderiza um delta (`float | None | "novo"`) como span colorido. Um Δ que
    arredonda para `0,0%` (`abs(valor) < 0.05`) é neutro — sem seta e sem cor."""
    if valor == "novo":
        return mark_safe('<span class="badge badge-ghost badge-sm">novo</span>')
    if valor is None:
        return mark_safe('<span class="text-base-content/50">—</span>')
    if valor == "" or not isinstance(valor, (int, float)):
        return ""
    if abs(valor) < 0.05:
        return mark_safe('<span class="text-base-content/50">0,0%</span>')
    pct = _formatar_pt_br(abs(valor), 1)
    if valor > 0:
        return mark_safe(f'<span class="text-error">↑&nbsp;+{pct}%</span>')
    return mark_safe(f'<span class="text-success">↓&nbsp;−{pct}%</span>')
```

(O antigo ramo final `valor == 0` some — está coberto por `abs(valor) < 0.05`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest apps/simulacao/tests/test_templatetags_variacao.py -v`
Expected: PASS (6/6).

- [ ] **Step 5: Regressão dos consumidores**

Run: `python -m pytest apps/simulacao/tests/test_resultados_comparacao.py apps/simulacao/tests/test_estoque_comparacao.py -q`
Expected: PASS (nenhum teste de comparação afirma o HTML de `variacao` diretamente — só o número cru).

- [ ] **Step 6: Commit**

```bash
git add apps/simulacao/templatetags/simulacao_filters.py apps/simulacao/tests/test_templatetags_variacao.py
git commit -m "feat(ux): variacao trata Δ que arredonda para 0,0% como neutro (Fase 15)"
```

---

### Task 2: Gráfico — tema, paleta e evento `vector:themechange`

**Files:**
- Modify: `templates/base.html` (a função `vectorApplyTheme`, ~linha 260)
- Create: `templates/simulacao/_grafico_tokens.html`
- Modify: `templates/simulacao/_estoque_grafico.html` (reescrever), `templates/simulacao/_resultados_grafico.html` (reescrever)
- Modify: `docs/design-system/README.md` (§7)
- Test: `apps/core/tests/test_base_template.py` (acrescentar um teste)

**Interfaces:**
- Consumes: nada de tasks anteriores.
- Produces:
  - `base.html`: `vectorApplyTheme(pref)` dispara `window.dispatchEvent(new CustomEvent('vector:themechange'))` no fim.
  - `_grafico_tokens.html`: define `window.vectorChartTokens()` → `{text, grid, accent, error, primary, dashed(hex) -> "rgba(...)"}`.
  - `_estoque_grafico.html` / `_resultados_grafico.html`: `render()` lê os tokens; datasets coloridos pela paleta; listener de `vector:themechange` (bind único).

- [ ] **Step 1: Write the failing test**

Acrescentar a `apps/core/tests/test_base_template.py`, dentro de `class BaseTemplateTests`:

```python
    def test_toggle_de_tema_dispara_evento(self):
        self.client.force_login(self.membro)
        html = self.client.get("/").content.decode()
        # a função de tema notifica quem desenha gráfico
        self.assertIn("vector:themechange", html)
        self.assertIn("function vectorApplyTheme", html)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest apps/core/tests/test_base_template.py::BaseTemplateTests::test_toggle_de_tema_dispara_evento -v`
Expected: FAIL — `"vector:themechange"` não está na `base.html`.

- [ ] **Step 3: `base.html` — disparar o evento**

Na função `vectorApplyTheme` (procure `function vectorApplyTheme(pref) {`), depois de `vectorSyncThemeIcon();` e antes do `}` de fechamento, acrescentar uma linha:

```js
    function vectorApplyTheme(pref) {
      localStorage.setItem('vector-theme-pref', pref);
      document.documentElement.dataset.themePref = pref;
      var resolved = pref === 'system'
        ? (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'vector-dark' : 'vector')
        : (pref === 'dark' ? 'vector-dark' : 'vector');
      document.documentElement.setAttribute('data-theme', resolved);
      vectorSyncThemeIcon();
      window.dispatchEvent(new CustomEvent('vector:themechange'));
    }
```

(O listener de `matchMedia` já chama `vectorApplyTheme('system')` — fica coberto de graça. **Não** mexer nos dois blocos de `<style>` nem no script anti-flash.)

- [ ] **Step 4: Criar `templates/simulacao/_grafico_tokens.html`**

```html
<script>
  window.vectorChartTokens = window.vectorChartTokens || function () {
    var cs = getComputedStyle(document.documentElement);
    function t(name) { return cs.getPropertyValue(name).trim(); }
    function rgba(hex, a) {
      var h = String(hex).replace('#', '');
      if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
      var n = parseInt(h, 16) || 0;
      return 'rgba(' + ((n >> 16) & 255) + ',' + ((n >> 8) & 255) + ',' + (n & 255) + ',' + a + ')';
    }
    return {
      text: t('--color-base-content'),
      grid: t('--color-base-300'),
      accent: t('--color-accent'),
      error: t('--color-error'),
      primary: t('--color-primary'),
      dashed: function (hex) { return rgba(hex, 0.55); },
    };
  };
</script>
```

- [ ] **Step 5: Reescrever `templates/simulacao/_estoque_grafico.html`**

```html
{{ grafico|json_script:"grafico-estoque-dados" }}
{% include "simulacao/_grafico_tokens.html" %}
<canvas id="grafico-estoque" height="90"></canvas>
<script>
(function () {
  var VER = "4.4.7";
  function render() {
    var el = document.getElementById("grafico-estoque");
    var raw = document.getElementById("grafico-estoque-dados");
    if (!el || !raw || !window.Chart) return;
    var g = JSON.parse(raw.textContent);
    var tk = window.vectorChartTokens();
    if (window._estoqueChart) window._estoqueChart.destroy();
    window._estoqueChart = new Chart(el, {
      type: g.tipo,
      data: {
        labels: g.labels,
        datasets: g.datasets.map(function (d) {
          var comp = d.label.indexOf("comparado") !== -1;
          var base = d.label.replace(" (comparado)", "");
          var cor = base.indexOf("Excedente") !== -1 ? tk.error : tk.accent;
          return {
            label: d.label, data: d.dados, yAxisID: d.eixo,
            borderColor: comp ? tk.dashed(cor) : cor,
            backgroundColor: comp ? tk.dashed(cor) : cor,
            borderDash: comp ? [5, 4] : [],
            pointRadius: 2,
          };
        }),
      },
      options: {
        responsive: true,
        scales: {
          y: {
            position: "left",
            ticks: {color: tk.text}, grid: {color: tk.grid},
            title: {display: true, text: "Toneladas", color: tk.text},
          },
        },
        plugins: {legend: {labels: {color: tk.text}}},
      },
    });
  }
  if (!window.__estoqueThemeBound) {
    window.__estoqueThemeBound = true;
    window.addEventListener("vector:themechange", render);
  }
  if (window.Chart) { render(); return; }
  var s = document.createElement("script");
  s.src = "https://cdn.jsdelivr.net/npm/chart.js@" + VER + "/dist/chart.umd.min.js";
  s.onload = render;
  document.head.appendChild(s);
})();
</script>
```

- [ ] **Step 6: Reescrever `templates/simulacao/_resultados_grafico.html`**

```html
{{ grafico|json_script:"grafico-dados" }}
{% include "simulacao/_grafico_tokens.html" %}
<canvas id="grafico-resultados" height="90"></canvas>
<script>
(function () {
  var VER = "4.4.7";
  function render() {
    var el = document.getElementById("grafico-resultados");
    var raw = document.getElementById("grafico-dados");
    if (!el || !raw || !window.Chart) return;
    var g = JSON.parse(raw.textContent);
    var tk = window.vectorChartTokens();
    if (window._resultadosChart) window._resultadosChart.destroy();
    window._resultadosChart = new Chart(el, {
      type: g.tipo,
      data: {
        labels: g.labels,
        datasets: g.datasets.map(function (d) {
          var comp = d.label.indexOf("comparado") !== -1;
          var cor = d.label.indexOf("Frete") !== -1 ? tk.primary : tk.accent;
          return {
            label: d.label, data: d.dados, yAxisID: d.eixo,
            type: d.eixo === "y2" ? "line" : g.tipo,
            borderColor: comp ? tk.dashed(cor) : cor,
            backgroundColor: comp ? tk.dashed(cor) : cor,
            borderDash: comp ? [5, 4] : [],
            pointRadius: 2,
          };
        }),
      },
      options: {
        responsive: true,
        scales: {
          y: {position: "left", ticks: {color: tk.text}, grid: {color: tk.grid},
              title: {display: true, text: "Toneladas", color: tk.text}},
          y2: {position: "right", grid: {drawOnChartArea: false},
               ticks: {color: tk.text},
               title: {display: true, text: "Frete (R$)", color: tk.text}},
        },
        plugins: {legend: {labels: {color: tk.text}}},
      },
    });
  }
  if (!window.__resultadosThemeBound) {
    window.__resultadosThemeBound = true;
    window.addEventListener("vector:themechange", render);
  }
  if (window.Chart) { render(); return; }
  var s = document.createElement("script");
  s.src = "https://cdn.jsdelivr.net/npm/chart.js@" + VER + "/dist/chart.umd.min.js";
  s.onload = render;
  document.head.appendChild(s);
})();
</script>
```

- [ ] **Step 7: `docs/design-system/README.md` §7 — acrescentar**

Ao fim da lista de bullets do §7 (antes de "Implementação de referência:"), acrescentar:

```markdown
- **Tema**: `render()` relê os tokens `--color-*` (via `getComputedStyle` — o snippet
  `templates/simulacao/_grafico_tokens.html` expõe `window.vectorChartTokens()`) e re-renderiza no
  evento `vector:themechange`, disparado por `vectorApplyTheme` na `base.html`. Cores de série vêm dos
  tokens (`accent` para a série principal, `error` / `primary` para a segunda), **nunca** das cores
  default do Chart.js. Série do cenário comparado = mesma cor, `borderDash: [5, 4]`, opacidade ~0.55
  (`tokens.dashed(cor)`). Eixos, legenda e título dos eixos em `--color-base-content`; grade em
  `--color-base-300`.
```

E na lista "Duas formas padronizadas" (renomear para "Três formas padronizadas"), acrescentar como item (3):

```markdown
(3) **linha mensal de série dupla num eixo só** — duas séries em `y` (ex. Saldo total / Excedente
total da aba Estoque), mesma escala de toneladas.
```

- [ ] **Step 8: Run tests**

Run: `python -m pytest apps/core/tests/test_base_template.py apps/simulacao/tests/test_views_resultados.py apps/simulacao/tests/test_views_estoque.py -q`
Expected: PASS. Os testes de view que checam `id="grafico-resultados"` / `id="grafico-dados"` / `id="grafico-estoque"` continuam válidos (os ids não mudaram). Depois `python manage.py check`.

- [ ] **Step 9: Commit**

```bash
git add templates/base.html templates/simulacao/_grafico_tokens.html templates/simulacao/_estoque_grafico.html templates/simulacao/_resultados_grafico.html docs/design-system/README.md apps/core/tests/test_base_template.py
git commit -m "feat(ux): gráfico tematizado + paleta AgroVector + evento vector:themechange (§7 DS)"
```

---

### Task 3: `aplicar_comparacao` deixa de inserir colunas Δ

**Files:**
- Modify: `apps/simulacao/estoque.py:337-365` (`aplicar_comparacao`)
- Modify: `apps/simulacao/resultados.py` (`aplicar_comparacao`, ~linhas 174-203)
- Test: `apps/simulacao/tests/test_estoque_comparacao.py`, `apps/simulacao/tests/test_resultados_comparacao.py` (ajustar asserções)

**Interfaces:**
- Produces (ambos os módulos): `aplicar_comparacao(dados, ...)` **não altera** `dados["colunas"]`. Continua gravando `linha["<m>_delta"]` (`float | None | "novo"`) para cada métrica `comparavel` e `dados["totais_delta"]`. `resultados.py` mantém o early-return `comparacao_ignorada` para `("diario","fabrica_armazem")`.
- Consumed by: Task 4 (templates leem `linha["<m>_delta"]` e `dados["totais_delta"]`).

- [ ] **Step 1: Ajustar os testes (que passam a falhar)**

Em `apps/simulacao/tests/test_estoque_comparacao.py`, no método `test_sistema_recebe_delta_e_colunas` — trocar a verificação de coluna inserida por verificação de ausência. Renomear para `test_sistema_recebe_delta`:

```python
    def test_sistema_recebe_delta(self):
        d = estoque.agregar(self.atual.id, "sistema", VAZIO)
        d = estoque.aplicar_comparacao(d, self.comp.id, "sistema", VAZIO)
        self.assertAlmostEqual(d["linhas"][0]["saldo_delta"], (200 - 160) / 160 * 100, places=6)
        keys = [c["key"] for c in d["colunas"]]
        self.assertNotIn("saldo_delta", keys)          # Δ não é mais coluna
        self.assertFalse(any(c.get("tipo") == "delta" for c in d["colunas"]))
        self.assertIn("saldo_delta", d["linhas"][0])    # é chave na linha
```

Em `apps/simulacao/tests/test_resultados_comparacao.py`, no `test_mensal_recebe_delta_e_colunas` (linhas ~45-56) — renomear para `test_mensal_recebe_delta` e trocar a asserção de `keys`:

```python
    def test_mensal_recebe_delta(self):
        d = resultados.agregar(self.atual.id, "mensal", "nada", VAZIO)
        d = resultados.aplicar_comparacao(d, self.comp.id, "mensal", "nada", VAZIO)
        self.assertAlmostEqual(d["linhas"][0]["ton_delta"], (10 - 8) / 8 * 100, places=9)
        self.assertEqual(d["linhas"][0]["custo_delta"], (100 - 125) / 125 * 100)
        self.assertAlmostEqual(d["linhas"][0]["sacas_delta"], d["linhas"][0]["ton_delta"], places=9)
        keys = [c["key"] for c in d["colunas"]]
        self.assertEqual(keys, ["dia", "ton", "sacas", "custo"])   # sem colunas *_delta
        self.assertFalse(any(c.get("tipo") == "delta" for c in d["colunas"]))
```

(Manter os args reais do teste original — confira o `periodo`/`agrupar` e o setup da classe; o corpo acima assume `("mensal","nada")`, ajuste se o teste original usar outro.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest apps/simulacao/tests/test_estoque_comparacao.py apps/simulacao/tests/test_resultados_comparacao.py -q`
Expected: FAIL — `assertNotIn("saldo_delta", keys)` / `assertEqual(keys, [...])` falham porque `aplicar_comparacao` ainda insere as colunas.

- [ ] **Step 3: `estoque.py` — remover o bloco de colunas**

Em `aplicar_comparacao` (linha ~337), apagar o bloco `novas_colunas` (as linhas de `novas_colunas = []` até `dados["colunas"] = novas_colunas`), deixando:

```python
def aplicar_comparacao(dados, cenario_comparado_id, visao, filtros):
    """Anota `dados` (retorno de `agregar` do cenário atual) com Δ% contra
    `cenario_comparado_id`: grava `linha["<m>_delta"]` para cada métrica
    `comparavel` e `dados["totais_delta"]`. **NÃO altera `dados["colunas"]`** — o
    template renderiza o Δ embutido na célula da métrica. Vale para as 3 visões."""
    visao = normalizar_visao(visao)
    comparaveis = [c["key"] for c in dados["colunas"] if c.get("comparavel")]

    comp = agregar(cenario_comparado_id, visao,
                   _traduzir_filtros(filtros, cenario_comparado_id), pagina=None)
    por_chave = {linha_c["_chave"]: linha_c for linha_c in comp["linhas"]}

    for linha in dados["linhas"]:
        alvo = por_chave.get(linha["_chave"])
        for m in comparaveis:
            linha[f"{m}_delta"] = _delta(linha[m], alvo[m] if alvo else None)

    dados["totais_delta"] = {
        m: _delta(dados["totais"][m], comp["totais"][m]) for m in comparaveis}
    return dados
```

- [ ] **Step 4: `resultados.py` — remover o bloco de colunas**

Em `aplicar_comparacao`, apagar o bloco `novas_colunas` (de `novas_colunas = []` até `dados["colunas"] = novas_colunas`), deixando:

```python
def aplicar_comparacao(dados, cenario_comparado_id, periodo, agrupar, filtros):
    """Anota `dados` com Δ% contra `cenario_comparado_id`: `linha["<m>_delta"]`
    por métrica e `dados["totais_delta"]`. **NÃO altera `dados["colunas"]`** — o Δ
    é renderizado embutido na célula. Linha crua (diario×fabrica_armazem) não
    recebe Δ."""
    periodo, agrupar = normalizar_visao(periodo, agrupar)
    if (periodo, agrupar) == ("diario", "fabrica_armazem"):
        dados["comparacao_ignorada"] = True
        return dados
    dados["comparacao_ignorada"] = False

    comp = agregar(cenario_comparado_id, periodo, agrupar,
                   _traduzir_filtros(filtros, cenario_comparado_id), pagina=None)
    por_chave = {linha_c["_chave"]: linha_c for linha_c in comp["linhas"]}

    for linha in dados["linhas"]:
        alvo = por_chave.get(linha["_chave"])
        for m in _METRICAS:
            linha[f"{m}_delta"] = _delta(linha[m], alvo[m] if alvo else None)

    dados["totais_delta"] = {
        m: _delta(dados["totais"][m], comp["totais"][m]) for m in _METRICAS}
    return dados
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest apps/simulacao/tests/test_estoque_comparacao.py apps/simulacao/tests/test_resultados_comparacao.py apps/simulacao/tests/test_estoque_agregar.py apps/simulacao/tests/test_resultados_agregar.py -q`
Expected: PASS. `python manage.py check`.

- [ ] **Step 6: Commit**

```bash
git add apps/simulacao/estoque.py apps/simulacao/resultados.py apps/simulacao/tests/test_estoque_comparacao.py apps/simulacao/tests/test_resultados_comparacao.py
git commit -m "refactor(ux): aplicar_comparacao não insere mais colunas Δ (embutido na célula)"
```

---

### Task 4: Δ embutido nas células das tabelas

**Files:**
- Modify: `templates/simulacao/_resultados_tabela.html`, `templates/simulacao/_estoque_tabela.html`
- Test: `apps/simulacao/tests/test_views_estoque.py:101-108` (`test_comparacao_gera_colunas_delta`), `apps/simulacao/tests/test_views_resultados.py`

**Interfaces:**
- Consumes: `dados["totais_delta"]` (dict) e `linha["<col.key>_delta"]` — presentes quando comparação ativa (Task 3).

- [ ] **Step 1: Ajustar o teste**

Em `apps/simulacao/tests/test_views_estoque.py`, `test_comparacao_gera_colunas_delta` — renomear para `test_comparacao_gera_delta_embutido` e trocar a asserção:

```python
    def test_comparacao_gera_delta_embutido(self):
        self._povoar()
        comp = Cenario.all_cooperativas.create(cooperativa=self.coop, nome="Comp")
        self._povoar(cenario=comp, saldo=30)
        self.client.force_login(self.user)
        r = self.client.get(self.url, {"visao": "sistema", "comparar": comp.id},
                            HTTP_HX_REQUEST="true")
        self.assertNotContains(r, "Δ%")          # não é mais cabeçalho de coluna
        self.assertContains(r, "↑")              # Δ renderizado inline (saldo 50 vs 30 → +66,7%)
        self.assertContains(r, "leading-tight")  # o span do Δ embutido
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest apps/simulacao/tests/test_views_estoque.py::EstoqueViewTests::test_comparacao_gera_delta_embutido -v`
Expected: FAIL — `assertNotContains(r, "Δ%")` falha (o template ainda tem o ramo `tipo == 'delta'` e as colunas vêm de... na verdade Task 3 já tirou as colunas, então o `Δ%` some do `<thead>`, mas o `↑`/`leading-tight` inline ainda não existe → `assertContains(r, "leading-tight")` falha).

- [ ] **Step 3: `_resultados_tabela.html` — Δ inline + `<tfoot>`**

No ramo de célula do `<tbody>` (o `{% for col in dados.colunas %}<td>...`), trocar os ramos `num` / `moeda` e **remover** o ramo `delta`:

```html
{% for col in dados.colunas %}
  <td>
    {% if col.tipo == 'data_dia' %}{{ linha.dia|date:'d/m/Y' }}
    {% elif col.tipo == 'data_mes' %}{{ linha.dia|date:'m/Y' }}
    {% elif col.tipo == 'texto' %}{{ linha|item:col.key }}
    {% elif col.tipo == 'num' %}{{ linha|item:col.key|volume }}{% if dados.totais_delta %}{% with dk=col.key|add:'_delta' %}<span class="block text-xs leading-tight">{{ linha|item:dk|variacao }}</span>{% endwith %}{% endif %}
    {% elif col.tipo == 'moeda' %}{{ linha|item:col.key|moeda }}{% if dados.totais_delta %}{% with dk=col.key|add:'_delta' %}<span class="block text-xs leading-tight">{{ linha|item:dk|variacao }}</span>{% endwith %}{% endif %}
    {% endif %}
  </td>
{% endfor %}
```

No `<tfoot>` (o `{% if dados.paginacao is None and dados.linhas %}`), trocar a célula por:

```html
<tfoot><tr class="font-semibold">
  {% for col in dados.colunas %}
    <td>
      {% if col.tipo == 'num' %}{{ dados.totais|item:col.key|volume }}{% if dados.totais_delta %}<span class="block text-xs leading-tight">{{ dados.totais_delta|item:col.key|variacao }}</span>{% endif %}
      {% elif col.tipo == 'moeda' %}{{ dados.totais|item:col.key|moeda }}{% if dados.totais_delta %}<span class="block text-xs leading-tight">{{ dados.totais_delta|item:col.key|variacao }}</span>{% endif %}
      {% elif forloop.first %}Total{% endif %}
    </td>
  {% endfor %}
</tr></tfoot>
```

- [ ] **Step 4: `_estoque_tabela.html` — Δ inline + `<tfoot>`**

No ramo `num` da célula (linha ~14) — acrescentar o Δ embutido depois do `<span>` do valor; **remover** o ramo `{% elif col.tipo == 'delta' %}` (linha ~13):

```html
{% elif col.tipo == 'num' %}<span class="{% if col.key == 'excedente' and linha.excedente > 0 %}text-error font-semibold{% elif col.key == 'saldo' and linha.saldo < 0 %}text-error font-semibold{% endif %}">{{ linha|item:col.key|volume }}</span>{% if dados.totais_delta %}{% with dk=col.key|add:'_delta' %}<span class="block text-xs leading-tight">{{ linha|item:dk|variacao }}</span>{% endwith %}{% endif %}
```

No `<tfoot>` (`{% if visao == 'sistema' and dados.linhas %}`), trocar a célula por:

```html
<tfoot><tr class="font-semibold">
  {% for col in dados.colunas %}
    <td>{% if col.tipo == 'num' %}{{ dados.totais|item:col.key|volume }}{% if dados.totais_delta %}<span class="block text-xs leading-tight">{{ dados.totais_delta|item:col.key|variacao }}</span>{% endif %}{% elif forloop.first %}Total{% endif %}</td>
  {% endfor %}
</tr></tfoot>
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest apps/simulacao/tests/test_views_estoque.py apps/simulacao/tests/test_views_resultados.py -q`
Expected: PASS. Se algum teste do Resultados afirmava `Δ%` no `<thead>`, ajustar para o Δ inline (mesmo padrão do Step 1).

- [ ] **Step 6: Commit**

```bash
git add templates/simulacao/_resultados_tabela.html templates/simulacao/_estoque_tabela.html apps/simulacao/tests/test_views_estoque.py apps/simulacao/tests/test_views_resultados.py
git commit -m "feat(ux): Δ da comparação embutido na célula (métrica + variação juntas)"
```

---

### Task 5: Barra de filtros — `<details>` para os avançados + rename de ids

**Files:**
- Modify: `apps/simulacao/views.py` (helper `_filtros_avancados` + contexto de `estoque_tab` / `resultados_tab`)
- Modify: `templates/simulacao/_estoque_content.html`, `templates/simulacao/_resultados_content.html`
- Test: `apps/simulacao/tests/test_views_estoque.py`, `apps/simulacao/tests/test_views_resultados.py`

**Interfaces:**
- Produces: `views._filtros_avancados(filtros) -> (ativos: bool, count: int)`. Contexto novo nas duas tab-views: `filtros_avancados_ativos` (bool), `filtros_avancados_count` (int). IDs dos `<select>` hand-rolled: `estoque-visao` / `estoque-comparar`; `resultados-periodo` / `resultados-agrupar` / `resultados-comparar`.

- [ ] **Step 1: Write the failing test**

Acrescentar a `apps/simulacao/tests/test_views_estoque.py` (dentro de `EstoqueViewTests`):

```python
    def test_barra_de_filtros_recolhida_por_default(self):
        self._povoar()
        self.client.force_login(self.user)
        r = self.client.get(self.url, HTTP_HX_REQUEST="true")
        self.assertContains(r, "<details")
        self.assertContains(r, 'id="estoque-visao"')
        self.assertNotContains(r, "<details open")

    def test_barra_de_filtros_abre_com_filtro_ativo(self):
        arm, _ = self._povoar()
        self.client.force_login(self.user)
        r = self.client.get(self.url, {"armazem_ids": [arm.id]}, HTTP_HX_REQUEST="true")
        self.assertContains(r, "<details open")
        self.assertContains(r, "badge badge-sm")   # contador
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest apps/simulacao/tests/test_views_estoque.py -k barra_de_filtros -v`
Expected: FAIL — `<details` não está no template.

- [ ] **Step 3: `views.py` — helper + contexto**

Acrescentar, logo antes de `_resultados_params` (ou perto dos outros helpers de módulo):

```python
def _filtros_avancados(filtros):
    """`(ativos, count)` — quantos dos filtros de mês/data/unidade estão preenchidos."""
    campos = ("mes_de", "mes_ate", "data_de", "data_ate", "armazem_ids", "fabrica_ids")
    n = sum(1 for c in campos if filtros.get(c))
    return n > 0, n
```

Em `resultados_tab`, dentro do bloco que monta `ctx` (depois de `filtros` já existir), acrescentar ao dict `ctx`:

```python
        "filtros_avancados_ativos": _filtros_avancados(filtros)[0],
        "filtros_avancados_count": _filtros_avancados(filtros)[1],
```

(ou uma variável local `fa_ativos, fa_count = _filtros_avancados(filtros)` e usar as duas.) Fazer o mesmo em `estoque_tab`.

- [ ] **Step 4: `_estoque_content.html` — reestruturar o form**

Substituir o `<form id="form-estoque">` inteiro (do `<form` ao `</form>`) por:

```html
  <form id="form-estoque"
        hx-get="{% url 'simulacao:estoque_tab' cenario.id %}"
        hx-target="#estoque-area" hx-swap="innerHTML" hx-push-url="true"
        hx-trigger="change from:#estoque-visao, change from:#estoque-comparar, submit"
        class="mb-4">
    <div class="flex flex-wrap items-end gap-3">
      <label class="flex flex-col text-sm">Visão
        <select id="estoque-visao" name="visao" class="select select-bordered select-sm">
          {% for valor, rotulo in visoes %}<option value="{{ valor }}" {% if valor == visao %}selected{% endif %}>{{ rotulo }}</option>{% endfor %}
        </select>
      </label>
      <label class="flex flex-col text-sm">Comparar com
        <select id="estoque-comparar" name="comparar" class="select select-bordered select-sm">
          <option value="">— sem comparação —</option>
          {% for c in comparaveis %}<option value="{{ c.id }}" {% if comparar == c.id|stringformat:'s' %}selected{% endif %}>{{ c.nome }}</option>{% endfor %}
        </select>
      </label>
      <button type="submit" class="btn btn-outline btn-sm">Aplicar</button>
      <a href="{% url 'simulacao:estoque_tab' cenario.id %}" class="btn btn-ghost btn-sm">Limpar</a>
    </div>
    <details class="mt-3" {% if filtros_avancados_ativos %}open{% endif %}>
      <summary class="cursor-pointer text-sm text-base-content/70">Filtros{% if filtros_avancados_count %} <span class="badge badge-sm badge-neutral">{{ filtros_avancados_count }}</span>{% endif %}</summary>
      <div class="mt-2 flex flex-wrap items-end gap-3">
        <label class="flex flex-col text-sm">Mês de {{ form.mes_de }}</label>
        <label class="flex flex-col text-sm">Mês até {{ form.mes_ate }}</label>
        <label class="flex flex-col text-sm">Armazéns {{ form.armazem_ids }}</label>
        <label class="flex flex-col text-sm">Fábricas {{ form.fabrica_ids }}</label>
      </div>
    </details>
  </form>
```

- [ ] **Step 5: `_resultados_content.html` — reestruturar o form**

Mesma estrutura. Linha principal = Período + Agrupar + Comparar + Aplicar + Limpar; `<details>` = Data de/até + Armazéns + Fábricas. `hx-trigger="change from:#resultados-periodo, change from:#resultados-agrupar, change from:#resultados-comparar, submit"`. IDs: `resultados-periodo` / `resultados-agrupar` / `resultados-comparar`. O `<select>` de Agrupar mantém o `{% if periodo == 'total' %}disabled{% endif %}`.

```html
  <form id="form-resultados"
        hx-get="{% url 'simulacao:resultados_tab' cenario.id %}"
        hx-target="#resultados-area" hx-swap="innerHTML" hx-push-url="true"
        hx-trigger="change from:#resultados-periodo, change from:#resultados-agrupar, change from:#resultados-comparar, submit"
        class="mb-4">
    <div class="flex flex-wrap items-end gap-3">
      <label class="flex flex-col text-sm">Período
        <select id="resultados-periodo" name="periodo" class="select select-bordered select-sm">
          {% for valor, rotulo in periodos %}<option value="{{ valor }}" {% if valor == periodo %}selected{% endif %}>{{ rotulo }}</option>{% endfor %}
        </select>
      </label>
      <label class="flex flex-col text-sm">Agrupar por
        <select id="resultados-agrupar" name="agrupar" class="select select-bordered select-sm" {% if periodo == 'total' %}disabled{% endif %}>
          {% for valor, rotulo in agrupamentos %}<option value="{{ valor }}" {% if valor == agrupar %}selected{% endif %}>{{ rotulo }}</option>{% endfor %}
        </select>
      </label>
      <label class="flex flex-col text-sm">Comparar com
        <select id="resultados-comparar" name="comparar" class="select select-bordered select-sm">
          <option value="">— sem comparação —</option>
          {% for c in comparaveis %}<option value="{{ c.id }}" {% if comparar == c.id|stringformat:'s' %}selected{% endif %}>{{ c.nome }}</option>{% endfor %}
        </select>
      </label>
      <button type="submit" class="btn btn-outline btn-sm">Aplicar</button>
      <a href="{% url 'simulacao:resultados_tab' cenario.id %}" class="btn btn-ghost btn-sm">Limpar</a>
    </div>
    <details class="mt-3" {% if filtros_avancados_ativos %}open{% endif %}>
      <summary class="cursor-pointer text-sm text-base-content/70">Filtros{% if filtros_avancados_count %} <span class="badge badge-sm badge-neutral">{{ filtros_avancados_count }}</span>{% endif %}</summary>
      <div class="mt-2 flex flex-wrap items-end gap-3">
        <label class="flex flex-col text-sm">Data de {{ form.data_de }}</label>
        <label class="flex flex-col text-sm">Data até {{ form.data_ate }}</label>
        <label class="flex flex-col text-sm">Armazéns {{ form.armazem_ids }}</label>
        <label class="flex flex-col text-sm">Fábricas {{ form.fabrica_ids }}</label>
      </div>
    </details>
  </form>
```

- [ ] **Step 6: Run tests**

Run: `python -m pytest apps/simulacao/tests/test_views_estoque.py apps/simulacao/tests/test_views_resultados.py apps/core/tests/test_render_smoke.py -q`
Expected: PASS. `python manage.py check`.

- [ ] **Step 7: Commit**

```bash
git add apps/simulacao/views.py templates/simulacao/_estoque_content.html templates/simulacao/_resultados_content.html apps/simulacao/tests/test_views_estoque.py apps/simulacao/tests/test_views_resultados.py
git commit -m "feat(ux): filtros avançados num <details> recolhível + ids de select prefixados"
```

---

### Task 6: Ajustes de tabela — thead/coluna fixos, realce, legenda, gráfico mobile, rótulos

**Files:**
- Modify: `templates/simulacao/_estoque_tabela.html`, `templates/simulacao/_resultados_tabela.html`, `templates/simulacao/_estoque_area.html`, `templates/simulacao/_resultados_area.html`
- Test: `apps/simulacao/tests/test_views_estoque.py`, `apps/simulacao/tests/test_views_resultados.py`

**Interfaces:**
- Consumes: `visao` no contexto (já existe), `dados` (já existe).

- [ ] **Step 1: Ajustar / acrescentar testes**

Em `apps/simulacao/tests/test_views_estoque.py`:

```python
    def test_sinalizacao_excedente(self):   # substitui o existente
        self._povoar(excedente=40)
        self.client.force_login(self.user)
        r = self.client.get(self.url, {"visao": "armazem"}, HTTP_HX_REQUEST="true")
        self.assertContains(r, "bg-error/10")
        self.assertContains(r, "border-l-4 border-error")

    def test_grafico_escondido_no_mobile(self):
        self._povoar()
        self.client.force_login(self.user)
        r = self.client.get(self.url, HTTP_HX_REQUEST="true")
        self.assertContains(r, "hidden sm:block")

    def test_legenda_de_unidade(self):
        self._povoar()
        self.client.force_login(self.user)
        r = self.client.get(self.url, HTTP_HX_REQUEST="true")
        self.assertContains(r, "Valores em toneladas")

    def test_thead_fixo_so_na_visao_por_unidade(self):
        self._povoar()
        self.client.force_login(self.user)
        sis = self.client.get(self.url, {"visao": "sistema"}, HTTP_HX_REQUEST="true")
        arm = self.client.get(self.url, {"visao": "armazem"}, HTTP_HX_REQUEST="true")
        self.assertNotContains(sis, "sticky top-0")
        self.assertContains(arm, "sticky top-0")
        self.assertContains(arm, "sticky left-0")
```

Em `apps/simulacao/tests/test_views_resultados.py` — acrescentar `test_grafico_escondido_no_mobile` (mesmo shape, na visão mensal) e `test_legenda_de_unidade`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest apps/simulacao/tests/test_views_estoque.py -k "sinalizacao or mobile or legenda or thead" -v`
Expected: FAIL — as classes/strings ainda não existem.

- [ ] **Step 3: `_estoque_tabela.html` — realce, container, thead, legenda**

- No topo do arquivo, depois do `{% load simulacao_filters %}`, acrescentar:
  `<p class="mb-2 text-xs text-base-content/60">Valores em toneladas</p>`
- Trocar `<div class="overflow-x-auto">` por:
  `<div class="{% if visao == 'sistema' %}overflow-x-auto{% else %}max-h-[70vh] overflow-auto{% endif %}">`
- `<thead><tr>` → `<thead class="{% if visao != 'sistema' %}sticky top-0 z-10 bg-base-100{% endif %}"><tr>`
- No `<thead>`, o `{% for col in dados.colunas %}<th>{{ col.label }}</th>{% endfor %}` →
  `{% for col in dados.colunas %}<th class="{% if visao != 'sistema' and forloop.first %}sticky left-0 bg-base-100 z-20{% endif %}">{{ col.label }}</th>{% endfor %}`
- A `<tr>` de dados: hoje `<tr class="hover:bg-base-200{% if alerta %} bg-error/5{% endif %}">`. Trocar por:
  `<tr class="hover:bg-base-200{% if alerta == 'ruptura' %} bg-error/20 border-l-4 border-error{% elif alerta %} bg-error/10 border-l-4 border-error{% endif %}">`
- A 1ª `<td>` de cada linha (a que abre o `{% for col in dados.colunas %}` — envolver com sticky quando por unidade). Trocar `<td>` por:
  `<td class="{% if visao != 'sistema' and forloop.first %}sticky left-0 z-10 {% if alerta == 'ruptura' %}bg-error/20{% elif alerta %}bg-error/10{% else %}bg-base-100{% endif %}{% endif %}">`
- O `⚠` da ruptura: hoje `{% if alerta == 'ruptura' and forloop.first %}⚠ {% endif %}` já está no ramo `mes`. Como a coluna `mes` sai das visões por unidade (Task 8), mover o `⚠` para o ramo `texto` (unidade) **naquela task**; nesta task deixar como está (a visão Sistema mantém a coluna `mes`).

- [ ] **Step 4: `_resultados_tabela.html` — legenda**

No topo, depois do `{% load simulacao_filters %}` (e depois do `{% if dados.comparacao_ignorada %}`), acrescentar:
`<p class="mb-2 text-xs text-base-content/60">Valores em toneladas</p>`
(As tabelas do Resultados não paginam nas visões longas de forma diferente e não recebem thead fixo — spec Decisão 5: "as tabelas do Resultados ficam como estão".)

- [ ] **Step 5: `_estoque_area.html` / `_resultados_area.html` — gráfico mobile + rótulos de export**

- `_estoque_area.html`: `{% if grafico %}<div id="estoque-grafico" class="mb-4">` → `class="mb-4 hidden sm:block"`. Botões: `Exportar (Excel)` → `Excel`; `CSV` mantém.
- `_resultados_area.html`: `<div id="resultados-grafico" class="mb-4">` → `class="mb-4 hidden sm:block"`. `Exportar (Excel)` → `Excel`.

- [ ] **Step 6: Run tests**

Run: `python -m pytest apps/simulacao/tests/test_views_estoque.py apps/simulacao/tests/test_views_resultados.py apps/core/tests/test_render_smoke.py -q`
Expected: PASS. `python manage.py check`.

- [ ] **Step 7: Commit**

```bash
git add templates/simulacao/_estoque_tabela.html templates/simulacao/_resultados_tabela.html templates/simulacao/_estoque_area.html templates/simulacao/_resultados_area.html apps/simulacao/tests/test_views_estoque.py apps/simulacao/tests/test_views_resultados.py
git commit -m "feat(ux): thead/1ª coluna fixos por unidade, realce visível, legenda t, gráfico só em sm+"
```

---

### Task 7: Card de pico do Estoque — barra de ocupação + 7 tiles

**Files:**
- Modify: `apps/simulacao/estoque.py` (`card_de_pico`)
- Modify: `templates/simulacao/_estoque_area.html`
- Test: `apps/simulacao/tests/test_estoque_card.py`, `apps/simulacao/tests/test_views_estoque.py`

**Interfaces:**
- Consumes: `card` no contexto (de `card_com_delta`, já no `estoque_tab`).
- Produces: `card_de_pico(...)` devolve, além do que já devolve: `mes_pico: str` (`_mes_ptbr` do mês de maior saldo; `""` para recorte vazio), `ocupacao_pct: float` (`round(min(saldo,cap)/cap*100, 1)`, `0.0` se `cap<=0`), `excedente_pct: float` (`round(excedente/cap*100, 1)`, `0.0` se `cap<=0`). `card_com_delta` repassa as três (não calcula Δ delas).

- [ ] **Step 1: Write the failing test**

Acrescentar a `apps/simulacao/tests/test_estoque_card.py` (dentro de `CardTests`):

```python
    def test_card_mes_pico_e_percentuais(self):
        c = estoque.card_de_pico(self.cen.id, VAZIO)
        self.assertEqual(c["mes_pico"], "02/2026")   # fev tem o maior saldo (250)
        self.assertEqual(c["ocupacao_pct"], 50.0)    # min(250, 500) / 500 * 100
        self.assertEqual(c["excedente_pct"], 10.0)   # 50 / 500 * 100

    def test_card_percentuais_sem_capacidade(self):
        cen = Cenario.objects.create(cooperativa=self.coop, nome="SemCap")
        arm = Armazem.objects.create(
            cooperativa=self.coop, cenario=cen, nome="A",
            capacidade_estatica=1, capacidade_expedicao_diaria=1, estoque_inicial=0)
        ResumoMensalArmazem.objects.create(
            cooperativa=self.coop, cenario=cen, armazem=arm, mes="2026-01",
            rec_produtor=10, envio_transbordo=0, vendas=0, saldo_estoque=5,
            capacidade_estatica=0, excedente=0)
        c = estoque.card_de_pico(cen.id, VAZIO)
        self.assertEqual(c["ocupacao_pct"], 0.0)
        self.assertEqual(c["excedente_pct"], 0.0)

    def test_card_vazio_tem_as_chaves_novas(self):
        cen = Cenario.objects.create(cooperativa=self.coop, nome="Vazio")
        c = estoque.card_de_pico(cen.id, VAZIO)
        self.assertEqual(c["mes_pico"], "")
        self.assertEqual(c["ocupacao_pct"], 0.0)
        self.assertEqual(c["excedente_pct"], 0.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest apps/simulacao/tests/test_estoque_card.py -k "mes_pico or percentuais or chaves_novas" -v`
Expected: FAIL — `KeyError: 'mes_pico'`.

- [ ] **Step 3: `estoque.py::card_de_pico` — as 3 chaves derivadas**

No início da função, o dict inicial ganha as chaves (para o recorte vazio já sair completo):

```python
    linhas = _agregar_sistema(cenario_id, filtros)
    card = {m: 0.0 for m in _METRICAS_CARD}
    card["saldo_min"] = 0.0
    card["mes_ruptura"] = None
    card["mes_pico"] = ""
    card["ocupacao_pct"] = 0.0
    card["excedente_pct"] = 0.0
    if not linhas:
        return card
```

No fim da função (depois de `card["capacidade"] = linhas[0]["capacidade"]` e do bloco de `saldo_min`/`mes_ruptura`):

```python
    pico = max(linhas, key=lambda linha: linha["saldo"])
    card["mes_pico"] = _mes_ptbr(pico["mes"])
    cap = card["capacidade"]
    if cap > 0:
        card["ocupacao_pct"] = round(min(card["saldo"], cap) / cap * 100, 1)
        card["excedente_pct"] = round(card["excedente"] / cap * 100, 1)
    return card
```

(`card_com_delta` **não muda** — já devolve `atual`, que agora tem as chaves novas; `delta` continua só sobre `_METRICAS_CARD`.)

- [ ] **Step 4: Run card tests**

Run: `python -m pytest apps/simulacao/tests/test_estoque_card.py -q`
Expected: PASS.

- [ ] **Step 5: `_estoque_area.html` — bloco do card**

Substituir o `<c-resumo-numerico>...</c-resumo-numerico>` inteiro (do `<c-resumo-numerico class="mb-4">` ao `</c-resumo-numerico>`) por:

```html
<div class="mb-4 rounded-lg border border-base-300 bg-base-100 p-4">
  <p class="mb-2 text-xs uppercase tracking-wide text-base-content/60">Pico do sistema{% if card.mes_pico %} · {{ card.mes_pico }}{% endif %}</p>
  <div class="relative h-6 overflow-hidden rounded border border-base-300 bg-base-200">
    <div class="absolute inset-y-0 left-0 bg-accent" style="width: {{ card.ocupacao_pct }}%"></div>
    {% if card.excedente_pct > 0 %}<div class="absolute inset-y-0 right-0 bg-error" style="width: {{ card.excedente_pct }}%; max-width: 100%; background-image: repeating-linear-gradient(45deg, rgba(255,255,255,.4) 0 3px, transparent 3px 7px)"></div>{% endif %}
    {% if card.mes_ruptura %}<div class="absolute inset-y-0 left-0 w-2 bg-error"></div>{% endif %}
  </div>
  <p class="mt-1.5 text-xs text-base-content/70">
    Saldo <b>{{ card.saldo|volume }} t</b> · Capacidade <b>{{ card.capacidade|volume }} t</b>
    {% if card.mes_ruptura %}· <span class="text-error">Ruptura em {{ card.mes_ruptura }} ({{ card.saldo_min|volume }} t)</span>
    {% elif card.excedente > 0 %}· <span class="text-error">Excedente +{{ card.excedente|volume }} t ({{ card.excedente_pct }}%)</span>{% endif %}
  </p>
</div>

<c-resumo-numerico class="mb-4">
  <div class="stat"><div class="stat-title">Recebimento</div>
    <div class="stat-value text-base-content">{{ card.recebimento|volume }}</div>
    {% if card.delta %}<div class="stat-desc">{{ card.delta.recebimento|variacao }}</div>{% endif %}</div>
  <div class="stat"><div class="stat-title">Transbordo</div>
    <div class="stat-value text-base-content">{{ card.transbordo|volume }}</div>
    {% if card.delta %}<div class="stat-desc">{{ card.delta.transbordo|variacao }}</div>{% endif %}</div>
  <div class="stat"><div class="stat-title">Esmagamento</div>
    <div class="stat-value text-base-content">{{ card.esmagamento|volume }}</div>
    {% if card.delta %}<div class="stat-desc">{{ card.delta.esmagamento|variacao }}</div>{% endif %}</div>
  <div class="stat"><div class="stat-title">Vendas</div>
    <div class="stat-value text-base-content">{{ card.vendas|volume }}</div>
    {% if card.delta %}<div class="stat-desc">{{ card.delta.vendas|variacao }}</div>{% endif %}</div>
  <div class="stat"><div class="stat-title">Saldo (pico)</div>
    <div class="stat-value {% if card.mes_ruptura or card.saldo > card.capacidade %}text-error{% else %}text-base-content{% endif %}">{% if card.mes_ruptura %}{{ card.saldo_min|volume }}{% else %}{{ card.saldo|volume }}{% endif %}</div>
    {% if card.mes_ruptura %}<div class="stat-desc text-error">ruptura em {{ card.mes_ruptura }}</div>{% elif card.delta %}<div class="stat-desc">{{ card.delta.saldo|variacao }}</div>{% endif %}</div>
  <div class="stat"><div class="stat-title">Cap. Estática</div>
    <div class="stat-value text-base-content">{{ card.capacidade|volume }}</div>
    {% if card.delta %}<div class="stat-desc">{{ card.delta.capacidade|variacao }}</div>{% endif %}</div>
  <div class="stat"><div class="stat-title">Excedente (pico)</div>
    <div class="stat-value {% if card.excedente > 0 %}text-error{% else %}text-base-content{% endif %}">{{ card.excedente|volume }}</div>
    {% if card.delta %}<div class="stat-desc">{{ card.delta.excedente|variacao }}</div>{% endif %}</div>
</c-resumo-numerico>
```

- [ ] **Step 6: Teste de view do card**

Acrescentar a `apps/simulacao/tests/test_views_estoque.py`:

```python
    def test_card_de_pico_no_html(self):
        self._povoar(excedente=40)
        self.client.force_login(self.user)
        r = self.client.get(self.url, HTTP_HX_REQUEST="true")
        self.assertContains(r, "Pico do sistema")
        self.assertContains(r, "Esmagamento")   # agora no card
        self.assertContains(r, "bg-accent")     # a barra de ocupação
```

- [ ] **Step 7: Run tests**

Run: `python -m pytest apps/simulacao/tests/test_estoque_card.py apps/simulacao/tests/test_views_estoque.py -q`
Expected: PASS. `python manage.py check` + `makemigrations --check --dry-run`.

- [ ] **Step 8: Commit**

```bash
git add apps/simulacao/estoque.py templates/simulacao/_estoque_area.html apps/simulacao/tests/test_estoque_card.py apps/simulacao/tests/test_views_estoque.py
git commit -m "feat(estoque): card de pico com barra de ocupação (saldo × capacidade × excedente) + 7 tiles"
```

---

### Task 8: Faixas de mês nas visões por unidade + coluna "Mês" fora

**Files:**
- Modify: `apps/simulacao/estoque.py` (`VISOES`, `agregar`)
- Modify: `apps/simulacao/templatetags/simulacao_filters.py` (novo filtro `mes_extenso`)
- Modify: `templates/simulacao/_estoque_tabela.html`
- Test: `apps/simulacao/tests/test_templatetags_mes_extenso.py` (criar), `apps/simulacao/tests/test_estoque_config.py`, `apps/simulacao/tests/test_estoque_agregar.py`, `apps/simulacao/tests/test_views_estoque.py`

**Interfaces:**
- Consumes: `_agregar_sistema` (já existe).
- Produces:
  - `VISOES["armazem"]["colunas"]` / `VISOES["fabrica"]["colunas"]` **sem** `_COL_MES` — a 1ª coluna é `{"key": "unidade", ...}`.
  - `agregar(visao="armazem"/"fabrica")` devolve `dados["faixas"]` = `dict` `{mes: <linha do sistema desse mês>}` (só meses do recorte). Visão `"sistema"` → `dados["faixas"] = None`.
  - `mes_extenso("2026-02") -> "Fevereiro 2026"` (filtro de template).

- [ ] **Step 1: Write the failing tests**

`apps/simulacao/tests/test_templatetags_mes_extenso.py` (criar):

```python
from django.test import SimpleTestCase

from apps.simulacao.templatetags.simulacao_filters import mes_extenso


class MesExtensoTests(SimpleTestCase):
    def test_formata(self):
        self.assertEqual(mes_extenso("2026-02"), "Fevereiro 2026")
        self.assertEqual(mes_extenso("2026-12"), "Dezembro 2026")

    def test_entrada_estranha_passa_reto(self):
        self.assertEqual(mes_extenso(""), "")
        self.assertEqual(mes_extenso("xpto"), "xpto")
```

Em `apps/simulacao/tests/test_estoque_config.py`, `test_colunas_de_dimensao` — a asserção `[:2] == ["mes", "unidade"]` passa a falhar. Trocar por:

```python
    def test_colunas_de_dimensao(self):
        chaves_sistema = [c["key"] for c in estoque.VISOES["sistema"]["colunas"]]
        self.assertEqual(chaves_sistema[0], "mes")
        self.assertNotIn("unidade", chaves_sistema)
        chaves_arm = [c["key"] for c in estoque.VISOES["armazem"]["colunas"]]
        self.assertEqual(chaves_arm[0], "unidade")
        self.assertNotIn("mes", chaves_arm)
```

Em `apps/simulacao/tests/test_estoque_agregar.py` (dentro de `AgregarTests`):

```python
    def test_visao_por_unidade_tem_faixas_do_sistema(self):
        d = estoque.agregar(self.cen.id, "armazem", VAZIO)
        self.assertEqual(set(d["faixas"]), {"2026-01", "2026-02"})
        self.assertEqual(d["faixas"]["2026-01"]["saldo"], 95.0)      # 50 + 35 + 10
        self.assertEqual(d["faixas"]["2026-01"]["capacidade"], 600.0)
        self.assertEqual(d["faixas"]["2026-02"]["excedente"], 50.0)
        self.assertNotIn("mes", [c["key"] for c in d["colunas"]])

    def test_visao_sistema_sem_faixas(self):
        d = estoque.agregar(self.cen.id, "sistema", VAZIO)
        self.assertIsNone(d["faixas"])
```

Em `apps/simulacao/tests/test_views_estoque.py`:

```python
    def test_faixa_de_mes_na_visao_por_unidade(self):
        self._povoar()
        self.client.force_login(self.user)
        r = self.client.get(self.url, {"visao": "armazem"}, HTTP_HX_REQUEST="true")
        self.assertContains(r, "sistema — saldo")
        self.assertNotContains(r, ">Mês<")   # coluna Mês saiu
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest apps/simulacao/tests/test_templatetags_mes_extenso.py apps/simulacao/tests/test_estoque_config.py apps/simulacao/tests/test_estoque_agregar.py -k "faixas or dimensao or mes_extenso or sem_faixas" -v`
Expected: FAIL — `mes_extenso` não existe; `chaves_arm[0]` ainda é `"mes"`; `d["faixas"]` não existe.

- [ ] **Step 3: `simulacao_filters.py` — `mes_extenso`**

Acrescentar (perto do `item` / `volume`):

```python
_MESES_PT = ("", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
             "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro")


@register.filter
def mes_extenso(mes):
    """`"2026-02"` -> `"Fevereiro 2026"`. Entrada sem `-` passa reto."""
    s = str(mes)
    if "-" not in s:
        return mes
    ano, m = s.split("-")[:2]
    try:
        return f"{_MESES_PT[int(m)]} {ano}"
    except (ValueError, IndexError):
        return mes
```

- [ ] **Step 4: `estoque.py` — `VISOES` sem `_COL_MES` + `agregar` com `faixas`**

Em `VISOES["armazem"]["colunas"]` e `VISOES["fabrica"]["colunas"]`, remover o `_COL_MES,` inicial (a 1ª coluna passa a ser o dict de `unidade`).

Em `agregar`, na visão `"sistema"`, o return ganha `"faixas": None`:

```python
        return {"colunas": cfg["colunas"], "linhas": linhas, "totais": totais,
                "paginacao": None, "faixas": None}
```

No fim da visão por unidade (antes do return), montar `faixas` e incluir no return:

```python
    totais = _totais_unidade(cenario_id, cfg["fonte"], filtros, extras)
    faixas = {}
    if linhas:
        meses = {linha["mes"] for linha in linhas}
        for sis in _agregar_sistema(cenario_id, filtros):
            if sis["mes"] in meses:
                faixas[sis["mes"]] = sis
    return {"colunas": cfg["colunas"], "linhas": linhas,
            "totais": totais, "paginacao": paginacao, "faixas": faixas}
```

- [ ] **Step 5: `_estoque_tabela.html` — `{% ifchanged %}` + mover o `⚠`**

No `<tbody>`, dentro do `{% for linha in dados.linhas %}`, **antes** do `{% with alerta=linha|item:'_alerta' %}`, acrescentar a faixa:

```html
{% for linha in dados.linhas %}
  {% if visao != 'sistema' %}{% ifchanged linha.mes %}{% with f=dados.faixas|item:linha.mes %}
    <tr class="band bg-base-200 font-medium">
      <td class="sticky left-0 z-20 bg-base-200">{{ linha.mes|mes_extenso }}</td>
      <td colspan="{{ dados.colunas|length|add:'-1' }}" class="text-right text-xs text-base-content/70">
        sistema — saldo {{ f.saldo|volume }} · cap {{ f.capacidade|volume }} · excedente <span class="{% if f.excedente %}text-error{% endif %}">{{ f.excedente|volume }}</span>
      </td>
    </tr>
  {% endwith %}{% endifchanged %}{% endif %}
  {% with alerta=linha|item:'_alerta' %}
  <tr class="hover:bg-base-200{% if alerta == 'ruptura' %} bg-error/20 border-l-4 border-error{% elif alerta %} bg-error/10 border-l-4 border-error{% endif %}">
    {% for col in dados.colunas %}
      <td class="{% if visao != 'sistema' and forloop.first %}sticky left-0 z-10 {% if alerta == 'ruptura' %}bg-error/20{% elif alerta %}bg-error/10{% else %}bg-base-100{% endif %}{% endif %}">
        {% if col.tipo == 'mes' %}{{ linha.mes|slice:'5:7' }}/{{ linha.mes|slice:':4' }}
        {% elif col.tipo == 'texto' %}{% if alerta == 'ruptura' and forloop.first %}⚠ {% endif %}{{ linha|item:col.key }}
        {% elif col.tipo == 'num' %}<span class="{% if col.key == 'excedente' and linha.excedente > 0 %}text-error font-semibold{% elif col.key == 'saldo' and linha.saldo < 0 %}text-error font-semibold{% endif %}">{{ linha|item:col.key|volume }}</span>{% if dados.totais_delta %}{% with dk=col.key|add:'_delta' %}<span class="block text-xs leading-tight">{{ linha|item:dk|variacao }}</span>{% endwith %}{% endif %}
        {% endif %}
      </td>
    {% endfor %}
  </tr>
  {% endwith %}
{% empty %}
```

Este snippet substitui **exatamente** o span do `{% for linha in dados.linhas %}` até (exclusive) o `{% empty %}` — mantendo intactos o resto do arquivo: a legenda e o `<div>`/`<thead>` da Task 6, o `<tfoot>` da Task 4, o `{% empty %}` e o bloco de paginação. Notas: o ramo `mes` fica (a visão Sistema ainda tem essa coluna); o ramo `delta` **não existe mais** (removido na Task 4 — não reintroduzir); o `⚠` da ruptura agora sai no ramo `texto` (a coluna `unidade`, 1ª das visões por unidade).

- [ ] **Step 6: Run tests**

Run: `python -m pytest apps/simulacao/tests/test_templatetags_mes_extenso.py apps/simulacao/tests/test_estoque_config.py apps/simulacao/tests/test_estoque_agregar.py apps/simulacao/tests/test_views_estoque.py -q`
Expected: PASS. `python manage.py check` + `makemigrations --check --dry-run` → "No changes detected".

- [ ] **Step 7: Commit**

```bash
git add apps/simulacao/estoque.py apps/simulacao/templatetags/simulacao_filters.py templates/simulacao/_estoque_tabela.html apps/simulacao/tests/test_templatetags_mes_extenso.py apps/simulacao/tests/test_estoque_config.py apps/simulacao/tests/test_estoque_agregar.py apps/simulacao/tests/test_views_estoque.py
git commit -m "feat(estoque): faixas de mês (totais do sistema) nas visões por unidade; coluna Mês sai"
```

---

### Task 9: Docs, `VERSION` 1.4.0, CHANGELOG, `.gitignore`, gate + tag

**Files:**
- Modify: `apps/simulacao/CLAUDE.md`, `CLAUDE.md` (raiz), `CHANGELOG.md`, `VERSION`, `.gitignore`

- [ ] **Step 1: `.gitignore`**

Acrescentar uma linha (perto de `.superpowers/` / `.worktrees/`):

```
.playwright-mcp/
```

- [ ] **Step 2: `VERSION`**

Conteúdo do arquivo → `1.4.0` (linha única + newline).

- [ ] **Step 3: `CHANGELOG.md`**

Nova seção acima de `## [1.3.0]`:

```markdown
## [1.4.0] - 2026-09-03

Fase 15 — Polimento UX Resultados + Estoque: as duas abas polidas juntas. Nenhuma mudança de regra de negócio, model ou engine — sem migrations, sem ADR novo. Ver a spec 2026-09-03.

### Added
- Estoque: card de pico com **barra de ocupação** (saldo × capacidade estática × excedente), rótulo "Pico do sistema · mês", e as 7 métricas (Esmagamento e Vendas incluídas).
- Estoque: **faixas de mês** nas visões por armazém / por fábrica, cada uma carregando os totais do sistema daquele mês; a coluna "Mês" saiu dessas visões.
- Gráfico (as duas abas): **tema** — relê os tokens `--color-*` e re-renderiza no evento `vector:themechange`; paleta AgroVector (`accent` / `error` / `primary`), série comparada tracejada. §7 do design system atualizado.
- Filtro de template `mes_extenso` (`"2026-02" → "Fevereiro 2026"`).

### Changed
- Comparação (as duas abas): o Δ% deixa de ser coluna e passa a ser **embutido na célula** da métrica (`aplicar_comparacao` não altera mais `dados["colunas"]`).
- `variacao`: um Δ que arredonda para `0,0%` (`abs < 0,05`) é neutro — sem seta e sem cor.
- Barra de filtros (as duas abas): mês/data + multi-selects num `<details>` recolhível, com contador; abre sozinho quando há filtro ativo. IDs dos `<select>` prefixados (`estoque-*` / `resultados-*`).
- Tabelas por unidade (Estoque): `<thead>` e 1ª coluna fixos ao rolar; realce de linha de alerta `bg-error/10` + borda (visível nos dois temas).
- Gráfico escondido abaixo de `sm` (mobile) — a tabela é a via ao dado. Botão de export "Excel" (era "Exportar (Excel)").
```

- [ ] **Step 4: `CLAUDE.md` raiz**

Nova seção após `## Fase 14 ...`:

```markdown
## Fase 15 — Polimento UX Resultados + Estoque (concluída)

Polimento das abas "Resultados" e "Estoque" juntas (achados da revisão de design de 2026-09-02). Ver
`docs/superpowers/specs/2026-09-03-fase15-polimento-ux-design.md`. Nenhum model muda — **sem
migrations**, **sem ADR novo** (a mudança do gráfico entra no §7 do `docs/design-system/README.md`).
`VERSION` → `1.4.0`.

- **Gráfico tematizado** — `render()` relê `--color-*` e re-renderiza no evento `vector:themechange`
  (disparado por `vectorApplyTheme` na `base.html`); paleta AgroVector via `templates/simulacao/_grafico_tokens.html`;
  série comparada tracejada. §7 do design system emendado.
- **Δ da comparação embutido na célula** — `aplicar_comparacao` (os dois módulos) não insere mais
  colunas Δ; a tabela renderiza `métrica` + `variacao` na mesma `<td>`. `variacao` trata Δ que
  arredonda para `0,0%` como neutro.
- **Barra de filtros** — avançados (mês/data + multi-selects) num `<details>` recolhível com contador.
- **Estoque** — card de pico com barra de ocupação + 7 tiles; faixas de mês (totais do sistema) nas
  visões por unidade, sem a coluna "Mês"; `<thead>`/1ª coluna fixos; realce de alerta visível nos dois
  temas; gráfico escondido no mobile.
```

Roadmap Status: "Fases 1–14 concluídas" → "Fases 1–15 concluídas"; menção de `VERSION` para `1.4.0` (tag `v1.4.0`, anotada, local).

- [ ] **Step 5: `apps/simulacao/CLAUDE.md`**

Acrescentar às entradas relevantes (estilo terso):
- `estoque.py`: `aplicar_comparacao` **não altera** `dados["colunas"]` (Δ embutido na célula); `card_de_pico` +`mes_pico`/`ocupacao_pct`/`excedente_pct`; `agregar` por unidade +`faixas` (`{mes: linha do sistema}`) e **sem** a coluna "Mês" (`VISOES["armazem"]`/`["fabrica"]`).
- `simulacao_filters.py`: `variacao` — Δ que arredonda para `0,0%` é neutro; novo `mes_extenso`.
- `views.py`: helper `_filtros_avancados`; `_estoque_content` / `_resultados_content` com `<details>` de filtros e ids `estoque-*` / `resultados-*`.
- `_estoque_area.html`: barra de ocupação no card; `_grafico_tokens.html` (novo) + os dois parciais de gráfico tematizados (§7 do DS).

- [ ] **Step 6: Verificação manual (registrar no commit/relatório)**

Checklist do SPEC — as duas abas × os dois temas × mobile; toggle de tema com o gráfico no ar; comparação com Δ embutido; card com/sem ruptura; faixas de mês + paginação; `<details>` de filtros.

- [ ] **Step 7: Checks finais + commit + tag**

Run:
```bash
python manage.py check
python manage.py makemigrations --check --dry-run   # → No changes detected
python -m pytest -q                                  # → 490 + ~20 novos, todos verdes
```

**Flake conhecido:** teardown de fixture transitório no Windows/PostgreSQL. Se a suíte completa acusar falha, re-rodar o arquivo isolado — só é falha real se falhar isolado também.

```bash
git add apps/simulacao/CLAUDE.md CLAUDE.md CHANGELOG.md VERSION .gitignore
git commit -m "docs: release 1.4.0 (Fase 15 — Polimento UX Resultados + Estoque)"
git tag -a v1.4.0 -m "Fase 15 — Polimento UX Resultados + Estoque"
```

(Não pushar automaticamente — o dono decide. Merge fast-forward em `main` ao fim da revisão de todas as tarefas.)

---

## Self-Review

**1. Cobertura do SPEC:**

| Decisão / seção do SPEC | Task |
|---|---|
| Decisão 1 — `variacao` limiar neutro | 1 |
| Decisão 2 — gráfico tema/paleta + `vector:themechange` + `_grafico_tokens.html` + §7 do DS | 2 |
| Decisão 3 — `aplicar_comparacao` para de inserir colunas (os 2 módulos) | 3 |
| Decisão 3 — Δ embutido nas células + `<tfoot>` (os 2 parciais de tabela) | 4 |
| Decisão 4 — barra de filtros `<details>` + `filtros_avancados_ativos`/`_count` | 5 |
| Decisão 5 — `<thead>`/1ª coluna fixos por unidade | 6, 8 (1ª coluna junto com as faixas) |
| Decisão 5 — realce de alerta `bg-error/10` + borda | 6 |
| Decisão 5 — legenda "Valores em toneladas" | 6 |
| Decisão 5 — ids dos selects prefixados | 5 |
| Decisão 5 — gráfico `hidden sm:block` | 6 |
| Decisão 5 — rótulos de export | 6 |
| Decisão 5 — coluna "Mês" fora das visões por unidade | 8 |
| Decisão 6 — card de pico (`mes_pico`/`ocupacao_pct`/`excedente_pct` + barra + 7 tiles) | 7 |
| Decisão 7 — faixas de mês (`dados["faixas"]` + `{% ifchanged %}` + `mes_extenso`) | 8 |
| Testes (`test_templatetags_variacao`, comparação ajustada, `card`, `agregar` faixas, `config`, views, `base_template`) | 1–8 |
| Docs (§7 DS, CLAUDE.md ×2, CHANGELOG, VERSION 1.4.0, `.gitignore`) | 2 (§7), 9 |
| Sem migrations | check no fim de 7, 8, 9 |

**2. Placeholders:** o Step 5 da Task 8 tem um parêntese "**na verdade remover o `{% elif col.tipo == 'delta' %}`** se sobrou" — não é buraco, é uma nota de reconciliação entre Task 4 (que remove esse ramo) e Task 8 (que reescreve o mesmo `<tbody>`): se as tasks forem feitas em ordem, o ramo já não existe; o snippet da Task 8 não o inclui. Nenhum `TBD`/`TODO`.

**3. Consistência de tipos / nomes:**
- `aplicar_comparacao(dados, cenario_comparado_id, visao, filtros)` (estoque) / `(dados, cenario_comparado_id, periodo, agrupar, filtros)` (resultados) — assinaturas inalteradas (Tasks 3, 4). Só o corpo muda.
- `dados["totais_delta"]` (dict, keyed por `col.key` da métrica) — produzido na Task 3, lido nas Tasks 4 e 8.
- `linha["<col.key>_delta"]` — produzido na Task 3, lido nas Tasks 4 e 8 via `{% with dk=col.key|add:'_delta' %}`.
- `card_de_pico` chaves novas: `mes_pico` (str), `ocupacao_pct` (float), `excedente_pct` (float) — Task 7 produz, Task 7 template lê. `card_com_delta` repassa (não muda).
- `dados["faixas"]`: `dict {mes: <linha sistema>}` nas visões por unidade, `None` na Sistema — Task 8 produz, Task 8 template lê (`dados.faixas|item:linha.mes`).
- `mes_extenso` (filtro) — Task 8 produz e consome.
- `_filtros_avancados(filtros) -> (bool, int)` — Task 5 produz e consome; contexto `filtros_avancados_ativos` / `filtros_avancados_count`.
- IDs `estoque-visao` / `estoque-comparar` / `resultados-periodo` / `resultados-agrupar` / `resultados-comparar` — Task 5 define nos templates **e** nos `hx-trigger`; nenhuma outra task depende deles.
- `vector:themechange` — Task 2 dispara (`base.html`) e escuta (os 2 parciais de gráfico); `window.vectorChartTokens` — Task 2 define (`_grafico_tokens.html`) e consome (os 2 parciais).
- Classes de realce: `bg-error/10` / `bg-error/20` / `border-l-4 border-error` — Task 6 introduz na `<tr>`, Task 8 replica no snippet reescrito do `<tbody>` (consistente).

Correções aplicadas na self-review: (a) Task 6 Step 3 deixa explícito que o `⚠` só migra de coluna na Task 8 (na Task 6 a visão Sistema ainda tem `mes`); (b) Task 8 Step 5 traz o `<tbody>` inteiro reescrito (não um diff parcial) porque Tasks 4, 6 e 8 tocam o mesmo bloco — o snippet final é a fonte de verdade; (c) `card_com_delta` marcado explicitamente como "não muda" na Task 7 para o implementador não procurar mudança lá.

## Execution Handoff

**Plano completo e salvo em `docs/superpowers/plans/2026-09-03-fase15-polimento-ux.md`. Duas opções de execução:**

**1. Subagent-Driven (recomendado)** — um subagent novo por task, revisão em dois estágios entre tasks, iteração rápida. Casa com a ordem "fundação primeiro" do SPEC.

**2. Inline Execution** — executo as tasks nesta sessão via `executing-plans`, em lotes com checkpoints.

**Qual abordagem?**
