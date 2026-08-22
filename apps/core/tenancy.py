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

    cooperativa = models.ForeignKey('core.Cooperativa', on_delete=models.PROTECT)

    objects = TenantManager()
    all_cooperativas = models.Manager()

    class Meta:
        abstract = True
