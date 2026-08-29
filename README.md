# Sistema de Planejamento de Transbordo

Este sistema otimiza a distribuição diária de soja entre armazéns e fábricas para minimizar o custo total de frete, respeitando limites de estoque e esmagamento.

## Tecnologias Utilizadas
- **Python 3.10+**
- **Streamlit** (Interface do Usuário)
- **Google OR-Tools** (Motor de Otimização)
- **SQLAlchemy** (ORM)
- **PostgreSQL** (Banco de Dados)
- **Pandas/Plotly** (Processamento e Visualização)

## Como Rodar

1.  **Configurar o Banco de Dados:**
    Crie um arquivo `.env` na raiz do projeto com as seguintes variáveis (obrigatório — não há mais fallback de credenciais embutido no código):
    ```env
    DB_USER=seu_usuario
    DB_PASSWORD=sua_senha
    DB_HOST=localhost
    DB_PORT=5432
    DB_NAME=comigo
    GEMINI_API_KEY=sua_chave   # opcional, só necessário para a aba "Assistente de IA"
    ```

2.  **Instalar Dependências:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Executar o Sistema:**
    ```bash
    streamlit run app.py
    ```

Os templates de Excel para carga de dados já estão prontos em `templates/` (não é mais necessário gerá-los).

## Desenvolvimento

```bash
pip install -r requirements-dev.txt   # adiciona pytest
pytest tests/ -v                      # suíte roda em SQLite em memória, sem precisar do Postgres
```

## Estrutura de Arquivos
- `app.py`: Interface Streamlit.
- `app_logic.py`: Lógica pura (sem Streamlit) extraída de `app.py`, testável isoladamente.
- `models.py`: Definições das tabelas em português (SQLAlchemy).
- `calculations.py`: Lógica de otimização com OR-Tools.
- `scenarios.py`: Clonagem de cenários (simulações).
- `data_loader.py`: Conexão com o banco e carregamento de dados XLSX.
- `logistics_services.py`: Camada de relatórios (somente leitura), compartilhada pelo MCP server e pelo Assistente de IA.
- `mcp_server.py`: Servidor MCP (FastMCP) para integração com LLMs externos.
- `ai_assistant.py`: Assistente de IA nativo (Gemini) embutido no app.
- `utils.py`: Formatação (padrão pt-BR) e helpers de exportação/UI.
- `templates/`: Modelos de arquivos Excel para carga de dados.
- `tests/`: Suíte de testes (pytest).

Para o guia completo do projeto (arquitetura, regras de negócio, convenções), veja [`CLAUDE.md`](CLAUDE.md).
