from django.urls import path
from . import views

app_name = 'espetaculo'

urlpatterns = [
    path('', views.espetaculo_home, name='home'),
]