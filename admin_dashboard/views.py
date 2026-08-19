from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from datetime import datetime
from decimal import Decimal
from django.utils import timezone
from django.db.models import Sum
from django.db import models
from django.db.models import Case, When, Value, IntegerField
from django.conf import settings
from espetaculo.models import Espetaculo, PedidoIngressoEvento
from django.db.models import Q
from datetime import date, timedelta


from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import redirect, render
from django.utils import timezone

from pagamentos.models import Mensalidade
from usuarios.models import Aluna, Turma


@login_required
def dashboard(request):
    """Dashboard com dados reais do banco e gráficos."""

    if not request.user.is_staff:
        return redirect("home")

    meses_pt = {
        1: "Janeiro",
        2: "Fevereiro",
        3: "Março",
        4: "Abril",
        5: "Maio",
        6: "Junho",
        7: "Julho",
        8: "Agosto",
        9: "Setembro",
        10: "Outubro",
        11: "Novembro",
        12: "Dezembro",
    }

    hoje = timezone.localdate()
    mes = hoje.month
    ano = hoje.year

    mes_atual = f"{meses_pt[mes]} {ano}"

    total_alunas = Aluna.objects.filter(
        ativa=True,
    ).count()

    total_turmas = Turma.objects.filter(
        ativa=True,
    ).count()

    mensalidades_mes = Mensalidade.objects.filter(
        mes_referencia__month=mes,
        mes_referencia__year=ano,
    )

    mensalidades_pagas_qs = mensalidades_mes.filter(
        status="pago",
    )

    mensalidades_pagas = mensalidades_pagas_qs.count()

    total_recebido = (
        mensalidades_pagas_qs.aggregate(
            total=Sum("valor"),
        )["total"]
        or Decimal("0.00")
    )

    mensalidades_pendentes_qs = (
        mensalidades_mes
        .filter(
            data_vencimento__gte=hoje,
            data_pagamento__isnull=True,
        )
        .exclude(
            status__in=[
                "pago",
                "cancelado",
            ],
        )
    )

    mensalidades_pendentes = (
        mensalidades_pendentes_qs.count()
    )

    mensalidades_atrasadas_qs = (
        mensalidades_mes
        .filter(
            data_vencimento__lt=hoje,
            data_pagamento__isnull=True,
        )
        .exclude(
            status__in=[
                "pago",
                "cancelado",
            ],
        )
    )

    mensalidades_atrasadas = (
        mensalidades_atrasadas_qs.count()
    )

    mensalidades_em_aberto_qs = (
        mensalidades_mes
        .filter(
            data_pagamento__isnull=True,
        )
        .exclude(
            status__in=[
                "pago",
                "cancelado",
            ],
        )
    )

    total_a_receber = (
        mensalidades_pendentes_qs.aggregate(
            total=Sum("valor"),
        )["total"]
        or Decimal("0.00")
    )

    total_atrasado = Decimal("0.00")

    for mensalidade in mensalidades_atrasadas_qs:
        try:
            total_atrasado += Decimal(
                str(mensalidade.valor_atualizado)
            )
        except (
            AttributeError,
            TypeError,
            ValueError,
        ):
            total_atrasado += (
                mensalidade.valor
                or Decimal("0.00")
            )

    total_em_aberto = (
        total_atrasado + total_a_receber
    )

    faturamento_meses = []
    faturamento_valores = []

    primeiro_dia_mes_atual = hoje.replace(day=1)

    for quantidade_meses_atras in range(5, -1, -1):
        mes_calculado = primeiro_dia_mes_atual

        for _ in range(quantidade_meses_atras):
            mes_anterior = (
                mes_calculado.replace(day=1)
                - timedelta(days=1)
            )

            mes_calculado = mes_anterior.replace(day=1)

        valor_mes = (
            Mensalidade.objects
            .filter(
                mes_referencia__month=mes_calculado.month,
                mes_referencia__year=mes_calculado.year,
                status="pago",
            )
            .aggregate(
                total=Sum("valor"),
            )["total"]
            or Decimal("0.00")
        )

        faturamento_meses.append(
            (
                f"{meses_pt[mes_calculado.month][:3]}/"
                f"{str(mes_calculado.year)[2:]}"
            )
        )

        faturamento_valores.append(
            float(valor_mes)
        )

    turmas_labels = []
    turmas_valores = []

    turmas = Turma.objects.filter(
        ativa=True,
    ).order_by("nome")

    for turma in turmas:
        total_alunas_turma = Aluna.objects.filter(
            turmas=turma,
            ativa=True,
        ).count()

        if total_alunas_turma > 0:
            turmas_labels.append(turma.nome)
            turmas_valores.append(total_alunas_turma)

    status_labels = [
        "Pagas",
        "Pendentes",
        "Atrasadas",
    ]

    status_valores = [
        mensalidades_pagas,
        mensalidades_pendentes,
        mensalidades_atrasadas,
    ]

    context = {
        "total_alunas": total_alunas,
        "total_turmas": total_turmas,
        "total_recebido": total_recebido,
        "mensalidades_pendentes": mensalidades_pendentes,
        "mensalidades_atrasadas": mensalidades_atrasadas,
        "mensalidades_pagas": mensalidades_pagas,
        "total_a_receber": total_a_receber,
        "total_atrasado": total_atrasado,
        "total_em_aberto": total_em_aberto,
        "mes_atual": mes_atual,
        "faturamento_meses": faturamento_meses,
        "faturamento_valores": faturamento_valores,
        "turmas_labels": turmas_labels,
        "turmas_valores": turmas_valores,
        "status_labels": status_labels,
        "status_valores": status_valores,
    }

    return render(
        request,
        "admin_dashboard/dashboard.html",
        context,
    )

@login_required
def alunas_list(request):
    """Lista de todas as alunas com busca e filtros"""

    if not request.user.is_staff:
        return redirect('home')

    try:
        from usuarios.models import Aluna, Turma
        from django.db.models import Q

        alunas = Aluna.objects.select_related('responsavel', 'usuario').prefetch_related('turmas').all()

        busca = request.GET.get('busca', '')
        if busca:
            alunas = alunas.filter(
                Q(nome__icontains=busca) |
                Q(responsavel__first_name__icontains=busca) |
                Q(responsavel__last_name__icontains=busca) |
                Q(usuario__first_name__icontains=busca) |
                Q(usuario__last_name__icontains=busca) |
                Q(usuario__email__icontains=busca)
            )

        turma = request.GET.get('turma', '')
        if turma:
            alunas = alunas.filter(turmas__nome=turma)

        status = request.GET.get('status', '')
        if status == 'ativas':
            alunas = alunas.filter(ativa=True)
        elif status == 'inativas':
            alunas = alunas.filter(ativa=False)

        alunas = alunas.distinct().order_by('nome')
        turmas = Turma.objects.filter(ativa=True).values_list('nome', flat=True).distinct()

    except Exception as e:
        print(f"Erro ao buscar alunas: {e}")
        import traceback
        traceback.print_exc()
        alunas = []
        turmas = []
        busca = ''
        turma = ''
        status = ''

    context = {
        'alunas': alunas,
        'turmas': turmas,
        'busca': busca,
        'turma_filtro': turma,
        'status_filtro': status,
        'total_alunas': len(alunas) if alunas else 0,
    }

    return render(request, 'admin_dashboard/alunas/list.html', context)

@login_required
def aluna_criar(request):
    """Criar nova aluna (infantil com responsável existente ou adulta com usuário existente)"""

    if not request.user.is_staff:
        return redirect('home')

    from decimal import Decimal, InvalidOperation
    from django.contrib import messages
    from django.contrib.auth.models import User
    from usuarios.models import Aluna, Turma, Perfil

    if request.method == 'POST':
        try:
            nome = request.POST.get('nome', '').strip()
            genero = request.POST.get('genero') or None
            data_nascimento = request.POST.get('data_nascimento') or None
            turmas_ids = request.POST.getlist('turmas')
            ativa = request.POST.get('ativa') == 'on'
            observacoes = request.POST.get('observacoes', '').strip()
            tipo_aluna = request.POST.get('tipo_aluna', 'infantil')

            responsavel_id = request.POST.get('responsavel', '').strip()
            usuario_id = request.POST.get('usuario', '').strip()
            cpf = request.POST.get('cpf', '').strip()
            telefone_aluna = request.POST.get('telefone_aluna', '').strip()

            valor_mensalidade = request.POST.get('valor_mensalidade')
            dia_vencimento = request.POST.get('dia_vencimento') or 10
            gerar_mensalidade_automatica = request.POST.get('gerar_mensalidade_automatica') == 'on'

            if not nome:
                messages.error(request, 'O nome da aluna é obrigatório!')
                return redirect('admin_dashboard:aluna_criar')

            valor_mensalidade_decimal = None
            if valor_mensalidade:
                try:
                    valor_mensalidade_decimal = Decimal(valor_mensalidade)
                    if valor_mensalidade_decimal < 0:
                        messages.error(request, 'O valor da mensalidade não pode ser negativo!')
                        return redirect('admin_dashboard:aluna_criar')
                except (InvalidOperation, ValueError):
                    messages.error(request, 'Informe um valor de mensalidade válido!')
                    return redirect('admin_dashboard:aluna_criar')

            try:
                dia_vencimento = int(dia_vencimento)
                if dia_vencimento < 1 or dia_vencimento > 31:
                    messages.error(request, 'O dia de vencimento deve estar entre 1 e 31!')
                    return redirect('admin_dashboard:aluna_criar')
            except (TypeError, ValueError):
                messages.error(request, 'Informe um dia de vencimento válido!')
                return redirect('admin_dashboard:aluna_criar')

            responsavel = None
            usuario = None

            if tipo_aluna == 'infantil':
                if not responsavel_id:
                    messages.error(request, 'Selecione um responsável!')
                    return redirect('admin_dashboard:aluna_criar')

                try:
                    responsavel = User.objects.get(
                        id=responsavel_id,
                        is_staff=False,
                        perfil__is_responsavel=True
                    )
                except User.DoesNotExist:
                    messages.error(request, 'Responsável inválido!')
                    return redirect('admin_dashboard:aluna_criar')

                if cpf:
                    perfil, created = Perfil.objects.get_or_create(
                        user=responsavel,
                        defaults={'telefone': '', 'is_responsavel': True}
                    )
                    perfil.cpf = cpf
                    perfil.is_responsavel = True
                    perfil.save()

            else:
                if not usuario_id:
                    messages.error(request, 'Selecione o usuário da aluna adulta!')
                    return redirect('admin_dashboard:aluna_criar')

                try:
                    usuario = User.objects.get(
                        id=usuario_id,
                        is_staff=False
                    )
                except User.DoesNotExist:
                    messages.error(request, 'Usuário da aluna adulta inválido!')
                    return redirect('admin_dashboard:aluna_criar')

                perfil, created = Perfil.objects.get_or_create(
                    user=usuario,
                    defaults={
                        'telefone': '',
                        'cpf': cpf or None,
                        'is_responsavel': False
                    }
                )
                if cpf:
                    perfil.cpf = cpf
                if telefone_aluna:
                    perfil.telefone = telefone_aluna
                perfil.is_responsavel = False
                perfil.save()

            turmas_selecionadas = []
            for turma_id in turmas_ids:
                try:
                    turma = Turma.objects.get(id=turma_id, ativa=True)
                    turmas_selecionadas.append(turma)
                except Turma.DoesNotExist:
                    pass

            aluna = Aluna.objects.create(
                nome=nome,
                genero=genero,
                data_nascimento=data_nascimento,
                responsavel=responsavel,
                usuario=usuario,
                tipo_aluna=tipo_aluna,
                ativa=ativa,
                observacoes=observacoes,
                valor_mensalidade=valor_mensalidade_decimal,
                dia_vencimento=dia_vencimento,
                gerar_mensalidade_automatica=gerar_mensalidade_automatica,
            )

            aluna.turmas.set(turmas_selecionadas)

            messages.success(request, f'Aluna {nome} criada com sucesso!')
            return redirect('admin_dashboard:alunas_list')

        except Exception as e:
            messages.error(request, f'Erro ao criar aluna: {e}')
            print(f"Erro detalhado: {e}")
            import traceback
            traceback.print_exc()
            return redirect('admin_dashboard:aluna_criar')

    try:
        responsaveis = User.objects.filter(
            is_staff=False,
            perfil__is_responsavel=True
        ).order_by('first_name', 'last_name', 'username')

        usuarios_adultas = User.objects.filter(
            is_staff=False
        ).exclude(
            aluna_vinculada__isnull=False
        ).order_by('first_name', 'last_name', 'username')

        turmas = Turma.objects.filter(ativa=True).order_by('nome')

    except Exception as e:
        print(f"Erro ao buscar dados: {e}")
        responsaveis = []
        usuarios_adultas = []
        turmas = []

    context = {
        'responsaveis': responsaveis,
        'usuarios_adultas': usuarios_adultas,
        'turmas': turmas,
    }

    return render(request, 'admin_dashboard/alunas/criar.html', context)

@login_required
def aluna_detalhes(request, pk):
    """Detalhes de uma aluna"""

    if not request.user.is_staff:
        return redirect('home')

    try:
        from decimal import Decimal
        from usuarios.models import Aluna
        from pagamentos.models import Mensalidade
        from django.db.models import Sum
        from django.contrib import messages

        aluna = Aluna.objects.select_related(
            'responsavel',
            'usuario'
        ).prefetch_related(
            'turmas'
        ).get(pk=pk)

        mensalidades = Mensalidade.objects.filter(aluna=aluna).order_by('-mes_referencia')

        total_pago = mensalidades.filter(status='pago').aggregate(
            total=Sum('valor')
        )['total'] or Decimal('0.00')

        total_pendente = mensalidades.filter(status='pendente').count()

    except Exception as e:
        from django.contrib import messages
        messages.error(request, f'Aluna nao encontrada: {e}')
        return redirect('admin_dashboard:alunas_list')

    context = {
        'aluna': aluna,
        'mensalidades': mensalidades[:12],
        'total_pago': total_pago,
        'total_pendente': total_pendente,
    }

    return render(request, 'admin_dashboard/alunas/detalhes.html', context)


@login_required
def aluna_editar(request, pk):
    """Editar aluna existente."""

    if not request.user.is_staff:
        return redirect('home')

    from django.contrib import messages
    from django.contrib.auth.models import User
    from django.db.models import Q
    from django.shortcuts import get_object_or_404, redirect, render
    from decimal import Decimal, InvalidOperation

    from usuarios.models import Aluna, Perfil, Turma

    aluna = get_object_or_404(
        Aluna.objects.select_related('responsavel', 'usuario'),
        pk=pk
    )

    if request.method == 'POST':
        try:
            aluna.nome = request.POST.get('nome', '').strip()
            aluna.genero = request.POST.get('genero') or None
            aluna.data_nascimento = request.POST.get('data_nascimento') or None
            aluna.ativa = request.POST.get('ativa') == 'on'
            aluna.observacoes = request.POST.get('observacoes', '').strip()
            aluna.tipo_aluna = request.POST.get('tipo_aluna') or aluna.tipo_aluna

            if not aluna.nome:
                messages.error(request, 'O nome da aluna é obrigatório.')
                return redirect(
                    'admin_dashboard:aluna_editar',
                    pk=pk
                )

            valor_mensalidade = request.POST.get('valor_mensalidade', '').strip()
            dia_vencimento = request.POST.get('dia_vencimento') or 10
            gerar_mensalidade_automatica = (
                request.POST.get('gerar_mensalidade_automatica') == 'on'
            )

            if valor_mensalidade:
                try:
                    valor_mensalidade_decimal = Decimal(valor_mensalidade)

                    if valor_mensalidade_decimal < 0:
                        messages.error(
                            request,
                            'O valor da mensalidade não pode ser negativo.'
                        )
                        return redirect(
                            'admin_dashboard:aluna_editar',
                            pk=pk
                        )

                    aluna.valor_mensalidade = valor_mensalidade_decimal

                except (InvalidOperation, ValueError):
                    messages.error(
                        request,
                        'Informe um valor de mensalidade válido.'
                    )
                    return redirect(
                        'admin_dashboard:aluna_editar',
                        pk=pk
                    )
            else:
                aluna.valor_mensalidade = None

            try:
                dia_vencimento = int(dia_vencimento)

                if dia_vencimento < 1 or dia_vencimento > 31:
                    messages.error(
                        request,
                        'O dia de vencimento deve estar entre 1 e 31.'
                    )
                    return redirect(
                        'admin_dashboard:aluna_editar',
                        pk=pk
                    )

                aluna.dia_vencimento = dia_vencimento

            except (TypeError, ValueError):
                messages.error(
                    request,
                    'Informe um dia de vencimento válido.'
                )
                return redirect(
                    'admin_dashboard:aluna_editar',
                    pk=pk
                )

            aluna.gerar_mensalidade_automatica = (
                gerar_mensalidade_automatica
            )

            responsavel_id = request.POST.get('responsavel', '').strip()
            usuario_id = request.POST.get('usuario', '').strip()
            telefone_aluna = request.POST.get(
                'telefone_aluna',
                ''
            ).strip()
            cpf = request.POST.get('cpf', '').strip()

            if aluna.tipo_aluna == 'adulto':
                aluna.responsavel = None

                if usuario_id:
                    try:
                        usuario = User.objects.get(
                            id=usuario_id,
                            is_staff=False
                        )
                    except User.DoesNotExist:
                        messages.error(
                            request,
                            'Usuário selecionado não foi encontrado.'
                        )
                        return redirect(
                            'admin_dashboard:aluna_editar',
                            pk=pk
                        )

                    conflito = (
                        Aluna.objects
                        .filter(usuario=usuario)
                        .exclude(pk=aluna.pk)
                        .exists()
                    )

                    if conflito:
                        messages.error(
                            request,
                            'Este usuário já está vinculado a outra aluna.'
                        )
                        return redirect(
                            'admin_dashboard:aluna_editar',
                            pk=pk
                        )

                    aluna.usuario = usuario

                    perfil_aluna, _ = Perfil.objects.get_or_create(
                        user=usuario,
                        defaults={
                            'telefone': '',
                            'is_responsavel': False,
                        }
                    )

                    perfil_aluna.telefone = telefone_aluna
                    perfil_aluna.is_responsavel = False
                    perfil_aluna.save()

                else:
                    aluna.usuario = None

            else:
                aluna.usuario = None

                if responsavel_id:
                    try:
                        aluna.responsavel = User.objects.get(
                            id=responsavel_id,
                            is_staff=False
                        )
                    except User.DoesNotExist:
                        messages.error(
                            request,
                            'Responsável selecionado não foi encontrado.'
                        )
                        return redirect(
                            'admin_dashboard:aluna_editar',
                            pk=pk
                        )
                else:
                    aluna.responsavel = None

            if aluna.responsavel:
                perfil_responsavel, _ = Perfil.objects.get_or_create(
                    user=aluna.responsavel,
                    defaults={
                        'telefone': '',
                        'is_responsavel': True,
                    }
                )

                perfil_responsavel.cpf = cpf
                perfil_responsavel.is_responsavel = True
                perfil_responsavel.save()

            turmas_ids = request.POST.getlist('turmas')
            turmas_selecionadas = []

            for turma_id in turmas_ids:
                try:
                    turma = Turma.objects.get(
                        id=turma_id,
                        ativa=True
                    )
                    turmas_selecionadas.append(turma)
                except Turma.DoesNotExist:
                    pass

            aluna.save()
            aluna.turmas.set(turmas_selecionadas)

            messages.success(
                request,
                f'Aluna {aluna.nome} atualizada com sucesso!'
            )

            return redirect(
                'admin_dashboard:aluna_detalhes',
                pk=aluna.pk
            )

        except Exception as e:
            messages.error(
                request,
                f'Erro ao atualizar aluna: {e}'
            )
            print(f'Erro detalhado ao atualizar aluna: {e}')

            import traceback
            traceback.print_exc()

            return redirect(
                'admin_dashboard:aluna_editar',
                pk=pk
            )

    try:
        responsaveis = (
            User.objects
            .filter(
                is_staff=False,
                perfil__is_responsavel=True
            )
            .order_by('first_name', 'last_name', 'username')
        )

        usuarios_adultas = (
            User.objects
            .filter(is_staff=False)
            .exclude(aluna_vinculada__isnull=False)
        )

        if aluna.usuario_id:
            usuarios_adultas = (
                User.objects
                .filter(
                    Q(is_staff=False) &
                    (
                        Q(aluna_vinculada__isnull=True) |
                        Q(id=aluna.usuario_id)
                    )
                )
                .order_by('first_name', 'last_name', 'username')
            )
        else:
            usuarios_adultas = usuarios_adultas.order_by(
                'first_name',
                'last_name',
                'username'
            )

        turmas = (
            Turma.objects
            .filter(ativa=True)
            .order_by('nome')
        )

        perfil_responsavel = None
        if aluna.responsavel_id:
            perfil_responsavel = (
                Perfil.objects
                .filter(user_id=aluna.responsavel_id)
                .first()
            )

        perfil_aluna = None
        if aluna.usuario_id:
            perfil_aluna = (
                Perfil.objects
                .filter(user_id=aluna.usuario_id)
                .first()
            )

        if aluna.valor_mensalidade is not None:
            valor_mensalidade_str = (
                f'{aluna.valor_mensalidade:.2f}'
            )
        else:
            valor_mensalidade_str = ''

    except Exception as e:
        print(f'Erro ao buscar dados da edição: {e}')

        responsaveis = []
        usuarios_adultas = []
        turmas = []
        perfil_responsavel = None
        perfil_aluna = None
        valor_mensalidade_str = ''

    context = {
        'aluna': aluna,
        'responsaveis': responsaveis,
        'usuarios_adultas': usuarios_adultas,
        'turmas': turmas,
        'perfil': perfil_responsavel,
        'perfil_aluna': perfil_aluna,
        'valor_mensalidade_str': valor_mensalidade_str,
    }

    return render(
        request,
        'admin_dashboard/alunas/editar.html',
        context
    )

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404, redirect, render

