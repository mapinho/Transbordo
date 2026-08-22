from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from apps.core.models import Cooperativa, User


@admin.register(Cooperativa)
class CooperativaAdmin(admin.ModelAdmin):
    list_display = ['nome', 'slug', 'ativo']
    prepopulated_fields = {'slug': ['nome']}


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    fieldsets = DjangoUserAdmin.fieldsets + (('Transbordo', {'fields': ('cooperativa', 'papel')}),)
    list_display = DjangoUserAdmin.list_display + ('cooperativa', 'papel')
    list_filter = DjangoUserAdmin.list_filter + ('cooperativa', 'papel')
