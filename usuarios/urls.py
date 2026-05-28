from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.user_login, name='login'),
    path('logout/', views.user_logout, name='logout'),
    path('cadastro/', views.cadastro, name='cadastro'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('perfil/', views.perfil, name='perfil'),
    path('alterar-senha/', views.alterar_senha, name='alterar_senha'),

    path('cobrancas-espetaculos/', views.cobrancas_espetaculos, name='cobrancas_espetaculos'),
    
    # Recuperação de senha por email
    path('esqueci-senha/', views.esqueci_senha, name='esqueci_senha'),
    path('redefinir-senha/<str:token>/', views.redefinir_senha, name='redefinir_senha'),
]