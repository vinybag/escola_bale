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
    list_display = ['nome', 'responsavel', 'idade', 'turma', 'ativa', 'data_matricula']
    search_fields = ['nome', 'responsavel__first_name', 'responsavel__last_name', 'responsavel__email']
    list_filter = ['ativa', 'turma', 'data_matricula']
    ordering = ['nome']
    
    def idade(self, obj):
        return f"{obj.idade} anos"
    idade.short_description = 'Idade'

@admin.register(RecuperacaoSenha)
class RecuperacaoSenhaAdmin(admin.ModelAdmin):
    list_display = ['user', 'criado_em', 'usado']
    search_fields = ['user__username', 'user__email']
    list_filter = ['usado', 'criado_em']
    ordering = ['-criado_em']