from usuarios.models import Aluna


@login_required
def aluna_definir_senha(request, pk):
    if not request.user.is_staff:
        return redirect('home')

    aluna = get_object_or_404(Aluna, pk=pk)

    if aluna.tipo_aluna != 'adulto':
        messages.error(request, 'Apenas alunas adultas com login próprio podem ter senha definida por aqui.')
        return redirect('admin_dashboard:alunas_list')

    if not aluna.usuario:
        messages.error(request, 'Esta aluna adulta ainda não possui um usuário vinculado.')
        return redirect('admin_dashboard:alunas_list')

    if request.method == 'POST':
        senha = request.POST.get('senha', '').strip()
        confirmar_senha = request.POST.get('confirmar_senha', '').strip()

        if not senha or not confirmar_senha:
            messages.error(request, 'Preencha os dois campos de senha.')
        elif senha != confirmar_senha:
            messages.error(request, 'As senhas não coincidem.')
        elif len(senha) < 6:
            messages.error(request, 'A senha deve ter pelo menos 6 caracteres.')
        else:
            usuario = aluna.usuario
            usuario.set_password(senha)
            usuario.save()
            messages.success(request, f'Senha da aluna {aluna.nome} atualizada com sucesso.')
            return redirect('admin_dashboard:alunas_list')

    context = {
        'aluna': aluna,
    }
    return render(request, 'admin_dashboard/alunas/definir_senha.html', context)

@login_required
def mensalidades_list(request):
    if not request.user.is_staff:
        return redirect('home')

    try:
        from pagamentos.models import Mensalidade
        from django.db.models import Q
        from django.utils import timezone

        hoje = timezone.localdate()

        mensalidades_qs = Mensalidade.objects.select_related(
            'aluna',
            'aluna__responsavel'
        ).all()

        busca = request.GET.get('busca', '').strip()
        if busca:
            mensalidades_qs = mensalidades_qs.filter(
                Q(aluna__nome__icontains=busca) |
                Q(aluna__responsavel__first_name__icontains=busca) |
                Q(aluna__responsavel__last_name__icontains=busca)
            )

        mes = request.GET.get('mes', '').strip()

        if mes:
            mensalidades_qs = mensalidades_qs.filter(
                mes_referencia__month=mes
            )
        else:
            mensalidades_qs = mensalidades_qs.filter(
                mes_referencia__month=hoje.month,
                mes_referencia__year=hoje.year
            )
            mes = str(hoje.month)

        mensalidades_qs = mensalidades_qs.order_by('-mes_referencia', 'aluna__nome')

        mensalidades = list(mensalidades_qs)

        status = request.GET.get('status', '').strip()
        if status:
            mensalidades = [m for m in mensalidades if m.status_atual == status]

    except Exception as e:
        print(f"Erro ao buscar mensalidades: {e}")
        mensalidades = []
        busca = ''
        status = ''
        mes = ''

    context = {
        'mensalidades': mensalidades,
        'busca': busca,
        'status_filtro': status,
        'mes_filtro': mes,
        'total_mensalidades': len(mensalidades),
    }

    return render(request, 'admin_dashboard/mensalidades/list.html', context)


from decimal import Decimal, InvalidOperation
from datetime import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.shortcuts import redirect, render

from pagamentos.models import Mensalidade
from usuarios.models import Aluna


@login_required
def mensalidade_criar(request):
    """Criar mensalidade manual"""

    if not request.user.is_staff:
        return redirect('home')

    def get_alunas():
        return Aluna.objects.filter(ativa=True).order_by('nome')

    def resolver_responsavel_financeiro(aluna):
        if aluna.responsavel:
            return aluna.responsavel

        if aluna.tipo_aluna == 'adulto' and aluna.usuario:
            return aluna.usuario

        return None

    if request.method == 'POST':
        aluna_id = (request.POST.get('aluna') or '').strip()
        mes_referencia = (request.POST.get('mes_referencia') or '').strip()
        data_vencimento = (request.POST.get('data_vencimento') or '').strip()
        valor = (request.POST.get('valor') or '').strip()
        status = (request.POST.get('status') or 'pendente').strip()

        alunas = get_alunas()

        context = {
            'alunas': alunas,
            'form_data': {
                'aluna': aluna_id,
                'mes_referencia': mes_referencia,
                'data_vencimento': data_vencimento,
                'valor': valor,
                'status': status or 'pendente',
            }
        }

        if not all([aluna_id, mes_referencia, data_vencimento, valor]):
            messages.error(request, 'Preencha todos os campos obrigatórios.')
            return render(request, 'admin_dashboard/mensalidades/criar.html', context)

        try:
            aluna = Aluna.objects.get(id=aluna_id, ativa=True)
        except Aluna.DoesNotExist:
            messages.error(request, 'Aluna não encontrada ou inativa.')
            return render(request, 'admin_dashboard/mensalidades/criar.html', context)

        responsavel_financeiro = resolver_responsavel_financeiro(aluna)

        if not responsavel_financeiro:
            if aluna.tipo_aluna == 'infantil':
                mensagem = (
                    f'Não foi possível criar a mensalidade de {aluna.nome}, '
                    'pois ela é infantil e não possui responsável vinculado.'
                )
            else:
                mensagem = (
                    f'Não foi possível criar a mensalidade de {aluna.nome}, '
                    'pois ela não possui responsável financeiro nem usuário próprio vinculado.'
                )

            messages.error(request, mensagem)
            return render(request, 'admin_dashboard/mensalidades/criar.html', context)

        try:
            mes_ref_date = datetime.strptime(f'{mes_referencia}-01', '%Y-%m-%d').date()
        except ValueError:
            messages.error(request, 'Mês de referência inválido.')
            return render(request, 'admin_dashboard/mensalidades/criar.html', context)

        try:
            data_venc_date = datetime.strptime(data_vencimento, '%Y-%m-%d').date()
        except ValueError:
            messages.error(request, 'Data de vencimento inválida.')
            return render(request, 'admin_dashboard/mensalidades/criar.html', context)

        try:
            valor_decimal = Decimal(valor)
        except (InvalidOperation, TypeError):
            messages.error(request, 'Valor inválido para a mensalidade.')
            return render(request, 'admin_dashboard/mensalidades/criar.html', context)

        if valor_decimal <= 0:
            messages.error(request, 'O valor da mensalidade deve ser maior que zero.')
            return render(request, 'admin_dashboard/mensalidades/criar.html', context)

        if status not in ['pendente', 'pago', 'atrasado', 'cancelado']:
            messages.error(request, 'Status inválido.')
            return render(request, 'admin_dashboard/mensalidades/criar.html', context)

        mensalidade_existente = Mensalidade.objects.filter(
            aluna=aluna,
            mes_referencia=mes_ref_date
        ).first()

        if mensalidade_existente:
            messages.error(
                request,
                f'Já existe uma mensalidade para {aluna.nome} no mês {mes_ref_date.strftime("%m/%Y")}.'
            )
            return render(request, 'admin_dashboard/mensalidades/criar.html', context)

        try:
            mensalidade = Mensalidade.objects.create(
                aluna=aluna,
                responsavel=responsavel_financeiro,
                mes_referencia=mes_ref_date,
                data_vencimento=data_venc_date,
                valor=valor_decimal,
                status=status,
            )
        except IntegrityError:
            messages.error(
                request,
                f'Não foi possível criar a mensalidade de {aluna.nome}. Verifique se já existe uma mensalidade para esse mês.'
            )
            return render(request, 'admin_dashboard/mensalidades/criar.html', context)

        messages.success(
            request,
            f'Mensalidade criada com sucesso para {mensalidade.aluna.nome}.'
        )
        return redirect('admin_dashboard:mensalidades_list')

    try:
        alunas = Aluna.objects.filter(ativa=True).order_by('nome')
    except Exception as e:
        print(f"Erro ao buscar alunas: {e}")
        alunas = []

    context = {
        'alunas': alunas,
        'form_data': {
            'aluna': '',
            'mes_referencia': '',
            'data_vencimento': '',
            'valor': '',
            'status': 'pendente',
        }
    }

    return render(request, 'admin_dashboard/mensalidades/criar.html', context)

@login_required
def avisos_list(request):
    """Lista de avisos"""

    if not request.user.is_staff:
        return redirect('home')

    try:
        from calendario_avisos.models import Aviso

        hoje = timezone.localdate()
        busca = request.GET.get('busca', '').strip()
        tipo = request.GET.get('tipo', '').strip()
        tipo_data = request.GET.get('tipo_data', 'proximos')

        avisos = Aviso.objects.all()

        if busca:
            avisos = avisos.filter(
                Q(titulo__icontains=busca) |
                Q(descricao__icontains=busca)
            )

        if tipo:
            avisos = avisos.filter(tipo=tipo)

        if tipo_data == 'passados':
            avisos = avisos.filter(
                data_evento__lt=hoje
            ).order_by('-data_evento', '-data_publicacao')
        else:
            avisos = avisos.filter(
                data_evento__gte=hoje
            ).order_by('data_evento', '-data_publicacao')

        total_avisos = avisos.count()

    except Exception as e:
        print(f"Erro ao buscar avisos: {e}")
        import traceback
        traceback.print_exc()
        avisos = []
        busca = ''
        tipo = ''
        tipo_data = 'proximos'
        total_avisos = 0

    context = {
        'avisos': avisos,
        'busca': busca,
        'tipo_filtro': tipo,
        'tipo_data': tipo_data,
        'total_avisos': total_avisos,
    }

    return render(request, 'admin_dashboard/avisos/list.html', context)


@login_required
def aviso_criar(request):
    """Criar novo aviso"""
    
    if not request.user.is_staff:
        return redirect('home')
    
    if request.method == 'POST':
        try:
            from calendario_avisos.models import Aviso
            from django.contrib import messages
            
            # Pega dados do form
            titulo = request.POST.get('titulo')
            descricao = request.POST.get('descricao')
            data_evento = request.POST.get('data_evento')
            tipo = request.POST.get('tipo', 'geral')
            
            # Validacao
            if not all([titulo, descricao, data_evento]):
                messages.error(request, 'Preencha todos os campos obrigatorios!')
                return redirect('admin_dashboard:aviso_criar')
            
            # Cria aviso
            aviso = Aviso.objects.create(
                titulo=titulo,
                descricao=descricao,
                data_evento=data_evento,
                tipo=tipo
            )
            
            messages.success(request, f'Aviso "{titulo}" criado com sucesso!')
            return redirect('admin_dashboard:avisos_list')
            
        except Exception as e:
            from django.contrib import messages
            messages.error(request, f'Erro ao criar aviso: {e}')
            print(f"Erro detalhado: {e}")
            import traceback
            traceback.print_exc()
            return redirect('admin_dashboard:aviso_criar')
    
    # GET - mostra form
    context = {}
    return render(request, 'admin_dashboard/avisos/criar.html', context)


@login_required
def aviso_editar(request, pk):
    """Editar aviso existente"""
    
    if not request.user.is_staff:
        return redirect('home')
    
    try:
        from calendario_avisos.models import Aviso
        aviso = Aviso.objects.get(pk=pk)
    except Exception as e:
        from django.contrib import messages
        messages.error(request, f'Aviso nao encontrado: {e}')
        return redirect('admin_dashboard:avisos_list')
    
    if request.method == 'POST':
        try:
            from django.contrib import messages
            
            # Atualiza dados
            aviso.titulo = request.POST.get('titulo')
            aviso.descricao = request.POST.get('descricao')
            aviso.data_evento = request.POST.get('data_evento')
            aviso.tipo = request.POST.get('tipo', 'geral')
            
            aviso.save()
            
            messages.success(request, f'Aviso "{aviso.titulo}" atualizado com sucesso!')
            return redirect('admin_dashboard:avisos_list')
            
        except Exception as e:
            from django.contrib import messages
            messages.error(request, f'Erro ao atualizar aviso: {e}')
            return redirect('admin_dashboard:aviso_editar', pk=pk)
    
    # GET - mostra form preenchido
    context = {
        'aviso': aviso,
    }
    
    return render(request, 'admin_dashboard/avisos/editar.html', context)


@login_required
def aviso_excluir(request, pk):
    """Excluir aviso"""
    
    if not request.user.is_staff:
        return redirect('home')
    
    if request.method == 'POST':
        try:
            from calendario_avisos.models import Aviso
            from django.contrib import messages
            
            aviso = Aviso.objects.get(pk=pk)
            titulo = aviso.titulo
            aviso.delete()
            
            messages.success(request, f'Aviso "{titulo}" excluido com sucesso!')
            
        except Exception as e:
            messages.error(request, f'Erro ao excluir aviso: {e}')
    
    return redirect('admin_dashboard:avisos_list')

@login_required
def aluna_excluir(request, pk):
    """Excluir aluna"""
    
    if not request.user.is_staff:
        return redirect('home')
    
    if request.method == 'POST':
        try:
            from usuarios.models import Aluna
            from django.contrib import messages
            
            aluna = Aluna.objects.get(pk=pk)
            nome = aluna.nome
            aluna.delete()
            
            messages.success(request, f'Aluna "{nome}" excluida com sucesso!')
            
        except Exception as e:
            from django.contrib import messages
            messages.error(request, f'Erro ao excluir aluna: {e}')
    
    return redirect('admin_dashboard:alunas_list')


@login_required
def mensalidade_editar(request, pk):
    """Editar mensalidade, status e data de pagamento."""

    if not request.user.is_staff:
        return redirect("home")

    mensalidade = get_object_or_404(Mensalidade, pk=pk)

    if request.method == "POST":
        try:
            mes_referencia_str = request.POST.get("mes_referencia", "").strip()
            data_vencimento_str = request.POST.get("data_vencimento", "").strip()
            data_pagamento_str = request.POST.get("data_pagamento", "").strip()
            valor_str = request.POST.get("valor", "").strip()
            status = request.POST.get("status", "").strip()

            status_permitidos = {"pendente", "pago", "vencido"}

            if status not in status_permitidos:
                raise ValueError("Status de pagamento inválido.")

            if not mes_referencia_str:
                raise ValueError("Informe o mês de referência.")

            if not data_vencimento_str:
                raise ValueError("Informe a data de vencimento.")

            if not valor_str:
                raise ValueError("Informe o valor da mensalidade.")

            try:
                mes_referencia = date.fromisoformat(f"{mes_referencia_str}-01")
            except ValueError:
                raise ValueError("O mês de referência é inválido.")

            try:
                data_vencimento = date.fromisoformat(data_vencimento_str)
            except ValueError:
                raise ValueError("A data de vencimento é inválida.")

            try:
                valor = Decimal(valor_str.replace(",", "."))
            except (InvalidOperation, ValueError):
                raise ValueError("O valor informado é inválido.")

            if valor < 0:
                raise ValueError("O valor não pode ser negativo.")

            data_pagamento = None

            if status == "pago":
                if not data_pagamento_str:
                    raise ValueError(
                        "Informe a data em que o pagamento foi recebido."
                    )

                try:
                    data_pagamento = date.fromisoformat(data_pagamento_str)
                except ValueError:
                    raise ValueError("A data de pagamento é inválida.")

                hoje = timezone.localdate()

                if data_pagamento > hoje:
                    raise ValueError(
                        "A data de pagamento não pode ser futura."
                    )

            mensalidade.mes_referencia = mes_referencia
            mensalidade.data_vencimento = data_vencimento
            mensalidade.valor = valor
            mensalidade.status = status
            mensalidade.data_pagamento = data_pagamento

            mensalidade.save()

            messages.success(
                request,
                "Mensalidade atualizada com sucesso!"
            )

            return redirect(
                "admin_dashboard:mensalidades_list"
            )

        except Exception as erro:
            messages.error(
                request,
                f"Erro ao atualizar mensalidade: {erro}"
            )

            return redirect(
                "admin_dashboard:mensalidade_editar",
                pk=pk,
            )

    context = {
        "mensalidade": mensalidade,
    }

    return render(
        request,
        "admin_dashboard/mensalidades/editar.html",
        context,
    )


