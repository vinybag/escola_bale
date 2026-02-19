from django.urls import path
from . import views

urlpatterns = [
    path('experimental/', views.agendar, name='agendar'),  # Mudei de 'agendar/' para 'experimental/'
    path('confirmacao/<int:agendamento_id>/', views.confirmacao, name='confirmacao'),
]
