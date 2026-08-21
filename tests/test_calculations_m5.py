"""
Testes M5 - Consolidação da lógica de janela de safra em `otimizar_dia`.

Contexto: `calculations.py` tinha TRÊS cópias independentes da lógica
"buscar SafraUnidade, senão usar padrão 15/01-15/04":
  1) `esta_na_safra` (função morta, nunca chamada em lugar nenhum)
  2) bloco inline dentro de `otimizar_dia` ao montar o objetivo do solver
  3) bloco inline dentro de `otimizar_dia` ao re-derivar o custo real para
     o resultado/log

Este arquivo fixa (caracteriza) o comportamento ATUAL antes da consolidação
e deve continuar passando, sem nenhuma alteração, depois da consolidação
para uma única função auxiliar compartilhada.

Nuance de TDD: como esta é uma correção de "drift futuro" (não há uma saída
incorreta HOJE para reproduzir como falha), a sequência correta aqui é:
    1. Escrever os testes de caracterização.
    2. Rodar contra o código ATUAL (pré-refactor) e confirmar que PASSAM
       (eles fixam o comportamento correto de hoje como baseline).
    3. Fazer a consolidação (extrair um único helper, usá-lo nos dois
       call-sites de `otimizar_dia`, remover a duplicação/código morto).
    4. Rodar os mesmos testes de novo e confirmar que continuam passando,
       provando que o refactor não alterou o comportamento observável.
"""
import datetime

import calculations
from models import SafraUnidade


# ---------------------------------------------------------------------------
# Testes de caracterização de ponta a ponta via otimizar_dia
# ---------------------------------------------------------------------------

def test_otimizar_dia_usa_custo_de_safra_quando_data_esta_na_janela(session, cenario, armazem, fabrica, rota):
    """Data dentro da janela de SafraUnidade -> custo_total usa custo_frete_ton (safra)."""
    safra = SafraUnidade(
        cenario_id=cenario.id,
        entidade_tipo='Armazém',
        entidade_id=armazem.id,
        data_inicio=datetime.date(2026, 2, 1),
        data_fim=datetime.date(2026, 3, 1),
    )
    session.add(safra)
    session.commit()

    data_teste = datetime.date(2026, 2, 15)  # dentro da janela
    estoques_atuais = {f'A_{armazem.id}': 2000, f'F_{fabrica.id}': 0}

    resultados = calculations.otimizar_dia(
        session, data=data_teste, estoques_atuais=estoques_atuais, cenario_id=cenario.id
    )

    assert resultados, "esperava ao menos uma movimentação"
    mov = resultados[0]
    assert mov['armazem_id'] == armazem.id
    assert mov['fabrica_id'] == fabrica.id
    custo_esperado = mov['quantidade_ton'] * rota.custo_frete_ton
    assert mov['custo_total'] == custo_esperado


def test_otimizar_dia_usa_custo_de_entressafra_quando_data_fora_da_janela(session, cenario, armazem, fabrica, rota):
    """Data fora (depois) da janela de SafraUnidade, mas ainda com estoque -> custo_total usa custo_frete_entressafra."""
    safra = SafraUnidade(
        cenario_id=cenario.id,
        entidade_tipo='Armazém',
        entidade_id=armazem.id,
        data_inicio=datetime.date(2026, 2, 1),
        data_fim=datetime.date(2026, 3, 1),
    )
    session.add(safra)
    session.commit()

    # Depois do fim da safra (não bloqueado, pois o bloqueio só ocorre ANTES
    # do início da safra), então a rota ainda pode ser escolhida, porém com
    # o custo de entressafra.
    data_teste = datetime.date(2026, 3, 15)
    estoques_atuais = {f'A_{armazem.id}': 2000, f'F_{fabrica.id}': 0}

    resultados = calculations.otimizar_dia(
        session, data=data_teste, estoques_atuais=estoques_atuais, cenario_id=cenario.id
    )

    assert resultados, "esperava ao menos uma movimentação"
    mov = resultados[0]
    custo_esperado = mov['quantidade_ton'] * rota.custo_frete_entressafra
    assert mov['custo_total'] == custo_esperado


# ---------------------------------------------------------------------------
# Teste unitário direto do helper consolidado (obter_janela_safra)
# ---------------------------------------------------------------------------

def test_obter_janela_safra_com_registro_data_dentro(session, cenario, armazem):
    safra = SafraUnidade(
        cenario_id=cenario.id,
        entidade_tipo='Armazém',
        entidade_id=armazem.id,
        data_inicio=datetime.date(2026, 2, 1),
        data_fim=datetime.date(2026, 3, 1),
    )
    session.add(safra)
    session.commit()

    na_safra, d_ini, d_fim = calculations.obter_janela_safra(
        session, 'Armazém', armazem.id, datetime.date(2026, 2, 15), cenario.id
    )

    assert na_safra is True
    assert d_ini == datetime.date(2026, 2, 1)
    assert d_fim == datetime.date(2026, 3, 1)


def test_obter_janela_safra_com_registro_data_fora(session, cenario, armazem):
    safra = SafraUnidade(
        cenario_id=cenario.id,
        entidade_tipo='Armazém',
        entidade_id=armazem.id,
        data_inicio=datetime.date(2026, 2, 1),
        data_fim=datetime.date(2026, 3, 1),
    )
    session.add(safra)
    session.commit()

    na_safra, d_ini, d_fim = calculations.obter_janela_safra(
        session, 'Armazém', armazem.id, datetime.date(2026, 3, 15), cenario.id
    )

    assert na_safra is False
    assert d_ini == datetime.date(2026, 2, 1)
    assert d_fim == datetime.date(2026, 3, 1)


def test_obter_janela_safra_sem_registro_usa_padrao_15jan_15abr(session, cenario, armazem):
    # Nenhum SafraUnidade criado para este armazém.
    na_safra_dentro, d_ini, d_fim = calculations.obter_janela_safra(
        session, 'Armazém', armazem.id, datetime.date(2026, 2, 1), cenario.id
    )
    assert d_ini == datetime.date(2026, 1, 15)
    assert d_fim == datetime.date(2026, 4, 15)
    assert na_safra_dentro is True

    na_safra_fora, d_ini2, d_fim2 = calculations.obter_janela_safra(
        session, 'Armazém', armazem.id, datetime.date(2026, 5, 1), cenario.id
    )
    assert d_ini2 == datetime.date(2026, 1, 15)
    assert d_fim2 == datetime.date(2026, 4, 15)
    assert na_safra_fora is False
