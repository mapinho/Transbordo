from django.contrib import admin

from apps.simulacao.models import Armazem, Cenario, Fabrica, Rota, MovimentacaoDiaria, PrevisaoArmazem, PrevisaoFabrica, SafraUnidade


@admin.register(Cenario)
class CenarioAdmin(admin.ModelAdmin):
    list_display = ('nome', 'cooperativa', 'is_oficial', 'data_criacao')
    list_filter = ('cooperativa', 'is_oficial')


@admin.register(Fabrica)
class FabricaAdmin(admin.ModelAdmin):
    list_display = ('nome', 'cenario', 'cooperativa')
    list_filter = ('cooperativa', 'cenario')


@admin.register(Armazem)
class ArmazemAdmin(admin.ModelAdmin):
    list_display = ('nome', 'cenario', 'cooperativa')
    list_filter = ('cooperativa', 'cenario')


@admin.register(Rota)
class RotaAdmin(admin.ModelAdmin):
    list_display = ('armazem', 'fabrica', 'cenario', 'cooperativa')
    list_filter = ('cooperativa', 'cenario')


@admin.register(PrevisaoFabrica)
class PrevisaoFabricaAdmin(admin.ModelAdmin):
    list_display = ('fabrica', 'mes_referencia', 'cooperativa')
    list_filter = ('cooperativa',)


@admin.register(PrevisaoArmazem)
class PrevisaoArmazemAdmin(admin.ModelAdmin):
    list_display = ('armazem', 'mes_referencia', 'cooperativa')
    list_filter = ('cooperativa',)


@admin.register(SafraUnidade)
class SafraUnidadeAdmin(admin.ModelAdmin):
    list_display = ('entidade_tipo', 'entidade_id', 'data_inicio', 'data_fim', 'cooperativa')
    list_filter = ('cooperativa', 'entidade_tipo')


@admin.register(MovimentacaoDiaria)
class MovimentacaoDiariaAdmin(admin.ModelAdmin):
    list_display = ('data', 'armazem', 'fabrica', 'quantidade_ton', 'cooperativa')
    list_filter = ('cooperativa', 'cenario')
