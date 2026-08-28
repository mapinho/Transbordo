# Fase 8 — Versionamento + limpeza

## Contexto e objetivo

A migração para Django (Fases 1–6, ver
`docs/superpowers/specs/2026-08-22-fase5-arquitetura-saas-django.md`) acumulou artefatos que já
cumpriram seu papel: planos de implementação de trabalho concluído, uma skill de review versionada no
repositório, docs de setup do MCP que a Fase 9 vai reescrever, análises one-off, notas de scratch. E o
projeto nunca teve um esquema de versão — não há como um deploy dizer "que versão está no ar".

Esta fase, entre a Auth (Fase 7) e o Deploy (Fase 10), faz duas coisas independentes:

1. **Versionamento** — introduz SemVer com uma fonte de verdade única, tag git por fase, e um
   `CHANGELOG.md`.
2. **Limpeza** — remove o lixo acumulado. **Não** toca no stack Streamlit/SQLAlchemy, que continua sendo
   a produção real até o Cutover (Fase 11) — essa remoção é explicitamente da Fase 11.

## Escopo

**Dentro:**
- Arquivo `VERSION` na raiz + leitura em `config/settings/base.py` (`APP_VERSION`) + exposição em
  `/healthz/` e no rodapé do template base.
- `CHANGELOG.md` (formato Keep a Changelog), back-fill das Fases 1–8.
- Tag git anotada `v0.8.0` ao final desta fase.
- Remoção da lista de arquivos abaixo (git preserva o histórico).
- ADR sobre o esquema de versionamento.
- Varredura `grep` confirmando que nada mais referencia os arquivos removidos.

**Fora:**
- Qualquer alteração no stack Streamlit/SQLAlchemy (`app.py`, `models.py`, `calculations.py`,
  `scenarios.py`, `data_loader.py`, `logistics_services.py`, `utils.py`, `app_logic.py`,
  `generate_templates.py`, `ai_assistant.py`, `tests/`). É a produção atual — sai na Fase 11.
- `mcp_server.py` — reescrito na Fase 9, não tocado aqui (mas `INSTRUCOES_MCP.md`/`toolspec.json`, que
  são só docs de setup, saem agora; a Fase 9 produz a documentação nova).
- `/healthz/` completo (`SELECT 1`, HEALTHCHECK do container) — isso é a Fase 10. Aqui `/healthz/` só
  ganha o campo de versão; se ainda não existir, cria-se um stub mínimo que retorna
  `{"version": APP_VERSION}`.

## Decisões de arquitetura

### 1. SemVer, `VERSION` na raiz como fonte de verdade

`MAJOR.MINOR.PATCH`. `v1.0.0` = Cutover (Streamlit desligado, Django é a produção). Até lá, `0.x` — uma
minor por fase da migração: `v0.8.0` (esta), `v0.9.0` (MCP/IA), `v0.10.0` (Deploy), `v1.0.0` (Cutover).
PATCH para correções pós-tag dentro da mesma fase.

- **`VERSION`** — arquivo de uma linha na raiz (`0.8.0`, sem o `v`). É a fonte de verdade.
- `config/settings/base.py` lê `(BASE_DIR / 'VERSION').read_text().strip()` uma vez no import →
  `APP_VERSION`. Falha explícita se o arquivo não existe (não silencia com um default).
- Tag git anotada por fase: `git tag -a v0.8.0 -m "Fase 8 — versionamento + limpeza"`, criada
  **ao final** do trabalho da fase, apontando para o commit que bumpa o `VERSION`.
- **Sem `pyproject.toml`** — o projeto usa `requirements.txt` puro deliberadamente
  (`docs/superpowers/specs/2026-08-22-...`, decisão de não herdar build config que não é usada). Um
  arquivo `VERSION` de uma linha é o mínimo que resolve.
- Alternativa rejeitada: CalVer (`AAAA.MM`) — só faz sentido com releases mensais regulares, que não é
  o caso; e não comunica "breaking" que é exatamente o que o cutover (0.x → 1.0) precisa comunicar.

### 2. `CHANGELOG.md` na raiz, formato Keep a Changelog

Uma seção por versão (`## [0.8.0] - 2026-XX-XX`), com `Added`/`Changed`/`Removed`/`Fixed`. Back-fill
enxuto das Fases 1–8 (uma a três linhas por fase — o detalhe está nos specs/ADRs, o CHANGELOG é o
índice). Mantido daqui em diante como parte de "fechar uma fase".

### 3. Limpeza — o que sai e por quê

O `git` preserva tudo; "remover" aqui é tirar do estado atual do repositório, não do histórico.

