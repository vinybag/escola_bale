from django.urls import path

from . import views

app_name = 'presenca'

urlpatterns = [
    path('<str:token>/', views.marcar_presenca, name='marcar'),
]
