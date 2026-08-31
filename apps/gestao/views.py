from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

import django_tables2 as tables2

from apps.core import permissions
from apps.core.models import Cooperativa, User
from apps.core.permissions import requer_admin_vector
from apps.gestao.filters import CooperativaFilter, UsuarioFilter
from apps.gestao.forms import CooperativaForm, MinhaCooperativaForm, UsuarioForm
from apps.gestao.tables import CooperativaTable, UsuarioTable


@login_required
@requer_admin_vector
def cooperativas(request):
    f = CooperativaFilter(request.GET, queryset=Cooperativa.objects.all().order_by('nome'))
    tabela = CooperativaTable(f.qs)
    tables2.RequestConfig(request, paginate={'per_page': 25}).configure(tabela)
    ctx = {'tabela': tabela, 'filtro': f}
    template = 'gestao/_cooperativas_content.html' if request.htmx else 'gestao/cooperativas.html'
    return render(request, template, ctx)


@login_required
@requer_admin_vector
def cooperativa_nova(request):
    form = CooperativaForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('gestao:cooperativas')
    return render(request, 'gestao/cooperativa_form.html', {'form': form, 'titulo': 'Nova organização'})


@login_required
@requer_admin_vector
def cooperativa_editar(request, cooperativa_id):
    obj = get_object_or_404(Cooperativa, id=cooperativa_id)
    form = CooperativaForm(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('gestao:cooperativas')
    return render(request, 'gestao/cooperativa_form.html', {'form': form, 'titulo': obj.nome})


def usuarios_visiveis(gestor):
    if permissions.e_admin_vector(gestor):
        return User.objects.all().order_by('username')
    return User.objects.filter(
        cooperativa=gestor.cooperativa,
        papel__in=(User.PAPEL_USUARIO_FABRICA, User.PAPEL_USUARIO_ARMAZEM),
    ).order_by('username')


def _requer_gestor(request):
    if not permissions.pode_gerir_usuarios(request.user):
        raise PermissionDenied


def email_configurado():
    return settings.EMAIL_BACKEND not in (
        'django.core.mail.backends.console.EmailBackend',
        'django.core.mail.backends.dummy.EmailBackend',
    )


@login_required
def usuarios(request):
    _requer_gestor(request)
    f = UsuarioFilter(request.GET, queryset=usuarios_visiveis(request.user))
    tabela = UsuarioTable(f.qs)
    tables2.RequestConfig(request, paginate={'per_page': 25}).configure(tabela)
    ctx = {'tabela': tabela, 'filtro': f}
    template = 'gestao/_usuarios_content.html' if request.htmx else 'gestao/usuarios.html'
    return render(request, template, ctx)


@login_required
def usuario_novo(request):
    _requer_gestor(request)
    form = UsuarioForm(request.POST or None, gestor=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('gestao:usuarios')
    return render(request, 'gestao/usuario_form.html', {'form': form, 'titulo': 'Novo usuário'})


@login_required
def usuario_editar(request, usuario_id):
    _requer_gestor(request)
    obj = get_object_or_404(usuarios_visiveis(request.user), id=usuario_id)
    form = UsuarioForm(request.POST or None, gestor=request.user, instance=obj)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('gestao:usuarios')
    return render(request, 'gestao/usuario_form.html', {
        'form': form, 'titulo': obj.username, 'pode_enviar_link': email_configurado(),
    })


@login_required
@require_POST
def usuario_enviar_link(request, usuario_id):
    _requer_gestor(request)
    if not email_configurado():
        raise Http404
    alvo = get_object_or_404(usuarios_visiveis(request.user), id=usuario_id)
    from allauth.account.forms import ResetPasswordForm
    form = ResetPasswordForm({'email': alvo.email})
    if form.is_valid():
        form.save(request)
        messages.success(request, f'Link de definição de senha enviado para {alvo.email}.')
    return redirect('gestao:usuario_editar', usuario_id=alvo.id)


@login_required
def minha_cooperativa(request):
    if not permissions.e_admin_cooperativa(request.user):
        raise PermissionDenied
    obj = request.user.cooperativa
    form = MinhaCooperativaForm(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('gestao:minha_cooperativa')
    return render(request, 'gestao/minha_cooperativa.html', {'form': form, 'cooperativa': obj})


@login_required
def conta(request):
    return render(request, 'gestao/conta.html')
