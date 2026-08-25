# Fase 5 — Arquitetura SaaS Multi-Cooperativa (Django 6 + HTMX)

> **Repositório**: este documento vive no repositório `Transbordo` (remote `origin`, `https://github.com/mapinho/Transbordo.git`), onde todo o desenvolvimento desta fase acontece daqui em diante. O repositório `Comigo` (`https://github.com/mapinho/Comigo.git`) está congelado como arquivo histórico da versão Streamlit — nenhum commit novo deve ir para lá.
>
> **Diretório local**: no momento em que esta spec foi escrita, o diretório de trabalho local ainda se chama `Comigo` no disco (o rename para `Transbordo` está pendente — bloqueado por um handle aberto do VSCode, a ser feito manualmente pelo usuário fora desta sessão). O conteúdo/histórico git já está correto; só o nome da pasta está pendente.

## Contexto e objetivo

O sistema (hoje um app Streamlit de cooperativa única, apelidado "Comigo") evolui para um produto SaaS multi-cooperativa, com o nome de produto voltando a ser **Transbordo** (nome original do projeto, antes da marca "Comigo" ter sido aplicada para este cliente específico). O objetivo desta fase é migrar de Streamlit + SQLAlchemy para **Django 6 + HTMX**, introduzindo o conceito de tenant (`Cooperativa`) que hoje não existe, sem reescrever o núcleo de otimização (`calculations.py`) que já funciona.

Esta spec foi desenhada replicando, onde fizer sentido, os padrões arquiteturais e de UX/UI de um projeto irmão do mesmo usuário — **APP_Vector** (`C:\Users\mario\OneDrive\Documents\Projects\Desenvolvimento_Claude_Code\APP_Vector`), um sistema de gestão de projetos Django, em produção, considerado bem-sucedido e bem documentado. Cada decisão abaixo cita explicitamente se foi herdada do APP_Vector, adaptada, ou desenhada do zero (porque o APP_Vector não tem precedente para ela — notavelmente, multi-tenancy e fila de jobs).

**Fora de escopo desta spec** (deliberadamente adiado): extrair um padrão genérico reutilizável (SPECs/SKILLs/agentes de Claude Code) a partir das decisões tomadas aqui, para uso em outros projetos futuros. Combinado explicitamente com o usuário: essa extração acontece **depois** que as decisões abaixo estiverem implementadas e validadas na prática no Transbordo — generalizar a partir de uma decisão já comprovada é mais seguro do que generalizar às cegas em paralelo.

## Decisões de arquitetura

### 1. Multi-tenancy: schema compartilhado + `cooperativa_id`

*Sem precedente no APP_Vector (single-tenant).*

- Novo model `Cooperativa` (raiz do tenant): `nome`, `slug`, `ativo`, parâmetros específicos por cooperativa (ex.: janela de safra padrão).
- `cooperativa_id` (FK, `on_delete=PROTECT`) propagado a `Cenario` e a todos os descendentes (`Fabrica`, `Armazem`, `Rota`, `PrevisaoFabrica`, `PrevisaoArmazem`, `SafraUnidade`, `MovimentacaoDiaria`, `ResumoMensalFabrica`, `ResumoMensalArmazem`) — mesmo tipo de migração aditiva que a correção A11 da Fase 1 já fez para `cenario_id`.
- Isolamento automático via `TenantManager`/middleware: toda query fica implicitamente escopada pela cooperativa do usuário autenticado, sem que cada view precise lembrar de filtrar manualmente.
- **Alternativa rejeitada**: `django-tenants` (schema-per-tenant) — isolamento mais forte, mas migrations por schema e integração menos comum com Procrastinate/HTMX; mais complexidade operacional do que o estágio atual do produto justifica.

### 2. Camada de domínio: módulos próprios, não dissolvidos em models

*Adaptação deliberada da convenção do APP_Vector.*

O APP_Vector não usa camada de serviço separada (lógica em métodos/properties de model + `django-fsm-2` + `permissions.py`/`workflow.py` por app), porque suas regras de negócio são CRUD com aprovação/workflow. O Transbordo tem uma exceção real: `calculations.py` é um motor de otimização por programação linear (~300 linhas de lógica pura, OR-Tools), e `logistics_services.py` é uma camada de leitura compartilhada por 3 consumidores (UI, MCP, IA).

