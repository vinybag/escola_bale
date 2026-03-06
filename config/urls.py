from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('admin-dashboard/', include('admin_dashboard.urls')),  # NOVO
    path('', include('core.urls')),
    path('conta/', include('usuarios.urls')),
    path('agenda/', include('agenda.urls')),
    path('pagamentos/', include('pagamentos.urls')),
    path('avisos/', include('calendario_avisos.urls')),  # NÃO ESQUECE!
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
