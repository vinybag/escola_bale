from django.urls import path
from . import views


urlpatterns = [
    path('experimental/', views.agendar, name='agendar'),
    path('experimental/aluna/', views.agendar_aluna, name='agendar_aluna'),
    path('experimental/pagamento/<int:agendamento_id>/', views.agendamento_pagamento, name='agendamento_pagamento'),
    path('experimental/verificar-pix/<str:payment_id>/', views.verificar_pagamento_agendamento, name='verificar_pagamento_agendamento'),
    path('confirmacao/<int:agendamento_id>/', views.confirmacao, name='confirmacao'),
]