@login_required
def mensalidade_excluir(request, pk):
    """Excluir mensalidade"""
    
    if not request.user.is_staff:
        return redirect('home')
    
    if request.method == 'POST':
        try:
            from pagamentos.models import Mensalidade
            from django.contrib import messages
            
            mensalidade = Mensalidade.objects.get(pk=pk)
            aluna_nome = mensalidade.aluna.nome
            mensalidade.delete()
            
            messages.success(request, f'Mensalidade de {aluna_nome} excluida com sucesso!')
            
        except Exception as e:
            from django.contrib import messages
            messages.error(request, f'Erro ao excluir mensalidade: {e}')
    
    return redirect('admin_dashboard:mensalidades_list')

@login_required
def espetaculos_list(request):
    """Lista de espetáculos"""

    if not request.user.is_staff:
        return redirect('home')

    try:
        from espetaculo.models import Espetaculo

        espetaculos = list(
            Espetaculo.objects.all().order_by('-data_apresentacao')
        )

        for esp in espetaculos:
            pedidos_qs = esp.pedidos_ingresso.filter(status='pago')
            esp.total_compradores = pedidos_qs.count()
            esp.total_ingressos_vendidos = sum(
                pedido.ingressos.count() for pedido in pedidos_qs
            )

    except Exception as e:
        print(f"Erro ao buscar espetáculos: {e}")
        espetaculos = []

    context = {
        'espetaculos': espetaculos,
        'total_espetaculos': len(espetaculos),
    }

    return render(request, 'admin_dashboard/espetaculos/list.html', context)


@login_required
def espetaculo_criar(request):
    """Criar novo espetáculo/evento"""

    if not request.user.is_staff:
        return redirect('home')

    if request.method == 'POST':
        try:
            from espetaculo.models import Espetaculo
            from django.contrib import messages
            from datetime import datetime

            titulo = request.POST.get('titulo')
            subtitulo = request.POST.get('subtitulo', '')
            descricao = request.POST.get('descricao')
            tipo = request.POST.get('tipo', 'espetaculo')
            publico = request.POST.get('publico') == 'on'

            data_apresentacao = request.POST.get('data_apresentacao')
            local = request.POST.get('local')
            endereco = request.POST.get('endereco')

            audicao_aberta = request.POST.get('audicao_aberta') == 'on'
            audicao_data_inicio = request.POST.get('audicao_data_inicio')
            audicao_data_fim = request.POST.get('audicao_data_fim')
            audicao_instrucoes = request.POST.get('audicao_instrucoes', '')

            venda_aberta = request.POST.get('venda_aberta') == 'on'
            venda_data_inicio = request.POST.get('venda_data_inicio')
            preco_ingresso = request.POST.get('preco_ingresso', '0')

            permite_ingresso_gratuito_aluna = request.POST.get('permite_ingresso_gratuito_aluna') == 'on'

            venda_com_assentos_numerados = request.POST.get('venda_com_assentos_numerados') == 'on'
            exige_login_para_compra = request.POST.get('exige_login_para_compra') == 'on'

            ativo = request.POST.get('ativo') == 'on'

            imagem = request.FILES.get('imagem')
            imagem_ingresso = request.FILES.get('imagem_ingresso')
            arquivo_divulgacao = request.FILES.get('arquivo_divulgacao')
            arquivo_informacoes = request.FILES.get('arquivo_informacoes')
            arquivo_edital = request.FILES.get('arquivo_edital')

            if not all([titulo, descricao, data_apresentacao, local, endereco]):
                messages.error(request, 'Preencha todos os campos obrigatórios!')
                return redirect('admin_dashboard:espetaculo_criar')

            data_apres = datetime.strptime(data_apresentacao, '%Y-%m-%dT%H:%M')

            Espetaculo.objects.create(
                titulo=titulo,
                subtitulo=subtitulo,
                descricao=descricao,
                tipo=tipo,
                publico=publico,
                data_apresentacao=data_apres,
                local=local,
                endereco=endereco,
                imagem=imagem,
                imagem_ingresso=imagem_ingresso,
                arquivo_divulgacao=arquivo_divulgacao,
                arquivo_informacoes=arquivo_informacoes,
                arquivo_edital=arquivo_edital,
                audicao_aberta=audicao_aberta,
                audicao_data_inicio=audicao_data_inicio if audicao_data_inicio else None,
                audicao_data_fim=audicao_data_fim if audicao_data_fim else None,
                audicao_instrucoes=audicao_instrucoes,
                venda_aberta=venda_aberta,
                venda_data_inicio=venda_data_inicio if venda_data_inicio else None,
                preco_ingresso=preco_ingresso,
                permite_ingresso_gratuito_aluna=permite_ingresso_gratuito_aluna,
                venda_com_assentos_numerados=venda_com_assentos_numerados,
                exige_login_para_compra=exige_login_para_compra,
                ativo=ativo
            )

            messages.success(request, f'"{titulo}" criado com sucesso!')
            return redirect('admin_dashboard:espetaculos_list')

        except Exception as e:
            from django.contrib import messages
            messages.error(request, f'Erro ao criar espetáculo/evento: {e}')
            import traceback
            traceback.print_exc()
            return redirect('admin_dashboard:espetaculo_criar')

    return render(request, 'admin_dashboard/espetaculos/criar.html', {})


@login_required
def espetaculo_editar(request, pk):
    """Editar espetáculo/evento existente"""

    if not request.user.is_staff:
        return redirect('home')

    try:
        from espetaculo.models import Espetaculo
        espetaculo = Espetaculo.objects.get(pk=pk)
    except Exception as e:
        from django.contrib import messages
        messages.error(request, f'Cadastro não encontrado: {e}')
        return redirect('admin_dashboard:espetaculos_list')

    if request.method == 'POST':
        try:
            from django.contrib import messages
            from datetime import datetime

            espetaculo.titulo = request.POST.get('titulo')
            espetaculo.subtitulo = request.POST.get('subtitulo', '')
            espetaculo.descricao = request.POST.get('descricao')
            espetaculo.tipo = request.POST.get('tipo', 'espetaculo')
            espetaculo.publico = request.POST.get('publico') == 'on'

            data_apresentacao = request.POST.get('data_apresentacao')
            espetaculo.data_apresentacao = datetime.strptime(data_apresentacao, '%Y-%m-%dT%H:%M')

            espetaculo.local = request.POST.get('local')
            espetaculo.endereco = request.POST.get('endereco')

            espetaculo.audicao_aberta = request.POST.get('audicao_aberta') == 'on'
            audicao_data_inicio = request.POST.get('audicao_data_inicio')
            espetaculo.audicao_data_inicio = audicao_data_inicio if audicao_data_inicio else None

            audicao_data_fim = request.POST.get('audicao_data_fim')
            espetaculo.audicao_data_fim = audicao_data_fim if audicao_data_fim else None
            espetaculo.audicao_instrucoes = request.POST.get('audicao_instrucoes', '')

            espetaculo.venda_aberta = request.POST.get('venda_aberta') == 'on'
            venda_data_inicio = request.POST.get('venda_data_inicio')
            espetaculo.venda_data_inicio = venda_data_inicio if venda_data_inicio else None
            espetaculo.preco_ingresso = request.POST.get('preco_ingresso', '0')

            espetaculo.permite_ingresso_gratuito_aluna = request.POST.get('permite_ingresso_gratuito_aluna') == 'on'

            espetaculo.venda_com_assentos_numerados = request.POST.get('venda_com_assentos_numerados') == 'on'
            espetaculo.exige_login_para_compra = request.POST.get('exige_login_para_compra') == 'on'

            espetaculo.ativo = request.POST.get('ativo') == 'on'

            imagem = request.FILES.get('imagem')
            if imagem:
                espetaculo.imagem = imagem

            imagem_ingresso = request.FILES.get('imagem_ingresso')
            if imagem_ingresso:
                espetaculo.imagem_ingresso = imagem_ingresso

            arquivo_divulgacao = request.FILES.get('arquivo_divulgacao')
            if arquivo_divulgacao:
                espetaculo.arquivo_divulgacao = arquivo_divulgacao

            arquivo_informacoes = request.FILES.get('arquivo_informacoes')
            if arquivo_informacoes:
                espetaculo.arquivo_informacoes = arquivo_informacoes

            arquivo_edital = request.FILES.get('arquivo_edital')
            if arquivo_edital:
                espetaculo.arquivo_edital = arquivo_edital

            espetaculo.save()

            messages.success(request, f'"{espetaculo.titulo}" atualizado com sucesso!')
            return redirect('admin_dashboard:espetaculos_list')

        except Exception as e:
            from django.contrib import messages
            messages.error(request, f'Erro ao atualizar espetáculo/evento: {e}')
            return redirect('admin_dashboard:espetaculo_editar', pk=pk)

    context = {
        'espetaculo': espetaculo,
    }
    return render(request, 'admin_dashboard/espetaculos/editar.html', context)

@login_required
def responsaveis_list(request):
    """Lista de responsaveis"""
    
    if not request.user.is_staff:
        return redirect('home')
    
    try:
        from django.contrib.auth.models import User
        from usuarios.models import Aluna, Perfil
        from django.db.models import Count
        
        # Pega apenas usuários que são responsáveis (marcados como True)
        responsaveis = User.objects.filter(
            is_staff=False,
            perfil__is_responsavel=True  # SÓ RESPONSÁVEIS DE VERDADE
        ).annotate(
            total_alunas=Count('alunas')
        ).order_by('first_name', 'last_name')
        
        # Busca
        busca = request.GET.get('busca', '')
        if busca:
            from django.db.models import Q
            responsaveis = responsaveis.filter(
                Q(first_name__icontains=busca) |
                Q(last_name__icontains=busca) |
                Q(email__icontains=busca)
            )
        
    except Exception as e:
        print(f"Erro ao buscar responsaveis: {e}")
        responsaveis = []
        busca = ''
    
    context = {
        'responsaveis': responsaveis,
        'busca': busca,
        'total_responsaveis': responsaveis.count() if responsaveis else 0,
    }
    
    return render(request, 'admin_dashboard/responsaveis/list.html', context)

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect, render

User = get_user_model()


@login_required
@transaction.atomic
def responsavel_criar(request):
    """Criar novo responsável no admin_dashboard"""

    if not request.user.is_staff:
        return redirect('home')

    from usuarios.models import Perfil

    if request.method == 'POST':
        nome = request.POST.get('nome', '').strip()
        email = request.POST.get('email', '').strip().lower()
        username = request.POST.get('username', '').strip()
        senha = request.POST.get('senha', '')
        confirmar_senha = request.POST.get('confirmar_senha', '')
        cpf = request.POST.get('cpf', '').strip()
        telefone = request.POST.get('telefone', '').strip()
        data_nascimento = request.POST.get('data_nascimento', '').strip()
        endereco = request.POST.get('endereco', '').strip()
        genero = request.POST.get('genero', '').strip()
        ativo = request.POST.get('ativo') == 'on'

        form_data = request.POST

        if not nome:
            messages.error(request, 'Informe o nome completo do responsável.')
            return render(request, 'admin_dashboard/responsaveis/criar.html', {
                'form_data': form_data
            })

        if not email:
            messages.error(request, 'Informe o e-mail do responsável.')
            return render(request, 'admin_dashboard/responsaveis/criar.html', {
                'form_data': form_data
            })

        if not username:
            messages.error(request, 'Informe o nome de usuário.')
            return render(request, 'admin_dashboard/responsaveis/criar.html', {
                'form_data': form_data
            })

        if not senha:
            messages.error(request, 'Informe a senha.')
            return render(request, 'admin_dashboard/responsaveis/criar.html', {
                'form_data': form_data
            })

        if len(senha) < 6:
            messages.error(request, 'A senha deve ter no mínimo 6 caracteres.')
            return render(request, 'admin_dashboard/responsaveis/criar.html', {
                'form_data': form_data
            })

        if senha != confirmar_senha:
            messages.error(request, 'A confirmação da senha não confere.')
            return render(request, 'admin_dashboard/responsaveis/criar.html', {
                'form_data': form_data
            })

        if User.objects.filter(username__iexact=username).exists():
            messages.error(request, 'Já existe um responsável com esse nome de usuário.')
            return render(request, 'admin_dashboard/responsaveis/criar.html', {
                'form_data': form_data
            })

        if User.objects.filter(email__iexact=email).exists():
            messages.error(request, 'Já existe um usuário com esse e-mail.')
            return render(request, 'admin_dashboard/responsaveis/criar.html', {
                'form_data': form_data
            })

        partes_nome = nome.split()
        first_name = partes_nome[0] if partes_nome else ''
        last_name = ' '.join(partes_nome[1:]) if len(partes_nome) > 1 else ''

        responsavel = User.objects.create_user(
            username=username,
            email=email,
            password=senha,
            first_name=first_name,
            last_name=last_name,
            is_active=ativo,
            is_staff=False,
            is_superuser=False,
        )

        Perfil.objects.create(
            user=responsavel,
            telefone=telefone or None,
            cpf=cpf or None,
            data_nascimento=data_nascimento or None,
            endereco=endereco or None,
            genero=genero or None,
            is_responsavel=True,
            is_tambem_aluno=False,
        )

        messages.success(request, f'Responsável "{responsavel.get_full_name() or responsavel.username}" criado com sucesso!')
        return redirect('admin_dashboard:responsaveis_list')

    return render(request, 'admin_dashboard/responsaveis/criar.html')

@login_required
def responsavel_editar(request, pk):
    """Editar dados do responsavel"""

    if not request.user.is_staff:
        return redirect('home')

    try:
        from django.contrib.auth.models import User
        from usuarios.models import Perfil, Aluna, Turma
        from django.contrib import messages

        responsavel = User.objects.get(pk=pk, is_staff=False)

        # Pega ou cria perfil, garantindo is_responsavel=True
        perfil, created = Perfil.objects.get_or_create(
            user=responsavel,
            defaults={'is_responsavel': True}
        )
        if not perfil.is_responsavel:
            perfil.is_responsavel = True
            perfil.save()

        alunas_vinculadas = Aluna.objects.filter(responsavel=responsavel).order_by('nome')
        alunas_nao_vinculadas = Aluna.objects.filter(responsavel__isnull=True, tipo_aluna='infantil').order_by('nome')
        aluna_associada = Aluna.objects.filter(responsavel=responsavel, tipo_aluna='adulto').first()

        if request.method == 'POST':
            responsavel.first_name = request.POST.get('first_name', '')
            responsavel.last_name = request.POST.get('last_name', '')
            responsavel.email = request.POST.get('email', '')
            responsavel.save()

            perfil.telefone = request.POST.get('telefone', '')
            perfil.cpf = request.POST.get('cpf', '')
            perfil.endereco = request.POST.get('endereco', '')
            perfil.genero = request.POST.get('genero', '') or None

            data_nascimento = request.POST.get('data_nascimento')
            if data_nascimento:
                perfil.data_nascimento = data_nascimento
            else:
                perfil.data_nascimento = None

            is_tambem_aluno = request.POST.get('is_tambem_aluno') == 'on'
            perfil.is_tambem_aluno = is_tambem_aluno
            perfil.save()

            if is_tambem_aluno:
                turmas_ids = request.POST.getlist('turmas_aluno')
                turmas_selecionadas = []
                for turma_id in turmas_ids:
                    try:
                        turma = Turma.objects.get(id=turma_id)
                        turmas_selecionadas.append(turma)
                    except Turma.DoesNotExist:
                        pass

                if aluna_associada:
                    aluna_associada.nome = responsavel.get_full_name() or responsavel.username
                    aluna_associada.data_nascimento = data_nascimento or None
                    aluna_associada.ativa = True
                    aluna_associada.save()
                    aluna_associada.turmas.set(turmas_selecionadas)
                    messages.success(request, f'Aluno {aluna_associada.nome} atualizado!')
                else:
                    aluna_associada = Aluna.objects.create(
                        nome=responsavel.get_full_name() or responsavel.username,
                        responsavel=responsavel,
                        tipo_aluna='adulto',
                        data_nascimento=data_nascimento or None,
                        ativa=True
                    )
                    aluna_associada.turmas.set(turmas_selecionadas)
                    messages.success(request, f'Aluno {aluna_associada.nome} cadastrado como aluno da escola!')
            else:
                if aluna_associada:
                    aluna_associada.responsavel = None
                    aluna_associada.ativa = False
                    aluna_associada.save()
                    messages.info(request, f'Aluno {aluna_associada.nome} foi desvinculado.')

            vincular_aluna_id = request.POST.get('vincular_aluna')
            if vincular_aluna_id:
                try:
                    aluna = Aluna.objects.get(id=vincular_aluna_id)
                    aluna.responsavel = responsavel
                    aluna.save()
                    messages.success(request, f'Aluna {aluna.nome} vinculada com sucesso!')
                except Aluna.DoesNotExist:
                    messages.error(request, 'Aluna não encontrada!')

            remover_aluna_id = request.POST.get('remover_aluna')
            if remover_aluna_id:
                try:
                    aluna = Aluna.objects.get(id=remover_aluna_id, responsavel=responsavel)
                    aluna.responsavel = None
                    aluna.save()
                    messages.success(request, f'Vínculo com {aluna.nome} removido!')
                except Aluna.DoesNotExist:
                    messages.error(request, 'Aluna não encontrada!')

            return redirect('admin_dashboard:responsavel_editar', pk=responsavel.pk)

        context = {
            'responsavel': responsavel,
            'perfil': perfil,
            'alunas_vinculadas': alunas_vinculadas,
            'alunas_nao_vinculadas': alunas_nao_vinculadas,
            'aluna_associada': aluna_associada,
            'turmas': Turma.objects.filter(ativa=True).order_by('nome'),
        }
        return render(request, 'admin_dashboard/responsaveis/editar.html', context)

    except Exception as e:
        from django.contrib import messages
        messages.error(request, f'Responsável não encontrado: {e}')
        return redirect('admin_dashboard:responsaveis_list')


