import logging
from ortools.linear_solver import pywraplp
import pandas as pd
import datetime
from models import Fabrica, Armazem, Rota, MovimentacaoDiaria, PrevisaoFabrica, PrevisaoArmazem, ResumoMensalFabrica, ResumoMensalArmazem, SafraUnidade
from sqlalchemy.orm import Session
from sqlalchemy import func

# Configuração de logging básico
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def _janela_safra_de_registro(safra, data):
    """
    Versão pura de `obter_janela_safra`: recebe o registro SafraUnidade já
    buscado (ou None) e resolve (na_safra, data_inicio, data_fim) sem
    tocar o banco.

    O registro em si é estático por (cenário, entidade) e pode ser
    pré-carregado uma única vez por `simular_periodo` (ver
    `_carregar_safras_por_armazem`), mas a janela de fallback (quando não
    há registro) depende do ANO de `data` -- por isso essa resolução
    continua sendo feita a cada chamada, e não pode ser cacheada junto com
    o registro.
    """
    if safra:
        data_inicio, data_fim = safra.data_inicio, safra.data_fim
    else:
        # Fallback: Se não houver configuração de safra, usamos um período padrão (15/01 a 15/04)
        ano = data.year
        data_inicio = datetime.date(ano, 1, 15)
        data_fim = datetime.date(ano, 4, 15)

    na_safra = data_inicio <= data <= data_fim
    return na_safra, data_inicio, data_fim


def obter_janela_safra(session: Session, entidade_tipo, entidade_id, data, cenario_id):
    """
    Determina a janela de safra (início/fim) de uma unidade (Armazém/Fábrica)
    e se `data` está dentro dela.

    Ponto único de verdade para a lógica "buscar SafraUnidade cadastrada,
    senão usar o período padrão 15/01 a 15/04 do ano de `data`". Deve ser
    usada por qualquer trecho que precise decidir custo de safra/entressafra
    ou a janela de bloqueio de movimentação.

    Retorna uma tupla (na_safra: bool, data_inicio: date, data_fim: date).
    """
    safra = session.query(SafraUnidade).filter(
        SafraUnidade.cenario_id == cenario_id,
        SafraUnidade.entidade_tipo == entidade_tipo,
        SafraUnidade.entidade_id == entidade_id
    ).first()
    return _janela_safra_de_registro(safra, data)


def _carregar_safras_por_armazem(session: Session, cenario_id):
    """
    Pré-carrega, em uma única query, todos os registros de SafraUnidade de
    armazéns do cenário, indexados por armazem_id. Cobre só
    entidade_tipo='Armazém' porque é o único tipo consultado dentro de
    `otimizar_dia`.
    """
    rows = session.query(SafraUnidade).filter(
        SafraUnidade.cenario_id == cenario_id,
        SafraUnidade.entidade_tipo == 'Armazém',
    ).all()
    return {r.entidade_id: r for r in rows}