- `calculations.py` → `apps/simulacao/engine.py`: as funções públicas (`otimizar_dia`, `simular_periodo`, `obter_janela_safra`, `obter_range_previsoes`) portadas quase 1:1, trocando `session.query(...)` (SQLAlchemy) por `Model.objects.filter(...)` (Django ORM). A lógica do solver (construção do modelo, função objetivo, coeficientes) não muda — só a camada de acesso a dados. Preserva todo o trabalho de performance das Fases 1 e 3 (pré-carregamento de fábricas/armazéns/rotas/safras, cache de janela de safra).
- `logistics_services.py` → `apps/simulacao/services.py`: mesmas assinaturas, Django ORM por baixo.
- Continua compatível com a convenção do APP_Vector, que já abre exceção para lógica não-trivial via módulos próprios (`permissions.py`/`workflow.py`) — só estende o mesmo princípio a um caso mais substancial.

### 3. Estrutura de apps Django

*Herdado do APP_Vector: um app por módulo de negócio, `core` só para o que é genuinely compartilhado.*

```
apps/
  core/          # Cooperativa, User, auth, TenantManager/middleware,
                 # helpers compartilhados de tabela/paginação/export
  simulacao/     # os 9 models atuais + views + engine.py + services.py + tasks.py
  integracoes/   # face JSON (Django Ninja) para MCP server e Assistente de IA
config/
  settings/{base,dev,prod}.py    # padrão do APP_Vector (ADR 0002 de lá)
templates/
  base.html, <app>/<view>.html + <app>/_<partial>.html, cotton/
docs/
  decisions/     # ADRs, começando em 0001
specs/           # spec por módulo de negócio
```

### 4. UI/UX: HTMX + Tailwind v4 + daisyUI 5 + django-cotton + Tabulator

*Herdado do APP_Vector para tudo, exceto edição em massa (lacuna real do APP_Vector).*

- Mesma stack visual do APP_Vector: HTMX 2, Tailwind v4 via CDN, daisyUI 5 via CDN, `django-cotton` para componentes (`<c-card>`, `<c-resumo-numerico>`).
- Tokens de design em CSS custom properties, dois temas via `data-theme` (claro/escuro) — usar a paleta "Grão & Aço" (verde/âmbar, identidade agrícola) já criada para o artefato do roteiro estratégico, no mesmo espírito do navy/accent do APP_Vector.
- Views função-a-função com o branch `request.htmx` obrigatório (padrão + achado de bug real do APP_Vector, ADR 0015 de lá — omitir o branch aninha a página inteira dentro do container HTMX).
- Tabelas somente-leitura (Dashboard, resumos mensais, movimentações diárias) usam `django-tables2` + `django-filter`, igual ao APP_Vector.
- Modal e diálogo de confirmação compartilhados (`#transbordo-modal`/`#transbordo-confirm`), copiando o padrão HTMX do APP_Vector (`htmx:afterSwap` para abrir modal, interceptar `htmx:confirm` para diálogo custom).
- **Lacuna real do APP_Vector, resolvida à parte**: edição em massa tipo planilha (hoje `st.data_editor`) para fábricas/armazéns/rotas/previsões, com números pt-BR (`.` milhar, `,` decimal) — o `<input type="number">` nativo do HTML ignora locale por especificação, causa raiz da dificuldade já relatada com esses campos. Resolvido com **Tabulator + editor customizado com IMask.js** especificamente nessas telas (pesquisa já feita e documentada no artefato "Roteiro Comigo"), mantendo o resto da UI no padrão HTMX/daisyUI/cotton.
- Formatação pt-BR (hoje `utils.format_dataframe`) vira template filters Django (`|moeda`, `|volume`), preservando a mesma convenção visual.

### 5. Autenticação e autorização

*Adaptação do padrão do APP_Vector (allauth + role-resolution por função, sem grupos/permissões nativas do Django, sem django-guardian) com uma dimensão nova: o tenant.*

- `django-allauth` com providers **Google** e **Microsoft (Azure AD)**, mais backend local Django (usuário/senha) para cooperativas sem SSO corporativo.
- **Sem auto-cadastro**: `SOCIALACCOUNT_AUTO_SIGNUP = False`. Uma conta SSO só autentica se já existir um `User` pré-cadastrado com aquele e-mail — associação por e-mail, nunca criação automática.
- `User` (`AbstractUser` + `cooperativa` FK nullable + `papel`):
  - **Admin Vector** (`cooperativa=None`, cross-tenant) — cadastra cooperativas, usuários e parâmetros iniciais. Único papel que cria usuários.
  - **Admin Cooperativa** — parametriza a própria cooperativa (janelas de safra, capacidades padrão), não cadastra usuários.
  - **Usuário Fábrica** — CRUD e edição em massa restritos a fábricas, dentro da cooperativa.
  - **Usuário Armazém** — idem, restrito a armazéns.
  - `is_staff`/`is_superuser` padrão do Django reservados à equipe Vector (acesso ao `/admin/`).
