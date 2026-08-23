import datetime
import json

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render

from apps.simulacao import services
from apps.simulacao.columns import (
    ARMAZEM_COLUMNS,
    FABRICA_COLUMNS,
    PREVISAO_ARMAZEM_COLUMNS,
    PREVISAO_FABRICA_COLUMNS,
    ROTA_COLUMNS,
    SAFRA_COLUMNS,
)
from apps.simulacao.models import (
    Armazem,
    Cenario,
    Fabrica,
    PrevisaoArmazem,
    PrevisaoFabrica,
    Rota,
    SafraUnidade,
)


@login_required
def cenarios_list(request):
    cooperativa_id = request.user.cooperativa_id

    if request.method == 'POST':
        nome = request.POST.get('nome', '').strip()
        origem_id = request.POST.get('origem_id')
        if nome and origem_id:
            services.clone_scenario(cooperativa_id, nome, int(origem_id))
        return redirect('simulacao:cenarios_list')

    cenarios = services.list_scenarios(cooperativa_id)
    context = {'cenarios': cenarios}
    template = 'simulacao/_cenarios_content.html' if request.htmx else 'simulacao/cenarios.html'
    return render(request, template, context)


@login_required
def fabricas_grid(request, cenario_id):
    cenario = get_object_or_404(Cenario, id=cenario_id)

    if request.method == 'POST':
        linhas = json.loads(request.POST.get('linhas_json', '[]'))
        try:
            _salvar_fabricas(cenario, linhas)
        except (ValueError, TypeError, Fabrica.DoesNotExist) as exc:
            return HttpResponseBadRequest(f"Erro ao salvar fábricas: {exc}")

    fabricas = list(Fabrica.objects.filter(cenario_id=cenario.id).order_by('nome'))
    rows = [
        {
            "id": f.id, "nome": f.nome,
            "capacidade_estatica": f.capacidade_estatica,
            "capacidade_esmagamento_diaria": f.capacidade_esmagamento_diaria,
            "capacidade_recebimento_diaria": f.capacidade_recebimento_diaria,
            "limite_caminhoes": f.limite_caminhoes,
            "carga_media_caminhao": f.carga_media_caminhao,
            "estoque_inicial": f.estoque_inicial,
        }
        for f in fabricas
    ]
    context = {"cenario": cenario, "active": "fabricas", "columns": FABRICA_COLUMNS, "rows": rows}
    template = 'simulacao/_fabricas_content.html' if request.htmx else 'simulacao/fabricas.html'
    return render(request, template, context)


def _salvar_fabricas(cenario, linhas):
    with transaction.atomic():
        for linha in linhas:
            fabrica_id = linha.get('id')
            if not fabrica_id:
                continue
            fabrica = Fabrica.objects.get(id=fabrica_id, cenario_id=cenario.id)
            fabrica.capacidade_estatica = float(linha['capacidade_estatica'])
            fabrica.capacidade_esmagamento_diaria = float(linha['capacidade_esmagamento_diaria'])
            fabrica.capacidade_recebimento_diaria = float(linha['capacidade_recebimento_diaria'])
            fabrica.limite_caminhoes = int(linha['limite_caminhoes'])
            fabrica.carga_media_caminhao = float(linha['carga_media_caminhao'])
            fabrica.estoque_inicial = float(linha['estoque_inicial'])
            fabrica.full_clean()
            fabrica.save()


@login_required
def armazens_grid(request, cenario_id):
    cenario = get_object_or_404(Cenario, id=cenario_id)

    if request.method == 'POST':
        linhas = json.loads(request.POST.get('linhas_json', '[]'))
        try:
            _salvar_armazens(cenario, linhas)
        except (ValueError, TypeError, Armazem.DoesNotExist) as exc:
            return HttpResponseBadRequest(f"Erro ao salvar armazéns: {exc}")

    armazens = list(Armazem.objects.filter(cenario_id=cenario.id).order_by('nome'))
    rows = [
        {
            "id": a.id, "nome": a.nome,
            "capacidade_estatica": a.capacidade_estatica,
            "capacidade_expedicao_diaria": a.capacidade_expedicao_diaria,
            "estoque_inicial": a.estoque_inicial,
        }
        for a in armazens
    ]
    context = {"cenario": cenario, "active": "armazens", "columns": ARMAZEM_COLUMNS, "rows": rows}
    template = 'simulacao/_armazens_content.html' if request.htmx else 'simulacao/armazens.html'
    return render(request, template, context)


