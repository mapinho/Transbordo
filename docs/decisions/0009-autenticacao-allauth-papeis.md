# ADR 0009 — Autenticação com allauth + autorização por papel

- Status: Aceito
- Data: 2026-08-29

## Contexto

A Fase 7 (`docs/superpowers/specs/2026-08-29-fase7-auth-design.md`) adiciona login federado
(Google + Microsoft) ao lado de usuário/senha local, sem auto-cadastro, mais uma camada de
autorização por `papel` aplicada a todas as views existentes, o bootstrap do primeiro Admin Vector
e o app `apps/gestao` (telas HTMX de cooperativas e usuários).

Até aqui a autenticação era só `django.contrib.auth.urls` sob `/accounts/`, sem papéis efetivos —
o campo `core.User.papel` existia (Fase 5) mas nada o consultava no ciclo de request.

## Decisão

- **django-allauth 65.x** substitui `django.contrib.auth.urls` sob `/accounts/`. Google e Microsoft
  (Azure AD multi-tenant, `tenant='common'`) configurados via
  `SOCIALACCOUNT_PROVIDERS[...]['APPS']` em settings — **sem linhas `SocialApp` no banco**. Credenciais
  vêm do ambiente (`GOOGLE_CLIENT_ID`/`SECRET`, `MICROSOFT_CLIENT_ID`/`SECRET`/`TENANT`).
- **Sem cadastro, nunca.** `SOCIALACCOUNT_AUTO_SIGNUP = False` e dois adapters em
  `apps/core/adapters.py`:
  - `NoSignupAccountAdapter.is_open_for_signup` → `False` (cadastro local fechado).
  - `AssociateByEmailSocialAdapter.pre_social_login` conecta o login social ao `User` **pré-criado**
    cujo `email` bate (case-insensitive); se não houver, adiciona mensagem pt-BR e redireciona ao
    login. Nunca cria `User`.
- **`core.User.email` obrigatório e único** (`EmailField(unique=True)`, migração `0004` com pré-checagem
  de e-mails vazios/duplicados). A associação por e-mail depende disso.
- **Autorização = funções puras + decorators finos** em `apps/core/permissions.py` (`papel_de`, os
  quatro `e_*`, os compostos `pode_*`, `papel_required(*papeis)`, `requer_edicao_fabricas`,
  `requer_edicao_armazens`, `requer_admin_vector`). Os decorators ficam **abaixo** de `@login_required`
  (anônimo é redirecionado, não recebe 403). `PermissionDenied` → `templates/403.html`.
  Rejeitados: Django Groups/Permissions (spec §5), django-guardian, django-rules — o modelo de papéis
  é fixo e pequeno; um módulo de predicados é mais legível e testável.
- **Bootstrap**: `python manage.py criar_admin_vector <username> --email <email>` cria o único
  `admin_vector` (`cooperativa=None`, `is_staff`/`is_superuser`, recusa um segundo). `createsuperuser`
  não serve — esbarra na `CheckConstraint` de coerência papel/cooperativa (migração `0003`).
- **Desvio da spec Fase 5 §5**: Admin Cooperativa agora **cadastra/edita** os usuários
  (`usuario_fabrica`/`usuario_armazem`) da própria cooperativa. Antes só o Admin Vector criava usuários.
- **`apps/gestao` sem models** — opera sobre `core.Cooperativa` e `core.User` através de forms que
  codificam as regras por papel no servidor. As telas cross-tenant (lista de cooperativas, lista de
  usuários do Admin Vector) usam `.objects` em models não-escopados, gated por `requer_admin_vector` /
  `pode_gerir_usuarios` — a exceção deliberada à regra dos ADRs 0001/0003/0006.
- **E-mail transacional opcional**: console em dev; SMTP em prod só se `DJANGO_EMAIL_HOST` estiver
  definido. Sem e-mail configurado, o link "enviar definição de senha" na tela de usuário fica
  desligado (a senha inicial é definida inline no form).

## Consequências

- Nova dependência de produção: `django-allauth[socialaccount]>=65.0,<66.0` (resolveu para 65.19.x).
  Novas migrações aplicadas: `sites`, `account`, `socialaccount`, `core.0004`.
- Novas variáveis de ambiente (todas opcionais exceto se o provedor for usado): `GOOGLE_CLIENT_ID`,
  `GOOGLE_CLIENT_SECRET`, `MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET`, `MICROSOFT_TENANT`,
  `DJANGO_EMAIL_*`, `DJANGO_DEFAULT_FROM_EMAIL`, `ADMIN_VECTOR_PASSWORD`.
- Verificação manual pendente antes de fechar a fase: round-trip SSO real (Google e Microsoft) para um
  usuário pré-criado e para um e-mail não cadastrado.
- Renumeração: a ADR planejada da Fase 9 (split MCP HTTP / IA in-process) passa de `0009` para `0010`.
