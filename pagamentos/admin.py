from django.contrib import admin
from .models import Mensalidade, WhatsAppMensagemRecebida

@admin.register(Mensalidade)
class MensalidadeAdmin(admin.ModelAdmin):
    list_display = ['aluna', 'mes_referencia', 'valor', 'data_vencimento', 'status', 'status_visual']
    list_filter = ['status', 'data_vencimento', 'forma_pagamento']
    search_fields = ['aluna__nome', 'responsavel__username']
    date_hierarchy = 'mes_referencia'
    
    def status_visual(self, obj):
        if obj.status == 'pago':
            return '✅ Pago'
        elif obj.esta_atrasada:
            return '🔴 Atrasado'
        else:
            return '⏳ Pendente'
    status_visual.short_description = 'Status Visual'


@admin.register(WhatsAppMensagemRecebida)
class WhatsAppMensagemRecebidaAdmin(admin.ModelAdmin):
    """Somente leitura: mostra quem escreveu no número de avisos e se a
    resposta automática foi enviada."""

    list_display = ['telefone', 'tipo', 'status', 'motivo', 'criado_em']
    list_filter = ['status', 'tipo']
    search_fields = ['telefone']
    date_hierarchy = 'criado_em'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
