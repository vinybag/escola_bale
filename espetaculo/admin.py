from django.contrib import admin
from .models import (
    Espetaculo,
    InscricaoAudicao,
    PedidoIngressoEvento,
    IngressoEvento,
)


@admin.register(Espetaculo)
class EspetaculoAdmin(admin.ModelAdmin):
    list_display = ['titulo', 'tipo', 'publico', 'data_apresentacao', 'venda_aberta', 'ativo']
    list_filter = ['tipo', 'publico', 'ativo', 'audicao_aberta', 'venda_aberta']
    search_fields = ['titulo', 'descricao', 'local']

    fieldsets = (
        ('Informações Básicas', {
            'fields': ('tipo', 'publico', 'titulo', 'subtitulo', 'descricao')
        }),
        ('Data e Local', {
            'fields': ('data_apresentacao', 'local', 'endereco')
        }),
        ('Arquivos', {
            'fields': ('imagem', 'arquivo_divulgacao', 'arquivo_informacoes', 'arquivo_edital')
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


@admin.register(PedidoIngressoEvento)
class PedidoIngressoEventoAdmin(admin.ModelAdmin):
    list_display = ['nome_completo', 'evento', 'quantidade', 'valor_total', 'status', 'criado_em']
    list_filter = ['status', 'criado_em', 'evento']
    search_fields = ['nome_completo', 'whatsapp', 'email', 'asaas_payment_id']


@admin.register(IngressoEvento)
class IngressoEventoAdmin(admin.ModelAdmin):
    list_display = ['codigo_unico', 'evento', 'pedido', 'status', 'criado_em']
    list_filter = ['status', 'evento', 'criado_em']
    search_fields = ['codigo_unico', 'pedido__nome_completo']