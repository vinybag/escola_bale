from django.urls import include, path
from . import views

app_name = 'espetaculo'

urlpatterns = [
    path('home/', views.espetaculo_home, name='home'),
    path('', include('espetaculo.urls_public')),
    path('espetaculos/<int:pk>/mapa/',views.mapa_assentos_publico,name='mapa_assentos_publico'),
    path('espetaculos/<int:pk>/mapa/selecionar/',views.assento_selecionar_api,name='assento_selecionar_api'),
    path('espetaculos/<int:pk>/mapa/confirmar/',views.confirmar_selecao_assentos,name='confirmar_selecao_assentos'),
]