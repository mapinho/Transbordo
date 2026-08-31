import django_tables2 as tables

from apps.core.models import Cooperativa, User


class CooperativaTable(tables.Table):
    nome = tables.Column(
        linkify=("gestao:cooperativa_editar", {"cooperativa_id": tables.A("pk")}),
    )

    class Meta:
        model = Cooperativa
        fields = ("nome", "slug", "ativo")
        attrs = {"class": "table table-sm"}
        template_name = "django_tables2/tailwind.html"
        empty_text = "Nenhuma organização."


class UsuarioTable(tables.Table):
    username = tables.Column(
        linkify=("gestao:usuario_editar", {"usuario_id": tables.A("pk")}),
    )

    class Meta:
        model = User
        fields = ("username", "email", "papel", "cooperativa", "is_active")
        attrs = {"class": "table table-sm"}
        template_name = "django_tables2/tailwind.html"
        empty_text = "Nenhum usuário."