- Checagem de papel via funções puras em `apps/<app>/permissions.py` (`papel_required('usuario_fabrica')`), replicando o padrão do APP_Vector (`pode_editar_projeto`) — nunca escondendo botão na UI como única proteção.

### 6. Fila de jobs assíncrona: Procrastinate

*Sem precedente no APP_Vector (sem fila alguma). Decisão do usuário, validada por pesquisa nesta sessão.*

- PostgreSQL-nativo (`LISTEN`/`NOTIFY` + `FOR UPDATE SKIP LOCKED`), sem Redis/RabbitMQ — menos peças móveis, mesma razão de escolha já usada pelo usuário em outros sistemas. Release mais recente confirmada em junho/2026, integração Django com autodiscovery e admin de monitoramento (`ProcrastinateJob`/`Event`/`Worker`, somente-leitura).
- `apps/simulacao/tasks.py`: `executar_simulacao(cenario_id, data_inicio, data_fim, estrategia)`, chamando `engine.simular_periodo`.
- O botão "Rodar Otimização" enfileira a task **transacionalmente** (junto com a mudança de estado do `Cenario`, ex. `status='processando'`) em vez de bloquear a UI com `st.spinner` — a view faz polling HTMX (`hx-trigger="every 2s"`) num fragmento de status até a task terminar. Resolve o item "UX/escalabilidade" que ficou adiado na Fase 4.
- Worker (`python manage.py procrastinate worker`) roda como serviço adicional no `docker-compose` (mais um container que o padrão single-service do APP_Vector, mas ainda sem broker separado).
- `LogExecucao` (Fase 4) continua registrando duração/escopo em nível de negócio; as tabelas do Procrastinate cobrem o nível operacional (retries, falhas de infra) — os dois convivem.

### 7. Face JSON para MCP e Assistente de IA

- `apps/integracoes/` expõe **Django Ninja** sobre `apps/simulacao/services.py`, substituindo o acesso direto ao ORM que `mcp_server.py`/`ai_assistant.py` fazem hoje.

### 8. Testes e CI

*CI real é uma decisão consciente de NÃO herdar a lacuna do APP_Vector (que não tem pipeline automatizado, só gate manual documentado).*

- `pytest-django`, continuando a disciplina de TDD já estabelecida no Comigo/Transbordo (Fases 1, 3 e 4). Fixtures de `tests/conftest.py` (hoje SQLAlchemy) precisam ser reconstruídas para o ORM Django — não portam diretamente.
- Padrão herdado do APP_Vector por módulo: CRUD feliz, uma regra de negócio confirmada por teste, rejeição de transição de estado inválida, testes de permissão (view-level e queryset-level).
- **Novo e crítico, sem precedente no APP_Vector**: testes de isolamento de tenant explícitos e formalizados — cooperativa A nunca pode enxergar dado de cooperativa B, nem via query direta ao `TenantManager`. Isso precisa ser provado por teste automatizado, não assumido.
- **CI real via GitHub Actions** no repositório `Transbordo`, rodando `pytest`/`manage.py check`/`makemigrations --check` a cada push/PR — ao contrário do gate manual do APP_Vector.

### 9. Documentação

*Herdado do APP_Vector quase integralmente — é a razão dele ter sido escolhido como referência.*

- `CLAUDE.md` (raiz) como ponto de entrada único, `specs/` (um arquivo por módulo de negócio, com tags `ASSUMPTION — VERIFICAR` para qualquer coisa não 100% confirmada), `docs/decisions/` (ADRs numeradas, `Status`/`Data`/`Contexto`/`Decisão`/`Consequências`).
- As decisões desta spec viram os primeiros ADRs em `docs/decisions/` no repositório Transbordo — matéria-prima que será destilada depois no padrão reutilizável (fora do escopo desta spec, ver acima).
- `Especificacao_Sistema_Transbordo_Atualizada.md` (já existente) vira a base para o `specs/` por módulo.
- Prática de documentar "achados reais" (bugs descobertos + fix, não só decisões) diretamente no CLAUDE.md/ADRs, como o APP_Vector faz.

