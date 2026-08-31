# apps/simulacao — file map

Detail for the files in this directory. See the root `CLAUDE.md` for the project-wide picture (Fase 5 Django migration context, business rules, environment setup).

- `apps/simulacao/models.py` — Django port of `models.py`'s 11 tables, every one with `cooperativa_id` (Fase 5, Port do Domínio) + `ConversaIA` (Fase 9b: histórico do Assistente de IA, `CooperativaScopedModel`, uma conversa `ativa` por cenário+usuário). `apps/simulacao/engine.py` — port of `calculations.py`. `apps/simulacao/services.py` — port of `logistics_services.py`. All three use `Model.all_cooperativas` internally, not `Model.objects` — see `docs/decisions/0006-...`.
- `apps/simulacao/assistente.py` — Fase 9b: loop Gemini (function-calling) in-process sobre `services.py`. `responder(conversa, mensagem)` reconstrói o chat de `conversa.mensagens`, envia com as 9 tools como closures ligadas ao cenário da aba, persiste os dois turnos, nunca propaga exceção. `AssistenteIndisponivel` se `settings.GEMINI_API_KEY` vazio. Port de `ai_assistant.py` (raiz, Streamlit) — duplicação temporária até a Fase 11. Backs `assistente_tab`/`assistente_enviar`/`assistente_nova` em `views.py`. Ver ADR 0010.
- `apps/simulacao/planilha.py` — Carga de Dados: `analisar()` reads and classifies a five-sheet `.xlsx` (Fábricas/Armazéns/Rotas/Previsões/Safras) without writing anything; `aplicar()` re-reads and writes inside one transaction; `gerar_template()` builds a blank workbook from the same column constants the parser consumes. Backs the upload/preview/confirm screens in `apps/simulacao/views.py` (`carga_upload`/`carga_preview`/`carga_template`).
- `apps/simulacao/views.py` — as views HTMX do domínio. Desde a **Fase 12** (ADR 0012) são gated por
  `@requer_membro_organizacao` (membro **ou** Admin Vector com organização selecionada) em vez de
  `@papel_required(*MEMBROS_COOPERATIVA)`, e os pontos que liam `request.user.cooperativa_id` cru usam
  o helper `apps.core.tenancy.cooperativa_id_do_request(request)` (= organização corrente,
  `PermissionDenied` se nenhuma). Os grids editáveis usam `Model.objects` (escopado pelo contextvar via
  `CooperativaScopeMiddleware`) e herdam o novo escopo de graça — Admin Vector com organização
  selecionada edita como super-membro. Telas re-estilizadas para o padrão AgroVector (subnav
  `tabs tabs-bordered`, cabeçalho de cenário em `<c-card>`, Tabulator re-tematizado).
- `apps/simulacao/tasks.py` — task assíncrona Procrastinate `executar_simulacao`, disparada pela aba
  "Simulação" (views `simulacao_tab`/`simulacao_executar`/`simulacao_status` em
  `apps/simulacao/views.py`); envolve `engine.simular_periodo` sem alterar sua lógica. `LogExecucao` é a
  fonte de verdade do status (`em_andamento`/`sucesso`/`erro`) consultada pelo polling HTMX. Ver ADR 0007
  e `docs/superpowers/specs/2026-08-26-fase5-simulacao-assincrona-design.md`.
