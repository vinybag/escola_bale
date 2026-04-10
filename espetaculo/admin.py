from django.contrib import admin
from .models import Espetaculo, InscricaoAudicao

@admin.register(Espetaculo)
class EspetaculoAdmin(admin.ModelAdmin):
    list_display = ['titulo', 'data_apresentacao', 'ativo']
    list_filter = ['ativo', 'audicao_aberta']
    search_fields = ['titulo', 'descricao']
    fieldsets = (
        ('Informações Básicas', {
            'fields': ('titulo', 'subtitulo', 'descricao')
        }),
        ('Data e Local', {
            'fields': ('data_apresentacao', 'local', 'endereco')
        }),
        ('Arquivos', {
            'fields': ('imagem', 'arquivo_informacoes', 'arquivo_edital')
        }),
        ('Audição', {
            'fields': ('audicao_aberta', 'audicao_data_inicio', 'audicao_data_fim', 'audicao_instrucoes')
        }),
        ('Venda de Ingressos', {
            'fields': ('venda_aberta', 'venda_data_inicio', 'preco_ingresso')
        }),
        ('Controle', {
            'fields': ('ativo',)
        }),
    )

@admin.register(InscricaoAudicao)
class InscricaoAudicaoAdmin(admin.ModelAdmin):
    list_display = ['nome_completo', 'whatsapp', 'idade', 'personagens', 'data_inscricao', 'lida']
    list_filter = ['lida', 'data_inscricao']
    search_fields = ['nome_completo', 'whatsapp']
    list_editable = ['lida']