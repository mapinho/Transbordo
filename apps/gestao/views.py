from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from apps.core.models import Cooperativa
from apps.core.permissions import requer_admin_vector
from apps.gestao.forms import CooperativaForm


@login_required
@requer_admin_vector
def cooperativas(request):
    itens = Cooperativa.objects.all().order_by('nome')
    template = 'gestao/_cooperativas_content.html' if request.htmx else 'gestao/cooperativas.html'
    return render(request, template, {'cooperativas': itens})


@login_required
@requer_admin_vector
def cooperativa_nova(request):
    form = CooperativaForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('gestao:cooperativas')
    return render(request, 'gestao/cooperativa_form.html', {'form': form, 'titulo': 'Nova cooperativa'})


@login_required
@requer_admin_vector
def cooperativa_editar(request, cooperativa_id):
    obj = get_object_or_404(Cooperativa, id=cooperativa_id)
    form = CooperativaForm(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('gestao:cooperativas')
    return render(request, 'gestao/cooperativa_form.html', {'form': form, 'titulo': obj.nome})


@login_required
def conta(request):
    return render(request, 'gestao/conta.html')
