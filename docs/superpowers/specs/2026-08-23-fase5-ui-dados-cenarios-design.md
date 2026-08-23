# Fase 5 — UI: Dados & Cenários (Django + HTMX)

## Contexto e objetivo

Terceira etapa do roteiro de migração descrito em
`docs/superpowers/specs/2026-08-22-fase5-arquitetura-saas-django.md` ("Fases de migração", item 3 —
"UI"). As etapas 1 (Fundação) e 2 (Port do domínio) já estão concluídas e mescladas em `main`
(`apps/core` com `Cooperativa`/`User`/`TenantManager`/`CooperativaScopeMiddleware`; `apps/simulacao`
com os 11 models, `engine.py` e `services.py`, todos com `cooperativa_id`).

Esta fase constrói a primeira superfície de UI real no lado Django: as telas de gestão de dados dentro
de um Cenário — o que hoje é a aba "Dados & Cenários" do Streamlit (`app.py`), com suas seis sub-abas
(Fábricas, Armazéns, Rotas, Previsões, Datas de Safra, Otimizar). Usa a stack definida no spec
arquitetural (§4): HTMX + Tailwind v4 + daisyUI 5 + `django-cotton`, com Tabulator + IMask.js
especificamente nas grades de edição em massa (a "lacuna real do APP_Vector" que o spec já identificou).

## Precedente: projeto irmão APP_Vector

`Desenvolvimento_Claude_Code/APP_Vector` (repositório local, mesmo usuário) é um app Django+HTMX já em
produção que documenta, na prática, exatamente as convenções que o spec da Fase 5 diz herdar — inclusive
uma skill própria (`.claude/skills/django-htmx-scaffold/SKILL.md`) com o processo completo (models →
admin → views/URLs → templates/partials HTMX → testes). Esta fase copia e adapta a fundação genérica de
lá (ver §1) em vez de reescrevê-la do zero, herdando de graça lições já pagas em produção — notadamente
o **ADR 0015** de lá (aninhamento de página inteira dentro de um `<div>` HTMX quando a view não faz o
branch `request.htmx`) e o gotcha de `<input type="date">` exigir `format="%Y-%m-%d"` no `forms.DateInput`
(o browser só aceita ISO nesse tipo de campo, não o locale pt-BR).

## Escopo desta fase

**Dentro:**
- Login básico (`django.contrib.auth`, sem SSO — ver §2).
- Listagem e criação (por clonagem) de Cenário.
- Grades editáveis: Fábricas, Armazéns, Rotas, Previsões (Fábrica + Armazém), Datas de Safra.
- Port de `scenarios.clone_scenario` (SQLAlchemy) para `apps/simulacao/services.py` — pré-requisito da
  tela de criação de Cenário, descoberto como lacuna durante este brainstorm (não fazia parte do escopo
  da Fase 2/Port do domínio, que só portou `engine.py`/`services.py` de leitura e simulação).

**Fora (fases seguintes do roteiro, ou não decidido):**
- Dashboard (leitura) — pode ser uma fase futura própria; não bloqueia esta.
- Carga de Dados (upload de Excel) — fase futura.
- Otimização (botão "Rodar Otimização" dentro da sub-aba "🚀 Otimizar", exportação de Excel de dados do
  cenário) — Fase 4 do roteiro (Procrastinate), pois depende da fila assíncrona.
- Assistente de IA — Fase 5 do roteiro (Face JSON / Django Ninja sobre `apps/integracoes/`).
- Auth completo (`django-allauth`, papéis Usuário Fábrica/Usuário Armazém com escopo restrito) — Fase 6
  do roteiro.
- `django-unfold` (tema do admin) e `django-import-export` (exportação Excel) — usados no APP_Vector, mas
  não exercitados por nenhuma tela desta fase; não viram dependência agora (YAGNI — entram quando alguma
  tela realmente precisar).
- `django-tables2`/`django-filter` — também não entram nesta fase. A listagem de Cenários é um catálogo
  pequeno por cooperativa (poucas dezenas no limite), o mesmo caso que o próprio APP_Vector já resolve
  sem tabela genérica ("catálogos pequenos sem necessidade de ordenação"). Entram quando uma tela
  somente-leitura de verdade (Dashboard, resumos mensais, movimentações diárias) precisar.
