from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import Perfil, Aluna
import random
import string

# Desregistra o User padrão
admin.site.unregister(User)

# Função para gerar senha
def gerar_senha_aleatoria():
    palavras = ['Bale', 'Danca', 'Ballet', 'Aluna', 'Rosa']
    numeros = ''.join(random.choices(string.digits, k=4))
    palavra = random.choice(palavras)
    return f"{palavra}{numeros}!"

# Inline para mostrar o Perfil junto com o User
class PerfilInline(admin.StackedInline):
    model = Perfil
    can_delete = False
    verbose_name = 'Informações do Responsável'
    verbose_name_plural = 'Informações do Responsável'
    fk_name = 'user'

class AlunaInline(admin.TabularInline):
    model = Aluna
    extra = 1
    verbose_name = 'Aluna'
    verbose_name_plural = 'Alunas da Família'
    fk_name = 'responsavel'

# Customiza o UserAdmin
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
    
    # Sobrescreve o formulário de criação para gerar senha
    def save_model(self, request, obj, form, change):
        if not change:  # Novo usuário
            # Gera senha aleatória
            senha_temp = gerar_senha_aleatoria()
            obj.set_password(senha_temp)
            obj.save()
            
            # Mostra a senha gerada para o admin
            self.message_user(
                request,
                f'✅ Usuário criado! Senha temporária: {senha_temp} (anote e envie ao responsável)',
                level='SUCCESS'
            )
        else:
            super().save_model(request, obj, form, change)

# Registra o User customizado
admin.site.register(User, UserAdmin)

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
