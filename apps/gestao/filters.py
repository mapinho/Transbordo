import django_filters
from django.db.models import Q

from apps.core.models import Cooperativa, User


class CooperativaFilter(django_filters.FilterSet):
    nome = django_filters.CharFilter(lookup_expr="icontains", label="Nome")

    class Meta:
        model = Cooperativa
        fields = ["nome", "ativo"]


class UsuarioFilter(django_filters.FilterSet):
    q = django_filters.CharFilter(method="busca", label="Busca")

    def busca(self, queryset, name, value):
        return queryset.filter(
            Q(username__icontains=value) | Q(email__icontains=value)
        )

    class Meta:
        model = User
        fields = ["papel"]
