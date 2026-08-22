from django.contrib import admin

from apps.simulacao.models import Armazem, Cenario, Fabrica, Rota


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
