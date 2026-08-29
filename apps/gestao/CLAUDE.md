# apps/gestao — file map

Telas de gestão da Fase 7 (ver `docs/superpowers/specs/2026-08-29-fase7-auth-design.md` e
`docs/decisions/0009-autenticacao-allauth-papeis.md`). Ver o `CLAUDE.md` raiz para o contexto do
projeto.

**Este app não tem models.** Opera sobre `core.Cooperativa` e `core.User`. Toda tela é gated por
`apps/core/permissions.py` — o `@login_required` vem primeiro, o gate de papel logo abaixo, e um papel
sem permissão recebe `PermissionDenied` → `templates/403.html` (não é botão escondido na UI).

- `views.py` — funções de view:
  - `cooperativas` / `cooperativa_nova` / `cooperativa_editar` — CRUD de cooperativas, `@requer_admin_vector`. Desativar (`ativo=False`) nunca apaga.
  - `usuarios` / `usuario_novo` / `usuario_editar` — CRUD de usuários, gated por `_requer_gestor` (Admin Vector **ou** Admin Cooperativa). `usuarios_visiveis(gestor)` é o filtro compartilhado: todos para Admin Vector; só `usuario_fabrica`/`usuario_armazem` da própria coop para Admin Cooperativa.
  - `usuario_enviar_link` (POST) — dispara o e-mail de definição de senha (allauth `ResetPasswordForm`); `Http404` se `email_configurado()` for falso (backend console/dummy).
  - `minha_cooperativa` — Admin Cooperativa edita só `dias_janela_safra_padrao` da própria coop.
  - `conta` — qualquer autenticado; mostra dados e links para as telas allauth (trocar senha, e-mails, contas sociais).
- `forms.py` — `CooperativaForm`, `MinhaCooperativaForm`, `UsuarioForm`. `UsuarioForm(gestor=...)` trava `cooperativa` e limita `papel` a fábrica/armazém quando o gestor não é Admin Vector; `save()` aplica a senha inicial (ou `set_unusable_password()` na criação sem senha) e roda `full_clean`.
- `context_processors.py` — `menu(request)` devolve os flags `menu_admin_vector` / `menu_admin_cooperativa` / `menu_gerir_usuarios` / `menu_membro_cooperativa` que o nav de `templates/base.html` consulta. `{}` para anônimo.
- `urls.py` — `app_name = 'gestao'`; rotas sob `/gestao/`.
- `tests/` — `test_cooperativas.py`, `test_usuarios.py`, `test_minha_cooperativa.py`, `test_conta.py`, `test_menu.py`.
