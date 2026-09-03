# apps/simulacao — file map

Detail for the files in this directory. See the root `CLAUDE.md` for the project-wide picture (Fase 5 Django migration context, business rules, environment setup).

- `apps/simulacao/models.py` — Django port of `models.py`'s 11 tables, every one with `cooperativa_id` (Fase 5, Port do Domínio) + `ConversaIA` (Fase 9b: histórico do Assistente de IA, `CooperativaScopedModel`, uma conversa `ativa` por cenário+usuário). `apps/simulacao/engine.py` — port of `calculations.py`. `apps/simulacao/services.py` — port of `logistics_services.py`. All three use `Model.all_cooperativas` internally, not `Model.objects` — see `docs/decisions/0006-...`.
- `apps/simulacao/assistente.py` — Fase 9b: loop Gemini (function-calling) in-process sobre `services.py`. `responder(conversa, mensagem)` reconstrói o chat de `conversa.mensagens`, envia com as 9 tools como closures ligadas ao cenário da aba, persiste os dois turnos, nunca propaga exceção. `AssistenteIndisponivel` se `settings.GEMINI_API_KEY` vazio. Port de `ai_assistant.py` (raiz, Streamlit) — duplicação temporária até a Fase 11. Backs `assistente_tab`/`assistente_enviar`/`assistente_nova` em `views.py`. Ver ADR 0010.
- `apps/simulacao/planilha.py` — Carga de Dados: `analisar()` reads and classifies a five-sheet `.xlsx` (Fábricas/Armazéns/Rotas/Previsões/Safras) without writing anything; `aplicar()` re-reads and writes inside one transaction; `gerar_template()` builds a blank workbook from the same column constants the parser consumes. Backs the upload/preview/confirm screens in `apps/simulacao/views.py` (`carga_upload`/`carga_preview`/`carga_template`).
- `apps/simulacao/resultados.py` — **Fase 13**: motor de agregação por ORM da aba "Resultados",
  funções puras sobre `MovimentacaoDiaria`. API:
  - `agregar(cenario_id, periodo, agrupar, filtros, pagina=1, limite=None)` — núcleo; devolve
    `{colunas, linhas, totais, paginacao}`. `limite` não-nulo e recorte maior → levanta
    `RecorteGrandeDemais` **antes** de materializar as linhas (guard do export).
  - `aplicar_comparacao(dados, cenario_comparado_id, periodo, agrupar, filtros)` — anota `dados` com
    `*_delta` por linha + `totais_delta`; linha crua (`diario×fabrica_armazem`) não recebe Δ.
    **Fase 15**: **não altera** `dados["colunas"]` (Δ embutido na célula da métrica).
  - `totais_do_recorte(cenario_id, filtros)` — 3 números do card (barato, sem montar linhas);
    `totais_com_delta(cenario_id, cenario_comparado_id, filtros)` — idem + `delta` por métrica.
  - `dados_grafico(cenario_id, periodo, agrupar, filtros, cenario_comparado_id)` — payload Chart.js
    (barras mensal / linha diário-total) ou `None`.
  - `cenarios_comparaveis(cenario_id, cooperativa_id)` — cenários da coop com `MovimentacaoDiaria`.
  - `normalizar_visao(periodo, agrupar)` — entrada única validada contra `VISOES` (9 formas =
    `(periodo, agrupar)` → def). `_traduzir_filtros(filtros, cenario_id)` (privada) re-resolve
    `armazem_ids`/`fabrica_ids` **por nome** para o cenário comparado (clones têm ids novos).
  - Constantes: `PERIODOS` / `AGRUPAMENTOS` (valores), `ROTULOS_PERIODO` / `ROTULOS_AGRUPAR` (pares
    `(valor, rótulo pt-BR)` p/ os `<select>`), `PAGE_SIZE=100`, `EXPORT_MAX=50_000`, `VISOES`.

  Usa `Model.objects` escopado, **não** `all_cooperativas`; **duplica de propósito** parte de
  `services.py::get_monthly_summary` / `get_daily_movements` — `services.py` é porte 1:1 congelado que
  alimenta MCP/API. Ver ADR 0013 e `docs/superpowers/specs/2026-09-01-fase13-painel-resultados-design.md`.
