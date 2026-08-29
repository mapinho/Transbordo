# Fase 7 — Auth (allauth + papéis + apps/gestao)

## Contexto e objetivo

O roteiro (`docs/superpowers/specs/2026-08-22-fase5-arquitetura-saas-django.md`, seção 5 e item 7 das
"Fases de migração") lista a Fase 7 como "Auth — allauth (Google + Microsoft + local), papéis, sem
auto-cadastro". Fundação, Port do Domínio, UI, Carga de Dados, Simulação Assíncrona e Face JSON já
estão em `main`.

Hoje o stack Django autentica com `django.contrib.auth.urls` puro (`/accounts/login/` +
`templates/registration/login.html` em Tailwind) e um único mecanismo de proteção nas views:
`@login_required`. O model `core.User` (`AbstractUser`) **já tem** os campos `cooperativa` (FK nullable)
e `papel` (4 choices) e uma `CheckConstraint` provando a coerência entre os dois. O
`CooperativaScopeMiddleware` **já** lê `request.user.cooperativa_id` para o contextvar do
`TenantManager`. O que falta:

1. Login federado (Google + Microsoft/Azure AD) além do usuário/senha local, sem auto-cadastro.
2. Bootstrap do primeiro Admin Vector (o `createsuperuser` esbarra na `CheckConstraint`).
3. Uma camada de autorização por **papel** — nenhuma view checa papel hoje; um `usuario_armazem`
   consegue editar fábricas.
4. Telas para o Admin Vector cadastrar cooperativas e usuários (e para o Admin Cooperativa cadastrar
   os usuários da própria cooperativa).

O isolamento de leitura entre cooperativas **já está fechado** pelo `TenantManager` +
`CooperativaScopeMiddleware`: um `get_object_or_404(Cenario, id=…)` para o id de outra cooperativa já
devolve 404 hoje. O retrofit desta fase é sobre **papel**, não sobre vazamento de tenant.

## Escopo

**Dentro:**

- `django-allauth` (última versão, ~65.x) com providers Google e Microsoft (Azure AD multi-tenant) +
  backend local, configurado via settings (sem linhas `SocialApp` no banco).
- Adapters custom: sem auto-cadastro (local e social), associação de conta social a `User`
  pré-cadastrado **por e-mail**, nunca criação automática.
- `apps/core/adapters.py`, `apps/core/permissions.py`; migração tornando `core.User.email`
  obrigatório e único.
- Comando `python manage.py criar_admin_vector`.
- Retrofit de `@papel_required` / predicados em todas as views de `apps/simulacao/views.py`.
- Novo app `apps/gestao/` (sem models novos) com 4 grupos de tela: Cooperativas CRUD, Usuários CRUD,
  "Minha cooperativa", Conta/perfil.
- Nav de `templates/base.html` sensível a papel, via context processor.
- Templates allauth (`account/`, `socialaccount/`) tematizados sobre `base.html`.
- ADR `0009-autenticacao-allauth-papeis.md`; renumeração da ADR planejada da Fase 9 para `0010`.
- Atualização de `CLAUDE.md`, `GEMINI.md`, `.env.example`, seção 5 do spec da Fase 5, novo
  `apps/gestao/CLAUDE.md`.
- Testes (TDD, red → green) para adapters, comando, matriz de permissões, retrofit e telas do gestao.

**Fora:**

