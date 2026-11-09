"""
Dados iniciais da lista de presença:

1) Cria a configuração com o "início do controle" = dia em que esta migration
   rodar (assim as alunas atuais não ganham faltas retroativas).
2) Tenta preencher os horários das turmas a partir do texto escrito à mão
   (campos "Horário" e "Dia da Semana"). O que não for possível interpretar com
   segurança fica sem horário: a escola cadastra na edição da turma.
   Os horários preenchidos aqui ficam marcados como "automáticos" para conferência.
"""
from django.db import migrations
from django.utils import timezone

from presenca.horarios_parse import interpretar_horario


def preencher(apps, schema_editor):
    Config = apps.get_model('presenca', 'ConfiguracaoPresenca')
    HorarioTurma = apps.get_model('presenca', 'HorarioTurma')
    Turma = apps.get_model('usuarios', 'Turma')

    Config.objects.get_or_create(pk=1, defaults={'data_inicio_controle': timezone.localdate()})

    for turma in Turma.objects.filter(tipo='turma', ativa=True):
        if HorarioTurma.objects.filter(turma=turma).exists():
            continue
        for dia, inicio, fim in interpretar_horario(turma.horario, turma.dia_semana):
            HorarioTurma.objects.create(
                turma=turma,
                dia_semana=dia,
                hora_inicio=inicio,
                hora_fim=fim,
                preenchido_automaticamente=True,
            )


class Migration(migrations.Migration):

    dependencies = [
        ('presenca', '0001_inicial'),
    ]

    operations = [
        migrations.RunPython(preencher, migrations.RunPython.noop),
    ]
