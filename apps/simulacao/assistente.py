"""Assistente de IA (Gemini function-calling) sobre apps/simulacao/services.py.

Port da lógica de `ai_assistant.py` (raiz, usada pelo Streamlit) para o app
Django: as ferramentas chamam `services.py` em processo, com a cooperativa e o
cenário fixados pelo contexto da aba. Ver Fase 9b e ADR 0010.
"""
from django.conf import settings
from google import genai
from google.genai import types

from apps.simulacao import services
from apps.simulacao.models import ConversaIA

SYSTEM_PROMPT = """Você é o Assistente de Inteligência Logística da COMIGO, especializado na otimização e simulação de transbordo de soja.
Sua missão é ajudar planejadores e analistas logísticos a compreenderem os dados do sistema, avaliar cenários de simulação, identificar gargalos e planejar movimentações para minimizar custos e evitar rupturas de estoque nas fábricas.

Diretrizes de Comportamento:
1. **Persona de Especialista**: Seu tom deve ser altamente profissional, preciso, consultivo e técnico. Você é um parceiro de planejamento estratégico.
2. **Uso de Ferramentas (Function Calling)**: Sempre utilize as ferramentas fornecidas para buscar as informações mais atualizadas do banco de dados de cenários e simulações. Nunca invente dados. Se não houver dados, informe educadamente que não há registros correspondentes para a consulta.
3. **Análise de Gargalos e Estoques**:
   - Destaque picos de estoque e volumes excedentes (alertas gerados por `get_stock_excesses_report` ou comparativos) como gargalos críticos de capacidade estática.
   - Explique o impacto de um estouro de capacidade (por exemplo, custos extras de armazenamento externo ou risco de armazenamento inadequado) e a importância de escoar o excedente.
4. **Análise de Custos**:
   - Sempre consulte as rotas e resumos de movimentações para avaliar o impacto financeiro.
   - Apresente custos formatados no padrão de moeda brasileiro: prefixo 'R$' com duas casas decimais e separadores de milhar (ex: R$ 1.250.300,50).
5. **Formatação e Legibilidade**:
   - Apresente dados tabulares usando tabelas Markdown claras e organizadas.
   - Use bullet points para conclusões e recomendações acionáveis.
   - Apresente volumes em Toneladas (Ton) com separador de milhar (ponto) e uma casa decimal, ou em Sacas (Sc).
6. **Gerenciamento de Cenários**:
   - Se o usuário não especificar qual cenário deseja analisar, use `list_scenarios` para identificar quais cenários existem, informe que está usando o cenário Oficial (is_oficial=True) por padrão e convide o usuário a escolher outro cenário se preferir.
   - Refira-se aos cenários pelo seu nome legível e forneça o ID quando útil para clareza técnica.
"""

_MODELO = "gemini-2.5-flash"


class AssistenteIndisponivel(Exception):
    """GEMINI_API_KEY não configurada."""


def _get_client() -> genai.Client:
    if not settings.GEMINI_API_KEY:
        raise AssistenteIndisponivel(
            "GEMINI_API_KEY não configurada — o Assistente de IA está indisponível."
        )
    return genai.Client(api_key=settings.GEMINI_API_KEY)