@login_required
def responsavel_redefinir_senha(request, pk):
    """Redefinir senha de um responsavel"""
    
    if not request.user.is_staff:
        return redirect('home')
    
    try:
        from django.contrib.auth.models import User
        from django.contrib import messages
        
        responsavel = User.objects.get(pk=pk, is_staff=False)
        
        if request.method == 'POST':
            nova_senha = request.POST.get('nova_senha')
            confirma_senha = request.POST.get('confirma_senha')
            
            if not nova_senha or not confirma_senha:
                messages.error(request, 'Preencha todos os campos!')
                return redirect('admin_dashboard:responsavel_redefinir_senha', pk=pk)
            
            if nova_senha != confirma_senha:
                messages.error(request, 'As senhas nao coincidem!')
                return redirect('admin_dashboard:responsavel_redefinir_senha', pk=pk)
            
            if len(nova_senha) < 6:
                messages.error(request, 'A senha deve ter no minimo 6 caracteres!')
                return redirect('admin_dashboard:responsavel_redefinir_senha', pk=pk)
            
            # Redefine a senha
            responsavel.set_password(nova_senha)
            responsavel.save()
            
            messages.success(request, f'Senha de {responsavel.get_full_name()} redefinida com sucesso!')
            return redirect('admin_dashboard:responsaveis_list')
        
        # GET - mostra form
        context = {
            'responsavel': responsavel,
        }
        return render(request, 'admin_dashboard/responsaveis/redefinir_senha.html', context)
        
    except Exception as e:
        from django.contrib import messages
        messages.error(request, f'Responsavel nao encontrado: {e}')
        return redirect('admin_dashboard:responsaveis_list')


@login_required
def responsavel_excluir(request, pk):
    """Excluir responsavel"""
    
    if not request.user.is_staff:
        return redirect('home')
    
    if request.method == 'POST':
        try:
            from django.contrib.auth.models import User
            from django.contrib import messages
            from usuarios.models import Aluna
            
            responsavel = User.objects.get(pk=pk, is_staff=False)
            
            # Verifica se o responsável tem alunas vinculadas
            total_alunas = Aluna.objects.filter(responsavel=responsavel).count()
            
            if total_alunas > 0:
                messages.error(
                    request, 
                    f'Não é possível excluir {responsavel.get_full_name()} pois ele(a) tem {total_alunas} aluna(s) vinculada(s).'
                )
                return redirect('admin_dashboard:responsaveis_list')
            
            nome = responsavel.get_full_name() or responsavel.username
            responsavel.delete()
            
            messages.success(request, f'Responsável "{nome}" excluído com sucesso!')
            
        except Exception as e:
            from django.contrib import messages
            messages.error(request, f'Erro ao excluir responsável: {e}')
    
    return redirect('admin_dashboard:responsaveis_list')


@login_required
def turmas_list(request):
    """Lista de turmas"""
    
    if not request.user.is_staff:
        return redirect('home')
    
    try:
        from usuarios.models import Turma
        
        turmas = Turma.objects.all().order_by('nome')
        
        # Busca
        busca = request.GET.get('busca', '')
        if busca:
            turmas = turmas.filter(nome__icontains=busca)
        
        # Filtro por status
        status = request.GET.get('status', '')
        if status == 'ativas':
            turmas = turmas.filter(ativa=True)
        elif status == 'inativas':
            turmas = turmas.filter(ativa=False)
        
    except Exception as e:
        print(f"Erro ao buscar turmas: {e}")
        turmas = []
        busca = ''
        status = ''
    
    context = {
        'turmas': turmas,
        'busca': busca,
        'status_filtro': status,
        'total_turmas': turmas.count() if turmas else 0,
    }
    
    return render(request, 'admin_dashboard/turmas/list.html', context)


@login_required
def turma_criar(request):
    """Criar nova turma"""

    if not request.user.is_staff:
        return redirect('home')

    if request.method == 'POST':
        try:
            from usuarios.models import Turma
            from django.contrib import messages

            nome = request.POST.get('nome')
            descricao = request.POST.get('descricao', '')
            horario = request.POST.get('horario', '')
            professor = request.POST.get('professor', '')
            capacidade_maxima = request.POST.get('capacidade_maxima', 20)
            ativa = request.POST.get('ativa') == 'on'
            disponivel_experimental = request.POST.get('disponivel_experimental') == 'on'
            dia_semana = request.POST.get('dia_semana') or None

            if not nome:
                messages.error(request, 'O nome da turma é obrigatório!')
                return redirect('admin_dashboard:turma_criar')

            turma = Turma.objects.create(
                nome=nome,
                descricao=descricao,
                horario=horario,
                professor=professor,
                capacidade_maxima=int(capacidade_maxima),
                ativa=ativa,
                disponivel_experimental=disponivel_experimental,
                dia_semana=dia_semana,
            )

            messages.success(request, f'Turma "{nome}" criada com sucesso!')
            return redirect('admin_dashboard:turmas_list')

        except Exception as e:
            from django.contrib import messages
            messages.error(request, f'Erro ao criar turma: {e}')
            import traceback
            traceback.print_exc()
            return redirect('admin_dashboard:turma_criar')

    return render(request, 'admin_dashboard/turmas/criar.html')


@login_required
def turma_editar(request, pk):
    """Editar turma existente"""

    if not request.user.is_staff:
        return redirect('home')

    try:
        from usuarios.models import Turma
        turma = Turma.objects.get(pk=pk)
    except Exception as e:
        from django.contrib import messages
        messages.error(request, f'Turma não encontrada: {e}')
        return redirect('admin_dashboard:turmas_list')

    if request.method == 'POST':
        try:
            from django.contrib import messages

            turma.nome = request.POST.get('nome')
            turma.descricao = request.POST.get('descricao', '')
            turma.horario = request.POST.get('horario', '')
            turma.professor = request.POST.get('professor', '')
            turma.capacidade_maxima = int(request.POST.get('capacidade_maxima', 20))
            turma.ativa = request.POST.get('ativa') == 'on'
            turma.disponivel_experimental = request.POST.get('disponivel_experimental') == 'on'
            turma.dia_semana = request.POST.get('dia_semana') or None

            turma.save()

            messages.success(request, f'Turma "{turma.nome}" atualizada com sucesso!')
            return redirect('admin_dashboard:turmas_list')

        except Exception as e:
            from django.contrib import messages
            messages.error(request, f'Erro ao atualizar turma: {e}')
            return redirect('admin_dashboard:turma_editar', pk=pk)

    context = {
        'turma': turma,
    }

    return render(request, 'admin_dashboard/turmas/editar.html', context)

@login_required
def turma_toggle_experimental(request, pk):
    """Ativa ou desativa a turma para aula experimental"""
    
    if not request.user.is_staff:
        return redirect('home')
    
    if request.method == 'POST':
        try:
            from usuarios.models import Turma
            from django.contrib import messages
            
            turma = Turma.objects.get(pk=pk)
            turma.disponivel_experimental = not turma.disponivel_experimental
            turma.save()
            
            if turma.disponivel_experimental:
                messages.success(request, f'Turma "{turma.nome}" ativada para aula experimental com sucesso!')
            else:
                messages.success(request, f'Turma "{turma.nome}" desativada da aula experimental com sucesso!')
        
        except Exception as e:
            messages.error(request, f'Erro ao alterar aula experimental: {e}')
    
    return redirect('admin_dashboard:turmas_list')


@login_required
def turma_excluir(request, pk):
    """Excluir turma"""
    
    if not request.user.is_staff:
        return redirect('home')
    
    if request.method == 'POST':
        try:
            from usuarios.models import Turma
            from django.contrib import messages
            
            turma = Turma.objects.get(pk=pk)
            
            # Verifica se tem alunas
            if turma.total_alunas > 0:
                messages.error(request, f'Nao e possivel excluir a turma "{turma.nome}" pois ela possui {turma.total_alunas} alunas!')
                return redirect('admin_dashboard:turmas_list')
            
            nome = turma.nome
            turma.delete()
            
            messages.success(request, f'Turma "{nome}" excluida com sucesso!')
            
        except Exception as e:
            from django.contrib import messages
            messages.error(request, f'Erro ao excluir turma: {e}')
    
    return redirect('admin_dashboard:turmas_list')


@login_required
def turma_detalhes(request, pk):
    """Detalhes da turma com lista de alunas matriculadas"""
    
    if not request.user.is_staff:
        return redirect('home')
    
    try:
        from usuarios.models import Turma, Aluna
        from datetime import date
        
        turma = Turma.objects.get(pk=pk)
        
        # Busca todas as alunas da turma
        alunas = Aluna.objects.filter(
            turmas=turma,  # CORRETO: usa ManyToMany
            ativa=True
        ).order_by('nome')
        
        # Calcula tempo de matrícula para cada aluna
        hoje = date.today()
        for aluna in alunas:
            if aluna.data_matricula:
                # Cálculo manual de anos e meses
                anos = hoje.year - aluna.data_matricula.year
                meses = hoje.month - aluna.data_matricula.month
                
                if meses < 0:
                    anos -= 1
                    meses += 12
                
                # Ajuste de dias
                if hoje.day < aluna.data_matricula.day:
                    meses -= 1
                    if meses < 0:
                        meses += 12
                        anos -= 1
                
                if anos > 0:
                    aluna.tempo_matricula = f"{anos} ano{'s' if anos > 1 else ''}"
                    if meses > 0:
                        aluna.tempo_matricula += f" e {meses} mes{'es' if meses > 1 else ''}"
                elif meses > 0:
                    aluna.tempo_matricula = f"{meses} mes{'es' if meses > 1 else ''}"
                else:
                    aluna.tempo_matricula = "Recém matriculada"
            else:
                aluna.tempo_matricula = "Data não registrada"
        
        total_alunas = alunas.count()
        
        # Estatísticas
        if turma.capacidade_maxima > 0:
            turma.capacidade_percentual = int((total_alunas / turma.capacidade_maxima) * 100)
        else:
            turma.capacidade_percentual = 0
        
    except Exception as e:
        from django.contrib import messages
        messages.error(request, f'Turma não encontrada: {e}')
        return redirect('admin_dashboard:turmas_list')
    
    context = {
        'turma': turma,
        'alunas': alunas,
        'total_alunas': total_alunas,
    }
    
    return render(request, 'admin_dashboard/turmas/detalhes.html', context)

@login_required
def inscricoes_audicao_list(request):
    """Lista de inscrições para audição com filtro por personagem"""
    if not request.user.is_staff:
        return redirect('home')

    from espetaculo.models import InscricaoAudicao

    inscricoes = InscricaoAudicao.objects.all().order_by('-data_inscricao')

    personagem_filtro = request.GET.get('personagem', '').strip()
    if personagem_filtro:
        inscricoes = inscricoes.filter(personagens__icontains=personagem_filtro)

    context = {
        'inscricoes': inscricoes,
        'personagem_filtro': personagem_filtro,
        'total_inscricoes': inscricoes.count(),
    }
    return render(request, 'admin_dashboard/espetaculos/inscricoes.html', context)

@login_required
def inscricao_audicao_excluir(request, pk):
    """Excluir inscrição para audição"""
    if not request.user.is_staff:
        return redirect('home')
    
    if request.method == 'POST':
        try:
            from espetaculo.models import InscricaoAudicao
            from django.contrib import messages
            
            inscricao = InscricaoAudicao.objects.get(pk=pk)
            nome = inscricao.nome_completo
            inscricao.delete()
            
            messages.success(request, f'Inscrição de {nome} excluída com sucesso!')
            
        except Exception as e:
            from django.contrib import messages
            messages.error(request, f'Erro ao excluir inscrição: {e}')
    
    return redirect('admin_dashboard:inscricoes_audicao')

from datetime import date
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from agenda.models import Agendamento, ConfiguracaoAgendamento
from agenda.services import liberar_gratuita
from usuarios.models import Turma


@login_required
def agendamentos_list(request):
    if not request.user.is_staff:
        return redirect("home")

    configuracao = ConfiguracaoAgendamento.obter()

    turmas_disponiveis = (
        Turma.objects
        .filter(
            ativa=True,
            disponivel_experimental=True,
        )
        .order_by("nome")
    )

    if request.method == "POST":
        acao = request.POST.get("acao")

        if acao == "toggle_campanha_gratuita":
            campanha_ativa = (
                request.POST.get(
                    "campanha_gratuita_ativa"
                )
                == "on"
            )

            configuracao.campanha_gratuita_ativa = (
                campanha_ativa
            )

            configuracao.save(
                update_fields=[
                    "campanha_gratuita_ativa",
                    "atualizado_em",
                ]
            )

            messages.success(
                request,
                "Campanha gratuita atualizada com sucesso.",
            )

        elif acao == "atualizar_valor":
            valor_str = (
                request.POST.get(
                    "valor_aula_experimental",
                    "",
                )
                .replace(",", ".")
                .strip()
            )

            try:
                novo_valor = Decimal(valor_str)

                if novo_valor < 0:
                    raise InvalidOperation

                configuracao.valor_aula_experimental = (
                    novo_valor
                )

                configuracao.save(
                    update_fields=[
                        "valor_aula_experimental",
                        "atualizado_em",
                    ]
                )

                messages.success(
                    request,
                    "Valor atualizado com sucesso.",
                )

            except (
                InvalidOperation,
                TypeError,
                ValueError,
            ):
                messages.error(
                    request,
                    "Informe um valor válido.",
                )

        elif acao == "atualizar_turmas_gratuitas":
            ids_turmas = request.POST.getlist(
                "turmas_gratuitas"
            )

            turmas_selecionadas = turmas_disponiveis.filter(
                id__in=ids_turmas
            )

            configuracao.turmas_gratuitas.set(
                turmas_selecionadas
            )

            messages.success(
                request,
                "Turmas gratuitas atualizadas com sucesso.",
            )

        query_params = {}

        if request.POST.get("tipo"):
            query_params["tipo"] = request.POST.get(
                "tipo"
            )

        if request.POST.get("mes"):
            query_params["mes"] = request.POST.get(
                "mes"
            )

        if request.POST.get("semana"):
            query_params["semana"] = request.POST.get(
                "semana"
            )

        url = reverse(
            "admin_dashboard:agendamentos_list"
        )

        if query_params:
            url += "?" + urlencode(query_params)

        return redirect(url)

    hoje = date.today()

    tipo = request.GET.get(
        "tipo",
        "proximos",
    )

    mes = request.GET.get(
        "mes",
        "",
    )

    semana = request.GET.get(
        "semana",
        "",
    )

    agendamentos = Agendamento.objects.all()

    if tipo == "antigos":
        agendamentos = agendamentos.filter(
            data__lt=hoje,
        )
    else:
        tipo = "proximos"

        agendamentos = agendamentos.filter(
            data__gte=hoje,
        )

    if mes:
        try:
            ano, mes_num = mes.split("-")

            agendamentos = agendamentos.filter(
                data__year=int(ano),
                data__month=int(mes_num),
            )

        except ValueError:
            pass

    if semana:
        try:
            ano_str, semana_str = semana.split("-W")

            ano = int(ano_str)
            num_semana = int(semana_str)

            inicio_semana = date.fromisocalendar(
                ano,
                num_semana,
                1,
            )

            fim_semana = date.fromisocalendar(
                ano,
                num_semana,
                7,
            )

            agendamentos = agendamentos.filter(
                data__gte=inicio_semana,
                data__lte=fim_semana,
            )

        except (
            ValueError,
            TypeError,
        ):
            pass

    agendamentos = agendamentos.order_by(
        "data",
        "horario",
    )

    meses_disponiveis = Agendamento.objects.dates(
        "data",
        "month",
        order="DESC",
    )

    total_geral = Agendamento.objects.count()

    total_proximos = Agendamento.objects.filter(
        data__gte=hoje,
    ).count()

    total_antigos = Agendamento.objects.filter(
        data__lt=hoje,
    ).count()

    turmas_gratuitas_ids = set(
        configuracao.turmas_gratuitas.values_list(
            "id",
            flat=True,
        )
    )

    context = {
        "agendamentos": agendamentos,
        "tipo": tipo,
        "mes": mes,
        "semana": semana,
        "hoje": hoje,
        "meses_disponiveis": meses_disponiveis,
        "total_geral": total_geral,
        "total_proximos": total_proximos,
        "total_antigos": total_antigos,
        "configuracao": configuracao,
        "turmas_disponiveis": turmas_disponiveis,
        "turmas_gratuitas_ids": turmas_gratuitas_ids,
    }

    return render(
        request,
        "admin_dashboard/agendamentos/list.html",
        context,
    )


@login_required
def agendamento_detalhes(request, pk):
    """Exibe os detalhes de um agendamento."""

    if not request.user.is_staff:
        return redirect("home")

    agendamento = get_object_or_404(
        Agendamento,
        pk=pk,
    )

    if (
        request.method == "POST"
        and request.POST.get("acao")
        == "liberar_gratuita"
    ):
        liberar_gratuita(agendamento)

        messages.success(
            request,
            (
                "Aula liberada como gratuita e evento "
                "criado na agenda."
            ),
        )

        return redirect(
            "admin_dashboard:agendamento_detalhes",
            pk=agendamento.pk,
        )

    return render(
        request,
        "admin_dashboard/agendamentos/detalhes.html",
        {
            "agendamento": agendamento,
        },
    )

