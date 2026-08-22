from django.contrib import admin

from apps.core.models import Cooperativa


@admin.register(Cooperativa)
class CooperativaAdmin(admin.ModelAdmin):
    list_display = ['nome', 'slug', 'ativo']
    prepopulated_fields = {'slug': ['nome']}
