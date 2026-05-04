from django.urls import path
from . import views

app_name = 'espetaculo'

urlpatterns = [
    path('', views.espetaculos_lista_publica, name='lista_publica'),
    path('<int:pk>/', views.espetaculo_detalhes_publico, name='detalhes_publico'),
    path('personagens/', views.personagens_publicos, name='personagens_publicos'),
    path('inscrever/', views.inscricao_audicao, name='inscricao_audicao'),
    path('api/personagens-por-idade/', views.get_personagens_por_idade, name='api_personagens_por_idade'),
    path('inscricao-sucesso/', views.inscricao_sucesso, name='inscricao_sucesso'),
]