from django.contrib import admin
from .models import Aviso, AvisoEnvioAutomatico, AvisoEnvioManual

@admin.register(Aviso)
class AvisoAdmin(admin.ModelAdmin):
    list_display = ['titulo', 'tipo', 'data_evento', 'ativo', 'data_publicacao']
    list_filter = ['tipo', 'ativo', 'data_evento']
    search_fields = ['titulo', 'descricao']


@admin.register(AvisoEnvioManual)
class AvisoEnvioManualAdmin(admin.ModelAdmin):
    """Somente leitura: histórico de quem usou "Enviar agora" e com que resultado."""

    list_display = ['aviso', 'criado_em', 'enviado_por', 'template',
                    'enviados', 'erros', 'concluido']
    list_filter = ['template', 'concluido']
    date_hierarchy = 'criado_em'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(AvisoEnvioAutomatico)
class AvisoEnvioAutomaticoAdmin(admin.ModelAdmin):
    """Somente leitura: resultado de cada envio feito pelo cron."""

    list_display = ['aviso', 'criado_em', 'template', 'enviados', 'erros']
    list_filter = ['template']
    date_hierarchy = 'criado_em'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
