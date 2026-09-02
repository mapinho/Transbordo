from django import forms
from django.core.validators import RegexValidator

from apps.simulacao.models import Armazem, Fabrica


_DATE_ATTRS = {"type": "date", "class": "input input-bordered input-sm"}
# daisyUI `.select` força altura de linha única — num <select multiple> ele
# achata as 4 linhas e o texto fica encavalado. Usar só borda/raio utilitários.
_MULTI_ATTRS = {"class": "rounded-lg border border-base-300 bg-base-100 p-1 text-sm", "size": "4"}
_MES_ATTRS = {"type": "month", "class": "input input-bordered input-sm"}
_valida_mes = RegexValidator(r"^\d{4}-\d{2}$", "Use o formato AAAA-MM.")


class ResultadosForm(forms.Form):
    data_de = forms.DateField(
        required=False, widget=forms.DateInput(attrs=_DATE_ATTRS, format="%Y-%m-%d"))
    data_ate = forms.DateField(
        required=False, widget=forms.DateInput(attrs=_DATE_ATTRS, format="%Y-%m-%d"))
    armazem_ids = forms.ModelMultipleChoiceField(queryset=Armazem.objects.none(), required=False)
    fabrica_ids = forms.ModelMultipleChoiceField(queryset=Fabrica.objects.none(), required=False)

    def __init__(self, *args, cenario=None, **kwargs):
        super().__init__(*args, **kwargs)
        if cenario is not None:
            self.fields["armazem_ids"].queryset = Armazem.objects.filter(cenario=cenario)
            self.fields["fabrica_ids"].queryset = Fabrica.objects.filter(cenario=cenario)
        self.fields["armazem_ids"].widget.attrs.update(_MULTI_ATTRS)
        self.fields["fabrica_ids"].widget.attrs.update(_MULTI_ATTRS)

    def filtros_limpos(self):
        d = self.cleaned_data
        return {
            "data_de": d.get("data_de"),
            "data_ate": d.get("data_ate"),
            "armazem_ids": [a.id for a in d.get("armazem_ids", [])],
            "fabrica_ids": [f.id for f in d.get("fabrica_ids", [])],
        }


class EstoqueForm(forms.Form):
    mes_de = forms.CharField(
        required=False, validators=[_valida_mes],
        widget=forms.TextInput(attrs=_MES_ATTRS))
    mes_ate = forms.CharField(
        required=False, validators=[_valida_mes],
        widget=forms.TextInput(attrs=_MES_ATTRS))
    armazem_ids = forms.ModelMultipleChoiceField(queryset=Armazem.objects.none(), required=False)
    fabrica_ids = forms.ModelMultipleChoiceField(queryset=Fabrica.objects.none(), required=False)

    def __init__(self, *args, cenario=None, **kwargs):
        super().__init__(*args, **kwargs)
        if cenario is not None:
            self.fields["armazem_ids"].queryset = Armazem.objects.filter(cenario=cenario)
            self.fields["fabrica_ids"].queryset = Fabrica.objects.filter(cenario=cenario)
        self.fields["armazem_ids"].widget.attrs.update(_MULTI_ATTRS)
        self.fields["fabrica_ids"].widget.attrs.update(_MULTI_ATTRS)

    def filtros_limpos(self):
        d = self.cleaned_data
        return {
            "mes_de": d.get("mes_de") or "",
            "mes_ate": d.get("mes_ate") or "",
            "armazem_ids": [a.id for a in d.get("armazem_ids", [])],
            "fabrica_ids": [f.id for f in d.get("fabrica_ids", [])],
        }
