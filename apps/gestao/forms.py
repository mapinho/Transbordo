from django import forms

from apps.core.models import Cooperativa


class CooperativaForm(forms.ModelForm):
    class Meta:
        model = Cooperativa
        fields = ['nome', 'slug', 'ativo', 'dias_janela_safra_padrao']
