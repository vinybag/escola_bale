from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('core.urls')),  # Páginas públicas (home, etc)
    path('agenda/', include('agenda.urls')),  # Agendamento experimental
    path('conta/', include('usuarios.urls')),  # Login, cadastro, perfil
    path('pagamentos/', include('pagamentos.urls')),  # Mensalidades
    path('avisos/', include('calendario_avisos.urls')),  # Calendário e avisos
]