@login_required
def agendamento_detalhes(request, pk):
    """Detalhes do agendamento"""
    if not request.user.is_staff:
        return redirect('home')

    from django.contrib import messages
    from agenda.models import Agendamento
    from agenda.services import liberar_gratuita

    agendamento = get_object_or_404(Agendamento, pk=pk)

    if request.method == 'POST' and request.POST.get('acao') == 'liberar_gratuita':
        liberar_gratuita(agendamento)
        messages.success(request, 'Aula liberada como gratuita e evento criado na agenda.')
        return redirect('admin_dashboard:agendamento_detalhes', pk=agendamento.pk)

    return render(request, 'admin_dashboard/agendamentos/detalhes.html', {'agendamento': agendamento})

@login_required
def agendamento_excluir(request, pk):
    """Excluir agendamento de aula experimental"""
    if not request.user.is_staff:
        return redirect('home')
    
    if request.method == 'POST':
        try:
            from agenda.models import Agendamento
            agendamento = Agendamento.objects.get(pk=pk)
            nome = agendamento.nome_aluna
            agendamento.delete()
            
            messages.success(request, f'Agendamento de {nome} excluído com sucesso!')
            
        except Exception as e:
            messages.error(request, f'Erro ao excluir agendamento: {e}')
    
    return redirect('admin_dashboard:agendamentos_list')

# ==================== VIEWS PARA PROFESSORES ====================

@login_required
def professor_dashboard(request):
    """Dashboard do professor - mostra apenas suas turmas"""

    from usuarios.models import Turma, Aluna
    from django.db.models import Case, When, Value, IntegerField, Q

    nomes_possiveis = []

    if request.user.first_name:
        nomes_possiveis.append(request.user.first_name.strip())

    nome_completo = request.user.get_full_name().strip()
    if nome_completo:
        nomes_possiveis.append(nome_completo)

    if request.user.username:
        nomes_possiveis.append(request.user.username.strip())

    nomes_possiveis = [nome for nome in nomes_possiveis if nome]
    nomes_possiveis = list(dict.fromkeys(nomes_possiveis))

    filtro_professor = Q()
    for nome in nomes_possiveis:
        filtro_professor |= Q(professor__iexact=nome)

    turmas = (
        Turma.objects
        .filter(ativa=True)
        .filter(filtro_professor)
        .annotate(
            ordem_dia=Case(
                When(dia_semana='Segunda', then=Value(1)),
                When(dia_semana='Terça', then=Value(2)),
                When(dia_semana='Quarta', then=Value(3)),
                When(dia_semana='Quinta', then=Value(4)),
                When(dia_semana='Sexta', then=Value(5)),
                When(dia_semana='Sábado', then=Value(6)),
                default=Value(99),
                output_field=IntegerField(),
            )
        )
        .order_by('ordem_dia', 'horario', 'nome')
    )

    total_turmas = turmas.count()
    total_alunas = Aluna.objects.filter(turmas__in=turmas, ativa=True).distinct().count()

    context = {
        'turmas': turmas,
        'total_turmas': total_turmas,
        'total_alunas': total_alunas,
        'nomes_possiveis': nomes_possiveis,
    }
    return render(request, 'admin_dashboard/professor/dashboard.html', context)

@login_required
def professor_turma_detalhes(request, pk):
    """Detalhes da turma para professor"""
    
    if not request.user.groups.filter(name='Professores').exists():
        return redirect('home')
    
    from usuarios.models import Turma, Aluna
    from django.shortcuts import get_object_or_404
    
    turma = get_object_or_404(Turma, pk=pk, professor_responsavel=request.user)
    alunas = Aluna.objects.filter(turmas=turma, ativa=True).order_by('nome')
    
    context = {
        'turma': turma,
        'alunas': alunas,
    }
    return render(request, 'admin_dashboard/professor/turma_detalhes.html', context)

@login_required
def professor_avisos(request):
    """Lista de avisos para professor"""

    if not request.user.groups.filter(name='Professores').exists():
        return redirect('home')

    from calendario_avisos.models import Aviso

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
        avisos = avisos.filter(
            data_evento__lt=hoje
        ).order_by('-data_evento', '-data_publicacao')
    else:
        avisos = avisos.filter(
            data_evento__gte=hoje
        ).order_by('data_evento', '-data_publicacao')

    return render(
        request,
        'admin_dashboard/professor/avisos.html',
        {
            'avisos': avisos,
            'busca': busca,
            'tipo_data': tipo_data,
        }
    )

@login_required
def professor_criar(request):
    """Criar novo professor (apenas para admin)"""
    
    if not request.user.is_staff:
        return redirect('home')
    
    from django.contrib.auth.models import User, Group
    from usuarios.models import Turma
    from django.contrib import messages
    
    if request.method == 'POST':
        nome = request.POST.get('nome')
        email = request.POST.get('email')
        senha = request.POST.get('senha')
        turmas_ids = request.POST.getlist('turmas')
        
        # Validações
        if not nome or not email or not senha:
            messages.error(request, 'Preencha todos os campos obrigatórios!')
            return redirect('admin_dashboard:professor_criar')
        
        if User.objects.filter(email=email).exists():
            messages.error(request, f'Email {email} já cadastrado!')
            return redirect('admin_dashboard:professor_criar')
        
        if len(senha) < 6:
            messages.error(request, 'A senha deve ter no mínimo 6 caracteres!')
            return redirect('admin_dashboard:professor_criar')
        
        # Cria o usuário
        username = email.split('@')[0]
        base_username = username
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{base_username}{counter}"
            counter += 1
        
        user = User.objects.create_user(
            username=username,
            email=email,
            password=senha,
            first_name=nome
        )
        
        # Adiciona ao grupo Professores
        grupo, _ = Group.objects.get_or_create(name='Professores')
        user.groups.add(grupo)
        
        # Vincula as turmas selecionadas
        for turma_id in turmas_ids:
            try:
                turma = Turma.objects.get(id=turma_id)
                turma.professor_responsavel = user
                turma.save()
            except Turma.DoesNotExist:
                pass
        
        messages.success(request, f'Professor {nome} criado com sucesso!')
        return redirect('admin_dashboard:professores_list')
    
    # GET - mostra formulário
    turmas = Turma.objects.filter(ativa=True).order_by('nome')
    
    context = {
        'turmas': turmas,
    }
    return render(request, 'admin_dashboard/professores/criar.html', context)

@login_required
def professores_list(request):
    """Lista de professores"""

    if not request.user.is_staff:
        return redirect('home')

    from django.contrib.auth.models import User
    from django.db.models import Count

    professores = (
        User.objects
        .filter(groups__name='Professores')
        .select_related('aluna_vinculada')
        .annotate(total_turmas=Count('turmas_ministradas'))
        .order_by('first_name')
    )

    return render(request, 'admin_dashboard/professores/list.html', {'professores': professores})

@login_required
def professor_editar(request, pk):
    """Editar professor"""
    
    if not request.user.is_staff:
        return redirect('home')
    
    from django.contrib.auth.models import User
    from usuarios.models import Turma
    from django.contrib import messages
    from django.shortcuts import get_object_or_404
    
    professor = get_object_or_404(User, pk=pk, groups__name='Professores')
    
    if request.method == 'POST':
        # Atualiza dados básicos
        professor.first_name = request.POST.get('nome')
        professor.email = request.POST.get('email')
        
        # Atualiza senha se fornecida
        nova_senha = request.POST.get('senha')
        if nova_senha:
            if len(nova_senha) >= 6:
                professor.set_password(nova_senha)
                messages.info(request, 'Senha alterada com sucesso!')
            else:
                messages.error(request, 'A senha deve ter no mínimo 6 caracteres!')
        
        professor.save()
        
        # Atualiza turmas vinculadas
        turmas_ids = request.POST.getlist('turmas')
        # Remove vínculos antigos
        Turma.objects.filter(professor_responsavel=professor).update(professor_responsavel=None)
        # Adiciona novos vínculos
        for turma_id in turmas_ids:
            Turma.objects.filter(id=turma_id).update(professor_responsavel=professor)
        
        messages.success(request, f'Professor {professor.first_name} atualizado com sucesso!')
        return redirect('admin_dashboard:professores_list')
    
    # GET - mostra formulário
    turmas_disponiveis = Turma.objects.filter(ativa=True).order_by('nome')
    turmas_vinculadas = professor.turmas_ministradas.all()
    
    context = {
        'professor': professor,
        'turmas_disponiveis': turmas_disponiveis,
        'turmas_vinculadas': turmas_vinculadas,
    }
    return render(request, 'admin_dashboard/professores/editar.html', context)

@login_required
def professor_excluir(request, pk):
    """Excluir professor"""
    
    if not request.user.is_staff:
        return redirect('home')
    
    if request.method == 'POST':
        from django.contrib.auth.models import User
        from usuarios.models import Turma
        
        professor = get_object_or_404(User, pk=pk, groups__name='Professores')
        nome = professor.first_name
        
        # Remove vínculo com turmas
        Turma.objects.filter(professor_responsavel=professor).update(professor_responsavel=None)
        
        professor.delete()
        messages.success(request, f'Professor {nome} excluído com sucesso!')
    
    return redirect('admin_dashboard:professores_list')

# ==================== VIEWS PARA PROFESSORES ====================

@login_required
def professor_transformar_em_aluna(request, pk):
    """Cadastra um professor também como aluna, usando o mesmo login."""

    if not request.user.is_staff:
        return redirect('home')

    if request.method != 'POST':
        return redirect('admin_dashboard:professores_list')

    from django.contrib.auth.models import User
    from django.contrib import messages
    from django.shortcuts import get_object_or_404
    from usuarios.models import Aluna, Perfil

    professor = get_object_or_404(User, pk=pk, groups__name='Professores')

    if hasattr(professor, 'aluna_vinculada') and professor.aluna_vinculada:
        messages.warning(
            request,
            f'{professor.get_full_name() or professor.username} já está cadastrada como aluna.'
        )
        return redirect('admin_dashboard:professores_list')

    nome_aluna = (
        professor.get_full_name().strip()
        or professor.first_name.strip()
        or professor.username
    )

    genero = None
    data_nascimento = None

    if hasattr(professor, 'perfil'):
        genero = professor.perfil.genero
        data_nascimento = professor.perfil.data_nascimento

    Aluna.objects.create(
        responsavel=None,
        usuario=professor,
        tipo_aluna='adulto',
        nome=nome_aluna,
        genero=genero,
        data_nascimento=data_nascimento,
        ativa=True,
        observacoes='Cadastro criado automaticamente a partir do perfil de professora.'
    )

    if hasattr(professor, 'perfil'):
        professor.perfil.is_tambem_aluno = True
        professor.perfil.save(update_fields=['is_tambem_aluno'])

    messages.success(
        request,
        f'{nome_aluna} foi cadastrada como aluna com sucesso, usando o mesmo login.'
    )
    return redirect('admin_dashboard:professores_list')

@login_required
def professor_dashboard(request):
    """Dashboard do professor - mostra apenas suas turmas"""
    
    if not request.user.groups.filter(name='Professores').exists():
        return redirect('home')
    
    from usuarios.models import Turma, Aluna
    
    # Turmas do professor
    turmas = Turma.objects.filter(professor_responsavel=request.user, ativa=True)
    
    # Totais
    total_turmas = turmas.count()
    total_alunas = Aluna.objects.filter(turmas__in=turmas, ativa=True).distinct().count()
    
    context = {
        'turmas': turmas,
        'total_turmas': total_turmas,
        'total_alunas': total_alunas,
    }
    return render(request, 'admin_dashboard/professor/dashboard.html', context)

@login_required
def professor_turma_detalhes(request, pk):
    """Detalhes da turma para professor"""
    
    if not request.user.groups.filter(name='Professores').exists():
        return redirect('home')
    
    from usuarios.models import Turma, Aluna
    from django.shortcuts import get_object_or_404
    
    turma = get_object_or_404(Turma, pk=pk, professor_responsavel=request.user)
    alunas = Aluna.objects.filter(turmas=turma, ativa=True).order_by('nome')
    
    # Calcula idade de cada aluna
    for aluna in alunas:
        aluna.idade_calculada = aluna.idade if aluna.idade else '--'
    
    context = {
        'turma': turma,
        'alunas': alunas,
        'total_alunas': alunas.count(),
    }
    return render(request, 'admin_dashboard/professor/turma_detalhes.html', context)

@login_required
def professor_agendamentos(request):
    """Lista os agendamentos das turmas do professor logado, com os mesmos filtros do admin"""

    if not request.user.groups.filter(name='Professores').exists():
        return redirect('home')

    from usuarios.models import Turma
    from agenda.models import Agendamento
    from django.utils import timezone
    import datetime

    turmas_professor = Turma.objects.filter(professor_responsavel=request.user, ativa=True)

    agendamentos = (
        Agendamento.objects
        .filter(aula__in=turmas_professor)
        .select_related('aula')
        .order_by('data', 'horario')
    )

    hoje = timezone.localdate()

    tipo = request.GET.get('tipo', 'proximos')
    mes = request.GET.get('mes', '')
    semana = request.GET.get('semana', '')

    if tipo == 'antigos':
        agendamentos = agendamentos.filter(data__lt=hoje).order_by('-data', '-horario')
    else:
        tipo = 'proximos'
        agendamentos = agendamentos.filter(data__gte=hoje)

    if mes:
        try:
            ano_str, mes_str = mes.split('-')
            agendamentos = agendamentos.filter(data__year=int(ano_str), data__month=int(mes_str))
        except (ValueError, AttributeError):
            pass

    if semana:
        try:
            ano_str, semana_str = semana.split('-W')
            ano_semana = int(ano_str)
            num_semana = int(semana_str)
            inicio_semana = datetime.date.fromisocalendar(ano_semana, num_semana, 1)
            fim_semana = datetime.date.fromisocalendar(ano_semana, num_semana, 7)
            agendamentos = agendamentos.filter(data__gte=inicio_semana, data__lte=fim_semana)
        except (ValueError, AttributeError):
            pass

    total_geral = Agendamento.objects.filter(aula__in=turmas_professor).count()
    total_proximos = Agendamento.objects.filter(aula__in=turmas_professor, data__gte=hoje).count()
    total_antigos = Agendamento.objects.filter(aula__in=turmas_professor, data__lt=hoje).count()

    meses_disponiveis = (
        Agendamento.objects
        .filter(aula__in=turmas_professor)
        .dates('data', 'month', order='DESC')
    )

    context = {
        'agendamentos': agendamentos,
        'total_geral': total_geral,
        'total_proximos': total_proximos,
        'total_antigos': total_antigos,
        'meses_disponiveis': meses_disponiveis,
        'tipo': tipo,
        'mes': mes,
        'semana': semana,
        'hoje': hoje,
    }
    return render(request, 'admin_dashboard/professor/agendamentos.html', context)

@login_required
def ficha_audicao(request, pk):
    """Página de ficha de avaliação para audição"""
    if not request.user.is_staff:
        return redirect('home')
    
    from espetaculo.models import InscricaoAudicao, AvaliacaoAudicao
    import ast
    
    inscricao = get_object_or_404(InscricaoAudicao, pk=pk)
    
    # Converte a lista de personagens corretamente
    try:
        personagens_lista = ast.literal_eval(inscricao.personagens)
        if not isinstance(personagens_lista, list):
            personagens_lista = [inscricao.personagens]
    except:
        # Fallback: tenta com split
        valor_limpo = inscricao.personagens.replace('[', '').replace(']', '').replace("'", "").strip()
        personagens_lista = [p.strip() for p in valor_limpo.split(',')] if valor_limpo else []
    
    # Dicionário para converter nomes dos personagens
    personagens_dict = {
        'thessalia': 'Thessália',
        'zyara': 'Zyara',
        'zyar': 'Zyar',
        'astela_nur': 'Astela Nur',
        'kai_ignus': 'Kai Ignus',
        'eldrick_felicius': 'Eldrick Felicius',
        'florine': 'Florine',
        'odessa': 'Odessa',
        'aurelia': 'Aurélia',
        'cora_del_amour': 'Cora del Amour',
        '3_marias': '3 Marias',
    }
    
    # Converte os nomes dos personagens para exibição legível
    personagens_legiveis = [personagens_dict.get(p, p) for p in personagens_lista]
    
    # Busca ou cria avaliações para cada personagem
    avaliacoes = {}
    for personagem, personagem_legivel in zip(personagens_lista, personagens_legiveis):
        aval, created = AvaliacaoAudicao.objects.get_or_create(
            inscricao=inscricao,
            personagem=personagem_legivel,
            defaults={
                'nome_participante': inscricao.nome_completo,
                'nivel': 'regular'
            }
        )
        avaliacoes[personagem_legivel] = aval
    
    if request.method == 'POST':
        # Salvar avaliações
        for personagem_legivel in personagens_legiveis:
            aval, created = AvaliacaoAudicao.objects.get_or_create(
                inscricao=inscricao,
                personagem=personagem_legivel
            )
            aval.nome_participante = request.POST.get(f'nome_{personagem_legivel}', inscricao.nome_completo)
            aval.nivel = request.POST.get(f'nivel_{personagem_legivel}', 'regular')
            aval.observacoes = request.POST.get(f'obs_{personagem_legivel}', '')
            aval.save()
        
        messages.success(request, 'Avaliação salva com sucesso!')
        return redirect('admin_dashboard:inscricoes_audicao')
    
    context = {
        'inscricao': inscricao,
        'avaliacoes': avaliacoes,
        'personagens_lista': personagens_legiveis,
        'nivel_opcoes': AvaliacaoAudicao.NIVEL_OPCOES,
    }
    return render(request, 'admin_dashboard/espetaculos/ficha.html', context)

#from weasyprint import HTML
from django.template.loader import render_to_string
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from datetime import datetime

@login_required
def ficha_pdf(request, pk):
    """Gera PDF da ficha de avaliação"""
    messages.warning(request, 'Função de PDF temporariamente indisponível. Use Ctrl+P para imprimir.')
    return redirect('admin_dashboard:inscricoes_audicao')


