"""Escopo de tenant (cooperativa) para queries automaticamente isoladas.

Ver docs/decisions/0003-tenant-isolation-fail-closed.md: sem cooperativa
corrente definida, o manager escopado retorna queryset vazio (falha
fechada) em vez de vazar dados de todas as cooperativas.
"""
from contextvars import ContextVar

from django.db import models

_cooperativa_atual = ContextVar('cooperativa_atual', default=None)


def definir_cooperativa_atual(cooperativa_id):
    return _cooperativa_atual.set(cooperativa_id)


def obter_cooperativa_atual():
    return _cooperativa_atual.get()


def resetar_cooperativa_atual(token):
    _cooperativa_atual.reset(token)


def obter_organizacao_corrente(request):
    """id da organização na qual o request opera, ou None.

    Membro de organização -> a própria cooperativa. Admin Vector -> a
    seleção guardada em session['org_corrente_id'] (validada contra
    Cooperativa ativa; id inválido é descartado). Anônimo -> None.
    """
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated:
        return None
    if getattr(user, 'cooperativa_id', None):
        return user.cooperativa_id
    from apps.core.permissions import e_admin_vector
    if not e_admin_vector(user):
        return None
    session = getattr(request, 'session', None)
    org_id = session.get('org_corrente_id') if session is not None else None
    if not org_id:
        return None
    from apps.core.models import Cooperativa
    if Cooperativa.objects.filter(id=org_id, ativo=True).exists():
        return org_id
    if session is not None:
        session.pop('org_corrente_id', None)
    return None


def cooperativa_id_do_request(request):
    """Como obter_organizacao_corrente, mas exige uma organização definida."""
    from django.core.exceptions import PermissionDenied
    org_id = obter_organizacao_corrente(request)
    if org_id is None:
        raise PermissionDenied('Selecione uma organização.')
    return org_id


class TenantManager(models.Manager):
    """Escopa automaticamente pela cooperativa corrente (contextvar).

    Sem cooperativa corrente definida, retorna queryset vazio — nunca
    todos os registros de todas as cooperativas.
    """

    def get_queryset(self):
        cooperativa_id = obter_cooperativa_atual()
        qs = super().get_queryset()
        if cooperativa_id is None:
            return qs.none()
        return qs.filter(cooperativa_id=cooperativa_id)


class CooperativaScopedModel(models.Model):
    """Base abstrata para models pertencentes a uma cooperativa.

    `objects` é escopado (TenantManager); `all_cooperativas` é a via de
    escape explícita para consultas cross-tenant deliberadas (ex.: Admin
    Vector). Nunca usar `all_cooperativas` a partir de uma view comum.
    """

    cooperativa = models.ForeignKey(
        'core.Cooperativa', on_delete=models.PROTECT, related_name='%(app_label)s_%(class)ss'
    )

    objects = TenantManager()
    all_cooperativas = models.Manager()

    class Meta:
        abstract = True
