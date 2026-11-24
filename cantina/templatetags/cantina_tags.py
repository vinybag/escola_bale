from decimal import Decimal

from django import template

register = template.Library()


@register.filter
def reais(valor):
    if valor is None or valor == '':
        return '—'

    texto = f'{Decimal(valor):,.2f}'
    return 'R$ ' + texto.replace(',', 'X').replace('.', ',').replace('X', '.')