def otimizar_dia(session: Session, data, estoques_atuais, estrategia='Econômico', cenario_id=None,
                  fabricas=None, armazens=None, rotas=None, safra_cache=None):
    """
    Otimiza a movimentação de soja para um dia específico.

    `fabricas`/`armazens`/`rotas`/`safra_cache` podem ser pré-carregados
    pelo chamador (ver `simular_periodo`) para evitar reconsultar o banco a
    cada dia simulado -- são dados estáticos por cenário. Se omitidos
    (None), a função consulta o banco ela mesma, preservando o
    comportamento e a assinatura originais para chamadas diretas/testes.
    """
    solver = pywraplp.Solver.CreateSolver('SCIP')
    if not solver:
        solver = pywraplp.Solver.CreateSolver('GLOP')

    if not solver:
        logger.error("Nenhum solver (SCIP ou GLOP) disponível no OR-Tools.")
        raise RuntimeError("Nenhum solver OR-Tools disponivel (SCIP ou GLOP).")

    if fabricas is None:
        fabricas = session.query(Fabrica).filter(Fabrica.cenario_id == cenario_id).all()
    if armazens is None:
        armazens = session.query(Armazem).filter(Armazem.cenario_id == cenario_id).all()
    if rotas is None:
        rotas = session.query(Rota).filter(Rota.cenario_id == cenario_id).all()

    if not rotas:
        return []

    # Variáveis de decisão
    v_mov = {}
    for r in rotas:
        v_mov[(r.armazem_id, r.fabrica_id)] = solver.NumVar(0, solver.infinity(), f'mov_{r.armazem_id}_{r.fabrica_id}')

    # 1. Capacidade de expedição dos armazéns
    for a in armazens:
        movs_saindo = [v_mov[(a.id, f.id)] for f in fabricas if (a.id, f.id) in v_mov]
        if movs_saindo:
            solver.Add(solver.Sum(movs_saindo) <= a.capacidade_expedicao_diaria)
            solver.Add(solver.Sum(movs_saindo) <= max(0, estoques_atuais.get(f'A_{a.id}', 0)))

    # 2. Capacidade de recebimento das fábricas (LIMITES OPERACIONAIS)
    for f in fabricas:
        movs_entrando = [v_mov[(a.id, f.id)] for a in armazens if (a.id, f.id) in v_mov]
        if not movs_entrando: continue
            
        recebimento_transbordo = solver.Sum(movs_entrando)
        
        # MANTEMOS: Limites físicos de descarga (Moega / Caminhões)
        solver.Add(recebimento_transbordo <= f.capacidade_recebimento_diaria)
        solver.Add(recebimento_transbordo <= f.limite_caminhoes * f.carga_media_caminhao)
        
        # REMOVIDO: Restrição de Capacidade Estática. 
        # O cliente deseja que a soja seja enviada para o local mais próximo mesmo que estoure a capacidade,
        # para evidenciar a necessidade de novos silos (Excedente).
        # espaco_disponivel = max(0, f.capacidade_estatica - estoques_atuais.get(f'F_{f.id}', 0) + f.capacidade_esmagamento_diaria)
        # solver.Add(recebimento_transbordo <= espaco_disponivel)

    # Variáveis para atendimento de demanda (slack variables)
    v_atendimento = {}
    for f in fabricas:
        demanda = max(0, f.capacidade_esmagamento_diaria - max(0, estoques_atuais.get(f'F_{f.id}', 0)))
        if demanda > 0:
            v_atendimento[f.id] = solver.NumVar(0, demanda, f'atend_{f.id}')
            movs_entrando = [v_mov[(a.id, f.id)] for a in armazens if (a.id, f.id) in v_mov]
            if movs_entrando:
                solver.Add(solver.Sum(movs_entrando) >= v_atendimento[f.id])

    # Pesos da Estratégia
    p_atendimento = 10000000 # Prioridade absoluta: não deixar a fábrica parar
    recompensa_base = 10000
    if estrategia == 'Econômico':
        recompensa_base = 100 # Reduzimos a recompensa base para o frete mandar na escolha do destino
    elif estrategia == 'Expedição':
        recompensa_base = 50000 # Força a saída do armazém a qualquer custo
    elif estrategia == 'Segurança':
        p_atendimento = 50000000

    objetivo = solver.Objective()
    for f_id, var in v_atendimento.items():
        objetivo.SetCoefficient(var, p_atendimento)
    
    for r in rotas:
        # Recupera a janela de safra para esta unidade (fonte única de verdade).
        # Usa o cache pré-carregado quando disponível, evitando reconsultar
        # SafraUnidade a cada rota/dia.
        if safra_cache is not None:
            na_safra, d_ini, d_fim = _janela_safra_de_registro(safra_cache.get(r.armazem_id), data)
        else:
            na_safra, d_ini, d_fim = obter_janela_safra(session, 'Armazém', r.armazem_id, data, cenario_id)

        # Bloqueio total ANTES da safra começar (armazéns vazios)
        if data < d_ini:
            solver.Add(v_mov[(r.armazem_id, r.fabrica_id)] == 0)
            continue

        # Define se é safra para custo e incentivo
        custo_ton = r.custo_frete_ton if na_safra else r.custo_frete_entressafra
        
        # Incentivo para movimentar: base + bônus de safra
        # O coeficiente agora é (Incentivo - Custo). Como queremos o mais próximo, 
        # o custo de frete tem peso real na escolha.
        incentivo_movimentar = recompensa_base + (1000 if na_safra else 0)
        
        # Coeficiente = Incentivo - Custo (Maximizar)
        objetivo.SetCoefficient(v_mov[(r.armazem_id, r.fabrica_id)], incentivo_movimentar - custo_ton)
    
    objetivo.SetMaximization()
    status = solver.Solve()

    if status == pywraplp.Solver.OPTIMAL or status == pywraplp.Solver.FEASIBLE:
        resultados = []
        for r in rotas:
            qtd = v_mov[(r.armazem_id, r.fabrica_id)].solution_value()
            if qtd > 0.001:
                # Determina o custo real usado para este dia no log (fonte única de verdade)
                if safra_cache is not None:
                    na_safra_real, _, _ = _janela_safra_de_registro(safra_cache.get(r.armazem_id), data)
                else:
                    na_safra_real, _, _ = obter_janela_safra(session, 'Armazém', r.armazem_id, data, cenario_id)
                custo_ton_real = r.custo_frete_ton if na_safra_real else r.custo_frete_entressafra
                
                resultados.append({
                    'armazem_id': r.armazem_id,
                    'fabrica_id': r.fabrica_id,
                    'quantidade_ton': qtd,
                    'custo_total': qtd * custo_ton_real
                })
        return resultados

    logger.warning(
        "Otimização do dia %s (cenario_id=%s) não encontrou solução ótima/viável (status=%s).",
        data, cenario_id, status
    )
    return None