def _salvar_armazens(cenario, linhas):
    with transaction.atomic():
        for linha in linhas:
            armazem_id = linha.get('id')
            if armazem_id:
                armazem = Armazem.objects.get(id=armazem_id, cenario_id=cenario.id)
            else:
                if not linha.get('nome'):
                    continue
                armazem = Armazem(cooperativa_id=cenario.cooperativa_id, cenario_id=cenario.id)
            armazem.nome = linha['nome']
            armazem.capacidade_estatica = float(linha['capacidade_estatica'])
            armazem.capacidade_expedicao_diaria = float(linha['capacidade_expedicao_diaria'])
            armazem.estoque_inicial = float(linha.get('estoque_inicial') or 0)
            armazem.full_clean()
            armazem.save()


@login_required
def rotas_grid(request, cenario_id):
    cenario = get_object_or_404(Cenario, id=cenario_id)

    if request.method == 'POST':
        linhas = json.loads(request.POST.get('linhas_json', '[]'))
        try:
            _salvar_rotas(cenario, linhas)
        except (ValueError, TypeError, Rota.DoesNotExist) as exc:
            return HttpResponseBadRequest(f"Erro ao salvar rotas: {exc}")

    rotas = list(Rota.objects.filter(cenario_id=cenario.id).select_related('armazem', 'fabrica'))
    rows = [
        {
            "id": r.id, "origem": r.armazem.nome, "destino": r.fabrica.nome,
            "distancia_km": r.distancia_km,
            "custo_frete_ton": r.custo_frete_ton,
            "custo_frete_entressafra": r.custo_frete_entressafra,
        }
        for r in rotas
    ]
    context = {"cenario": cenario, "active": "rotas", "columns": ROTA_COLUMNS, "rows": rows}
    template = 'simulacao/_rotas_content.html' if request.htmx else 'simulacao/rotas.html'
    return render(request, template, context)


def _salvar_rotas(cenario, linhas):
    with transaction.atomic():
        for linha in linhas:
            rota_id = linha.get('id')
            if not rota_id:
                continue
            rota = Rota.objects.get(id=rota_id, cenario_id=cenario.id)
            rota.distancia_km = float(linha['distancia_km'])
            rota.custo_frete_ton = float(linha['custo_frete_ton'])
            rota.custo_frete_entressafra = float(linha['custo_frete_entressafra'])
            rota.full_clean()
            rota.save()


@login_required
def previsoes_grid(request, cenario_id):
    cenario = get_object_or_404(Cenario, id=cenario_id)

    if request.method == 'POST':
        linhas_fabrica = json.loads(request.POST.get('linhas_fabrica_json', '[]'))
        linhas_armazem = json.loads(request.POST.get('linhas_armazem_json', '[]'))
        try:
            _salvar_previsoes(cenario, linhas_fabrica, linhas_armazem)
        except (ValueError, TypeError, PrevisaoFabrica.DoesNotExist, PrevisaoArmazem.DoesNotExist) as exc:
            return HttpResponseBadRequest(f"Erro ao salvar previsões: {exc}")

    previsoes_fab = list(
        PrevisaoFabrica.objects.filter(fabrica__cenario_id=cenario.id).select_related('fabrica')
    )
    previsoes_arm = list(
        PrevisaoArmazem.objects.filter(armazem__cenario_id=cenario.id).select_related('armazem')
    )
    rows_fabrica = [
        {
            "id": p.id, "fabrica": p.fabrica.nome, "mes_referencia": p.mes_referencia.strftime('%Y-%m'),
            "recebimento_produtor": p.recebimento_produtor, "vendas": p.vendas,
        }
        for p in previsoes_fab
    ]
    rows_armazem = [
        {
            "id": p.id, "armazem": p.armazem.nome, "mes_referencia": p.mes_referencia.strftime('%Y-%m'),
            "recebimento_produtor": p.recebimento_produtor, "vendas": p.vendas,
        }
        for p in previsoes_arm
    ]
    context = {
        "cenario": cenario, "active": "previsoes",
        "columns_fabrica": PREVISAO_FABRICA_COLUMNS, "rows_fabrica": rows_fabrica,
        "columns_armazem": PREVISAO_ARMAZEM_COLUMNS, "rows_armazem": rows_armazem,
    }
    template = 'simulacao/_previsoes_content.html' if request.htmx else 'simulacao/previsoes.html'
    return render(request, template, context)


