import logging

from django import template
from django.db import DatabaseError
from django.db.models import Q

from .. import regras
from ..models import Contrato, OpcaoBolsa

register = template.Library()
logger = logging.getLogger(__name__)

# Estas tags aparecem em telas que já existiam (painel da família e formulários de aluna).
# Se as tabelas novas ainda não existirem (migração não aplicada), a tela antiga continua
# funcionando, só sem o recurso de contratos, em vez de dar erro 500.


@register.inclusion_tag('contratos/admin/_campos_bolsa.html')
def campos_bolsa(aluna=None):
    """Bloco "É bolsista?" para os formulários de criar e editar aluna."""
    try:
        bolsa = regras.bolsa_da_aluna(aluna) if aluna is not None and aluna.pk else None
        opcoes = list(OpcaoBolsa.objects.filter(ativa=True))
    except DatabaseError:
        logger.exception('Contratos: tabelas de bolsa indisponíveis (migrações aplicadas?)')
        return {'opcoes': [], 'bolsista': False, 'opcao_id': None, 'indisponivel': True}

    if bolsa and bolsa.opcao not in opcoes:
        opcoes.append(bolsa.opcao)

    return {
        'opcoes': opcoes,
        'bolsista': bolsa is not None,
        'opcao_id': bolsa.opcao_id if bolsa else None,
    }


@register.inclusion_tag('contratos/admin/_aluna_contrato.html', takes_context=True)
def contrato_da_aluna(context, aluna):
    """Bloco "Contrato" da ficha da aluna no admin."""
    try:
        contratos = list(
            Contrato.objects.filter(aluna=aluna)
            .defer('pdf_assinado', 'scan_arquivo')
            .order_by('-ano', '-criado_em')
        )
        bolsa = regras.bolsa_da_aluna(aluna)
        ano_ativo = regras.ano_ativo()
    except DatabaseError:
        logger.exception('Contratos: tabelas indisponíveis (migrações aplicadas?)')
        return {'aluna': aluna, 'indisponivel': True, 'csrf_token': context.get('csrf_token')}

    ativo = next((c for c in contratos if c.status != Contrato.ANULADO), None)

    return {
        'aluna': aluna,
        'contrato': ativo,
        'anulados': [c for c in contratos if c.status == Contrato.ANULADO],
        'bolsa': bolsa,
        'ano_ativo': ano_ativo,
        'csrf_token': context.get('csrf_token'),
    }


@register.simple_tag
def contratos_pendentes(user):
    """Quantos contratos da família ainda precisam de ação (para o aviso no painel)."""
    if not user.is_authenticated:
        return 0

    try:
        return (
            Contrato.objects.filter(
                Q(aluna__responsavel=user) | Q(aluna__usuario=user) | Q(contratante=user),
                status__in=Contrato.STATUS_ABERTOS,
            ).distinct().count()
        )
    except DatabaseError:
        logger.exception('Contratos: tabelas indisponíveis (migrações aplicadas?)')
        return 0