def _fazer_ferramentas(cenario):
    """9 closures ligadas a `cenario`, delegando para services.py em processo.
    O cenário é fixo pela aba, então as tools não recebem `scenario_id`."""
    cid = cenario.cooperativa_id
    sid = cenario.id

    def list_scenarios() -> list[dict]:
        """
        Lista todos os cenários de simulação cadastrados no sistema,
        indicando qual é o cenário oficial e o seu ID correspondente.
        """
        return services.list_scenarios(cooperativa_id=cid)

    def get_daily_movements(
        start_date: str | None = None,
        end_date: str | None = None,
        origin_id: int | None = None,
        destination_id: int | None = None,
        limit: int = 150,
    ) -> list[dict]:
        """
        Retorna a lista detalhada de movimentações diárias de soja para o cenário desta aba.
        Permite filtrar por intervalo de datas (AAAA-MM-DD), ID do armazém de origem (origin_id),
        ID da fábrica de destino (destination_id). Retorna o volume em Ton, Sc (sacas) e Custo Financeiro.
        """
        return services.get_daily_movements(
            scenario_id=sid, start_date=start_date, end_date=end_date,
            origin_id=origin_id, destination_id=destination_id, limit=limit,
        )

    def get_monthly_summary(
        start_date: str | None = None, end_date: str | None = None,
    ) -> dict:
        """
        Retorna o resumo consolidado por mês (e detalhamento por rota) das movimentações do cenário.
        Útil para análise mensal do volume movimentado em toneladas, sacas e o custo total de frete.
        Intervalos de data opcionais no formato AAAA-MM-DD.
        """
        return services.get_monthly_summary(
            scenario_id=sid, start_date=start_date, end_date=end_date,
        )

    def get_factories_summary() -> list[dict]:
        """
        Exibe o resumo mensal de operações de todas as fábricas (unidades de esmagamento)
        cadastradas no cenário desta aba. Inclui dados de recebimento do produtor,
        recebimento via transbordo, volume esmagado, saldo de estoque final no mês,
        capacidade estática máxima e volume excedente armazenado fora da capacidade.
        """
        return services.get_factories_summary(scenario_id=sid)

    def get_warehouses_summary() -> list[dict]:
        """
        Exibe o resumo mensal de operações de todos os armazéns (origens) cadastrados
        no cenário desta aba. Inclui dados de recebimento de produtor local,
        envio via transbordo para fábricas, vendas locais efetuadas, saldo de estoque
        final no mês, capacidade estática e volume excedente (transbordado/fora da capacidade).
        """
        return services.get_warehouses_summary(scenario_id=sid)

    def compare_factories() -> list[dict]:
        """
        Agrega as métricas de desempenho e gargalos para todas as fábricas no cenário.
        Permite ao LLM comparar facilmente quais fábricas tiveram maior esmagamento total,
        picos de estoque máximos registrados ao longo do cenário, volume total de recebimento,
        e a quantidade total acumulada de excedentes (risco de ruptura/armazenamento incorreto).
        """
        return services.compare_factories(scenario_id=sid)

    def compare_warehouses() -> list[dict]:
        """
        Agrega as métricas de desempenho e escoamento para todos os armazéns no cenário.
        Permite comparar quais armazéns receberam mais soja direta do produtor, quais
        escoaram o maior volume via transbordo, as vendas totais acumuladas e os maiores
        picos de estoque (gargalos de estocagem) e excedentes gerados no cenário.
        """
        return services.compare_warehouses(scenario_id=sid)

    def get_stock_excesses_report() -> list[dict]:
        """
        Gera um relatório analítico contendo todos os alertas de estouro de capacidade estática
        (excedentes de estoque > 0) para armazéns e fábricas ao longo dos meses do cenário.
        Identifica com precisão quais meses e locais sofreram com sobrecarga de estocagem.
        """
        return services.get_stock_excesses_report(scenario_id=sid)

    def get_stock_ruptures_report() -> list[dict]:
        """
        Gera um relatório analítico contendo todos os alertas de ruptura de estoque
        (saldo_estoque < 0) para armazéns e fábricas ao longo dos meses do cenário.
        Identifica com precisão quais meses e locais sofreram com déficit de estoque
        (estoque negativo), risco crítico de parada de operação por falta de matéria-prima.
        """
        return services.get_stock_ruptures_report(scenario_id=sid)

    return [
        list_scenarios, get_daily_movements, get_monthly_summary,
        get_factories_summary, get_warehouses_summary, compare_factories,
        compare_warehouses, get_stock_excesses_report, get_stock_ruptures_report,
    ]


def _historico(conversa: ConversaIA) -> list[types.Content]:
    papel_para_role = {'user': 'user', 'assistant': 'model'}
    return [
        types.Content(
            role=papel_para_role[m['papel']],
            parts=[types.Part(text=m['conteudo'])],
        )
        for m in conversa.mensagens
    ]


def responder(conversa: ConversaIA, mensagem_usuario: str) -> str:
    conversa.adicionar('user', mensagem_usuario)
    if not conversa.titulo:
        conversa.titulo = mensagem_usuario[:120]

    try:
        client = _get_client()
        chat = client.chats.create(
            model=_MODELO,
            history=_historico(conversa)[:-1],  # tudo menos a mensagem recém-adicionada
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                tools=_fazer_ferramentas(conversa.cenario),
                temperature=0.2,
            ),
        )
        resposta = chat.send_message(mensagem_usuario).text or ''
    except AssistenteIndisponivel as exc:
        resposta = str(exc)
    except Exception as exc:  # noqa: BLE001 — nunca propaga para a view
        resposta = f"Ocorreu um erro ao consultar a inteligência artificial: {exc}"

    conversa.adicionar('assistant', resposta)
    conversa.save()
    return resposta
