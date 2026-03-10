from django.urls import path
from . import views

app_name = 'admin_dashboard'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    
    # Alunas
    path('alunas/', views.alunas_list, name='alunas_list'),
    path('alunas/criar/', views.aluna_criar, name='aluna_criar'),
    path('alunas/<int:pk>/', views.aluna_detalhes, name='aluna_detalhes'),
    path('alunas/<int:pk>/editar/', views.aluna_editar, name='aluna_editar'),
    
    # Mensalidades
    path('mensalidades/', views.mensalidades_list, name='mensalidades_list'),
    path('mensalidades/criar/', views.mensalidade_criar, name='mensalidade_criar'),
    
    # Avisos
    path('avisos/', views.avisos_list, name='avisos_list'),  # ADICIONA
    path('avisos/criar/', views.aviso_criar, name='aviso_criar'),  # ADICIONA
    path('avisos/<int:pk>/editar/', views.aviso_editar, name='aviso_editar'),  # ADICIONA
    path('avisos/<int:pk>/excluir/', views.aviso_excluir, name='aviso_excluir'),  # ADICIONA
]