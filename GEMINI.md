# GEMINI.md - Comigo (Transbordo de Soja)

## 1. Visão Geral do Projeto
O sistema **Comigo** é uma ferramenta de simulação e otimização logística para transbordo de soja. Ele permite planejar a movimentação de grãos entre Armazéns (origens) e Fábricas (destinos), visando minimizar custos de frete e garantir o suprimento contínuo das unidades de esmagamento.

## 2. Pilha Tecnológica
- **Linguagem:** Python 3.13+
- **Frontend:** Streamlit
- **Persistência:** SQLAlchemy (SQLite/PostgreSQL)
- **Processamento de Dados:** Pandas
- **Motor de Otimização:** Google OR-Tools (Programação Linear)

## 3. Convenções de Interface (UI/UX)

### 3.1. Formatação de Dados (Padrão Brasileiro)
Todas as exibições de tabelas devem utilizar a função `format_dataframe(df)` em `utils.py`, que garante:
- **Separador de Milhar:** Ponto (`.`)
- **Separador Decimal:** Vírgula (`,`)
- **Moeda:** Prefixo `R$` e 2 casas decimais.
- **Volume (Ton):** 1 casa decimal.
- **IDs:** Devem ser exibidos como **inteiros** (sem casas decimais).

### 3.2. Exibição de Tabelas
- Utilize `st.dataframe(format_dataframe(df), hide_index=True)` para visualização amigável.
- Para adicionar totais, use `append_totals_row(df)` antes da formatação.
- Colunas de ID devem ter a detecção automática habilitada em `utils.py` (via regex/substring 'id') para evitar formatação como float.

### 3.3. Edição de Dados (`st.data_editor`)
- Utilize `get_model_column_config(ModelClass)` para gerar automaticamente a configuração de colunas do Streamlit baseada nos metadados do SQLAlchemy (`info`).

## 4. Arquitetura de Dados

### 4.1. Modelos Principais
- `Cenario`: Agrupador de simulações. O ID `NULL` ou `is_oficial=True` representa o Plano Oficial.
- `Fabrica` / `Armazem`: Entidades logísticas.
- `Rota`: Conexão entre armazém e fábrica com custos de frete (Safra/Entressafra).
- `PrevisaoFabrica` / `PrevisaoArmazem`: Dados mensais de recebimento e vendas.
- `MovimentacaoDiaria`: Resultado da otimização.

### 4.2. Metadados do Modelo (`info`)
Os campos no `models.py` utilizam o parâmetro `info` para guiar a UI:
- `label`: Nome amigável da coluna.
- `type`: 'number', 'date', 'text'.
- `format`: '%d' para inteiros, 'localized' para padrão brasileiro.
- `hidden`: Se `True`, a coluna é omitida na UI.

## 5. Regras de Negócio Críticas
- **Deep Copy de Cenários:** Ao criar um novo cenário, todos os dados vinculados (fábricas, armazéns, rotas, previsões) devem ser duplicados.
- **Balanço de Massa:** `Estoque Final = Estoque Inicial + Entradas - Saídas`.
- **Prioridade de Otimização:** 1. Garantir esmagamento (evitar ruptura) > 2. Minimizar Custo de Frete > 3. Escoar Armazéns em Safra.

## 6. Fluxo de Trabalho (Workflows)
1. **Carga de Dados:** `data_loader.py` gerencia a conexão e clonagem.
2. **Cálculos:** `calculations.py` contém o motor de otimização diário.
3. **Exportação:** Todas as tabelas devem ter opção de exportação para Excel via `export_to_excel`.

## 7. Assistente de Dados Inteligente (MCP Server)
O sistema possui suporte nativo ao protocolo **Model Context Protocol (MCP)** para permitir que LLMs conectem-se e analisem de forma autônoma a nossa base de dados logística.
- **Servidor:** `mcp_server.py` (desenvolvido usando o framework `fastmcp`).
- **Como Utilizar:** Consulte o guia detalhado em `INSTRUCOES_MCP.md` para integrar com o **Claude Desktop** e com o **Gemini** (via Cursor, Cline ou pontes SSE).

## 8. Stack Django (Fases 5–7)
A migração para **Django 6 + HTMX** (SaaS multi-cooperativa) convive no mesmo repositório com o app
Streamlit. O detalhe canônico está em `CLAUDE.md` (seções "Fase 5/6/7"); resumo:
- `apps/core` (identidade, tenancy, papéis), `apps/simulacao` (port do domínio + Carga de Dados),
  `apps/integracoes` (Face JSON Django Ninja em `/api/v1/`), `apps/gestao` (telas de gestão, Fase 7).
- **Fase 7 — Auth:** `django-allauth` sob `/accounts/` (Google + Microsoft + usuário/senha), **sem
  auto-cadastro** (`apps/core/adapters.py` — login social só associa por e-mail a `User` pré-criado).
  `core.User.email` obrigatório e único. Autorização por papel em `apps/core/permissions.py`, aplicada
  em todas as views. Primeiro admin: `python manage.py criar_admin_vector <username> --email <email>`.
  Ver `docs/superpowers/specs/2026-08-29-fase7-auth-design.md` e ADR 0009.
- `.env` do stack Django: `DJANGO_DB_*`, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`; Fase 7 acrescenta
  `GOOGLE_CLIENT_ID/SECRET`, `MICROSOFT_CLIENT_ID/SECRET/TENANT`, `DJANGO_EMAIL_*`,
  `DJANGO_DEFAULT_FROM_EMAIL`, `ADMIN_VECTOR_PASSWORD` (todas opcionais salvo se o recurso for usado).
