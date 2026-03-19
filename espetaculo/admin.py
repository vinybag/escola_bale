from django.contrib import admin
from .models import Espetaculo

@admin.register(Espetaculo)
class EspetaculoAdmin(admin.ModelAdmin):
    list_display = ['titulo', 'data_apresentacao', 'local', 'ativo']
    list_filter = ['ativo', 'audicao_aberta', 'venda_aberta']
    search_fields = ['titulo', 'local']
