from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import Perfil, Aluna

# Desregistra o User padrão para customizar
admin.site.unregister(User)

# Inline para criar Perfil junto com User
class PerfilInline(admin.StackedInline):
    model = Perfil
    can_delete = False
    verbose_name = 'Informações do Responsável'
    verbose_name_plural = 'Informações do Responsável'
    fk_name = 'user'

# Inline para criar Alunas junto com User
class AlunaInline(admin.TabularInline):
    model = Aluna
    extra = 1
    verbose_name = 'Aluna'
    verbose_name_plural = 'Alunas da Família'
    fk_name = 'responsavel'

# Customiza o admin de User
class UserAdmin(BaseUserAdmin):
    inlines = (PerfilInline, AlunaInline)
    list_display = ['username', 'email', 'first_name', 'last_name', 'get_telefone', 'get_qtd_alunas', 'is_active']
    list_filter = ['is_staff', 'is_active', 'date_joined']
    search_fields = ['username', 'first_name', 'last_name', 'email']
    
    def get_telefone(self, obj):
        try:
            return obj.perfil.telefone
        except:
            return '-'
    get_telefone.short_description = 'Telefone'
    
    def get_qtd_alunas(self, obj):
        return obj.alunas.count()
    get_qtd_alunas.short_description = 'Nº Alunas'

# Registra o User customizado
admin.site.register(User, UserAdmin)

# Mantém o admin de Aluna separado também (para acesso rápido)
@admin.register(Aluna)
class AlunaAdmin(admin.ModelAdmin):
    list_display = ['nome', 'responsavel', 'idade', 'turma_atual', 'ativa', 'data_matricula']
    list_filter = ['ativa', 'turma_atual', 'data_matricula']
    search_fields = ['nome', 'responsavel__username', 'responsavel__first_name', 'responsavel__last_name']
    date_hierarchy = 'data_matricula'
    
    fieldsets = (
        ('Informações da Aluna', {
            'fields': ('nome', 'data_nascimento', 'responsavel')
        }),
        ('Matrícula', {
            'fields': ('turma_atual', 'ativa', 'observacoes')
        }),
    )
