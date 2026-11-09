from django import template

from presenca.models import DIAS_SEMANA

register = template.Library()


@register.inclusion_tag('presenca/admin/_horarios_turma_form.html')
def horarios_turma_form(turma=None):
    """Seção "Horários das aulas" para os formulários de criar/editar turma."""
    horarios = []
    if turma is not None and getattr(turma, 'pk', None):
        horarios = list(turma.horarios_aula.all())
    return {'horarios': horarios, 'dias': DIAS_SEMANA}