@login_required
def espetaculo_participacoes(request, pk):
    if not request.user.is_staff:
        return redirect('home')

    try:
        from decimal import Decimal
        from django.contrib import messages
        from django.db.models import Prefetch
        from django.shortcuts import get_object_or_404, redirect, render

        from usuarios.models import Aluna, Turma
        from espetaculo.models import (
            Espetaculo,
            ParticipacaoEspetaculo,
            CobrancaEspetaculo,
            ParcelaCobrancaEspetaculo,
        )

        espetaculo = get_object_or_404(Espetaculo, pk=pk)

        if request.method == 'POST':
            aluna_id = request.POST.get('aluna_id')

            if not aluna_id:
                messages.error(request, 'Selecione uma aluna.')
                return redirect('admin_dashboard:espetaculo_participacoes', pk=pk)

            participacao_existente = ParticipacaoEspetaculo.objects.filter(
                espetaculo=espetaculo,
                aluna_id=aluna_id
            ).first()

            if participacao_existente:
                messages.warning(request, 'Essa aluna já está vinculada a este espetáculo.')
                return redirect('admin_dashboard:espetaculo_participacoes', pk=pk)

            ParticipacaoEspetaculo.objects.create(
                espetaculo=espetaculo,
                aluna_id=aluna_id,
                vai_dancar=True
            )

            messages.success(request, 'Participação adicionada com sucesso.')
            return redirect('admin_dashboard:espetaculo_participacoes', pk=pk)

        turma_id = request.GET.get('turma')

        parcelas_qs = ParcelaCobrancaEspetaculo.objects.order_by('numero_parcela', 'id')

        cobrancas_qs = (
            CobrancaEspetaculo.objects
            .prefetch_related(
                Prefetch('parcelas', queryset=parcelas_qs)
            )
            .order_by('-criado_em', '-id')
        )

        participacoes = (
            ParticipacaoEspetaculo.objects
            .filter(espetaculo=espetaculo)
            .select_related('aluna', 'aluna__responsavel', 'espetaculo')
            .prefetch_related(
                'aluna__turmas',
                Prefetch('cobrancas', queryset=cobrancas_qs)
            )
            .order_by('aluna__nome')
        )

        if turma_id:
            participacoes = participacoes.filter(aluna__turmas__id=turma_id).distinct()

        alunas_disponiveis = (
            Aluna.objects
            .exclude(participacoes_espetaculo__espetaculo=espetaculo)
            .order_by('nome')
        )

        turmas = Turma.objects.order_by('nome')

        status_por_participacao = {}
        quantidade_cobrancas_por_participacao = {}

        total_recebido_taxa_palco = Decimal('0.00')
        total_recebido_figurino = Decimal('0.00')
        total_a_receber_taxa_palco = Decimal('0.00')
        total_a_receber_figurino = Decimal('0.00')

        def resumir_status(lista_cobrancas):
            if not lista_cobrancas:
                return None

            total_pago = sum(
                (c.total_pago() or Decimal('0.00') for c in lista_cobrancas),
                Decimal('0.00')
            )

            total_cobrado = sum(
                (c.valor_total_efetivo() or Decimal('0.00') for c in lista_cobrancas),
                Decimal('0.00')
            )

            if total_pago <= Decimal('0.00'):
                return 'pendente'

            if total_pago < total_cobrado:
                return 'parcial'

            return 'pago'

        for participacao in participacoes:
            cobrancas = list(participacao.cobrancas.all())

            cobrancas_taxa_palco = [c for c in cobrancas if c.tipo == 'taxa_palco']
            cobrancas_figurino = [c for c in cobrancas if c.tipo == 'figurino']

            pago_taxa_palco = sum(
                (c.total_pago() or Decimal('0.00') for c in cobrancas_taxa_palco),
                Decimal('0.00')
            )

            pago_figurino = sum(
                (c.total_pago() or Decimal('0.00') for c in cobrancas_figurino),
                Decimal('0.00')
            )

            pendente_taxa_palco = sum(
                (c.total_pendente() or Decimal('0.00') for c in cobrancas_taxa_palco),
                Decimal('0.00')
            )

            pendente_figurino = sum(
                (c.total_pendente() or Decimal('0.00') for c in cobrancas_figurino),
                Decimal('0.00')
            )

            total_recebido_taxa_palco += pago_taxa_palco
            total_recebido_figurino += pago_figurino
            total_a_receber_taxa_palco += pendente_taxa_palco
            total_a_receber_figurino += pendente_figurino

            status_por_participacao[participacao.pk] = {
                'taxa_palco_status': resumir_status(cobrancas_taxa_palco),
                'figurino_status': resumir_status(cobrancas_figurino),
                'taxa_palco_pago': pago_taxa_palco,
                'figurino_pago': pago_figurino,
                'total_pago': pago_taxa_palco + pago_figurino,
            }

            quantidade_cobrancas_por_participacao[participacao.pk] = len(cobrancas)

        total_recebido_geral = total_recebido_taxa_palco + total_recebido_figurino
        total_a_receber_geral = total_a_receber_taxa_palco + total_a_receber_figurino

        context = {
            'espetaculo': espetaculo,
            'participacoes': participacoes,
            'alunas_disponiveis': alunas_disponiveis,
            'turmas': turmas,
            'turma_selecionada': turma_id,
            'total_participacoes': participacoes.count(),
            'status_por_participacao': status_por_participacao,
            'quantidade_cobrancas_por_participacao': quantidade_cobrancas_por_participacao,
            'total_recebido_taxa_palco': total_recebido_taxa_palco,
            'total_recebido_figurino': total_recebido_figurino,
            'total_recebido_geral': total_recebido_geral,
            'total_a_receber_taxa_palco': total_a_receber_taxa_palco,
            'total_a_receber_figurino': total_a_receber_figurino,
            'total_a_receber_geral': total_a_receber_geral,
        }

        return render(
            request,
            'admin_dashboard/espetaculos/participacoes.html',
            context
        )

    except Exception as e:
        from django.contrib import messages
        messages.error(request, f'Erro ao carregar participações: {e}')
        return redirect('admin_dashboard:espetaculos_list')

@login_required
def espetaculo_participantes_png(request, pk):
    if not request.user.is_staff:
        return redirect('home')

    import os
    from io import BytesIO
    from PIL import Image, ImageDraw, ImageFont
    from django.http import HttpResponse
    from django.shortcuts import get_object_or_404
    from django.conf import settings

    from usuarios.models import Turma
    from espetaculo.models import Espetaculo, ParticipacaoEspetaculo

    espetaculo = get_object_or_404(Espetaculo, pk=pk)
    turma_id = request.GET.get('turma')

    participacoes = (
        ParticipacaoEspetaculo.objects
        .filter(espetaculo=espetaculo)
        .select_related('aluna')
        .prefetch_related('aluna__turmas')
        .order_by('aluna__nome')
    )

    if turma_id:
        participacoes = participacoes.filter(aluna__turmas__id=turma_id).distinct()

    # Buscar a turma selecionada (se houver)
    turma_selecionada_obj = None
    if turma_id:
        turma_selecionada_obj = Turma.objects.filter(id=turma_id).first()

    grupos = {}
    for participacao in participacoes:
        if turma_id and turma_selecionada_obj:
            # Se há filtro, usar apenas a turma selecionada como rótulo
            turmas_para_agrupar = [turma_selecionada_obj]
        else:
            # Sem filtro, usar todas as turmas da aluna
            turmas_para_agrupar = list(participacao.aluna.turmas.all())

        if not turmas_para_agrupar:
            grupos.setdefault('Sem turma', []).append(participacao.aluna.nome)
        else:
            for turma in turmas_para_agrupar:
                grupos.setdefault(turma.nome, []).append(participacao.aluna.nome)

    for nomes in grupos.values():
        nomes.sort()

    grupos_ordenados = dict(sorted(grupos.items(), key=lambda x: x[0]))

    # Caminho absoluto da fonte
    fonte_path = os.path.join(
        settings.BASE_DIR,
        'static',
        'fonts',
        'NotoSans-VariableFont_wdth,wght.ttf'
    )

    try:
        ImageFont.truetype(fonte_path, 20)
        fonte_existe = True
    except Exception:
        fonte_existe = False

    escala = 2 if fonte_existe else 1

    def carregar_fonte(tamanho, negrito=False):
        if not fonte_existe:
            return ImageFont.load_default()
        fonte = ImageFont.truetype(fonte_path, tamanho)
        try:
            if negrito:
                fonte.set_variation_by_name('Bold')
            else:
                fonte.set_variation_by_name('Regular')
        except Exception:
            try:
                if negrito:
                    fonte.set_variation_by_axes([100, 700])
                else:
                    fonte.set_variation_by_axes([100, 400])
            except Exception:
                pass
        return fonte

    def quebrar_texto(texto, fonte, largura_maxima, draw):
        palavras = texto.split(' ')
        linhas = []
        linha_atual = ''

        for palavra in palavras:
            linha_teste = f"{linha_atual} {palavra}".strip()
            bbox = draw.textbbox((0, 0), linha_teste, font=fonte)
            largura_linha = bbox[2] - bbox[0]

            if largura_linha <= largura_maxima or not linha_atual:
                linha_atual = linha_teste
            else:
                linhas.append(linha_atual)
                linha_atual = palavra

        if linha_atual:
            linhas.append(linha_atual)

        return linhas

    fonte_titulo = carregar_fonte(36 * escala, negrito=True)
    fonte_turma = carregar_fonte(26 * escala, negrito=True)
    fonte_nome = carregar_fonte(22 * escala, negrito=False)

    largura = 1000 * escala
    margem = 60 * escala
    altura_linha_nome = 34 * escala
    altura_espaco_turma = 60 * escala
    altura_linha_titulo = 46 * escala

    largura_maxima_titulo = largura - (2 * margem)

    # Imagem temporária apenas para medir o texto antes de saber a altura final
    imagem_temp = Image.new("RGB", (10, 10))
    draw_temp = ImageDraw.Draw(imagem_temp)

    # Se houver turma selecionada, mostra no título
    if turma_selecionada_obj:
        titulo = f"Participantes - {turma_selecionada_obj.nome}"
    else:
        titulo = f"Participantes - {espetaculo.titulo}"

    linhas_titulo = quebrar_texto(titulo, fonte_titulo, largura_maxima_titulo, draw_temp)

    altura_bloco_titulo = 40 * escala + (len(linhas_titulo) * altura_linha_titulo) + (30 * escala)

    altura_total = altura_bloco_titulo
    for nomes in grupos_ordenados.values():
        altura_total += altura_espaco_turma + (len(nomes) * altura_linha_nome) + (25 * escala)
    altura_total += margem

    imagem = Image.new("RGB", (largura, altura_total), "white")
    draw = ImageDraw.Draw(imagem)

    y = 40 * escala
    for linha in linhas_titulo:
        draw.text((margem, y), linha, fill="#2f2438", font=fonte_titulo)
        y += altura_linha_titulo

    y += 30 * escala

    for turma_nome, nomes in grupos_ordenados.items():
        draw.rectangle(
            [(margem, y), (largura - margem, y + 42 * escala)],
            fill="#ede7f5"
        )
        draw.text((margem + 14 * escala, y + 8 * escala), turma_nome, fill="#6b2d8f", font=fonte_turma)
        y += altura_espaco_turma

        for nome in nomes:
            draw.text((margem + 24 * escala, y), f"• {nome}", fill="#2f2438", font=fonte_nome)
            y += altura_linha_nome

        y += 25 * escala

    if fonte_existe:
        largura_final = largura // escala
        altura_final = altura_total // escala
        imagem = imagem.resize((largura_final, altura_final), Image.LANCZOS)

    buffer = BytesIO()
    imagem.save(buffer, format='PNG', optimize=True)
    buffer.seek(0)

    if turma_selecionada_obj:
        nome_arquivo = f"participantes-{turma_selecionada_obj.nome.lower().replace(' ', '-')}.png"
    else:
        nome_arquivo = f"participantes-{espetaculo.titulo.lower().replace(' ', '-')}.png"

    response = HttpResponse(buffer.getvalue(), content_type='image/png')
    response['Content-Disposition'] = f'attachment; filename="{nome_arquivo}"'
    return response
    
from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render


from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.dateparse import parse_date


@login_required
def participacao_cobrancas(request, pk):
    if not request.user.is_staff:
        return redirect('home')

    try:
        from decimal import Decimal, InvalidOperation
        from django.contrib import messages
        from django.core.exceptions import ValidationError
        from django.db.models import Prefetch
        from django.shortcuts import get_object_or_404, render, redirect
        from django.utils.dateparse import parse_date

        from espetaculo.models import (
            ParticipacaoEspetaculo,
            CobrancaEspetaculo,
            ParcelaCobrancaEspetaculo,
        )

        participacao = get_object_or_404(
            ParticipacaoEspetaculo.objects.select_related(
                'espetaculo',
                'aluna',
                'aluna__responsavel'
            ),
            pk=pk
        )

        if request.method == 'POST':
            tipo = (request.POST.get('tipo') or '').strip()
            descricao = (request.POST.get('descricao') or '').strip()
            valor_total = (request.POST.get('valor_total') or '').strip()
            permitir_parcelamento = request.POST.get('permitir_parcelamento') == 'on'
            desconto_irmaos = request.POST.get('desconto_irmaos') == 'on'
            sem_desconto = request.POST.get('sem_desconto') == 'on'
            max_parcelas = request.POST.get('max_parcelas') or 1
            vencimento_primeira_parcela = request.POST.get('vencimento_primeira_parcela')

            valor_figurino_avista = (request.POST.get('valor_figurino_avista') or '').strip()
            valor_figurino_parcelado = (request.POST.get('valor_figurino_parcelado') or '').strip()

            if not tipo or not descricao or not valor_total:
                messages.error(request, 'Preencha os campos obrigatórios da cobrança.')
                return redirect('admin_dashboard:participacao_cobrancas', pk=pk)

            try:
                valor_total = Decimal(valor_total.replace(',', '.'))
            except (InvalidOperation, AttributeError):
                messages.error(request, 'Valor total inválido.')
                return redirect('admin_dashboard:participacao_cobrancas', pk=pk)

            valor_figurino_avista_decimal = None
            valor_figurino_parcelado_decimal = None

            if tipo == 'figurino':
                if not valor_figurino_avista:
                    messages.error(request, 'Informe o valor à vista do figurino.')
                    return redirect('admin_dashboard:participacao_cobrancas', pk=pk)

                try:
                    valor_figurino_avista_decimal = Decimal(valor_figurino_avista.replace(',', '.'))
                except (InvalidOperation, AttributeError):
                    messages.error(request, 'Valor à vista do figurino inválido.')
                    return redirect('admin_dashboard:participacao_cobrancas', pk=pk)

                if permitir_parcelamento:
                    if not valor_figurino_parcelado:
                        messages.error(request, 'Informe o valor parcelado do figurino.')
                        return redirect('admin_dashboard:participacao_cobrancas', pk=pk)

                    try:
                        valor_figurino_parcelado_decimal = Decimal(valor_figurino_parcelado.replace(',', '.'))
                    except (InvalidOperation, AttributeError):
                        messages.error(request, 'Valor parcelado do figurino inválido.')
                        return redirect('admin_dashboard:participacao_cobrancas', pk=pk)

            try:
                max_parcelas = int(max_parcelas)
            except Exception:
                max_parcelas = 1

            if max_parcelas < 1:
                max_parcelas = 1

            if not permitir_parcelamento:
                max_parcelas = 1

            data_vencimento = None
            if vencimento_primeira_parcela:
                data_vencimento = parse_date(vencimento_primeira_parcela)

            if vencimento_primeira_parcela and not data_vencimento:
                messages.error(request, 'Data de vencimento inválida.')
                return redirect('admin_dashboard:participacao_cobrancas', pk=pk)

            cobranca = CobrancaEspetaculo(
                participacao=participacao,
                tipo=tipo,
                descricao=descricao,
                valor_total=valor_total,
                permitir_parcelamento=permitir_parcelamento,
                max_parcelas=max_parcelas,
                vencimento_primeira_parcela=data_vencimento,
                desconto_irmaos=desconto_irmaos,
                sem_desconto=sem_desconto,
                valor_figurino_avista=valor_figurino_avista_decimal,
                valor_figurino_parcelado=valor_figurino_parcelado_decimal,
            )

            try:
                cobranca.full_clean()
                cobranca.save()
            except ValidationError as e:
                if hasattr(e, 'message_dict'):
                    for mensagens_validacao in e.message_dict.values():
                        for mensagem in mensagens_validacao:
                            messages.error(request, mensagem)
                else:
                    messages.error(request, 'Erro de validação ao criar cobrança.')
                return redirect('admin_dashboard:participacao_cobrancas', pk=pk)

            messages.success(request, 'Cobrança criada com sucesso.')
            return redirect('admin_dashboard:participacao_cobrancas', pk=pk)

        parcelas_qs = ParcelaCobrancaEspetaculo.objects.order_by('numero_parcela', 'id')

        cobrancas = (
            CobrancaEspetaculo.objects
            .filter(participacao=participacao)
            .prefetch_related(
                Prefetch('parcelas', queryset=parcelas_qs)
            )
            .order_by('-criado_em', '-id')
        )

        context = {
            'participacao': participacao,
            'cobrancas': cobrancas,
            'total_cobrancas': cobrancas.count(),
        }

        return render(
            request,
            'admin_dashboard/espetaculos/participacao_cobrancas.html',
            context
        )

    except Exception as e:
        messages.error(request, f'Erro ao carregar cobranças: {e}')
        return redirect('admin_dashboard:espetaculos_list')