def simular_periodo(session: Session, data_inicio, data_fim_previsao, cenario_id=None, estrategia='Econômico'):
    c_id = int(cenario_id) if cenario_id is not None else None

    try:
        # REQUISITO: Limpeza Absoluta via ORM para evitar rastro de dados (ghost data)
        # A deleção NÃO é commitada isoladamente: ela faz parte da mesma
        # transação do recálculo e da inserção final. Se algo falhar no meio
        # do caminho, o rollback abaixo desfaz a deleção e os dados antigos
        # permanecem intactos.
        session.query(MovimentacaoDiaria).filter(MovimentacaoDiaria.cenario_id == c_id).delete(synchronize_session=False)
        session.query(ResumoMensalFabrica).filter(ResumoMensalFabrica.cenario_id == c_id).delete(synchronize_session=False)
        session.query(ResumoMensalArmazem).filter(ResumoMensalArmazem.cenario_id == c_id).delete(synchronize_session=False)

        # Ajuste data_inicio para o dia 1 do mês para capturar o volume total.
        data_inicio_ajustada = pd.to_datetime(data_inicio).date().replace(day=1)

        # Carregar estoques iniciais
        fabricas = session.query(Fabrica).filter(Fabrica.cenario_id == c_id).all()
        armazens = session.query(Armazem).filter(Armazem.cenario_id == c_id).all()

        # Pré-carregamento (Fase 3 / performance): fábricas, armazéns, rotas
        # e janelas de safra são estáticos por cenário -- carregados uma
        # única vez aqui em vez de reconsultados a cada dia dentro de
        # otimizar_dia (que antes rodava até 730 vezes).
        rotas = session.query(Rota).filter(Rota.cenario_id == c_id).all()
        safra_cache = _carregar_safras_por_armazem(session, c_id)

        # Previsões mensais também são pré-carregadas por inteiro e
        # indexadas por (entidade_id, mes_referencia): antes eram
        # reconsultadas por fábrica/armazém a cada dia, mesmo o mês só
        # mudando uma vez por mês.
        fabrica_ids = [f.id for f in fabricas]
        armazem_ids = [a.id for a in armazens]
        previsoes_fab = {
            (p.fabrica_id, p.mes_referencia): p
            for p in session.query(PrevisaoFabrica).filter(PrevisaoFabrica.fabrica_id.in_(fabrica_ids)).all()
        }
        previsoes_arm = {
            (p.armazem_id, p.mes_referencia): p
            for p in session.query(PrevisaoArmazem).filter(PrevisaoArmazem.armazem_id.in_(armazem_ids)).all()
        }

        estoques_atuais = {}
        for f in fabricas: estoques_atuais[f'F_{f.id}'] = f.estoque_inicial
        for a in armazens: estoques_atuais[f'A_{a.id}'] = a.estoque_inicial

        data_atual = data_inicio_ajustada
        d_fim_p = pd.to_datetime(data_fim_previsao).date()

        resumos_fab = {}
        resumos_arm = {}
        dias_executados = 0
        max_dias = 730

        while True:
            mes_str = data_atual.strftime('%Y-%m')

            if mes_str not in resumos_fab:
                resumos_fab[mes_str] = {f.id: {'rec_produtor': 0, 'rec_transbordo': 0, 'esmagado': 0, 'cap_estatica': f.capacidade_estatica} for f in fabricas}
            if mes_str not in resumos_arm:
                resumos_arm[mes_str] = {a.id: {'rec_produtor': 0, 'envio_transbordo': 0, 'vendas': 0, 'cap_estatica': a.capacidade_estatica} for a in armazens}

            mes_atual_date = datetime.date(data_atual.year, data_atual.month, 1)
            dias_no_mes = pd.Period(data_atual.strftime('%Y-%m-%d')).days_in_month

            # 1. Processar Previsões
            for f in fabricas:
                prev = previsoes_fab.get((f.id, mes_atual_date))
                if prev:
                    rec_diario = (prev.recebimento_produtor or 0) / dias_no_mes
                    vend_diario = (prev.vendas or 0) / dias_no_mes
                    estoques_atuais[f'F_{f.id}'] += (rec_diario - vend_diario)
                    resumos_fab[mes_str][f.id]['rec_produtor'] += rec_diario

            for a in armazens:
                prev = previsoes_arm.get((a.id, mes_atual_date))
                if prev:
                    rec_diario = (prev.recebimento_produtor or 0) / dias_no_mes
                    vend_diario = (prev.vendas or 0) / dias_no_mes
                    estoques_atuais[f'A_{a.id}'] += (rec_diario - vend_diario)
                    resumos_arm[mes_str][a.id]['rec_produtor'] += rec_diario
                    resumos_arm[mes_str][a.id]['vendas'] += vend_diario

            # 2. Otimizar transbordo
            movimentacoes = otimizar_dia(
                session, data_atual, estoques_atuais, estrategia=estrategia, cenario_id=c_id,
                fabricas=fabricas, armazens=armazens, rotas=rotas, safra_cache=safra_cache,
            )

            if movimentacoes:
                for mov in movimentacoes:
                    session.add(MovimentacaoDiaria(
                        cenario_id=c_id,
                        data=data_atual,
                        armazem_id=mov['armazem_id'],
                        fabrica_id=mov['fabrica_id'],
                        quantidade_ton=mov['quantidade_ton'],
                        custo_total=mov['custo_total']
                    ))
                    estoques_atuais[f'A_{mov["armazem_id"]}'] -= mov['quantidade_ton']
                    estoques_atuais[f'F_{mov["fabrica_id"]}'] += mov['quantidade_ton']
                    resumos_arm[mes_str][mov['armazem_id']]['envio_transbordo'] += mov['quantidade_ton']
                    resumos_fab[mes_str][mov['fabrica_id']]['rec_transbordo'] += mov['quantidade_ton']

            # 3. Processar consumo diário (esmagamento)
            for f in fabricas:
                esmagado_real = min(max(0, estoques_atuais[f'F_{f.id}']), f.capacidade_esmagamento_diaria)
                estoques_atuais[f'F_{f.id}'] -= esmagado_real
                resumos_fab[mes_str][f.id]['esmagado'] += esmagado_real

            # 4. Verificar Condição de Parada
            total_estoque_arm = sum(max(0, estoques_atuais[f'A_{a.id}']) for a in armazens)
            acabaram_previsoes = data_atual >= d_fim_p
            armazens_vazios = total_estoque_arm < 1.0

            eh_ultimo_dia_simulacao = (acabaram_previsoes and armazens_vazios) or dias_executados >= max_dias
            eh_ultimo_dia_mes = (data_atual + datetime.timedelta(days=1)).month != data_atual.month

            if eh_ultimo_dia_mes or eh_ultimo_dia_simulacao:
                for f in fabricas:
                    resumos_fab[mes_str][f.id]['saldo_estoque'] = estoques_atuais[f'F_{f.id}']
                    resumos_fab[mes_str][f.id]['excedente'] = max(0, estoques_atuais[f'F_{f.id}'] - resumos_fab[mes_str][f.id]['cap_estatica'])
                for a in armazens:
                    resumos_arm[mes_str][a.id]['saldo_estoque'] = estoques_atuais[f'A_{a.id}']
                    resumos_arm[mes_str][a.id]['excedente'] = max(0, estoques_atuais[f'A_{a.id}'] - resumos_arm[mes_str][a.id]['cap_estatica'])

            if eh_ultimo_dia_simulacao:
                break

            data_atual += datetime.timedelta(days=1)
            dias_executados += 1

        # Salvar Resumos Mensais
        for mes, fab_dict in resumos_fab.items():
            for f_id, dados in fab_dict.items():
                session.add(ResumoMensalFabrica(
                    cenario_id=c_id, mes=mes, fabrica_id=f_id,
                    rec_produtor=dados['rec_produtor'], rec_transbordo=dados['rec_transbordo'],
                    esmagado=dados['esmagado'], saldo_estoque=dados.get('saldo_estoque', 0),
                    capacidade_estatica=dados['cap_estatica'], excedente=dados.get('excedente', 0)
                ))

        for mes, arm_dict in resumos_arm.items():
            for a_id, dados in arm_dict.items():
                session.add(ResumoMensalArmazem(
                    cenario_id=c_id, mes=mes, armazem_id=a_id,
                    rec_produtor=dados['rec_produtor'], envio_transbordo=dados['envio_transbordo'],
                    vendas=dados['vendas'], saldo_estoque=dados.get('saldo_estoque', 0),
                    capacidade_estatica=dados['cap_estatica'], excedente=dados.get('excedente', 0)
                ))

        session.commit()
    except Exception:
        # Garante atomicidade: se qualquer etapa falhar (deleção, recálculo
        # dia-a-dia ou inserção dos resumos), desfazemos toda a transação
        # para não deixar o cenário com dados apagados e não substituídos.
        session.rollback()
        raise

def obter_range_previsoes(session: Session, cenario_id=None):
    min_f = session.query(func.min(PrevisaoFabrica.mes_referencia)).join(Fabrica).filter(Fabrica.cenario_id == cenario_id).scalar()
    max_f = session.query(func.max(PrevisaoFabrica.mes_referencia)).join(Fabrica).filter(Fabrica.cenario_id == cenario_id).scalar()
    min_a = session.query(func.min(PrevisaoArmazem.mes_referencia)).join(Armazem).filter(Armazem.cenario_id == cenario_id).scalar()
    max_a = session.query(func.max(PrevisaoArmazem.mes_referencia)).join(Armazem).filter(Armazem.cenario_id == cenario_id).scalar()
    
    dates = [d for d in [min_f, max_f, min_a, max_a] if d is not None]
    if not dates:
        return None, None
        
    start_date = min(dates)
    end_date_start_month = max(dates)
    end_date = (pd.Timestamp(end_date_start_month) + pd.offsets.MonthEnd(0)).date()
    
    return start_date, end_date
