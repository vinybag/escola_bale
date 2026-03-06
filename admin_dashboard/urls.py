from django.urls import path
from . import views

app_name = 'admin_dashboard'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('alunas/', views.alunas_list, name='alunas_list'),
    path('alunas/criar/', views.aluna_criar, name='aluna_criar'),
    path('alunas/<int:pk>/', views.aluna_detalhes, name='aluna_detalhes'),  # ADICIONA
    path('alunas/<int:pk>/editar/', views.aluna_editar, name='aluna_editar'),  # ADICIONA
]