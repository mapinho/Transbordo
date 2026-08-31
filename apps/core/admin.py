from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from unfold.admin import ModelAdmin as UnfoldModelAdmin
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

from apps.core.models import Cooperativa, User


@admin.register(Cooperativa)
class CooperativaAdmin(UnfoldModelAdmin):
    list_display = ('nome', 'slug', 'ativo')
    prepopulated_fields = {'slug': ['nome']}


@admin.register(User)
class UserAdmin(UnfoldModelAdmin, DjangoUserAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm
    fieldsets = DjangoUserAdmin.fieldsets + (('Transbordo', {'fields': ('cooperativa', 'papel')}),)
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        ('Transbordo', {'fields': ('email', 'cooperativa', 'papel')}),
    )
    list_display = DjangoUserAdmin.list_display + ('cooperativa', 'papel')
    list_filter = DjangoUserAdmin.list_filter + ('cooperativa', 'papel')
