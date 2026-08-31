from django.contrib import admin
from unfold.admin import ModelAdmin as UnfoldModelAdmin

from apps.integracoes.models import ApiKey


@admin.register(ApiKey)
class ApiKeyAdmin(UnfoldModelAdmin):
    list_display = ('nome', 'cooperativa', 'ativo', 'created_at')
    list_filter = ('ativo', 'cooperativa')
    readonly_fields = ('chave', 'created_at')
    search_fields = ('nome',)