| Item | Motivo |
|---|---|
| `GEMINI.md` | Gemini CLI não é mais usado para este projeto |
| `.gemini/settings.json` (e o diretório `.gemini/`) | idem |
| linha "keep roughly in sync with GEMINI.md" em `CLAUDE.md` | o arquivo de destino deixa de existir |
| `code-reviewer/SKILL.md`, `code-reviewer/references/common-patterns.md`, `code-reviewer/scripts/review.py` | skill de review versionada no repo, superada pelo fluxo superpowers/ECC |
| `INSTRUCOES_MCP.md` | setup do MCP no Claude Desktop/Cursor/Vertex — reescrito na Fase 9 |
| `toolspec.json` | descritor de tools do MCP legado — a Fase 9 não usa |
| `conductor/ai-assistant-plan.md`, `conductor/mcp-server.md` (e o diretório `conductor/`) | notas históricas de implementação já concluída; a Fase 9 as supera |
| `docs/superpowers/plans/*.md` (7 arquivos) | planos passo-a-passo de trabalho concluído — descartáveis por design; os **specs** correspondentes ficam |
| `Relatorio_Revisao_Codigo_Fase1.md` | trilha de auditoria da Fase 1, completa; os achados já estão no `CLAUDE.md` |
| `analise_mineiros.py` | análise one-off, não faz parte do produto |
| `Relatorio_Analise_Impacto_Vendas_Mineiros.md` | relatório da análise one-off acima |
| `Cenário de Simulação.txt` | nota de scratch, superada por `Especificacao_Sistema_Transbordo_Atualizada.md` |
| `Especificação Transbordo.txt` | idem |
| `exportacao/*.xlsx` (4 arquivos) | output gerado, commitado por engano — **adicionar `exportacao/` ao `.gitignore`** |

**Mantidos** (decisão explícita, não são lixo):
- `docs/superpowers/specs/*` — capturam decisões, referenciados por ADRs e `CLAUDE.md`; o roteiro da
  migração vive aqui.
- `docs/decisions/*` (ADRs 0001–0009).
- `Especificacao_Sistema_Transbordo_Atualizada.md` — único spec funcional consolidado; a Fase 5 previu
  que ele "vira a base para o `specs/` por módulo", processo incremental ainda em curso.
- Todo o stack Streamlit/SQLAlchemy (Fase 11).

### 4. Ordem dentro da fase

1. Versionamento primeiro: cria `VERSION` (`0.8.0`), `APP_VERSION` nas settings, campo no `/healthz/`,
   rodapé, `CHANGELOG.md`. Testes verdes.
2. Limpeza: remove os arquivos da tabela, ajusta `.gitignore`, roda a varredura `grep` por referências
   pendentes (em `CLAUDE.md`, `README.md`, `.github/workflows/ci.yml`, `Dockerfile`,
   `docker-compose.yml`, `deploy.sh`). Testes verdes de novo.
3. `git tag -a v0.8.0`.

## Testes

- `config/settings/base.py` lê `VERSION` — teste que `APP_VERSION` bate com o conteúdo do arquivo, e
  que a ausência do arquivo levanta erro claro (não retorna default).
- `/healthz/` retorna `{"version": "0.8.0"}` (JSON) — teste de view.
- Rodapé do template base renderiza a versão — teste de template/contexto.
- Pós-limpeza: `python manage.py check` limpo, `pytest` (Django + SQLAlchemy) verde — nada que foi
  removido era importado por código vivo.
- Varredura textual (script ou passo manual documentado): `grep -rn` pelos nomes dos arquivos removidos
  nos arquivos de config/docs mantidos — zero hits.

## Verificação

- `cat VERSION` → `0.8.0`; `curl /healthz/` → contém `"version": "0.8.0"`.
- `git tag` lista `v0.8.0` anotada.
- `git status` limpo; `git log --stat` do commit de limpeza mostra só remoções + o ajuste de
  `.gitignore` + `CHANGELOG.md`.
- `CHANGELOG.md` tem seções de `[0.1.0]` a `[0.8.0]`.

## Decisões em aberto / riscos

- **`Especificacao_Sistema_Transbordo_Atualizada.md` fica, por ora.** É o único documento funcional
  consolidado. Quando o `specs/` por módulo cobrir todo o domínio, ele pode sair — não é escopo desta
  fase decidir isso.
- **Baixo risco de quebra.** A lista de remoção é toda de docs, notas e uma skill — nenhum arquivo `.py`
  de produção. O passo de varredura `grep` + a suíte verde são a rede.
