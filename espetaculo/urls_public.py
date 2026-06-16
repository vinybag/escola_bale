from django.urls import path
from . import views

app_name = 'espetaculo'

urlpatterns = [
    path('', views.espetaculos_lista_publica, name='lista_publica'),
    path('personagens/', views.personagens_publicos, name='personagens_publicos'),
    path('inscrever/', views.inscricao_audicao, name='inscricao_audicao'),
    path('api/personagens-por-idade/', views.get_personagens_por_idade, name='api_personagens_por_idade'),
    path('inscricao-sucesso/', views.inscricao_sucesso, name='inscricao_sucesso'),

    path('audicao/nova/', views.audicao_nova_publica, name='audicao_nova_publica'),
    path('audicao/rosa-branca/', views.audicao_rosa_branca, name='audicao_rosa_branca'),
    path('audicao/rosa-branca/sucesso/', views.audicao_rosa_branca_sucesso, name='audicao_rosa_branca_sucesso'),

    path('evento/<int:pk>/', views.evento_detalhe_publico, name='evento_detalhe_publico'),
    path('evento/<int:pk>/comprar/', views.comprar_ingresso, name='comprar_ingresso'),
    path('ingresso/pix/<int:pedido_id>/', views.pagar_ingresso_pix, name='pagar_ingresso_pix'),
    path('ingresso/verificar-pix/<str:payment_id>/', views.verificar_pagamento_ingresso_pix, name='verificar_pagamento_ingresso_pix'),
    path('ingresso/sucesso/<int:pedido_id>/', views.ingresso_sucesso, name='ingresso_sucesso'),

    path('<int:pk>/', views.espetaculo_detalhes_publico, name='detalhes_publico'),
]