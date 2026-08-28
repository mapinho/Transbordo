# apps/simulacao — file map

Detail for the files in this directory. See the root `CLAUDE.md` for the project-wide picture (Fase 5 Django migration context, business rules, environment setup).

- `apps/simulacao/models.py` — Django port of `models.py`'s 11 tables, every one with `cooperativa_id` (Fase 5, Port do Domínio). `apps/simulacao/engine.py` — port of `calculations.py`. `apps/simulacao/services.py` — port of `logistics_services.py`. All three use `Model.all_cooperativas` internally, not `Model.objects` — see `docs/decisions/0006-...`.
- `apps/simulacao/planilha.py` — Carga de Dados: `analisar()` reads and classifies a five-sheet `.xlsx` (Fábricas/Armazéns/Rotas/Previsões/Safras) without writing anything; `aplicar()` re-reads and writes inside one transaction; `gerar_template()` builds a blank workbook from the same column constants the parser consumes. Backs the upload/preview/confirm screens in `apps/simulacao/views.py` (`carga_upload`/`carga_preview`/`carga_template`).
- `apps/simulacao/legado.py` — development-only tool that mirrors the seven input tables from the legacy Postgres database (`comigo`) into a Django tenant, so the Django screens can be exercised against real data before Carga de Dados/Otimização are ported. `abrir_sessao_legado` / `ler_legado` read via the legacy SQLAlchemy `models.py`; `escrever` apaga-e-recarrega the target tenant inside `transaction.atomic()`. Has an expiration date: dies when the Streamlit stack is retired. See `docs/superpowers/specs/2026-08-24-espelhamento-dados-legado-design.md`. Exposed via the `espelhar_legado` management command (`apps/simulacao/management/commands/espelhar_legado.py`), which refuses to run unless `settings.DEBUG` is true and requires `DATABASE_URL` (the legacy connection string) in the environment.
- `apps/simulacao/tasks.py` — task assíncrona Procrastinate `executar_simulacao`, disparada pela aba
  "Simulação" (views `simulacao_tab`/`simulacao_executar`/`simulacao_status` em
  `apps/simulacao/views.py`); envolve `engine.simular_periodo` sem alterar sua lógica. `LogExecucao` é a
  fonte de verdade do status (`em_andamento`/`sucesso`/`erro`) consultada pelo polling HTMX. Ver ADR 0007
  e `docs/superpowers/specs/2026-08-26-fase5-simulacao-assincrona-design.md`.