- Infra de e-mail transacional (SMTP) obrigatória — fica opcional/deferida (ver Seção "Novo usuário e
  senha"). Dev usa backend de console.
- Verificação de e-mail (`ACCOUNT_EMAIL_VERIFICATION = 'none'`) — o Vector cria as contas, o e-mail
  não é auto-declarado.
- Round-trip OAuth real automatizado nos testes (dependente de provider) — cobrimos a lógica de
  segurança dos adapters diretamente.
- Qualquer mexida no stack Streamlit/SQLAlchemy.
- Telas de parametrização de safra/capacidade além do campo `dias_janela_safra_padrao` que já existe
  em `Cooperativa` (o resto vem quando `SafraUnidade` ganhar semântica real).

## Decisões de design

### 1. Dependências e settings

- `requirements.txt` ganha `django-allauth[socialaccount]`.
- `INSTALLED_APPS` ganha `django.contrib.sites`, `allauth`, `allauth.account`,
  `allauth.socialaccount`, `allauth.socialaccount.providers.google`,
  `allauth.socialaccount.providers.microsoft`, `apps.gestao`. `SITE_ID = 1`.
- `MIDDLEWARE` ganha `allauth.account.middleware.AccountMiddleware` depois de
  `AuthenticationMiddleware` e antes de `apps.core.middleware.CooperativaScopeMiddleware`.
- `AUTHENTICATION_BACKENDS`: default do Django + `allauth.account.auth_backends.AuthenticationBackend`.
- Credenciais de provider via `SOCIALACCOUNT_PROVIDERS` com a chave `APPS` lendo do ambiente
  (`GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`, `MICROSOFT_CLIENT_ID`/`MICROSOFT_CLIENT_SECRET`,
  `MICROSOFT_TENANT='common'`). Sem `SocialApp` no banco → deploy não precisa de passo no admin.
- allauth: `SOCIALACCOUNT_AUTO_SIGNUP = False`, `ACCOUNT_ADAPTER` e `SOCIALACCOUNT_ADAPTER` custom
  (Seção 2), `ACCOUNT_EMAIL_VERIFICATION = 'none'`, `ACCOUNT_LOGIN_METHODS = {'username', 'email'}`.
  `LOGIN_REDIRECT_URL` / `LOGIN_URL` inalterados (`/simulacao/cenarios/` e `/accounts/login/`).
- E-mail: `EMAIL_BACKEND` de console em `dev`; `prod` usa SMTP se `DJANGO_EMAIL_HOST` estiver setado,
  senão console.

### 2. Fluxo de autenticação e adapters

- `config/urls.py`: troca `include('django.contrib.auth.urls')` por `include('allauth.urls')` sob
  `/accounts/`.
- `apps/core/adapters.py`:
  - `NoSignupAccountAdapter(DefaultAccountAdapter)` — `is_open_for_signup()` → `False`. O form de
    cadastro local some; `/accounts/signup/` responde 403.
  - `AssociateByEmailSocialAdapter(DefaultSocialAccountAdapter)`:
    - `is_open_for_signup()` → `False`.
    - `pre_social_login(request, sociallogin)`:
      - `sociallogin.is_existing` (conta social já ligada) → segue.
      - senão, busca `User` pelo e-mail verificado do provider:
        - achou → `sociallogin.connect(request, user)` (liga o `SocialAccount`, autentica).
        - não achou → `raise ImmediateHttpResponse` redirecionando para o login com mensagem pt-BR:
          *"Nenhuma conta cadastrada para este e-mail. Contate o administrador."*
    - Nunca cria `User`.
- Templates: allauth procura `templates/account/*.html` e `templates/socialaccount/*.html`.
  Sobrescrevemos só os que o usuário vê — `login.html`, `password_reset*.html`,
  `password_change.html`, `password_set.html`, `email.html`, `connections.html`, `logout.html` —
  cada um estendendo `base.html`. O `templates/registration/login.html` atual é removido (allauth usa
  `account/login.html`). A tela de login mostra o form usuário/senha **e** os botões "Entrar com
  Google" / "Entrar com Microsoft".
- Única mudança em `core.User`: `email` passa a ser obrigatório e único (migração adicionando
  `UniqueConstraint` em `email` + validação no form de usuário), porque a associação social é por
  e-mail. `ACCOUNT_UNIQUE_EMAIL = True`. A `CheckConstraint` de papel↔cooperativa continua válida —
  só ligamos conta social a usuário pré-criado.

### 3. Bootstrap: comando `criar_admin_vector`

- `apps/core/management/commands/criar_admin_vector.py` —
  `python manage.py criar_admin_vector <username> --email <email>`.
  - Cria `User` com `papel=admin_vector`, `cooperativa=None`, `is_staff=True`, `is_superuser=True`.
  - Pede senha interativamente (input escondido, com confirmação), estilo `createsuperuser`.
    `--password-from-env` lê `ADMIN_VECTOR_PASSWORD` para uso não-interativo/CI.
  - Recusa (exit 1, mensagem clara) se já existir qualquer usuário `admin_vector` — é bootstrap
    único, não gerência de usuário. Demais Admin Vector saem pela tela do gestao (Seção 5).
  - Roda `full_clean()` antes de salvar (exercita `clean()` + constraint).
- `createsuperuser` fica como está (ainda esbarra na constraint) — não é o caminho divulgado.
  *(Alternativa considerada: sobrescrever `UserManager.create_superuser` para default do papel —
  rejeitada porque faz `createsuperuser` criar admin cross-tenant silenciosamente.)*

### 4. Camada de autorização e retrofit em simulacao

`apps/core/permissions.py` — funções puras + decorators, sem estado:

- Predicados: `e_admin_vector(user)`, `e_admin_cooperativa(user)`, `e_usuario_fabrica(user)`,
  `e_usuario_armazem(user)`; compostos `pode_gerir_usuarios(user)` (`admin_vector` ou
  `admin_cooperativa`), `pode_editar_fabricas(user)` (`admin_cooperativa` ou `usuario_fabrica`),
  `pode_editar_armazens(user)` (`admin_cooperativa` ou `usuario_armazem`).
- Decorators para FBV: `@papel_required(*papeis)` e os wrappers semânticos
  `@requer_edicao_fabricas` / `@requer_edicao_armazens` / `@requer_admin_vector`. Assumem
  `@login_required` antes; em falha levantam `PermissionDenied` (403), nunca redirecionam.
- Template `403.html` estendendo `base.html`.

Retrofit em `apps/simulacao/views.py` (~20 views):

| Grupo de view | Gate adicionado |
|---|---|
| `cenarios_list`, aba/executar/status de simulação, `carga_*` | `@papel_required(admin_cooperativa, usuario_fabrica, usuario_armazem)` |
| `fabricas_grid` + saves de fábrica | `@requer_edicao_fabricas` |
| `armazens_grid` + saves de armazém | `@requer_edicao_armazens` |
| `rotas_grid`, `previsoes_grid`, `safras_grid` | `@papel_required(admin_cooperativa, usuario_fabrica, usuario_armazem)` |

- O escopo de objeto por tenant já é do `TenantManager` + middleware; adicionamos só um helper de
  legibilidade `cenario_do_usuario(request, cenario_id)` embrulhando `get_object_or_404`, sem mudança
  de comportamento.
- `admin_vector` (sem cooperativa) em qualquer view de simulacao → `PermissionDenied`; ele opera só
  no gestao.

### 5. App `apps/gestao`

App novo, **sem models novos** (opera sobre `core.Cooperativa` e `core.User`). Estrutura:
`apps/gestao/{forms,views,urls,context_processors}.py`, `templates/gestao/*.html` (+ parciais
`_*_content.html`, mesmo padrão do simulacao), `apps/gestao/tests/`. Montado em
`path('gestao/', include('apps.gestao.urls'))`.

Telas e gate:

1. **Cooperativas CRUD** — `@requer_admin_vector`. Listar / criar / editar / alternar `ativo`.
   Usa `Cooperativa.all_cooperativas` (cross-tenant é o ponto). Desativar nunca apaga.
2. **Usuários CRUD** — `pode_gerir_usuarios`:
   - **Admin Vector**: vê todos os usuários (`User.objects.all()` sem escopo para este papel), pode
     setar qualquer `papel` (inclusive `admin_vector`) e qualquer `cooperativa`.
   - **Admin Cooperativa**: queryset filtrado por `request.user.cooperativa`; choices de `papel`
     limitados a `usuario_fabrica` / `usuario_armazem`; campo `cooperativa` oculto e forçado à
     própria. Não edita linhas `admin_vector` / `admin_cooperativa`.
   - Form roda `User.full_clean()` (constraint papel↔cooperativa). Senha: campo inline no create
     (opcional; vazio → `set_unusable_password()`); botão "enviar link de definição de senha" visível
     só quando há backend de e-mail real configurado. View de edição nunca mostra o hash.
3. **Minha cooperativa** — `e_admin_cooperativa`. Form único editando só a `cooperativa` do usuário
   logado (`nome` read-only, `dias_janela_safra_padrao`). Sem lista de usuários.
4. **Conta / perfil** — qualquer autenticado. Majoritariamente as views allauth tematizadas
   (`account/`, `socialaccount/connections.html`) para trocar senha e ligar/desligar Google/Microsoft.
   Uma view `conta` no gestao é a landing que aponta para elas.

Os forms impõem as regras no servidor (`clean()`), nunca só via campo oculto/disabled.

### 6. Navegação (`templates/base.html` + `_subnav`)

- Nav sensível a papel, via context processor `apps.gestao.context_processors.menu` (expõe
  booleanos), registrado em `TEMPLATES['OPTIONS']['context_processors']`:
  - todo autenticado: "Cenários" / "Simulação", "Conta".
  - `admin_cooperativa`: + "Minha cooperativa".
  - `pode_gerir_usuarios`: + "Usuários".
  - `admin_vector`: "Cooperativas" / "Usuários" apenas — **sem** links de simulacao.
  - `is_staff`: + link "/admin/".
- Mostra usuário logado + label do `papel` + logout. Esconder link **nunca** é a única proteção — os
  gates das Seções 4/5 são a autoridade.

### 7. Novo usuário e senha

Por decisão: **inline por padrão, link por e-mail opcional**.

- Form de criação de usuário tem campo de senha (admin digita ou gera, repassa fora de banda). Vazio
  → `set_unusable_password()`.
- Se `settings.EMAIL_BACKEND` não for o dummy/console de teste, aparece o botão "enviar link de
  definição de senha", que dispara o fluxo `password_reset` do allauth.
- Config de SMTP (`DJANGO_EMAIL_*`) é opcional nesta fase; sem ela o fluxo de link fica desligado sem
  quebrar nada.

## Componentes e interfaces

| Unidade | O que faz | Como se usa | Depende de |
|---|---|---|---|
| `apps/core/adapters.py` | Bloqueia signup; associa conta social por e-mail | Referenciado por `ACCOUNT_ADAPTER` / `SOCIALACCOUNT_ADAPTER` | allauth, `core.User` |
| `apps/core/permissions.py` | Predicados de papel + decorators | `from apps.core.permissions import papel_required, pode_editar_fabricas` | `core.User.papel` |
| `criar_admin_vector` (command) | Bootstrap do 1º Admin Vector | `manage.py criar_admin_vector ...` | `core.User` |
| `apps/gestao/forms.py` | Forms de Cooperativa e User com regras por papel | Views do gestao | `core.User`, `core.Cooperativa`, `permissions` |
| `apps/gestao/views.py` | 4 grupos de tela HTMX | URLs `/gestao/` | `forms`, `permissions` |
| `apps/gestao/context_processors.py` | Booleanos de menu por papel | Template `base.html` | `permissions` |

## Tratamento de erro

- Não autenticado em rota protegida → redirect para `/accounts/login/` (comportamento
  `@login_required` atual).
- Autenticado sem papel para a ação → `PermissionDenied` → `403.html`. Nunca redirect (seria confuso:
  "faça login" para quem já está logado).
- Login social com e-mail sem `User` correspondente → volta para o login com mensagem pt-BR, sem
  criar nada.
- Form de usuário violando a constraint papel↔cooperativa → `ValidationError` exibido no form (o
  `full_clean()` pega antes do banco).
- Admin Cooperativa tentando editar usuário de outra cooperativa ou `admin_*` → 404/403 (queryset
  filtrado + checagem no `clean()`).

## Estratégia de teste

TDD (red → green) em tudo. Suíte SQLAlchemy (`tests/`) intocada.

- **Adapters** (`apps/core/tests/test_adapters.py`): `SocialLogin` com e-mail conhecido/desconhecido →
  connect vs. rejeição; nenhum `User` criado; `is_open_for_signup` → `False` nos dois.
- **Bootstrap** (`test_command_criar_admin_vector.py`): flags corretas; recusa no 2º run; honra
  `--password-from-env`.
- **Permissões** (`apps/core/tests/test_permissions.py`): matriz table-driven — cada `papel` × cada
  predicado/decorator → allow/deny esperado.
- **Retrofit simulacao**: estender `test_views_*.py` — `usuario_armazem` recebe 403 no POST de
  `fabricas_grid`; `usuario_fabrica` recebe 403 em `armazens_grid`; `admin_vector` recebe 403 em toda
  simulacao; happy paths seguem passando.
- **gestao** (`apps/gestao/tests/`): Cooperativas CRUD só admin vector; create de usuário do Admin
  Cooperativa é coop-scoped e não cria `admin_vector`; "minha cooperativa" edita só a própria linha;
  perfil renderiza.
- **Wiring allauth**: smoke test — `/accounts/login/` renderiza o form local + os botões de provider;
  `/accounts/signup/` responde 403.

## Documentação e housekeeping

- **Nova ADR `docs/decisions/0009-autenticacao-allauth-papeis.md`** — allauth via settings; sem
  auto-cadastro + adapter associate-by-email; camada de permissões por função pura (sem Groups /
  guardian / rules); comando `criar_admin_vector`; Admin Cooperativa gerencia usuários da própria
  cooperativa.
- **Renumeração de ADR**: Fase 7 fica com `0009`; a ADR planejada da Fase 9 passa a `0010`. Atualizar
  as ~10 referências em `docs/superpowers/specs/2026-08-28-fase9-*`,
  `plans/2026-08-28-fase9a-*`, `fase9b-*` e a linha "ADRs 0001–0009" do spec da Fase 8.
- **`docs/superpowers/specs/2026-08-22-fase5-arquitetura-saas-django.md` §5** — desvio: Admin
  Cooperativa passa a cadastrar/editar usuários (`usuario_fabrica` / `usuario_armazem`) da própria
  cooperativa. O texto atual diz "não cadastra usuários" e "Único papel que cria usuários" (Admin
  Vector) — corrigir na mesma commit do spec da Fase 7 (trigger de `sync-specs-skills`).
- **`CLAUDE.md`** — nova seção "Fase 7 — Auth (concluída)": fluxo allauth, `criar_admin_vector`,
  `apps/gestao/` no file map, convenção do `permissions.py`, env vars de provider/SMTP.
- **`GEMINI.md`** — espelhar as mudanças de arquitetura do `CLAUDE.md`.
- **`.env.example`** — `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`, `MICROSOFT_CLIENT_ID`/
  `MICROSOFT_CLIENT_SECRET`, `DJANGO_EMAIL_*`, `ADMIN_VECTOR_PASSWORD`.
- **Novo `apps/gestao/CLAUDE.md`** — file map do app, no estilo de `apps/simulacao/CLAUDE.md`.

## Riscos / pontos de atenção

- allauth 65.x mudou nomes de vários settings (`ACCOUNT_LOGIN_METHODS`, `ACCOUNT_SIGNUP_FIELDS`) —
  fixar na versão instalada e conferir contra a doc da versão, não de memória.
- O provider Microsoft do allauth com `tenant='common'` exige que o app registration na Azure seja
  multi-tenant; conta pessoal Microsoft (MSA) pode ou não ser aceita conforme a config do app —
  validar com uma conta real antes de fechar a fase.
- A migração de `email` único em `core.User` pode falhar se o banco local já tiver usuários com
  `email` vazio/duplicado (criados via shell nas fases anteriores) — a migração precisa de um passo
  de dados que detecte e aborte com mensagem clara, ou o dev limpa manualmente antes.
