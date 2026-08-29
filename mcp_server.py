"""Comigo/Transbordo — servidor MCP (stdio).

Cliente HTTP da face JSON (`/api/v1/`, Fase 6). Configuração por variáveis de
ambiente (com fallback para `.env` em dev):

    TRANSBORDO_API_URL   base da API, ex. https://transbordo.exemplo.com/api/v1
    TRANSBORDO_API_KEY   chave X-API-Key (carrega a cooperativa)

Exemplo de bloco `mcp.json` de um cliente (Claude Desktop / Cursor):

    {
      "mcpServers": {
        "transbordo": {
          "command": "python",
          "args": ["/caminho/para/mcp_server.py"],
          "env": {
            "TRANSBORDO_API_URL": "https://transbordo.exemplo.com/api/v1",
            "TRANSBORDO_API_KEY": "..."
          }
        }
      }
    }
"""
import os

import httpx
from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

load_dotenv()

BASE_URL = (os.getenv("TRANSBORDO_API_URL") or "").rstrip("/")
API_KEY = os.getenv("TRANSBORDO_API_KEY") or ""
if not BASE_URL or not API_KEY:
    raise RuntimeError(
        "Defina TRANSBORDO_API_URL e TRANSBORDO_API_KEY no ambiente (ou no .env) — "
        "o servidor MCP agora fala com a face JSON /api/v1/ por HTTP."
    )

mcp = FastMCP(
    "Comigo Logistica MCP Server",
    instructions="Servidor MCP para consulta e analise de simulacoes e movimentacoes logisticas de soja da Comigo.",
)


def _get(path: str, **params):
    """GET tipado contra a face JSON. Params None sao descartados."""
    limpos = {k: v for k, v in params.items() if v is not None}
    resp = httpx.get(
        f"{BASE_URL}{path}",
        params=limpos,
        headers={"X-API-Key": API_KEY},
        timeout=30,
    )
    if resp.status_code == 401:
        raise ToolError("Chave de API inválida ou inativa (TRANSBORDO_API_KEY).")
    if resp.status_code == 404:
        raise ToolError("Cenário não encontrado para esta cooperativa.")
    if resp.status_code >= 400:
        try:
            raise ToolError(resp.json().get("detail", resp.text))
        except ValueError:
            raise ToolError(resp.text or f"Erro HTTP {resp.status_code}")
    return resp.json()


@mcp.tool()
def list_scenarios() -> list[dict]:
    """
    Lista todos os cenarios de simulacao cadastrados no sistema,
    indicando qual e o cenario oficial e o seu ID correspondente.
    """
    return _get("/cenarios/")


@mcp.tool()
def get_daily_movements(
    scenario_id: int,
    start_date: str | None = None,
    end_date: str | None = None,
    origin_id: int | None = None,
    destination_id: int | None = None,
    limit: int = 150
) -> list[dict]:
    """
    Retorna a lista detalhada de movimentacoes diarias de soja para um cenario especifico.
    Permite filtrar por intervalo de datas (AAAA-MM-DD), ID do armazem de origem (origin_id),
    ID da fabrica de destino (destination_id). Retorna o volume em Ton, Sc (sacas) e Custo Financeiro.
    """
    return _get(
        f"/cenarios/{scenario_id}/movimentacoes/",
        start_date=start_date,
        end_date=end_date,
        origin_id=origin_id,
        destination_id=destination_id,
        limit=limit,
    )


@mcp.tool()
def get_monthly_summary(
    scenario_id: int,
    start_date: str | None = None,
    end_date: str | None = None
) -> dict:
    """
    Retorna o resumo consolidado por mes (e detalhamento por rota) das movimentacoes.
    Util para analise mensal do volume movimentado em toneladas, sacas e o custo total de frete.
    Intervalos de data opcionais no formato AAAA-MM-DD.
    """
    return _get(
        f"/cenarios/{scenario_id}/resumo-mensal/",
        start_date=start_date,
        end_date=end_date,
    )


@mcp.tool()
def get_factories_summary(scenario_id: int) -> list[dict]:
    """
    Exibe o resumo mensal de operacoes de todas as fabricas (unidades de esmagamento)
    cadastradas no cenario especificado. Inclui dados de recebimento do produtor,
    recebimento via transbordo, volume esmagado, saldo de estoque final no mes,
    capacidade estatica maxima e volume excedente armazenado fora da capacidade.
    """
    return _get(f"/cenarios/{scenario_id}/fabricas/resumo/")


@mcp.tool()
def get_warehouses_summary(scenario_id: int) -> list[dict]:
    """
    Exibe o resumo mensal de operacoes de todos os armazens (origens) cadastrados
    no cenario especificado. Inclui dados de recebimento de produtor local,
    envio via transbordo para fabricas, vendas locais efetuadas, saldo de estoque
    final no mes, capacidade estatica e volume excedente (transbordado/fora da capacidade).
    """
    return _get(f"/cenarios/{scenario_id}/armazens/resumo/")


@mcp.tool()
def compare_factories(scenario_id: int) -> list[dict]:
    """
    Agrega as metricas de desempenho e gargalos para todas as fabricas no cenario.
    Permite ao LLM comparar facilmente quais fabricas tiveram maior esmagamento total,
    picos de estoque maximos registrados ao longo do cenario, volume total de recebimento,
    e a quantidade total acumulada de excedentes (risco de ruptura/armazenamento incorreto).
    """
    return _get(f"/cenarios/{scenario_id}/fabricas/comparacao/")


@mcp.tool()
def compare_warehouses(scenario_id: int) -> list[dict]:
    """
    Agrega as metricas de desempenho e escoamento para todos os armazens no cenario.
    Permite comparar quais armazens receberam mais soja direta do produtor, quais
    escoaram o maior volume via transbordo, as vendas totais acumuladas e os maiores
    picos de estoque (gargalos de estocagem) e excedentes gerados no cenario.
    """
    return _get(f"/cenarios/{scenario_id}/armazens/comparacao/")


@mcp.tool()
def get_stock_excesses_report(scenario_id: int) -> list[dict]:
    """
    Gera um relatorio analitico contendo todos os alertas de estouro de capacidade estatica
    (excedentes de estoque > 0) para armazens e fabricas ao longo dos meses do cenario.
    Identifica com precisao quais meses e locais sofreram com sobrecarga de estocagem.
    """
    return _get(f"/cenarios/{scenario_id}/alertas/excedentes/")


@mcp.tool()
def get_stock_ruptures_report(scenario_id: int) -> list[dict]:
    """
    Gera um relatorio analitico contendo todos os alertas de ruptura de estoque
    (saldo_estoque < 0) para armazens e fabricas ao longo dos meses do cenario.
    Identifica com precisao quais meses e locais sofreram com deficit de estoque
    (estoque negativo), risco critico de parada de operacao por falta de materia-prima.
    """
    return _get(f"/cenarios/{scenario_id}/alertas/rupturas/")


if __name__ == "__main__":
    mcp.run(transport="stdio")
