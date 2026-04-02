from django.urls import path
from . import views

app_name = 'admin_dashboard'

urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='dashboard'),
    
    # Alunas
    path('alunas/', views.alunas_list, name='alunas_list'),
    path('alunas/criar/', views.aluna_criar, name='aluna_criar'),
    path('alunas/<int:pk>/', views.aluna_detalhes, name='aluna_detalhes'),
    path('alunas/<int:pk>/editar/', views.aluna_editar, name='aluna_editar'),
    path('alunas/<int:pk>/excluir/', views.aluna_excluir, name='aluna_excluir'),
    
    # Turmas - NOVO
    path('turmas/', views.turmas_list, name='turmas_list'),
    path('turmas/criar/', views.turma_criar, name='turma_criar'),
    path('turmas/<int:pk>/', views.turma_detalhes, name='turma_detalhes'),
    path('turmas/<int:pk>/editar/', views.turma_editar, name='turma_editar'),
    path('turmas/<int:pk>/excluir/', views.turma_excluir, name='turma_excluir'),
    
    # Mensalidades
    path('mensalidades/', views.mensalidades_list, name='mensalidades_list'),
    path('mensalidades/criar/', views.mensalidade_criar, name='mensalidade_criar'),
    path('mensalidades/<int:pk>/editar/', views.mensalidade_editar, name='mensalidade_editar'),
    path('mensalidades/<int:pk>/excluir/', views.mensalidade_excluir, name='mensalidade_excluir'),
    
    # Avisos
    path('avisos/', views.avisos_list, name='avisos_list'),
    path('avisos/criar/', views.aviso_criar, name='aviso_criar'),
    path('avisos/<int:pk>/editar/', views.aviso_editar, name='aviso_editar'),
    path('avisos/<int:pk>/excluir/', views.aviso_excluir, name='aviso_excluir'),
    
    # Espetáculos
    path('espetaculos/', views.espetaculos_list, name='espetaculos_list'),
    path('espetaculos/criar/', views.espetaculo_criar, name='espetaculo_criar'),
    path('espetaculos/<int:pk>/editar/', views.espetaculo_editar, name='espetaculo_editar'),
    
    # Responsáveis
    path('responsaveis/', views.responsaveis_list, name='responsaveis_list'),
    path('responsaveis/<int:pk>/editar/', views.responsavel_editar, name='responsavel_editar'),
    path('responsaveis/<int:pk>/redefinir-senha/', views.responsavel_redefinir_senha, name='responsavel_redefinir_senha'),
    path('responsaveis/<int:pk>/excluir/', views.responsavel_excluir, name='responsavel_excluir'),
]