- `delete_scenario` — não portado agora; nenhuma tela desta fase expõe exclusão de cenário (o Streamlit
  também não expõe esse botão na aba "Dados & Cenários").

## Decisões de arquitetura

### 1. Fundação visual: copiada e adaptada do APP_Vector

- Pacotes novos em `requirements.txt` (versões espelhando `APP_Vector/pyproject.toml`, únicas usadas de
  fato nesta fase):
  - `django-htmx>=1.19,<2.0`
  - `django-cotton>=2.7,<3.0`
  - `django-crispy-forms>=2.7,<3.0`
  - `crispy-tailwind>=1.0,<2.0`
- `config/settings/base.py`: `INSTALLED_APPS` ganha `django_htmx`, `django_cotton`, `crispy_forms`,
  `crispy_tailwind`; `MIDDLEWARE` ganha `django_htmx.middleware.HtmxMiddleware` (habilita
  `request.htmx`); `CRISPY_ALLOWED_TEMPLATE_PACKS = ["tailwind"]`, `CRISPY_TEMPLATE_PACK = "tailwind"`.
- `templates_django/base.html` — adaptado de `APP_Vector/templates/tailwind/layout/*` (Tailwind v4 via
  Play CDN + daisyUI 5, mesmo mecanismo de tema via `data-theme`), trocando os tokens de cor
  navy/accent do APP_Vector pela paleta **"Grão & Aço"** (verde/âmbar, identidade agrícola) já definida
  para o artefato do roteiro estratégico do Comigo.
- `templates_django/cotton/card.html` — adaptado de `APP_Vector/templates/cotton/card.html` (`<c-card>`
  como wrapper padrão; nada de `<div class="rounded-lg border ...">` manual). Os demais componentes cotton
  do APP_Vector (`breadcrumb`, `lista_cartao`, `resumo_numerico`) não são copiados agora — não têm
  consumidor nesta fase (telas de Dashboard/resumo os usariam; ficam para a fase que os introduzir).
- `static/simulacao/js/modal.js` (ou local equivalente) — adaptado do padrão de modal/confirm
  compartilhado do APP_Vector (`#transbordo-modal`/`#transbordo-confirm`, `htmx:afterSwap` para abrir
  modal, interceptação de `htmx:confirm` para diálogo custom). Usado nesta fase apenas para o diálogo de
  confirmação ao salvar alterações não triviais (se necessário) — avaliar durante a implementação se as
  grades precisam mesmo de confirm ou se "Salvar" direto já é suficiente (o Streamlit não pede
  confirmação hoje).
- Filtros de template pt-BR (`apps/simulacao/templatetags/simulacao_filters.py`): `|moeda`, `|volume`,
  porte de `utils.format_dataframe`'s regras de formatação (`.` milhar, `,` decimal) para uso em template
  Django, preservando a mesma convenção visual do Streamlit.

### 2. Login básico

- `django.contrib.auth` (já instalado) — uma `LoginView` simples (usuário/senha), template
  `templates_django/registration/login.html` com o mesmo `base.html`/paleta.
- `LOGIN_URL`, `LOGIN_REDIRECT_URL` em `config/settings/base.py`.
- Todas as views desta fase exigem `@login_required`.
- Usuários de teste criados via Django admin (já registrado, Fase 1/Fundação) ou fixture — sem tela de
  auto-cadastro (nunca haverá, nem na Fase 6 — `SOCIALACCOUNT_AUTO_SIGNUP = False` no spec arquitetural).
- Fase 6 troca por `django-allauth` (Google/Microsoft/local) sem mexer no `User` model nem nas views
  desta fase — só troca o backend de autenticação por trás do mesmo `@login_required`.

### 3. Estrutura de telas e URLs

Diferente do Streamlit (que guarda o cenário selecionado em `st.session_state` e troca sub-abas sem
navegação real), as telas desta fase usam URLs enderaçáveis por `cenario_id` — mais idiomático em
Django/HTMX e permite compartilhar/favoritar o link de uma grade específica de um cenário específico:

