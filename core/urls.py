from django.urls import path, include
from . import demo, views

urlpatterns = [
    # Páginas públicas existentes
    path('', views.home, name='home'),
    path('sobre/', views.sobre, name='sobre'),

    # Demonstração (só funciona com DEMO_MODE ligado)
    path('demo/entrar/<str:quem>/', demo.entrar, name='demo_entrar'),

    # Configuração inicial (criação do primeiro admin, uso único)
    path('setup-inicial/<str:token>/', views.configuracao_inicial, name='setup_inicial'),

    # NOVAS URLs públicas do espetáculo
    path('espetaculos/', include('espetaculo.urls_public')),
]