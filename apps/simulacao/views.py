from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from apps.simulacao import services
from apps.simulacao.models import Cenario


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
