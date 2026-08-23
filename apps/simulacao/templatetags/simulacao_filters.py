from django import template

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
