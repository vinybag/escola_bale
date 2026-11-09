from django.contrib import admin

from .models import ConfiguracaoPresenca, DiaSemAula, HorarioTurma, Presenca


@admin.register(Presenca)
class PresencaAdmin(admin.ModelAdmin):
    list_display = ('aluna', 'turma', 'data', 'registrada_em', 'origem', 'anulada')
    list_filter = ('origem', 'anulada', 'turma')
    search_fields = ('aluna__nome',)
    date_hierarchy = 'data'


@admin.register(HorarioTurma)
class HorarioTurmaAdmin(admin.ModelAdmin):
    list_display = ('turma', 'dia_semana', 'hora_inicio', 'hora_fim', 'preenchido_automaticamente')
    list_filter = ('turma', 'dia_semana')


admin.site.register(DiaSemAula)
admin.site.register(ConfiguracaoPresenca)
