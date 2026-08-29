from apps.core import permissions


def menu(request):
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated:
        return {}
    return {
        'menu_admin_vector': permissions.e_admin_vector(user),
        'menu_admin_cooperativa': permissions.e_admin_cooperativa(user),
        'menu_gerir_usuarios': permissions.pode_gerir_usuarios(user),
        'menu_membro_cooperativa': permissions.papel_de(user) in permissions.MEMBROS_COOPERATIVA,
    }
