from django.contrib import admin

from apps.simulacao.models import Armazem, Cenario, Fabrica, Rota, MovimentacaoDiaria, PrevisaoArmazem, PrevisaoFabrica, SafraUnidade, LogExecucao, ResumoMensalArmazem, ResumoMensalFabrica


class AllCooperativasAdminMixin:
    """Faz o admin usar `Model.all_cooperativas` (manager sem escopo) em vez
    do `get_queryset()` padrão do ModelAdmin, que passa por
    `Model._default_manager` -- ou seja, `objects`, o `TenantManager`
    fail-closed (ver apps.core.tenancy). Sem este mixin, um usuário Admin
    Vector (`cooperativa=None`) veria toda página do admin vazia, porque o
    TenantManager retorna queryset vazio quando não há cooperativa corrente
    no contexto -- exatamente o caso de um usuário que enxerga todas as
    cooperativas."""

    def get_queryset(self, request):
        return self.model.all_cooperativas.get_queryset()


@admin.register(Cenario)
class CenarioAdmin(AllCooperativasAdminMixin, admin.ModelAdmin):
    list_display = ('nome', 'cooperativa', 'is_oficial', 'data_criacao')
    list_filter = ('cooperativa', 'is_oficial')


@admin.register(Fabrica)
class FabricaAdmin(AllCooperativasAdminMixin, admin.ModelAdmin):
    list_display = ('nome', 'cenario', 'cooperativa')
    list_filter = ('cooperativa', 'cenario')


@admin.register(Armazem)
class ArmazemAdmin(AllCooperativasAdminMixin, admin.ModelAdmin):
    list_display = ('nome', 'cenario', 'cooperativa')
    list_filter = ('cooperativa', 'cenario')


@admin.register(Rota)
class RotaAdmin(AllCooperativasAdminMixin, admin.ModelAdmin):
    list_display = ('armazem', 'fabrica', 'cenario', 'cooperativa')
    list_filter = ('cooperativa', 'cenario')


@admin.register(PrevisaoFabrica)
class PrevisaoFabricaAdmin(AllCooperativasAdminMixin, admin.ModelAdmin):
    list_display = ('fabrica', 'mes_referencia', 'cooperativa')
    list_filter = ('cooperativa',)


@admin.register(PrevisaoArmazem)
class PrevisaoArmazemAdmin(AllCooperativasAdminMixin, admin.ModelAdmin):
    list_display = ('armazem', 'mes_referencia', 'cooperativa')
    list_filter = ('cooperativa',)


@admin.register(SafraUnidade)
class SafraUnidadeAdmin(AllCooperativasAdminMixin, admin.ModelAdmin):
    list_display = ('entidade_tipo', 'entidade_id', 'data_inicio', 'data_fim', 'cooperativa')
    list_filter = ('cooperativa', 'entidade_tipo')


@admin.register(MovimentacaoDiaria)
class MovimentacaoDiariaAdmin(AllCooperativasAdminMixin, admin.ModelAdmin):
    list_display = ('data', 'armazem', 'fabrica', 'quantidade_ton', 'cooperativa')
    list_filter = ('cooperativa', 'cenario')


@admin.register(LogExecucao)
class LogExecucaoAdmin(AllCooperativasAdminMixin, admin.ModelAdmin):
    list_display = ('data_execucao', 'status', 'cenario', 'dias_simulados', 'cooperativa')
    list_filter = ('cooperativa', 'status')


@admin.register(ResumoMensalFabrica)
class ResumoMensalFabricaAdmin(AllCooperativasAdminMixin, admin.ModelAdmin):
    list_display = ('mes', 'fabrica', 'saldo_estoque', 'cooperativa')
    list_filter = ('cooperativa', 'cenario')


@admin.register(ResumoMensalArmazem)
class ResumoMensalArmazemAdmin(AllCooperativasAdminMixin, admin.ModelAdmin):
    list_display = ('mes', 'armazem', 'saldo_estoque', 'cooperativa')
    list_filter = ('cooperativa', 'cenario')