```
apps/simulacao/urls.py:
  /simulacao/cenarios/                          GET  lista + form de criação (clone)
                                                 POST cria (clona) um novo Cenario
  /simulacao/cenarios/<cenario_id>/fabricas/     GET  grade completa | POST upsert em lote
  /simulacao/cenarios/<cenario_id>/armazens/     GET  grade completa | POST upsert em lote
  /simulacao/cenarios/<cenario_id>/rotas/        GET  grade completa | POST upsert em lote
  /simulacao/cenarios/<cenario_id>/previsoes/    GET  grade completa (2 sub-grades) | POST upsert em lote
  /simulacao/cenarios/<cenario_id>/safras/       GET  grade completa | POST upsert em lote
```

Cada uma das 5 páginas de grade compartilha uma sub-navegação (abas) para as outras 4, e todas resolvem
o `Cenario` via `Cenario.objects.get(id=cenario_id)` — usando o manager `objects` (`TenantManager`,
fail-closed), não `all_cooperativas`: isso é deliberado e é exatamente o contraponto do lado "view" para
o que a **ADR 0006** (Fase 2) já previu como responsabilidade da próxima camada — aqui, tentar acessar o
cenário de outra cooperativa por adivinhação de ID no URL resulta em `Cenario.DoesNotExist` → 404, não em
vazamento de dado. Isto é comportamento a testar explicitamente (ver §7).

### 4. Padrão da grade editável (Tabulator + IMask.js) — a peça nova

Este é o único padrão sem precedente direto no APP_Vector (lá as listagens são `django-tables2`
somente-leitura ou formulários `crispy-forms` um-registro-por-vez; aqui a UX real do Streamlit é edição
tipo planilha, todas as linhas de uma vez, com um botão "Salvar" que faz upsert em lote).

- Cada view de grade (`FabricasView`, `ArmazensView`, ...) segue o branch obrigatório
  `request.htmx` (**ADR 0015 do APP_Vector**): sem HTMX, renderiza a página completa (com
  `base.html` + sub-navegação); com HTMX (troca de aba via `hx-get`), renderiza só o partial da grade.
- Configuração de colunas é um dict Python explícito por view (rótulo, formato pt-BR, editável ou não,
  largura) — não introspecção genérica do model. São 5 grades fixas com necessidades diferentes o
  bastante (Rotas tem 2 FKs a resolver para nome; Safras tem datas, não números) que uma abstração
  genérica seria over-engineering para este número de telas.
- O config de colunas é serializado como JSON num `<script type="application/json">` no template (nunca
  interpolado direto via filtro `|safe` — evita quebrar em nomes com aspas) e lido por
  `static/simulacao/js/grid_editor.js`, um único módulo JS reaproveitado pelas 5 páginas, parametrizado
  por esse JSON — evita 5 blocos de configuração Tabulator copiados e colados.
- Editor customizado de número com IMask.js nas colunas numéricas (`.` milhar, `,` decimal) — resolve a
  limitação do `<input type="number">` nativo, que ignora locale por especificação (a causa raiz já
  documentada no artefato "Roteiro Comigo").
- POST na mesma URL da grade faz upsert em lote numa única transação (`transaction.atomic()`), mesma
  semântica do Streamlit: linha com `id` existente atualiza; linha nova (sem `id`, se a grade permitir
  adicionar linhas — replicar exatamente quais grades permitem isso hoje: `Armazém` permite no Streamlit
  via `num_rows="dynamic"`, `Fábricas`/`Rotas` não) cria; tudo confirma ou tudo reverte junto. Depois do
  commit, a view responde com o partial da grade recarregado (dados frescos do banco), igual ao
  `st.rerun()`/refresh de cache que o Streamlit já faz hoje após salvar.
- O Cenário oficial (`is_oficial=True`) aparece e é editável nas mesmas grades que qualquer outro — sem
  caso especial. Reflete o comportamento atual do Streamlit e a regra de negócio já corrigida no
  `CLAUDE.md` (Fase 2): o oficial é uma linha `Cenario` real como qualquer outra.

### 5. Port de `clone_scenario`

