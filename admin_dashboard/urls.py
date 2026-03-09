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
    path('mensalidades/', views.mensalidades_list, name='mensalidades_list'),  # ADICIONA
    path('mensalidades/criar/', views.mensalidade_criar, name='mensalidade_criar'),  # ADICIONA
]