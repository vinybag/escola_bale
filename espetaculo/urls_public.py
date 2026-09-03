from django.urls import path
from . import views

app_name = 'espetaculo'

urlpatterns = [
    # Página pública geral
    path('', views.espetaculos_lista_publica, name='lista_publica'),
    path('personagens/', views.personagens_publicos, name='personagens_publicos'),
    path('inscrever/', views.inscricao_audicao, name='inscricao_audicao'),
    path('api/personagens-por-idade/', views.get_personagens_por_idade, name='api_personagens_por_idade'),
    path('inscricao-sucesso/', views.inscricao_sucesso, name='inscricao_sucesso'),

    # Audições públicas
    path('audicao/nova/', views.audicao_nova_publica, name='audicao_nova_publica'),
    path('audicao/rosa-branca/', views.audicao_rosa_branca, name='audicao_rosa_branca'),
    path('audicao/rosa-branca/sucesso/', views.audicao_rosa_branca_sucesso, name='audicao_rosa_branca_sucesso'),

    # Evento público e ingressos
    path('evento/<int:pk>/', views.evento_detalhe_publico, name='evento_detalhe_publico'),
    path('espetaculos/<int:pk>/mapa/',views.mapa_assentos_publico,name='mapa_assentos_publico'),
    path('espetaculos/<int:pk>/mapa/selecionar/',views.assento_selecionar_api,name='assento_selecionar_api'),
    path('espetaculos/<int:pk>/mapa/confirmar/',views.confirmar_selecao_assentos,name='confirmar_selecao_assentos'),
    path('evento/<int:pk>/comprar/', views.comprar_ingresso, name='comprar_ingresso'),
    path('ingresso/pix/<int:pedido_id>/voltar/',views.voltar_do_pagamento_ingresso,name='voltar_do_pagamento_ingresso',),
    path('ingresso/pix/<int:pedido_id>/', views.pagar_ingresso_pix, name='pagar_ingresso_pix'),
    path('ingresso/verificar-pix/<str:payment_id>/', views.verificar_pagamento_ingresso_pix, name='verificar_pagamento_ingresso_pix'),
    path('ingresso/sucesso/<int:pedido_id>/', views.ingresso_sucesso, name='ingresso_sucesso'),
    path('ingressos/<int:ingresso_id>/imagem/', views.ver_imagem_ingresso, name='ver_imagem_ingresso'),
    path('ingressos/<int:ingresso_id>/baixar/', views.baixar_ingresso, name='baixar_ingresso'),
    path('ingressos/<int:ingresso_id>/baixar-qr/', views.baixar_qrcode_ingresso, name='baixar_qrcode_ingresso'),

        # Check-in
path(
    'checkin/login/',
    views.login_checkin,
    name='login_checkin',
),

path(
    'checkin/logout/',
    views.logout_checkin,
    name='logout_checkin',
),

path(
    'checkin/',
    views.selecionar_evento_checkin,
    name='selecionar_evento_checkin',
),

path(
    'evento/<int:pk>/checkin/',
    views.checkin_ingressos,
    name='checkin_ingressos',
),

path(
    'checkin/validar/',
    views.validar_ingresso_checkin,
    name='validar_ingresso_checkin',
),

    # Detalhe público genérico do espetáculo
    path('<int:pk>/', views.espetaculo_detalhes_publico, name='detalhes_publico'),
]