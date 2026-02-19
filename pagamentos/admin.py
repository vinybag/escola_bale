from django.contrib import admin
from .models import Mensalidade

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
