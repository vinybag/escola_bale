from django.urls import path

from . import admin_views as v

app_name = 'cantina_admin'

urlpatterns = [
    path('', v.lista, name='lista'),
    path('codigo/', v.buscar_codigo, name='buscar_codigo'),
    path('novo/', v.novo, name='novo'),
    path('<int:pk>/', v.editar, name='editar'),
    path('<int:pk>/ajustar/', v.ajustar, name='ajustar'),
    path('<int:pk>/alternar/', v.alternar, name='alternar'),
    path('<int:pk>/excluir/', v.excluir, name='excluir'),
    path('movimentacoes/', v.movimentacoes, name='movimentacoes'),
]
