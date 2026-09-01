from django import template
from django.utils.safestring import mark_safe

register = template.Library()


def _formatar_pt_br(valor, casas_decimais):
    if valor is None or valor == '':
        return ''
    numero = float(valor)
    texto = f"{numero:,.{casas_decimais}f}"
    return texto.replace(',', 'X').replace('.', ',').replace('X', '.')


@register.filter
def moeda(valor):
    """Porte de `utils.format_valor`: 'R$ 1.234,50'."""
    if valor is None or valor == '':
        return ''
    return f"R$ {_formatar_pt_br(valor, 2)}"


@register.filter
def volume(valor):
    """Porte de `utils.format_volume`: '1.234,5'."""
    return _formatar_pt_br(valor, 1)


@register.filter
def item(dicionario, chave):
    """Lookup de dict com chave variável no template."""
    if isinstance(dicionario, dict):
        return dicionario.get(chave)
    return ""


@register.filter
def variacao(valor):
    """Renderiza um delta (`float | None | "novo"`) como span colorido."""
    if valor == "novo":
        return mark_safe('<span class="badge badge-ghost badge-sm">novo</span>')
    if valor is None:
        return mark_safe('<span class="text-base-content/50">—</span>')
    if valor == "" or not isinstance(valor, (int, float)):
        return ""
    pct = _formatar_pt_br(abs(valor), 1)
    if valor > 0:
        return mark_safe(f'<span class="text-error">↑&nbsp;+{pct}%</span>')
    if valor < 0:
        return mark_safe(f'<span class="text-success">↓&nbsp;−{pct}%</span>')
    return mark_safe('<span class="text-base-content/50">0,0%</span>')