`apps/simulacao/services.py` ganha `clone_scenario(cooperativa_id, scenario_name, source_scenario_id)` —
porte 1:1 de `scenarios.clone_scenario` (SQLAlchemy), com as mesmas garantias:
- Totalmente transacional (`transaction.atomic()`), reverte tudo em qualquer falha (mesma garantia da
  função original, e do mesmo padrão já usado em `engine.simular_periodo`, Fase 2).
- Mapas `fabrica_map`/`armazem_map` (ID antigo → ID novo) para manter integridade referencial em Rotas,
  Previsões e Safras clonadas.
- Consulta em lote (não por linha) para Previsões, evitando N+1 — mesmo padrão já corrigido no final da
  Fase 2 para as funções de relatório de `services.py`.
- Boundary de tenant explícito via `cooperativa_id` (parâmetro obrigatório, seguindo o mesmo formato que
  a ADR 0006 já exige de toda função em `engine.py`/`services.py` — inclusive valida que
  `source_scenario_id` pertence à `cooperativa_id` informada antes de clonar, já que aqui, ao contrário
  de `list_scenarios`, existe um ID de origem vindo potencialmente de fora que precisa ser checado).
- Usa `Model.all_cooperativas` internamente (é uma função de domínio, não uma view) — a checagem de posse
  do `source_scenario_id` é feita explicitamente dentro da função, não herdada do manager.
- Testes seguindo o mesmo rigor da Fase 2: clonagem básica, integridade referencial pós-clone, isolamento
  de tenant (cooperativa A não consegue clonar um cenário de cooperativa B nem por acidente).

### 6. Permissões

- Somente `@login_required` + o escopo de cooperativa que o `TenantManager`/`CooperativaScopeMiddleware`
  já fazem automaticamente (Fase 1/Fundação) — qualquer usuário autenticado da cooperativa vê e edita
  todos os dados da própria cooperativa nesta fase, sem distinção de papel.
- Sem restrição por papel (Usuário Fábrica vs. Usuário Armazém) ainda — isso é escopo da Fase 6
  (`apps/<app>/permissions.py`, `papel_required(...)`, no padrão que o APP_Vector já usa para
  `pode_editar_projeto`). Não faz sentido implementar checagem de papel antes do `User.papel` ter uma UI
  de atribuição real (também Fase 6).

### 7. Testes

`pytest-django`, por view de grade (Fábricas/Armazéns/Rotas/Previsões/Safras) e para a view de Cenários:
- Página completa: `GET` sem `hx-request` renderiza com `base.html` (contém a sub-navegação).
- Partial: `GET` com header `HX-Request: true` renderiza só o fragmento da grade (sem `base.html`) —
  prova direta do branch do ADR 0015, não só ausência de erro.
- `POST` com dados válidos faz upsert correto (linha existente atualiza, linha nova cria quando a grade
  permite) e devolve o partial atualizado.
- `POST`/`GET` para um `cenario_id` de outra cooperativa retorna 404 (tenant isolation via `TenantManager`
  no nível da view) — teste de dois-cooperativas, no mesmo espírito do que a revisão final da Fase 2
  cobrou (deferred finding: "zero cross-tenant test coverage").
- `login_required`: acesso sem sessão autenticada redireciona para login.
- `clone_scenario`: clonagem básica, integridade referencial, isolamento de tenant (ver §5).

## Decisões em aberto / riscos

- **Confirmação antes de salvar**: o Streamlit salva direto ao clicar "Salvar Alterações X", sem
  confirmação. Esta fase mantém esse comportamento (sem modal de confirm nas grades) — o modal/confirm
  do APP_Vector fica disponível como padrão pronto caso alguma ação futura precise (ex. uma eventual
  exclusão de linha), mas não é usado nas grades de salvar desta fase.
- **`django-tables2`/`django-filter` adiados**: risco baixo — se a listagem de Cenários crescer a ponto
  de precisar paginação/ordenação antes da fase de Dashboard chegar, isso pode ser revisitado como uma
  tarefa pequena, sem redesenho.
- **Tailwind/daisyUI via CDN (sem build step)**: mesma nota de risco que o spec arquitetural já registra
  (§4 de lá) — reavaliar perto do cutover final, não assumir que CDN-only escala indefinidamente.
