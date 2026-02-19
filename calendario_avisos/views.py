from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from .models import Aviso

@login_required
def calendario(request):
    avisos = Aviso.objects.filter(ativo=True).order_by('-data_publicacao')
    return render(request, 'calendario_avisos/calendario.html', {'avisos': avisos})
