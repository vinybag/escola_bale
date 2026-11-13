from django import template

from ..models import formatar_moeda

register = template.Library()


@register.filter
def moeda(valor):
    return formatar_moeda(valor) if valor is not None else '—'


@register.inclusion_tag('precos/admin/_campos_turma.html')
def campos_preco_turma(turma=None):
    """Bloco "Mensalidade" dos formulários de criar e editar turma."""
    from usuarios.models import Turma

    valor = turma.valor_mensalidade if turma is not None else None

    return {
        'valor_texto': f'{valor:.2f}'.replace('.', ',') if valor is not None else '',
        'regime': turma.regime_preco if turma is not None else 'normal',
        'regimes': Turma.REGIMES_PRECO,
    }