def _salvar_previsoes(cenario, linhas_fabrica, linhas_armazem):
    with transaction.atomic():
        for linha in linhas_fabrica:
            previsao_id = linha.get('id')
            if not previsao_id:
                continue
            previsao = PrevisaoFabrica.objects.get(id=previsao_id, fabrica__cenario_id=cenario.id)
            previsao.recebimento_produtor = float(linha['recebimento_produtor'])
            previsao.vendas = float(linha['vendas'])
            previsao.full_clean()
            previsao.save()
        for linha in linhas_armazem:
            previsao_id = linha.get('id')
            if not previsao_id:
                continue
            previsao = PrevisaoArmazem.objects.get(id=previsao_id, armazem__cenario_id=cenario.id)
            previsao.recebimento_produtor = float(linha['recebimento_produtor'])
            previsao.vendas = float(linha['vendas'])
            previsao.full_clean()
            previsao.save()


@login_required
def safras_grid(request, cenario_id):
    cenario = get_object_or_404(Cenario, id=cenario_id)

    if request.method == 'POST':
        linhas = json.loads(request.POST.get('linhas_json', '[]'))
        try:
            _salvar_safras(cenario, linhas)
        except (ValueError, TypeError, SafraUnidade.DoesNotExist) as exc:
            return HttpResponseBadRequest(f"Erro ao salvar datas de safra: {exc}")

    safras = list(SafraUnidade.objects.filter(cenario_id=cenario.id))
    armazem_ids = {s.entidade_id for s in safras if s.entidade_tipo == 'Armazém'}
    fabrica_ids = {s.entidade_id for s in safras if s.entidade_tipo != 'Armazém'}
    armazens_map = {a.id: a.nome for a in Armazem.objects.filter(id__in=armazem_ids)} if armazem_ids else {}
    fabricas_map = {f.id: f.nome for f in Fabrica.objects.filter(id__in=fabrica_ids)} if fabrica_ids else {}

    rows = []
    for s in safras:
        if s.entidade_tipo == 'Armazém':
            unidade_nome = armazens_map.get(s.entidade_id, 'N/A')
        else:
            unidade_nome = fabricas_map.get(s.entidade_id, 'N/A')
        rows.append({
            "id": s.id, "tipo": s.entidade_tipo, "unidade": unidade_nome,
            "data_inicio": s.data_inicio.strftime('%Y-%m-%d'),
            "data_fim": s.data_fim.strftime('%Y-%m-%d'),
        })

    context = {"cenario": cenario, "active": "safras", "columns": SAFRA_COLUMNS, "rows": rows}
    template = 'simulacao/_safras_content.html' if request.htmx else 'simulacao/safras.html'
    return render(request, template, context)


def _salvar_safras(cenario, linhas):
    with transaction.atomic():
        for linha in linhas:
            safra_id = linha.get('id')
            if not safra_id:
                continue
            safra = SafraUnidade.objects.get(id=safra_id, cenario_id=cenario.id)
            safra.data_inicio = datetime.date.fromisoformat(linha['data_inicio'])
            safra.data_fim = datetime.date.fromisoformat(linha['data_fim'])
            safra.full_clean()
            safra.save()
