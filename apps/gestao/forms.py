from crispy_forms.helper import FormHelper
from django import forms

from apps.core import permissions
from apps.core.models import Cooperativa, User


class _HelperMixin:
    """Dá ao form um ``helper`` crispy que só renderiza os campos.

    O ``<form>``, o ``{% csrf_token %}`` e os botões ficam no template.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.disable_csrf = True


class CooperativaForm(_HelperMixin, forms.ModelForm):
    class Meta:
        model = Cooperativa
        fields = ['nome', 'slug', 'ativo', 'dias_janela_safra_padrao']


class MinhaCooperativaForm(_HelperMixin, forms.ModelForm):
    class Meta:
        model = Cooperativa
        fields = ['dias_janela_safra_padrao']


class UsuarioForm(_HelperMixin, forms.ModelForm):
    senha = forms.CharField(
        required=False, widget=forms.PasswordInput, label='Senha inicial',
        help_text='Deixe em branco para criar sem senha (defina depois pelo link de e-mail).',
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'papel', 'cooperativa', 'is_active']
        labels = {'cooperativa': 'Organização'}

    def __init__(self, *args, gestor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.gestor = gestor
        if gestor is not None and not permissions.e_admin_vector(gestor):
            self.fields['cooperativa'].queryset = (
                self.fields['cooperativa'].queryset.filter(pk=gestor.cooperativa_id)
            )
            self.fields['cooperativa'].initial = gestor.cooperativa_id
            self.fields['cooperativa'].disabled = True
            self.fields['cooperativa'].required = False
            self.fields['papel'].choices = [
                c for c in User.PAPEL_CHOICES
                if c[0] in (User.PAPEL_USUARIO_FABRICA, User.PAPEL_USUARIO_ARMAZEM)
            ]

    def clean(self):
        cleaned = super().clean()
        gestor = self.gestor
        if gestor is not None and not permissions.e_admin_vector(gestor):
            cleaned['cooperativa'] = gestor.cooperativa
            if cleaned.get('papel') not in (User.PAPEL_USUARIO_FABRICA, User.PAPEL_USUARIO_ARMAZEM):
                self.add_error('papel', 'Papel não permitido para este gestor.')
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        senha = self.cleaned_data.get('senha')
        if senha:
            user.set_password(senha)
        elif not user.pk:
            user.set_unusable_password()
        user.full_clean(exclude=['password'])
        if commit:
            user.save()
        return user
