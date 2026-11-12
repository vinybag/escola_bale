from django.urls import path

from . import admin_views as v

app_name = 'contratos_admin'

urlpatterns = [
    path('', v.lista, name='lista'),
    path('gerar-pendentes/', v.gerar_pendentes, name='gerar_pendentes'),
    path('modelos/', v.modelos, name='modelos'),
    path('modelos/<int:pk>/', v.modelo_detalhe, name='modelo_detalhe'),
    path('modelos/<int:pk>/pdf/', v.modelo_pdf, name='modelo_pdf'),
    path('bolsas/', v.bolsas, name='bolsas'),
    path('aluna/<int:aluna_id>/gerar/', v.gerar_para_aluna, name='gerar_para_aluna'),
    path('<int:pk>/', v.detalhe, name='detalhe'),
    path('<int:pk>/acao/', v.acao, name='acao'),
    path('<int:pk>/arquivo/<str:tipo>/', v.download, name='download'),
]
