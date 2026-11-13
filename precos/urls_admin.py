from django.urls import path

from . import admin_views as v

app_name = 'precos_admin'

urlpatterns = [
    path('', v.regras, name='regras'),
    path('regras/nova/', v.regra_nova, name='regra_nova'),
    path('regras/<int:pk>/', v.regra_editar, name='regra_editar'),
    path('regras/<int:pk>/alternar/', v.regra_alternar, name='regra_alternar'),
    path('regras/<int:pk>/excluir/', v.regra_excluir, name='regra_excluir'),
    path('combinacoes/', v.combinacoes, name='combinacoes'),
    path('combinacoes/nova/', v.combinacao_nova, name='combinacao_nova'),
    path('combinacoes/<int:pk>/', v.combinacao_editar, name='combinacao_editar'),
    path('combinacoes/<int:pk>/alternar/', v.combinacao_alternar, name='combinacao_alternar'),
    path('combinacoes/<int:pk>/excluir/', v.combinacao_excluir, name='combinacao_excluir'),
    path('grupos/', v.grupos, name='grupos'),
    path('grupos/<int:pk>/', v.grupo_detalhe, name='grupo_detalhe'),
    path('parentescos/', v.graus, name='graus'),
    path('simulador/', v.simulador, name='simulador'),
    path('configuracao/', v.configuracao, name='configuracao'),
]