### 10. Deploy/infra

*Herdado do APP_Vector, adaptando o que a Fase 4 já construiu para o Comigo/Streamlit.*

- `Dockerfile`/`docker-compose.yml` (já existentes, Fase 4) adaptados: gunicorn + `collectstatic` no lugar de `streamlit run`, serviço `worker` adicional para o Procrastinate.
- PostgreSQL continua externo/bare-metal (já é assim hoje), não containerizado — mesma decisão do APP_Vector (ADR 0001 de lá).
- `/healthz/` fazendo `SELECT 1` real, usado tanto pelo `HEALTHCHECK` do container quanto pelo monitor do proxy reverso.
- Apache (`comigo.conf`/`comigo-le-ssl.conf`, já existentes) re-roteado para a nova porta/serviço.
- Runbook de deploy manual (`git pull` → `docker compose build` → `migrate` → `check --deploy` → `up -d` → poll do healthcheck), mesmo padrão do `deploy.sh` do APP_Vector.

## Repositórios

- **`Comigo`** (`https://github.com/mapinho/Comigo.git`, remote local `comigo`) — congelado como arquivo histórico da versão final em produção com Streamlit. Já sincronizado (`git push comigo main`, 22/08/2026). Nenhum commit novo a partir de agora.
- **`Transbordo`** (`https://github.com/mapinho/Transbordo.git`, remote local `origin`) — onde todo o desenvolvimento desta fase acontece. Já sincronizado com o histórico mesclado (`git push origin main`, 22/08/2026).
- Diretório local continua o mesmo (não duas pastas separadas) — rename pendente de `Comigo` para `Transbordo` no disco, bloqueado por handle aberto do VSCode nesta sessão; a ser feito manualmente pelo usuário.
- **Escopo do rename "Comigo" → "Transbordo"**: só marca/produto (título de páginas, README, cabeçalho do CLAUDE.md, nomes de container/rede Docker, configs de deploy, nome do repositório). Termos de domínio em português (`Cenario`, `Fabrica`, `Armazem`, `Rota`, `Safra`, ...) continuam exatamente como estão — descrevem o negócio de logística de soja, não o nome do produto.

## Fases de migração

1. **Fundação** — projeto Django 6 no diretório local (já apontando para `origin`/Transbordo), apps `core`/`simulacao`/`integracoes`, settings `base/dev/prod`, CI (GitHub Actions) desde o commit zero, models `Cooperativa`+`User`+`TenantManager`.
2. **Port do domínio** — `engine.py`, `services.py`, os 9 models com `cooperativa_id`, testes de isolamento de tenant.
3. **UI** — views HTMX+Tailwind+daisyUI+cotton para cenários/fábricas/armazéns/rotas/previsões, Tabulator+IMask.js nas telas de edição em massa.
4. **Carga de Dados** — importação de planilha .xlsx (upload, pré-visualização, confirmação) — a otimização não tem o que otimizar sem dados carregados.
5. **Procrastinate** — task assíncrona de simulação + polling HTMX de progresso.
6. **Face JSON** — Django Ninja para MCP server e Assistente de IA.
7. **Auth** — allauth (Google + Microsoft + local), papéis, sem auto-cadastro.
8. **Deploy** — Dockerfile/compose adaptado, Apache re-roteado, `/healthz/`.
9. **Cutover** — segunda cooperativa piloto valida isolamento e desempenho sob carga concorrente, Streamlit desligado. `Comigo.git` permanece congelado.

## Decisões em aberto / riscos

- **Nenhuma decisão de arquitetura ficou em aberto** ao final deste brainstorm — todas as questões centrais (tenancy, camada de domínio, UI, auth, fila de jobs, CI, repositórios, escopo do rename) foram resolvidas e aprovadas nesta sessão.
- **Risco operacional, não arquitetural**: rename do diretório local pendente (bloqueado por VSCode) — não bloqueia o início da Fase 5 em si, mas precisa acontecer antes ou durante a Fase 1 de migração (Fundação) para evitar confusão de caminho.
- **Risco a monitorar durante a implementação**: `Tailwind v4`/`daisyUI 5` via CDN (sem build step) foi uma decisão explícita do APP_Vector com nota própria de "reavaliar perto de produção real" (ADR 0007 de lá) — vale reavaliar também aqui antes do cutover final, não assumir que CDN-only escala indefinidamente.
