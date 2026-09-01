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
    `*_delta` por linha + colunas Δ% + `totais_delta`; linha crua (`diario×fabrica_armazem`) não
    recebe Δ.
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
- `apps/simulacao/forms.py` — **Fase 13**: `ResultadosForm` (`forms.Form` puro; datas +
  `armazem_ids` / `fabrica_ids` do cenário; `filtros_limpos()` devolve o dict de filtros).
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
  `_resultados_tabela`). templatetags `variacao` / `item` / `cenario_tem_resultado` em
  `templatetags/simulacao_filters.py`.
- `apps/simulacao/tasks.py` — task assíncrona Procrastinate `executar_simulacao`, disparada pela aba
  "Simulação" (views `simulacao_tab`/`simulacao_executar`/`simulacao_status` em
  `apps/simulacao/views.py`); envolve `engine.simular_periodo` sem alterar sua lógica. `LogExecucao` é a
  fonte de verdade do status (`em_andamento`/`sucesso`/`erro`) consultada pelo polling HTMX. Ver ADR 0007
  e `docs/superpowers/specs/2026-08-26-fase5-simulacao-assincrona-design.md`.
