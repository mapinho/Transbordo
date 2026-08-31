from apps.core import permissions
from apps.core.models import Cooperativa
from apps.core.tenancy import obter_organizacao_corrente


def menu(request):
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated:
        return {}
    org_id = obter_organizacao_corrente(request)
    org = Cooperativa.objects.filter(id=org_id).first() if org_id else None
    e_membro = permissions.papel_de(user) in permissions.MEMBROS_COOPERATIVA
    organizacoes_disponiveis = (
        Cooperativa.objects.filter(ativo=True).order_by('nome')
        if permissions.e_admin_vector(user) else None
    )
    return {
        'menu_admin_vector': permissions.e_admin_vector(user),
        'menu_admin_cooperativa': permissions.e_admin_cooperativa(user),
        'menu_gerir_usuarios': permissions.pode_gerir_usuarios(user),
        'menu_membro_cooperativa': e_membro,
        'org': org,
        'organizacoes_disponiveis': organizacoes_disponiveis,
        'mostra_modulos': e_membro or (permissions.e_admin_vector(user) and org is not None),
    }
