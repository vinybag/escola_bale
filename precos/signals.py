"""Mantém `EntradaTurma` em dia quando as turmas de uma aluna são marcadas ou desmarcadas."""

from django.db.models.signals import m2m_changed
from django.dispatch import receiver
from django.utils import timezone

from usuarios.models import Aluna, Turma

from .models import EntradaTurma


@receiver(m2m_changed, sender=Aluna.turmas.through)
def acompanhar_turmas_da_aluna(sender, instance, action, reverse, pk_set, **kwargs):
    if action == 'post_add':
        hoje = timezone.localdate()

        if reverse:  # turma.alunas.add(aluna)
            pares = [(Aluna.objects.get(pk=pk), instance) for pk in pk_set or []]
        else:
            pares = [(instance, turma) for turma in Turma.objects.filter(pk__in=pk_set or [])]

        for aluna, turma in pares:
            # Na criação da aluna a data de matrícula é hoje, então a turma entra como "aluna nova".
            EntradaTurma.objects.get_or_create(aluna=aluna, turma=turma, defaults={'data_entrada': hoje})

    elif action == 'post_remove':
        filtro = {'turma': instance, 'aluna_id__in': pk_set} if reverse else {'aluna': instance, 'turma_id__in': pk_set}
        EntradaTurma.objects.filter(**filtro).delete()

    elif action == 'post_clear':
        EntradaTurma.objects.filter(**({'turma': instance} if reverse else {'aluna': instance})).delete()
