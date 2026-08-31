# Transbordo

SaaS multi-cooperativa para planejamento e otimização de transbordo de soja: movimentação diária entre
armazéns e fábricas minimizando frete, garantindo que as fábricas não fiquem sem matéria-prima.
Simulação de cenários ("e se"), Face JSON (`/api/v1/`) e assistente de IA (Gemini).

Django 6 + HTMX. Reconstruído a partir do app Streamlit original (**Comigo**, em produção à parte,
congelado — ver `docs/decisions/0011-...`).

## Rodar (dev)

1. `.env` na raiz (ver `.env.example`) — `DJANGO_SECRET_KEY`, `DJANGO_DB_*`, etc. Precisa de um
   PostgreSQL local com o banco/role `transbordo` (ver `docs/decisions/0002-...`).
2. Instalar:
   ```bash
   pip install -e ".[dev]"   # runtime + pytest/pytest-django
   ```
3. Migrar e subir:
   ```bash
   python manage.py migrate
   python manage.py runserver
   python manage.py procrastinate worker   # outro terminal — a aba Simulação depende dele
   ```
4. Primeiro Admin Vector: `python manage.py criar_admin_vector <username> --email <email>`.

Após o login, a aplicação abre na home em `/` (`LOGIN_REDIRECT_URL`): dashboard consolidado para o
Admin Vector, home da organização para os membros. UI no padrão da suíte **AgroVector** — ver
`docs/design-system/README.md` e `docs/decisions/0012-...`.

## Testes

```bash
pytest
```

## Deploy

Ver `docs/DEPLOY.md` (Docker Compose + gunicorn + Apache; runbook de primeira vez, recorrente,
rollback e migração de dados dev→prod).

## MCP

`mcp_server.py` é um servidor MCP (stdio) que expõe os relatórios de logística como *tools* para
clientes LLM (Claude Desktop, Cursor, Gemini CLI). É um **cliente HTTP** da Face JSON — não acessa o
banco.

| var | valor |
|---|---|
| `TRANSBORDO_API_URL` | base da API, ex. `https://transbordo.vectorconsulting.com.br/api/v1` |
| `TRANSBORDO_API_KEY` | uma `ApiKey` ativa (admin) — carrega a cooperativa |

Bloco `mcp.json` do cliente:

    {
      "mcpServers": {
        "transbordo": {
          "command": "python",
          "args": ["/caminho/para/mcp_server.py"],
          "env": {
            "TRANSBORDO_API_URL": "https://transbordo.vectorconsulting.com.br/api/v1",
            "TRANSBORDO_API_KEY": "..."
          }
        }
      }
    }

## Guia completo

Arquitetura, regras de negócio e convenções: [`CLAUDE.md`](CLAUDE.md).