@login_required
def cobranca_espetaculo_enviar_asaas(request, pk):
    if not request.user.is_staff:
        return redirect('home')

    if request.method != 'POST':
        messages.error(request, 'Método inválido.')
        return redirect('admin_dashboard:espetaculos_list')

    try:
        from django.shortcuts import get_object_or_404
        from espetaculo.models import CobrancaEspetaculo

        cobranca = get_object_or_404(
            CobrancaEspetaculo.objects.select_related(
                'participacao',
                'participacao__aluna',
                'participacao__aluna__responsavel',
                'participacao__aluna__usuario',
                'participacao__espetaculo',
            ).prefetch_related('parcelas'),
            pk=pk
        )

        if cobranca.enviado_asaas:
            messages.warning(request, 'Essa cobrança já foi enviada ao Asaas.')
            return redirect(
                'admin_dashboard:participacao_cobrancas',
                pk=cobranca.participacao.pk
            )

        aluna = cobranca.participacao.aluna
        responsavel = aluna.responsavel

        # AJUSTE: aluna adulta sem responsável usa o próprio usuário como titular da cobrança
        titular_cobranca = responsavel if responsavel else (
            aluna.usuario if aluna.tipo_aluna == 'adulto' else None
        )

        if not titular_cobranca:
            messages.error(
                request,
                'A aluna não possui responsável nem login próprio vinculado para gerar cobrança.'
            )
            return redirect(
                'admin_dashboard:participacao_cobrancas',
                pk=cobranca.participacao.pk
            )

        if not cobranca.vencimento_primeira_parcela:
            messages.error(
                request,
                'Defina o vencimento da primeira parcela antes de disponibilizar a cobrança.'
            )
            return redirect(
                'admin_dashboard:participacao_cobrancas',
                pk=cobranca.participacao.pk
            )

        if not cobranca.opcoes_parcelas:
            messages.error(
                request,
                'Esta cobrança não possui opções de pagamento válidas no período atual.'
            )
            return redirect(
                'admin_dashboard:participacao_cobrancas',
                pk=cobranca.participacao.pk
            )

        # AJUSTE: mensagem ajustada para contemplar aluna adulta titular
        if responsavel:
            texto_titular = 'pela responsável'
        else:
            texto_titular = 'pela própria aluna'

        messages.info(
            request,
            f'A escolha de pagamento é feita {texto_titular} na área dela. '
            'A cobrança será enviada ao Asaas somente quando ela escolher à vista ou a quantidade de parcelas.'
        )
        return redirect(
            'admin_dashboard:participacao_cobrancas',
            pk=cobranca.participacao.pk
        )

    except Exception as e:
        messages.error(request, f'Erro ao processar cobrança: {e}')
        return redirect('admin_dashboard:espetaculos_list')
    
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.db import transaction


@login_required
def cobranca_espetaculo_escolher_parcelas(request, pk):
    """Responsável (ou aluna adulta titular) escolhe quantidade de parcelas e cria cobranças Pix no Asaas."""

    if request.method != 'POST':
        messages.error(request, 'Método inválido.')
        return redirect('home')

    try:
        from decimal import Decimal
        from django.db import transaction
        from django.shortcuts import get_object_or_404
        from django.utils import timezone
        from espetaculo.models import CobrancaEspetaculo, ParcelaCobrancaEspetaculo
        from pagamentos.services.asaas import (
            AsaasError,
            get_or_create_customer,
            create_payment,
            create_installment_payment,
            list_installment_payments,
        )

        cobranca = get_object_or_404(
            CobrancaEspetaculo.objects.select_related(
                'participacao',
                'participacao__aluna',
                'participacao__aluna__responsavel',
                'participacao__aluna__usuario',
                'participacao__espetaculo',
            ).prefetch_related('parcelas'),
            pk=pk
        )

        aluna = cobranca.participacao.aluna
        responsavel = aluna.responsavel

        # AJUSTE 1: aluna adulta sem responsável usa o próprio usuário como titular da cobrança
        titular_cobranca = responsavel if responsavel else (
            aluna.usuario if aluna.tipo_aluna == 'adulto' else None
        )

        if not request.user.is_staff and request.user != titular_cobranca:
            messages.error(request, 'Acesso negado.')
            return redirect('home')

        if cobranca.enviado_asaas:
            messages.warning(request, 'Essa cobrança já foi enviada ao Asaas.')
            return redirect('cobrancas_espetaculos')

        # AJUSTE 2: mensagem e checagem agora consideram o titular (responsável OU aluna adulta)
        if not titular_cobranca:
            messages.error(
                request,
                'A aluna não possui responsável nem login próprio vinculado para gerar cobrança.'
            )
            return redirect('cobrancas_espetaculos')

        if not cobranca.vencimento_primeira_parcela:
            messages.error(request, 'O vencimento da primeira parcela não foi definido.')
            return redirect('cobrancas_espetaculos')

        try:
            num_parcelas = int(request.POST.get('num_parcelas', 1))
        except (ValueError, TypeError):
            num_parcelas = 1

        opcoes_validas = cobranca.opcoes_parcelas

        if not opcoes_validas:
            messages.error(
                request,
                'Esta cobrança não possui opções de pagamento disponíveis neste período.'
            )
            return redirect('cobrancas_espetaculos')

        if num_parcelas not in opcoes_validas:
            messages.error(
                request,
                'A opção de pagamento escolhida não está mais disponível.'
            )
            return redirect('cobrancas_espetaculos')

        valor_final = cobranca.valor_com_desconto(num_parcelas)
        percentual_desconto = cobranca.percentual_desconto_para(num_parcelas)

        hoje = timezone.localdate()
        due_date = cobranca.vencimento_primeira_parcela

        if due_date < hoje:
            due_date = hoje

        # AJUSTE 3: cliente Asaas criado a partir do titular (responsável OU aluna adulta)
        customer = get_or_create_customer(titular_cobranca)

        if not customer or not customer.get('id'):
            raise AsaasError('Não foi possível obter o cliente no Asaas.')

        descricao_base = (
            f'{cobranca.get_tipo_display()} - '
            f'{cobranca.participacao.espetaculo.titulo} - '
            f'{cobranca.participacao.aluna.nome}'
        )

        if cobranca.tipo == 'figurino':
            if num_parcelas == 1:
                descricao_base += ' - valor à vista'
            else:
                descricao_base += f' - {num_parcelas}x com valor parcelado'
        elif percentual_desconto > Decimal('0.00'):
            descricao_base += f' - desconto de {percentual_desconto}%'

        billing_type = 'PIX'

        parcelas_existentes = list(cobranca.parcelas.all())
        if parcelas_existentes:
            existe_pagamento = any(
                (parcela.valor_pago or Decimal('0.00')) > Decimal('0.00')
                or parcela.status in ('parcial', 'pago')
                for parcela in parcelas_existentes
            )
            if existe_pagamento:
                messages.error(
                    request,
                    'Esta cobrança já possui parcelas com pagamento registrado e não pode ser recriada.'
                )
                return redirect('cobrancas_espetaculos')

        if num_parcelas > 1:
            retorno = create_installment_payment(
                customer_id=customer['id'],
                total_value=valor_final,
                installment_count=num_parcelas,
                due_date=due_date,
                description=descricao_base,
                external_reference=f'cobranca_espetaculo:{cobranca.pk}',
                billing_type=billing_type,
            )

            installment_id = retorno.get('installment')
            if not installment_id:
                raise AsaasError('O Asaas não retornou o installment da cobrança parcelada.')

            parcelas_response = list_installment_payments(installment_id)
            parcelas_asaas = parcelas_response.get('data', [])

            parcelas_asaas = sorted(
                parcelas_asaas,
                key=lambda item: item.get('dueDate') or ''
            )

            with transaction.atomic():
                if parcelas_existentes:
                    cobranca.parcelas.all().delete()

                cobranca.asaas_customer_id = customer.get('id')
                cobranca.billing_type = billing_type
                cobranca.enviado_asaas = True
                cobranca.save(update_fields=['asaas_customer_id', 'billing_type', 'enviado_asaas'])

                for idx, item in enumerate(parcelas_asaas, start=1):
                    parcela = ParcelaCobrancaEspetaculo.objects.create(
                        cobranca=cobranca,
                        numero_parcela=idx,
                        total_parcelas=len(parcelas_asaas),
                        valor=item.get('value') or 0,
                        vencimento=item.get('dueDate'),
                        asaas_payment_id=item.get('id'),
                        asaas_installment_id=installment_id,
                        asaas_invoice_url=item.get('invoiceUrl'),
                        asaas_bank_slip_url=item.get('bankSlipUrl'),
                        asaas_transaction_receipt_url=item.get('transactionReceiptUrl'),
                        asaas_nosso_numero=item.get('nossoNumero'),
                        asaas_status=item.get('status'),
                        billing_type=item.get('billingType') or billing_type,
                    )
                    parcela.atualizar_status_asaas(item.get('status'))

                cobranca.atualizar_status()

            if cobranca.vencimento_primeira_parcela < hoje:
                messages.warning(
                    request,
                    f'A data original de vencimento já havia passado. A primeira parcela foi ajustada para {due_date.strftime("%d/%m/%Y")}.'
                )

            if cobranca.tipo == 'figurino':
                messages.success(
                    request,
                    f'Cobrança de figurino em {num_parcelas}x enviada com sucesso! Pague via Pix abaixo.'
                )
            elif percentual_desconto > Decimal('0.00'):
                messages.success(
                    request,
                    f'Cobrança em {num_parcelas}x enviada com sucesso, com {percentual_desconto}% de desconto! Pague via Pix abaixo.'
                )
            else:
                messages.success(
                    request,
                    f'Cobrança em {num_parcelas}x enviada com sucesso! Pague via Pix abaixo.'
                )

        else:
            retorno = create_payment(
                customer_id=customer['id'],
                value=valor_final,
                due_date=due_date,
                description=descricao_base,
                external_reference=f'cobranca_espetaculo:{cobranca.pk}',
                billing_type=billing_type,
            )

            with transaction.atomic():
                if parcelas_existentes:
                    cobranca.parcelas.all().delete()

                cobranca.asaas_customer_id = customer.get('id')
                cobranca.billing_type = billing_type
                cobranca.enviado_asaas = True
                cobranca.save(update_fields=['asaas_customer_id', 'billing_type', 'enviado_asaas'])

                parcela = ParcelaCobrancaEspetaculo.objects.create(
                    cobranca=cobranca,
                    numero_parcela=1,
                    total_parcelas=1,
                    valor=retorno.get('value') or valor_final,
                    vencimento=retorno.get('dueDate') or due_date,
                    asaas_payment_id=retorno.get('id'),
                    asaas_invoice_url=retorno.get('invoiceUrl'),
                    asaas_bank_slip_url=retorno.get('bankSlipUrl'),
                    asaas_transaction_receipt_url=retorno.get('transactionReceiptUrl'),
                    asaas_nosso_numero=retorno.get('nossoNumero'),
                    asaas_status=retorno.get('status'),
                    billing_type=retorno.get('billingType') or billing_type,
                )
                parcela.atualizar_status_asaas(retorno.get('status'))

                cobranca.atualizar_status()

            if cobranca.vencimento_primeira_parcela < hoje:
                messages.warning(
                    request,
                    f'A data original de vencimento já havia passado. O vencimento foi ajustado para {due_date.strftime("%d/%m/%Y")}.'
                )

            if cobranca.tipo == 'figurino':
                messages.success(
                    request,
                    'Cobrança de figurino à vista enviada com sucesso! Pague via Pix abaixo.'
                )
            elif percentual_desconto > Decimal('0.00'):
                messages.success(
                    request,
                    f'Cobrança à vista enviada com sucesso, com {percentual_desconto}% de desconto! Pague via Pix abaixo.'
                )
            else:
                messages.success(
                    request,
                    'Cobrança à vista enviada com sucesso! Pague via Pix abaixo.'
                )

        return redirect('cobrancas_espetaculos')

    except Exception as e:
        messages.error(request, f'Erro ao gerar cobrança: {e}')
        return redirect('cobrancas_espetaculos')

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.db import transaction


@login_required
def cobranca_espetaculo_excluir(request, pk):
    if not request.user.is_staff:
        return redirect('home')

    if request.method != 'POST':
        messages.error(request, 'Método inválido para excluir cobrança.')
        return redirect('admin_dashboard:espetaculos_list')

    try:
        from espetaculo.models import CobrancaEspetaculo

        cobranca = get_object_or_404(
            CobrancaEspetaculo.objects.select_related('participacao'),
            pk=pk
        )

        participacao_pk = cobranca.participacao.pk
        descricao = str(cobranca)

        with transaction.atomic():
            cobranca.delete()

        messages.success(request, f'Cobrança "{descricao}" excluída com sucesso.')
        return redirect('admin_dashboard:participacao_cobrancas', pk=participacao_pk)

    except Exception as e:
        messages.error(request, f'Erro ao excluir cobrança: {e}')
        return redirect('admin_dashboard:espetaculos_list')

@login_required
def parcela_cobranca_espetaculo_marcar_pago(request, pk):
    if not request.user.is_staff:
        return redirect('home')

    if request.method != 'POST':
        messages.error(request, 'Método inválido.')
        return redirect('admin_dashboard:espetaculos_list')

    try:
        from django.shortcuts import get_object_or_404
        from espetaculo.models import ParcelaCobrancaEspetaculo

        parcela = get_object_or_404(
            ParcelaCobrancaEspetaculo.objects.select_related(
                'cobranca',
                'cobranca__participacao',
                'cobranca__participacao__aluna',
                'cobranca__participacao__espetaculo',
            ),
            pk=pk
        )

        if parcela.status == 'pago':
            messages.info(request, 'Essa parcela já está marcada como paga.')
            return redirect(
                'admin_dashboard:participacao_cobrancas',
                pk=parcela.cobranca.participacao.pk
            )

        parcela.marcar_como_pago()

        messages.success(
            request,
            f'Parcela {parcela.numero_parcela}/{parcela.total_parcelas} marcada como paga com sucesso.'
        )
        return redirect(
            'admin_dashboard:participacao_cobrancas',
            pk=parcela.cobranca.participacao.pk
        )

    except Exception as e:
        messages.error(request, f'Erro ao marcar parcela como paga: {e}')
        return redirect('admin_dashboard:espetaculos_list')
    
def espetaculo_ingressos_vendidos(request, pk):
    espetaculo = get_object_or_404(Espetaculo, pk=pk)

    busca = request.GET.get('q', '').strip()

    pedidos = (
        PedidoIngressoEvento.objects
        .filter(evento=espetaculo, status='pago')
        .prefetch_related('ingressos')
        .order_by('-criado_em')
    )

    if busca:
        pedidos = pedidos.filter(
            Q(nome_completo__icontains=busca) |
            Q(email__icontains=busca) |
            Q(whatsapp__icontains=busca)
        )

    total_pedidos = pedidos.count()
    total_ingressos = sum(pedido.ingressos.count() for pedido in pedidos)

    context = {
        'espetaculo': espetaculo,
        'pedidos': pedidos,
        'busca': busca,
        'total_pedidos': total_pedidos,
        'total_ingressos': total_ingressos,
    }

    return render(
        request,
        'admin_dashboard/espetaculos/espetaculo_ingressos_vendidos.html',
        context
    )

@login_required
def excluir_participacao(request, pk):
    if not request.user.is_staff:
        return redirect('home')

    from espetaculo.models import ParticipacaoEspetaculo

    participacao = get_object_or_404(ParticipacaoEspetaculo, pk=pk)
    espetaculo_pk = participacao.espetaculo.pk

    if request.method == 'POST':
        nome = participacao.aluna.nome
        participacao.delete()
        messages.success(request, f'Participação de {nome} removida com sucesso.')
    else:
        messages.error(request, 'Ação inválida.')

    return redirect('admin_dashboard:espetaculo_participacoes', pk=espetaculo_pk)


@login_required
def marcar_parcela_pago_dinheiro(request, pk):
    if not request.user.is_staff:
        return redirect('home')

    from django.contrib import messages
    from django.shortcuts import get_object_or_404, redirect
    from espetaculo.models import ParcelaCobrancaEspetaculo

    parcela = get_object_or_404(
        ParcelaCobrancaEspetaculo.objects.select_related('cobranca', 'cobranca__participacao'),
        pk=pk
    )
    participacao_pk = parcela.cobranca.participacao.pk

    if request.method == 'POST':
        if parcela.status != 'pago':
            parcela.forma_pagamento_manual = 'DINHEIRO'
            parcela.save(update_fields=['forma_pagamento_manual'])
            parcela.marcar_como_pago()
            messages.success(
                request,
                f'Parcela {parcela.numero_parcela}/{parcela.total_parcelas} marcada como paga em dinheiro.'
            )
        else:
            messages.warning(request, 'Esta parcela já está paga.')

    return redirect('admin_dashboard:participacao_cobrancas', pk=participacao_pk)

@login_required
def cobranca_espetaculo_marcar_pago(request, pk):
    if not request.user.is_staff:
        return redirect('home')

    if request.method != 'POST':
        messages.error(request, 'Método inválido.')
        return redirect('admin_dashboard:espetaculos_list')

    try:
        from django.shortcuts import get_object_or_404
        from django.db import transaction
        from espetaculo.models import CobrancaEspetaculo, ParcelaCobrancaEspetaculo

        cobranca = get_object_or_404(
            CobrancaEspetaculo.objects.select_related(
                'participacao',
                'participacao__aluna',
                'participacao__espetaculo',
            ).prefetch_related('parcelas'),
            pk=pk
        )

        if cobranca.parcelas.filter(status='pago').exists():
            messages.info(request, 'Essa cobrança já possui parcela paga.')
            return redirect(
                'admin_dashboard:participacao_cobrancas',
                pk=cobranca.participacao.pk
            )

        with transaction.atomic():
            parcela = cobranca.parcelas.exclude(status='pago').order_by('numero_parcela').first()

            if not parcela:
                parcela = ParcelaCobrancaEspetaculo.objects.create(
                    cobranca=cobranca,
                    numero_parcela=1,
                    total_parcelas=1,
                    valor=cobranca.valor_total,
                    vencimento=cobranca.vencimento_primeira_parcela,
                    status='pendente',
                    billing_type=cobranca.billing_type or 'MANUAL',
                )

            parcela.marcar_como_pago()

            if hasattr(cobranca, 'atualizar_status'):
                cobranca.atualizar_status()
            else:
                cobranca.status = 'pago'
                cobranca.save(update_fields=['status'])

        messages.success(request, 'Cobrança marcada como paga com sucesso.')
        return redirect(
            'admin_dashboard:participacao_cobrancas',
            pk=cobranca.participacao.pk
        )

    except Exception as e:
        messages.error(request, f'Erro ao marcar cobrança como paga: {e}')
        return redirect('admin_dashboard:espetaculos_list')


