"""Autorização por papel — funções puras + decorators finos (spec Fase 7 §4,
ADR 0009). Sem Django Groups, sem django-guardian. Os decorators assumem que
`@login_required` rodou antes (usuário anônimo já foi redirecionado)."""
from functools import wraps

from django.core.exceptions import PermissionDenied

from apps.core.models import User

MEMBROS_COOPERATIVA = (
    User.PAPEL_ADMIN_COOPERATIVA,
    User.PAPEL_USUARIO_FABRICA,
    User.PAPEL_USUARIO_ARMAZEM,
)


def papel_de(user):
    return getattr(user, 'papel', '') or ''


def e_admin_vector(user):
    return papel_de(user) == User.PAPEL_ADMIN_VECTOR


def e_admin_cooperativa(user):
    return papel_de(user) == User.PAPEL_ADMIN_COOPERATIVA


def e_usuario_fabrica(user):
    return papel_de(user) == User.PAPEL_USUARIO_FABRICA


def e_usuario_armazem(user):
    return papel_de(user) == User.PAPEL_USUARIO_ARMAZEM


def pode_gerir_usuarios(user):
    return e_admin_vector(user) or e_admin_cooperativa(user)


def pode_editar_fabricas(user, request=None):
    if e_admin_cooperativa(user) or e_usuario_fabrica(user):
        return True
    return bool(e_admin_vector(user) and _org_do_request(request))


def pode_editar_armazens(user, request=None):
    if e_admin_cooperativa(user) or e_usuario_armazem(user):
        return True
    return bool(e_admin_vector(user) and _org_do_request(request))


def _org_do_request(request):
    if request is None:
        return None
    from apps.core.tenancy import obter_organizacao_corrente
    return obter_organizacao_corrente(request)


def papel_required(*papeis):
    def decorator(view):
        @wraps(view)
        def _wrapped(request, *args, **kwargs):
            if papel_de(request.user) not in papeis:
                raise PermissionDenied
            return view(request, *args, **kwargs)
        return _wrapped
    return decorator


def _predicado_required(predicado):
    def decorator(view):
        @wraps(view)
        def _wrapped(request, *args, **kwargs):
            if not predicado(request.user, request):
                raise PermissionDenied
            return view(request, *args, **kwargs)
        return _wrapped
    return decorator


def requer_membro_organizacao(view):
    @wraps(view)
    def _wrapped(request, *args, **kwargs):
        user = request.user
        if papel_de(user) in MEMBROS_COOPERATIVA:
            return view(request, *args, **kwargs)
        if e_admin_vector(user) and _org_do_request(request) is not None:
            return view(request, *args, **kwargs)
        raise PermissionDenied('Selecione uma organização.')
    return _wrapped


requer_edicao_fabricas = _predicado_required(pode_editar_fabricas)
requer_edicao_armazens = _predicado_required(pode_editar_armazens)
requer_admin_vector = _predicado_required(lambda user, request=None: e_admin_vector(user))
