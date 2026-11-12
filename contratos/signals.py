import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender='usuarios.Aluna')
def criar_contrato_pendente_da_aluna_nova(sender, instance, created, **kwargs):
    """
    Quando uma aluna é criada (por qualquer tela), já nasce um contrato pendente
    para ela, desde que exista um modelo de contrato ativo.

    O tipo do contrato (padrão ou bolsista) só é decidido quando a família abre o
    contrato, porque a bolsa é gravada logo depois da aluna.
    """
    if not created or not instance.ativa:
        return

    try:
        from .servicos import criar_contrato_pendente

        criar_contrato_pendente(instance)
    except Exception:
        # Um problema no contrato nunca pode impedir o cadastro da aluna.
        logger.exception('Não foi possível criar o contrato pendente da aluna %s', instance.pk)
