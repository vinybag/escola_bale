from django.contrib import admin
from .models import Perfil, Turma, Aluna, RecuperacaoSenha

@admin.register(Perfil)
class PerfilAdmin(admin.ModelAdmin):
    list_display = ['user', 'telefone', 'cpf', 'criado_em']
    search_fields = ['user__username', 'user__email', 'telefone', 'cpf']
    list_filter = ['criado_em']

@admin.register(Turma)
class TurmaAdmin(admin.ModelAdmin):
    list_display = ['nome', 'professor', 'horario', 'total_alunas', 'capacidade_maxima', 'vagas_disponiveis', 'ativa']
    search_fields = ['nome', 'professor']
    list_filter = ['ativa', 'criado_em']
    ordering = ['nome']

@admin.register(Aluna)
class AlunaAdmin(admin.ModelAdmin):
    list_display = ['nome', 'responsavel', 'idade', 'get_turmas', 'ativa', 'data_matricula']
    search_fields = ['nome', 'responsavel__first_name', 'responsavel__last_name', 'responsavel__email']
    list_filter = ['ativa', 'data_matricula']  # Removeu 'turma' daqui
    ordering = ['nome']
    
    def idade(self, obj):
        if obj.idade:
            return f"{obj.idade} anos"
        return "-"
    idade.short_description = 'Idade'
    
    def get_turmas(self, obj):
        return ", ".join([turma.nome for turma in obj.turmas.all()]) if obj.turmas.exists() else "-"
    get_turmas.short_description = 'Turmas'

@admin.register(RecuperacaoSenha)
class RecuperacaoSenhaAdmin(admin.ModelAdmin):
    list_display = ['user', 'criado_em', 'usado']
    search_fields = ['user__username', 'user__email']
    list_filter = ['usado', 'criado_em']
    ordering = ['-criado_em']