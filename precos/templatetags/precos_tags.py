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


@register.inclusion_tag('precos/_calculo_aluna.html', takes_context=True)
def calculo_aluna(context, aluna=None):
    """Caixa "Cálculo da mensalidade" das fichas de criar e editar aluna."""
    import json

    from usuarios.models import Aluna

    from .. import servico
    from ..models import GrauParentesco, LigacaoFamiliar

    gravada = aluna is not None and getattr(aluna, 'pk', None)
    manual = servico.valor_e_manual(aluna) if gravada else False
    iniciais = {}
    ligacoes = []
    ligadas_pela_outra = []

    if gravada:
        servico.garantir_entradas(aluna)

        for entrada in aluna.entradas_turma.all():
            iniciais[str(entrada.turma_id)] = {'data': entrada.data_entrada.isoformat(), 'ordem': entrada.ordem}

        ligacoes = [
            {'parente': l.parente_id, 'grau': l.grau_id}
            for l in LigacaoFamiliar.objects.filter(aluna=aluna)
        ]
        ligadas_pela_outra = [
            f'{l.aluna.nome} ({l.grau.nome})'
            for l in LigacaoFamiliar.objects.filter(parente=aluna).select_related('aluna', 'grau')
        ]

    outras = Aluna.objects.filter(ativa=True)

    if gravada:
        outras = outras.exclude(pk=aluna.pk)

    return {
        'aluna': aluna if gravada else None,
        'manual': manual,
        'marcada': servico.marcada_para_receber(aluna) if gravada else False,
        'graus': GrauParentesco.objects.all(),
        'outras_alunas': outras.order_by('nome'),
        'ligacoes': ligacoes,
        'ligadas_pela_outra': ligadas_pela_outra,
        'iniciais_json': json.dumps(iniciais),
        'ligacoes_json': json.dumps(ligacoes),
        'request': context.get('request'),
    }
