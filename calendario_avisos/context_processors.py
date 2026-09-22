from django.utils import timezone


def avisos_banner(request):
    """
    Deixa disponível, em toda página (para quem está logado), os
    avisos ativos com data futura (ou de hoje) que sejam relevantes
    para o usuário — reaproveitando a mesma lógica de destinatário
    usada na página de calendário.

    Isso é o que faz o aviso "aparecer assim que a pessoa loga ou
    entra no site", sem precisar navegar até uma página específica.
    """
    if not request.user.is_authenticated:
        return {}

    from django.db.models import Q
    from .models import Aviso
    from .views import _turmas_ids_do_usuario

    hoje = timezone.localdate()
    avisos = Aviso.objects.filter(ativo=True, data_evento__gte=hoje)

    if not request.user.is_staff:
        from espetaculo.models import Personagem

        turmas_ids, alunas_ids = _turmas_ids_do_usuario(request)
        personagens_ids = set(
            Personagem.objects.filter(elenco__aluna__id__in=alunas_ids)
            .values_list('id', flat=True)
        ) if alunas_ids else set()

        avisos = avisos.filter(
            Q(turmas__isnull=True, alunas__isnull=True, professoras__isnull=True, personagens__isnull=True)
            | Q(turmas__id__in=turmas_ids)
            | Q(alunas__id__in=alunas_ids)
            | Q(professoras=request.user)
            | Q(personagens__id__in=personagens_ids)
        ).distinct()

    avisos = avisos.order_by('data_evento')[:3]

    return {'avisos_banner': avisos}