@login_required
def cobranca_espetaculo_marcar_pago_dinheiro(request, pk):
    if not request.user.is_staff:
        return redirect('home')

    if request.method != 'POST':
        messages.error(request, 'Método inválido.')
        return redirect('admin_dashboard:espetaculos_list')

    try:
        from django.shortcuts import get_object_or_404
        from django.db import transaction
        from espetaculo.models import CobrancaEspetaculo, ParcelaCobrancaEspetaculo

        cobranca = get_object_or_404(
            CobrancaEspetaculo.objects.select_related(
                'participacao',
                'participacao__aluna',
                'participacao__espetaculo',
            ).prefetch_related('parcelas'),
            pk=pk
        )

        if cobranca.parcelas.filter(status='pago').exists():
            messages.info(request, 'Essa cobrança já possui parcela paga.')
            return redirect(
                'admin_dashboard:participacao_cobrancas',
                pk=cobranca.participacao.pk
            )

        with transaction.atomic():
            parcela = cobranca.parcelas.exclude(status='pago').order_by('numero_parcela').first()

            if not parcela:
                parcela = ParcelaCobrancaEspetaculo.objects.create(
                    cobranca=cobranca,
                    numero_parcela=1,
                    total_parcelas=1,
                    valor=cobranca.valor_total,
                    vencimento=cobranca.vencimento_primeira_parcela,
                    status='pendente',
                    billing_type='DINHEIRO',
                )
            else:
                if hasattr(parcela, 'billing_type'):
                    parcela.billing_type = 'DINHEIRO'
                    parcela.save(update_fields=['billing_type'])

            parcela.marcar_como_pago()

            if hasattr(cobranca, 'billing_type') and not cobranca.billing_type:
                cobranca.billing_type = 'DINHEIRO'
                campos_update = ['billing_type']
                if hasattr(cobranca, 'status'):
                    pass
                cobranca.save(update_fields=campos_update)

            if hasattr(cobranca, 'atualizar_status'):
                cobranca.atualizar_status()
            else:
                cobranca.status = 'pago'
                cobranca.save(update_fields=['status'])

        messages.success(request, 'Cobrança marcada como paga em dinheiro com sucesso.')
        return redirect(
            'admin_dashboard:participacao_cobrancas',
            pk=cobranca.participacao.pk
        )

    except Exception as e:
        messages.error(request, f'Erro ao marcar cobrança como paga em dinheiro: {e}')
        return redirect('admin_dashboard:espetaculos_list')
    
@login_required
def parcela_cobranca_espetaculo_registrar_pagamento_parcial(request, pk):
    if not request.user.is_staff:
        return redirect('home')

    if request.method != 'POST':
        messages.error(request, 'Método inválido.')
        return redirect('admin_dashboard:espetaculos_list')

    try:
        from django.shortcuts import get_object_or_404
        from django.db import transaction
        from espetaculo.models import ParcelaCobrancaEspetaculo

        parcela = get_object_or_404(
            ParcelaCobrancaEspetaculo.objects.select_related(
                'cobranca',
                'cobranca__participacao',
                'cobranca__participacao__aluna',
                'cobranca__participacao__espetaculo',
            ),
            pk=pk
        )

        valor_pago = (request.POST.get('valor_pago') or '').replace(',', '.').strip()
        observacao = (request.POST.get('observacao_pagamento') or '').strip()

        with transaction.atomic():
            parcela.registrar_pagamento(
                valor=valor_pago,
                forma_pagamento='DINHEIRO',
                observacao=observacao,
            )

        if parcela.status == 'pago':
            messages.success(
                request,
                f'Pagamento registrado e parcela {parcela.numero_parcela}/{parcela.total_parcelas} quitada com sucesso.'
            )
        else:
            messages.success(
                request,
                f'Pagamento parcial registrado com sucesso na parcela {parcela.numero_parcela}/{parcela.total_parcelas}.'
            )

        return redirect(
            'admin_dashboard:participacao_cobrancas',
            pk=parcela.cobranca.participacao.pk
        )

    except Exception as e:
        messages.error(request, f'Erro ao registrar pagamento parcial: {e}')
        return redirect('admin_dashboard:espetaculos_list')
    
@login_required
def cobranca_espetaculo_registrar_pagamento_parcial(request, pk):
    if not request.user.is_staff:
        return redirect('home')

    if request.method != 'POST':
        messages.error(request, 'Método inválido.')
        return redirect('admin_dashboard:espetaculos_list')

    try:
        from decimal import Decimal
        from django.shortcuts import get_object_or_404
        from django.db import transaction
        from espetaculo.models import CobrancaEspetaculo, ParcelaCobrancaEspetaculo

        cobranca = get_object_or_404(
            CobrancaEspetaculo.objects.select_related(
                'participacao',
                'participacao__aluna',
                'participacao__espetaculo',
            ).prefetch_related('parcelas'),
            pk=pk
        )

        valor_pago = (request.POST.get('valor_pago') or '').replace(',', '.').strip()
        observacao = (request.POST.get('observacao_pagamento') or '').strip()

        with transaction.atomic():
            parcela = cobranca.parcelas.order_by('numero_parcela').first()

            if not parcela:
                parcela = ParcelaCobrancaEspetaculo.objects.create(
                    cobranca=cobranca,
                    numero_parcela=1,
                    total_parcelas=1,
                    valor=cobranca.valor_total_efetivo(),
                    vencimento=cobranca.vencimento_primeira_parcela,
                    status='pendente',
                    billing_type='DINHEIRO',
                    forma_pagamento_manual='DINHEIRO',
                )

            parcela.registrar_pagamento(
                valor=valor_pago,
                forma_pagamento='DINHEIRO',
                observacao=observacao,
            )

            if hasattr(cobranca, 'billing_type') and not cobranca.billing_type:
                cobranca.billing_type = 'DINHEIRO'
                cobranca.save(update_fields=['billing_type'])

        if parcela.status == 'pago':
            messages.success(request, 'Pagamento registrado e cobrança quitada com sucesso.')
        else:
            messages.success(request, 'Pagamento parcial registrado com sucesso.')

        return redirect(
            'admin_dashboard:participacao_cobrancas',
            pk=cobranca.participacao.pk
        )

    except Exception as e:
        messages.error(request, f'Erro ao registrar pagamento parcial: {e}')
        return redirect('admin_dashboard:espetaculos_list')
    
@login_required
def marcar_cobranca_pago_dinheiro(request, pk):
    if not request.user.is_staff:
        return redirect('home')

    from django.contrib import messages
    from django.db import transaction
    from django.shortcuts import get_object_or_404, redirect
    from django.utils import timezone
    from espetaculo.models import CobrancaEspetaculo

    cobranca = get_object_or_404(
        CobrancaEspetaculo.objects.select_related('participacao').prefetch_related('parcelas'),
        pk=pk
    )
    participacao_pk = cobranca.participacao.pk

    if request.method == 'POST':
        parcelas = list(cobranca.parcelas.all())

        if not parcelas:
            messages.error(request, 'Essa cobrança não possui parcelas geradas.')
            return redirect('admin_dashboard:participacao_cobrancas', pk=participacao_pk)

        with transaction.atomic():
            for parcela in parcelas:
                if parcela.status != 'pago':
                    parcela.forma_pagamento_manual = 'DINHEIRO'
                    parcela.valor_pago = parcela.valor
                    parcela.status = 'pago'
                    if not parcela.data_pagamento:
                        parcela.data_pagamento = timezone.now()
                    parcela.save(update_fields=[
                        'forma_pagamento_manual',
                        'valor_pago',
                        'status',
                        'data_pagamento',
                    ])

            cobranca.atualizar_status()

        messages.success(request, 'Cobrança inteira marcada como paga em dinheiro.')

    return redirect('admin_dashboard:participacao_cobrancas', pk=participacao_pk)

@login_required
def espetaculo_mapa_assentos(request, pk):
    """Importar ou atualizar o mapa de assentos de um evento."""

    if not request.user.is_staff:
        return redirect('home')

    import json
    from decimal import Decimal, InvalidOperation

    from django.contrib import messages
    from django.db import transaction
    from django.shortcuts import get_object_or_404, redirect, render

    from espetaculo.models import Espetaculo, MapaAssentos, Assento

    espetaculo = get_object_or_404(Espetaculo, pk=pk)

    mapa = MapaAssentos.objects.filter(
        evento=espetaculo
    ).first()

    if request.method == 'POST':
        imagem_mapa = request.FILES.get('imagem_mapa')
        arquivo_json = request.FILES.get('arquivo_json')
        json_colado = request.POST.get('json_colado', '').strip()
        manter_vendidos = request.POST.get('manter_vendidos') == 'on'

        if arquivo_json:
            try:
                conteudo = arquivo_json.read().decode('utf-8-sig')
            except UnicodeDecodeError:
                messages.error(
                    request,
                    'O arquivo JSON precisa estar salvo em UTF-8.'
                )
                return redirect(
                    'admin_dashboard:espetaculo_mapa_assentos',
                    pk=pk
                )
        elif json_colado:
            conteudo = json_colado
        else:
            messages.error(
                request,
                'Envie um arquivo JSON ou cole o conteúdo do JSON.'
            )
            return redirect(
                'admin_dashboard:espetaculo_mapa_assentos',
                pk=pk
            )

        try:
            dados = json.loads(conteudo)
        except json.JSONDecodeError as erro:
            messages.error(
                request,
                f'JSON inválido na linha {erro.lineno}, coluna {erro.colno}: {erro.msg}'
            )
            return redirect(
                'admin_dashboard:espetaculo_mapa_assentos',
                pk=pk
            )

        if not isinstance(dados, dict):
            messages.error(
                request,
                'O JSON precisa ser um objeto com a chave "assentos".'
            )
            return redirect(
                'admin_dashboard:espetaculo_mapa_assentos',
                pk=pk
            )

        lista_assentos = dados.get('assentos')

        if not isinstance(lista_assentos, list) or not lista_assentos:
            messages.error(
                request,
                'O JSON precisa conter uma lista não vazia na chave "assentos".'
            )
            return redirect(
                'admin_dashboard:espetaculo_mapa_assentos',
                pk=pk
            )

        try:
            largura_original = int(
                dados.get(
                    'largura_original',
                    mapa.largura_original if mapa else 1600
                )
            )
            altura_original = int(
                dados.get(
                    'altura_original',
                    mapa.altura_original if mapa else 1200
                )
            )
        except (TypeError, ValueError):
            messages.error(
                request,
                'largura_original e altura_original precisam ser números inteiros.'
            )
            return redirect(
                'admin_dashboard:espetaculo_mapa_assentos',
                pk=pk
            )

        if largura_original <= 0 or altura_original <= 0:
            messages.error(
                request,
                'largura_original e altura_original precisam ser maiores que zero.'
            )
            return redirect(
                'admin_dashboard:espetaculo_mapa_assentos',
                pk=pk
            )

        dados_validados = []
        identificadores_vistos = set()
        erros = []

        for indice, item in enumerate(lista_assentos, start=1):
            if not isinstance(item, dict):
                erros.append(
                    f'Item {indice}: precisa ser um objeto JSON.'
                )
                continue

            identificador = str(item.get('id', '')).strip()

            if not identificador:
                erros.append(
                    f'Item {indice}: campo "id" não informado.'
                )
                continue

            if identificador in identificadores_vistos:
                erros.append(
                    f'Assento "{identificador}": ID duplicado no JSON.'
                )
                continue

            identificadores_vistos.add(identificador)

            fileira = str(
                item.get('fileira', identificador[:1])
            ).strip()

            setor = str(
                item.get('setor', '')
            ).strip()

            if not fileira:
                erros.append(
                    f'Assento "{identificador}": fileira não informada.'
                )
                continue

            try:
                numero = int(item.get('numero'))
            except (TypeError, ValueError):
                erros.append(
                    f'Assento "{identificador}": numero inválido.'
                )
                continue

            if numero < 0:
                erros.append(
                    f'Assento "{identificador}": numero não pode ser negativo.'
                )
                continue

            try:
                x_pct = Decimal(str(item.get('x_pct')))
                y_pct = Decimal(str(item.get('y_pct')))
            except (InvalidOperation, TypeError, ValueError):
                erros.append(
                    f'Assento "{identificador}": x_pct/y_pct inválidos.'
                )
                continue

            if not (Decimal('0') <= x_pct <= Decimal('100')):
                erros.append(
                    f'Assento "{identificador}": x_pct precisa estar entre 0 e 100.'
                )
                continue

            if not (Decimal('0') <= y_pct <= Decimal('100')):
                erros.append(
                    f'Assento "{identificador}": y_pct precisa estar entre 0 e 100.'
                )
                continue

            dados_validados.append({
                'identificador': identificador,
                'fileira': fileira,
                'numero': numero,
                'setor': setor,
                'x_pct': x_pct,
                'y_pct': y_pct,
            })

        if erros:
            mensagens = '\n'.join(erros[:10])

            if len(erros) > 10:
                mensagens += f'\nE mais {len(erros) - 10} erro(s).'

            messages.error(
                request,
                f'O JSON possui erros e não foi importado:\n{mensagens}'
            )

            return redirect(
                'admin_dashboard:espetaculo_mapa_assentos',
                pk=pk
            )

        try:
            with transaction.atomic():
                if mapa is None:
                    mapa = MapaAssentos.objects.create(
                        evento=espetaculo,
                        imagem_mapa=imagem_mapa,
                        largura_original=largura_original,
                        altura_original=altura_original,
                    )
                else:
                    if imagem_mapa:
                        mapa.imagem_mapa = imagem_mapa

                    mapa.largura_original = largura_original
                    mapa.altura_original = altura_original
                    mapa.save()

                assentos_existentes = {
                    assento.identificador: assento
                    for assento in mapa.assentos.all()
                }

                ids_importados = {
                    item['identificador']
                    for item in dados_validados
                }

                para_criar = []
                para_atualizar = []

                criados = 0
                atualizados = 0
                preservados = 0

                for item in dados_validados:
                    identificador = item['identificador']
                    assento_existente = assentos_existentes.get(identificador)

                    if assento_existente:
                        if (
                            manter_vendidos
                            and assento_existente.status in (
                                'vendido',
                                'bloqueado_manual',
                            )
                        ):
                            preservados += 1
                            continue

                        assento_existente.fileira = item['fileira']
                        assento_existente.numero = item['numero']
                        assento_existente.setor = item['setor']
                        assento_existente.x_pct = item['x_pct']
                        assento_existente.y_pct = item['y_pct']

                        para_atualizar.append(assento_existente)
                        atualizados += 1

                    else:
                        para_criar.append(
                            Assento(
                                mapa=mapa,
                                identificador=identificador,
                                fileira=item['fileira'],
                                numero=item['numero'],
                                setor=item['setor'],
                                x_pct=item['x_pct'],
                                y_pct=item['y_pct'],
                            )
                        )
                        criados += 1

                if para_criar:
                    Assento.objects.bulk_create(
                        para_criar,
                        batch_size=500
                    )

                if para_atualizar:
                    Assento.objects.bulk_update(
                        para_atualizar,
                        fields=[
                            'fileira',
                            'numero',
                            'setor',
                            'x_pct',
                            'y_pct',
                        ],
                        batch_size=500
                    )

                assentos_orfaos = mapa.assentos.exclude(
                    identificador__in=ids_importados
                )

                removidos = 0

                for assento_orfao in assentos_orfaos:
                    if (
                        manter_vendidos
                        and assento_orfao.status in (
                            'vendido',
                            'bloqueado_manual',
                        )
                    ):
                        preservados += 1
                        continue

                    assento_orfao.delete()
                    removidos += 1

        except Exception as erro:
            import traceback
            traceback.print_exc()

            messages.error(
                request,
                f'Erro ao salvar o mapa de assentos: {erro}'
            )

            return redirect(
                'admin_dashboard:espetaculo_mapa_assentos',
                pk=pk
            )

        resumo = (
            f'{criados} criado(s), '
            f'{atualizados} atualizado(s), '
            f'{removidos} removido(s).'
        )

        if preservados:
            resumo += (
                f' {preservados} vendido(s)/bloqueado(s) '
                f'preservado(s).'
            )

        messages.success(
            request,
            f'Mapa importado com sucesso: {resumo}'
        )

        return redirect(
            'admin_dashboard:espetaculo_mapa_assentos',
            pk=pk
        )

    context = {
        'espetaculo': espetaculo,
        'mapa': mapa,
        'assentos': mapa.assentos.all() if mapa else [],
    }

    return render(
        request,
        'admin_dashboard/espetaculos/mapa_assentos.html',
        context
    )

@login_required
def espetaculo_assentos_gerenciar(request, pk):
    """Exibir e gerenciar visualmente os assentos de um evento."""

    if not request.user.is_staff:
        return redirect('home')

    from django.contrib import messages
    from django.shortcuts import get_object_or_404, redirect, render
    from espetaculo.models import Espetaculo, MapaAssentos, Assento

    espetaculo = get_object_or_404(Espetaculo, pk=pk)

    mapa = MapaAssentos.objects.filter(
        evento=espetaculo
    ).prefetch_related('assentos').first()

    if not mapa:
        messages.warning(
            request,
            'Este evento ainda não possui um mapa de assentos importado.'
        )
        return redirect(
            'admin_dashboard:espetaculo_mapa_assentos',
            pk=pk
        )

    assentos = mapa.assentos.all().order_by('fileira', 'numero')

    context = {
        'espetaculo': espetaculo,
        'mapa': mapa,
        'assentos': assentos,
    }

    return render(
        request,
        'admin_dashboard/espetaculos/assentos_gerenciar.html',
        context
    )


@login_required
def espetaculo_assento_acao(request, pk, assento_id):
    """Bloquear ou liberar manualmente um assento."""

    if not request.user.is_staff:
        return redirect('home')

    from django.contrib import messages
    from django.shortcuts import get_object_or_404, redirect
    from espetaculo.models import Espetaculo, Assento

    espetaculo = get_object_or_404(Espetaculo, pk=pk)

    assento = get_object_or_404(
        Assento.objects.select_related('mapa__evento'),
        pk=assento_id,
        mapa__evento=espetaculo,
    )

    if request.method != 'POST':
        return redirect(
            'admin_dashboard:espetaculo_assentos_gerenciar',
            pk=pk
        )

    acao = request.POST.get('acao')
    motivo = request.POST.get('motivo', '').strip()

    if acao == 'bloquear':
        if assento.status != 'disponivel':
            messages.error(
                request,
                f'O assento {assento.identificador} não está disponível.'
            )
        else:
            assento.bloquear_manualmente(motivo=motivo)
            messages.success(
                request,
                f'Assento {assento.identificador} bloqueado manualmente.'
            )

    elif acao == 'liberar':
        if assento.status != 'bloqueado_manual':
            messages.error(
                request,
                f'O assento {assento.identificador} não está bloqueado manualmente.'
            )
        else:
            assento.liberar()
            messages.success(
                request,
                f'Assento {assento.identificador} liberado.'
            )

    else:
        messages.error(request, 'Ação de assento inválida.')

    return redirect(
        'admin_dashboard:espetaculo_assentos_gerenciar',
        pk=pk
    )