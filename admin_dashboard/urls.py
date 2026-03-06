from django.urls import path
from django.http import HttpResponse

app_name = 'admin_dashboard'

def test_view(request):
    return HttpResponse("Admin Dashboard funcionando!")  # SEM EMOJI!

urlpatterns = [
    path('', test_view, name='test'),
]