from django.urls import path

from . import views

app_name = 'contratos'

urlpatterns = [
    path('', views.lista, name='lista'),
    path('<int:pk>/dados/', views.dados, name='dados'),
    path('<int:pk>/revisar/', views.revisar, name='revisar'),
    path('<int:pk>/pdf/<str:tipo>/', views.pdf, name='pdf'),
    path('<int:pk>/enviar-codigo/', views.enviar_codigo, name='enviar_codigo'),
    path('<int:pk>/assinar/', views.assinar, name='assinar'),
]
