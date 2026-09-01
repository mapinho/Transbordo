from django import forms

from apps.simulacao.models import Armazem, Fabrica


class ResultadosForm(forms.Form):
    data_de = forms.DateField(required=False)
    data_ate = forms.DateField(required=False)
    armazem_ids = forms.ModelMultipleChoiceField(queryset=Armazem.objects.none(), required=False)
    fabrica_ids = forms.ModelMultipleChoiceField(queryset=Fabrica.objects.none(), required=False)

    def __init__(self, *args, cenario=None, **kwargs):
        super().__init__(*args, **kwargs)
        if cenario is not None:
            self.fields["armazem_ids"].queryset = Armazem.objects.filter(cenario=cenario)
            self.fields["fabrica_ids"].queryset = Fabrica.objects.filter(cenario=cenario)

    def filtros_limpos(self):
        d = self.cleaned_data
        return {
            "data_de": d.get("data_de"),
            "data_ate": d.get("data_ate"),
            "armazem_ids": [a.id for a in d.get("armazem_ids", [])],
            "fabrica_ids": [f.id for f in d.get("fabrica_ids", [])],
        }
