import json

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render

from apps.simulacao import services
from apps.simulacao.columns import ARMAZEM_COLUMNS, FABRICA_COLUMNS
from apps.simulacao.models import Armazem, Cenario, Fabrica


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
