from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.utils import timezone
from .models import Aviso


def _turmas_ids_do_usuario(request):
    """
    Descobre quais turmas o usuário logado "representa": se ele for uma
    aluna adulta, usa a(s) turma(s) dela; se for responsável, usa a(s)
    turma(s) de todas as alunas vinculadas a ele.
    """
    from usuarios.models import Aluna

    alunas_do_usuario = Aluna.objects.filter(
        Q(usuario=request.user) | Q(responsavel=request.user),
        ativa=True,
    ).distinct()

    turmas_ids = set(
        alunas_do_usuario.values_list('turmas__id', flat=True)
    )
    turmas_ids.discard(None)

    alunas_ids = set(alunas_do_usuario.values_list('id', flat=True))

    return turmas_ids, alunas_ids


@login_required
def calendario(request):
    hoje = timezone.localdate()
    busca = request.GET.get('busca', '').strip()
    tipo_data = request.GET.get('tipo_data', 'proximos')

    avisos = Aviso.objects.filter(ativo=True)

    # Staff/admin sempre vê todos os avisos, sem filtro de destinatário.
    if not request.user.is_staff:
        turmas_ids, alunas_ids = _turmas_ids_do_usuario(request)

        avisos = avisos.filter(
            Q(turmas__isnull=True, alunas__isnull=True, professoras__isnull=True)
            | Q(turmas__id__in=turmas_ids)
            | Q(alunas__id__in=alunas_ids)
            | Q(professoras=request.user)
        ).distinct()

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