- `apps/simulacao/estoque.py` — **Fase 14**: motor de agregação por ORM da aba "Estoque", funções
  puras sobre `ResumoMensalArmazem` / `ResumoMensalFabrica` (balanço mensal). API:
  - `agregar(cenario_id, visao, filtros, pagina=1, limite=None)` — núcleo; devolve
    `{colunas, linhas, totais, paginacao, faixas}`. Três visões: `sistema` (merge das duas tabelas por mês,
    só ela tem `<tfoot>`), `armazem`, `fabrica`. `limite` não-nulo e recorte maior → levanta
    `RecorteGrandeDemais` **antes** de materializar as linhas (guard do export). Grava `_alerta` por
    linha ∈ `{None, "excedente", "ruptura"}`. **Fase 15**: nas visões `armazem`/`fabrica` grava
    `faixas` (`{mes: linha do sistema}`) e **remove** a coluna "Mês" (`VISOES["armazem"]`/`["fabrica"]`).
  - `card_de_pico(cenario_id, filtros)` — card "pior momento do sistema" (pico de excedente + saldo
    mínimo mensal + `mes_ruptura` quando negativo); `card_com_delta(cenario_id, cenario_comparado_id,
    filtros)` — idem + `delta` por métrica. **Fase 15**: `card_de_pico` + `mes_pico` /
    `ocupacao_pct` / `excedente_pct` (barra de ocupação do card); `card_com_delta` só repassa.
  - `aplicar_comparacao(dados, cenario_comparado_id, visao, filtros)` — anota `dados` com `*_delta` por
    linha + `totais_delta`, nas 3 visões. **Fase 15**: **não altera** `dados["colunas"]` (Δ embutido
    na célula da métrica).
  - `dados_grafico(cenario_id, filtros, cenario_comparado_id)` — payload Chart.js (linha Saldo total /
    Excedente total por mês, série do comparado opcional) ou `None`.
  - `cenarios_comparaveis(cenario_id, cooperativa_id)` — cenários da coop com balanço mensal.
  - `normalizar_visao(visao)` — entrada única validada contra `VISOES`.
    `_traduzir_filtros(filtros, cenario_id)` (privada) re-resolve `armazem_ids`/`fabrica_ids` por nome
    para o cenário comparado.
  - Constantes: `VISOES`, `ROTULOS_VISAO` (pares `(valor, rótulo pt-BR)` p/ o `<select>`),
    `PAGE_SIZE=100`, `EXPORT_MAX=50_000`, `RecorteGrandeDemais`.

  Usa `Model.objects` escopado pelo contextvar, **não** `all_cooperativas`; **duplica de propósito**
  parte de `services.py::get_factories_summary` / `get_warehouses_summary` / `compare_*` — `services.py`
  é porte 1:1 congelado que alimenta MCP/Face JSON/Assistente. Sem migrations. Ver
  `docs/superpowers/specs/2026-09-02-fase14-painel-estoque-design.md`.
- `apps/simulacao/forms.py` — **Fase 13**: `ResultadosForm` (`forms.Form` puro; datas +
  `armazem_ids` / `fabrica_ids` do cenário; `filtros_limpos()` devolve o dict de filtros). **Fase 14**:
  `EstoqueForm` (`forms.Form` puro; mês `type=month` — `CharField` + regex `YYYY-MM` — + multi de
  armazém / fábrica; `filtros_limpos()` devolve `{mes_de, mes_ate, armazem_ids, fabrica_ids}`).
- `apps/simulacao/views.py` — as views HTMX do domínio. Desde a **Fase 12** (ADR 0012) são gated por
  `@requer_membro_organizacao` (membro **ou** Admin Vector com organização selecionada) em vez de
  `@papel_required(*MEMBROS_COOPERATIVA)`, e os pontos que liam `request.user.cooperativa_id` cru usam
  o helper `apps.core.tenancy.cooperativa_id_do_request(request)` (= organização corrente,
  `PermissionDenied` se nenhuma). Os grids editáveis usam `Model.objects` (escopado pelo contextvar via
  `CooperativaScopeMiddleware`) e herdam o novo escopo de graça — Admin Vector com organização
  selecionada edita como super-membro. Telas re-estilizadas para o padrão AgroVector (subnav
  `tabs tabs-bordered`, cabeçalho de cenário em `<c-card>`, Tabulator re-tematizado). **Fase 13**
  acrescentou a aba "Resultados": views `resultados_tab` / `resultados_export` sobre `resultados.py` +
  `ResultadosForm`, com dois helpers de módulo — `_resultados_params(request, cenario)` (parse
  compartilhado: `form`, `filtros`, `periodo`, `agrupar`, `comparar_id: int | None`) e
  `_resultados_template(request, tem_dados)` (dispatch da parcial pelo header `HX-Target` via
  `request.htmx.target`: `resultados.html` / `_resultados_content` / `_resultados_area` /
  `_resultados_tabela`). **Fase 14** acrescentou a aba "Resultados"-irmã "Estoque": views
  `estoque_tab` / `estoque_export` sobre `estoque.py` + `EstoqueForm`, com os mesmos dois helpers de
  módulo — `_estoque_params(request, cenario)` (parse: `form`, `filtros`, `visao`,
  `comparar_id: int | None`) e `_estoque_template(request, tem_dados)` (dispatch 4-vias pelo
  `HX-Target`: `estoque.html` / `_estoque_content` / `_estoque_area` / `_estoque_tabela`).
  templatetags `variacao` / `item` / `cenario_tem_simulacao` em `templatetags/simulacao_filters.py`
  (`cenario_tem_resultado` renomeado na Fase 14 — a checagem "a simulação rodou" serve às abas
  Resultados **e** Estoque). **Fase 15**: `simulacao_filters.py` — `variacao` trata Δ que arredonda
  para `0,0%` como neutro (sem seta/cor); novo filtro `mes_extenso` (`"2026-02" → "Fevereiro 2026"`).
  `views.py` — helper `_filtros_avancados(filtros) -> (ativos, count)`; `_estoque_content` /
  `_resultados_content` põem os filtros avançados (mês/data + multi-selects) num `<details>` recolhível
  com contador e prefixam os ids dos `<select>` (`estoque-*` / `resultados-*`); `resultados_export` /
  `estoque_export` emitem coluna `Δ%` na comparação e `estoque_export` re-prefixa a coluna "Mês" nas
  visões por unidade.
- `apps/simulacao/tasks.py` — task assíncrona Procrastinate `executar_simulacao`, disparada pela aba
  "Simulação" (views `simulacao_tab`/`simulacao_executar`/`simulacao_status` em
  `apps/simulacao/views.py`); envolve `engine.simular_periodo` sem alterar sua lógica. `LogExecucao` é a
  fonte de verdade do status (`em_andamento`/`sucesso`/`erro`) consultada pelo polling HTMX. Ver ADR 0007
  e `docs/superpowers/specs/2026-08-26-fase5-simulacao-assincrona-design.md`.
