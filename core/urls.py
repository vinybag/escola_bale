from django.urls import path
from . import views
from .criar_admin_view import criar_admin_secreto

urlpatterns = [
    path('', views.home, name='home'),
    path('sobre/', views.sobre, name='sobre'),
    path('criar-admin-secreto/', criar_admin_secreto),
]