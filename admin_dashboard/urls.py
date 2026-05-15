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
    path('inscricoes-audicao/', views.inscricoes_audicao_list, name='inscricoes_audicao'),
    path('inscricoes-audicao/<int:pk>/excluir/', views.inscricao_audicao_excluir, name='inscricao_audicao_excluir'),
    
    # Responsáveis
    path('responsaveis/', views.responsaveis_list, name='responsaveis_list'),
    path('responsaveis/<int:pk>/editar/', views.responsavel_editar, name='responsavel_editar'),
    path('responsaveis/<int:pk>/redefinir-senha/', views.responsavel_redefinir_senha, name='responsavel_redefinir_senha'),
    path('responsaveis/<int:pk>/excluir/', views.responsavel_excluir, name='responsavel_excluir'),

    # Agendamentos
    path('agendamentos/', views.agendamentos_list, name='agendamentos_list'),
    path('agendamentos/<int:pk>/', views.agendamento_detalhes, name='agendamento_detalhes'),
    path('agendamentos/<int:pk>/excluir/', views.agendamento_excluir, name='agendamento_excluir'),

    # Professores
    path('professores/', views.professores_list, name='professores_list'),
    path('professores/criar/', views.professor_criar, name='professor_criar'),
    path('professores/<int:pk>/editar/', views.professor_editar, name='professor_editar'),
    path('professores/<int:pk>/excluir/', views.professor_excluir, name='professor_excluir'),

    # Professor
    path('professor/dashboard/', views.professor_dashboard, name='professor_dashboard'),
    path('professor/turma/<int:pk>/', views.professor_turma_detalhes, name='professor_turma_detalhes'),
    path('professor/avisos/', views.professor_avisos, name='professor_avisos'),

    #Ficha
    path('ficha-audicao/<int:pk>/pdf/', views.ficha_pdf, name='ficha_pdf'),
]