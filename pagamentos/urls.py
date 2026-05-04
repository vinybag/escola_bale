from django.urls import path
from . import views

urlpatterns = [
    path('mensalidades/', views.mensalidades, name='mensalidades'),
    path('pagar/<int:mensalidade_id>/', views.pagar, name='pagar'),
    path('pagar/cartao/<int:mensalidade_id>/', views.pagar_cartao, name='pagar_cartao'),
    path('pagar/pix/<int:mensalidade_id>/', views.pagar_pix, name='pagar_pix'),
    path('verificar-pix/<str:payment_id>/', views.verificar_pagamento_pix, name='verificar_pagamento_pix'),
    path('sucesso/', views.pagamento_sucesso, name='pagamento_sucesso'),
    path('cancelado/', views.pagamento_cancelado, name='pagamento_cancelado'),
    
    # Webhook do Asaas (não requer autenticação)
    path('webhook/asaas/', views.webhook_asaas, name='webhook_asaas'),
]