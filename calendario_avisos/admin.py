from django.contrib import admin
from .models import Aviso

@admin.register(Aviso)
class AvisoAdmin(admin.ModelAdmin):
    list_display = ['titulo', 'tipo', 'data_evento', 'ativo', 'data_publicacao']
    list_filter = ['tipo', 'ativo', 'data_evento']
    search_fields = ['titulo', 'descricao']
