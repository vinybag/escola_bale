from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.utils import timezone
from .models import Aviso


@login_required
def calendario(request):
    hoje = timezone.localdate()
    busca = request.GET.get('busca', '').strip()
    tipo_data = request.GET.get('tipo_data', 'proximos')

    avisos = Aviso.objects.filter(ativo=True)

    if busca:
        avisos = avisos.filter(
            Q(titulo__icontains=busca) |
            Q(descricao__icontains=busca)
        )

    if tipo_data == 'passados':
        avisos = avisos.filter(data_evento__lt=hoje).order_by('-data_evento', '-data_publicacao')
    else:
        avisos = avisos.filter(data_evento__gte=hoje).order_by('data_evento', '-data_publicacao')

    return render(
        request,
        'calendario_avisos/calendario.html',
        {
            'avisos': avisos,
            'busca': busca,
            'tipo_data': tipo_data,
        }
    )