from django.urls import include, path
from . import views

app_name = 'espetaculo'

urlpatterns = [
    path('home/', views.espetaculo_home, name='home'),
    path('', include('espetaculo.urls_public')),
]