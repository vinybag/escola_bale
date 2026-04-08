from django.urls import path, include
from . import views

urlpatterns = [
    # Páginas públicas existentes
    path('', views.home, name='home'),
    path('sobre/', views.sobre, name='sobre'),
    
    # NOVAS URLs públicas do espetáculo
    path('espetaculos/', include('espetaculo.urls_public')),
]