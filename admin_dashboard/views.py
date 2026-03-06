from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from datetime import datetime
from decimal import Decimal


@login_required
def dashboard(request):
    """Dashboard com dados reais do banco"""
    
    # Apenas staff pode acessar
    if not request.user.is_staff:
        return redirect('home')
    
    # Valores default (caso de erro)
    total_alunas = 0
    total_recebido = Decimal('0.00')
    mensalidades_pendentes = 0
    mensalidades_pagas = 0
    mes_atual = datetime.now().strftime('%B %Y')
    
    try:
        # Imports DENTRO do try (evita quebrar o Django se der erro)
        from usuarios.models import Aluna
        from pagamentos.models import Mensalidade
        from django.db.models import Sum
        
        # Estatisticas
        hoje = datetime.now().date()
        mes = hoje.month
        ano = hoje.year
        
        # Total de alunas ativas
        total_alunas = Aluna.objects.filter(ativa=True).count()
        
        # Mensalidades do mes atual
        mensalidades_mes = Mensalidade.objects.filter(
            mes_referencia__month=mes,
            mes_referencia__year=ano
        )
        
        # Total recebido no mes
        total_recebido = mensalidades_mes.filter(
            status='pago'
        ).aggregate(total=Sum('valor'))['total'] or Decimal('0.00')
        
        # Mensalidades pendentes e pagas
        mensalidades_pendentes = mensalidades_mes.filter(status='pendente').count()
        mensalidades_pagas = mensalidades_mes.filter(status='pago').count()
        
    except Exception as e:
        # Se der erro, mostra no console mas nao quebra
        print(f"Erro no dashboard: {e}")
        # Usa os valores default ja definidos acima
    
    context = {
        'total_alunas': total_alunas,
        'total_recebido': total_recebido,
        'mensalidades_pendentes': mensalidades_pendentes,
        'mensalidades_pagas': mensalidades_pagas,
        'mes_atual': mes_atual,
    }
    
    return render(request, 'admin_dashboard/dashboard.html', context)

@login_required
def alunas_list(request):
    """Lista de todas as alunas com busca e filtros"""
    
    if not request.user.is_staff:
        return redirect('home')
    
    try:
        from usuarios.models import Aluna
        from django.db.models import Q
        
        # Query base
        alunas = Aluna.objects.select_related('responsavel').all()
        
        # Busca
        busca = request.GET.get('busca', '')
        if busca:
            alunas = alunas.filter(
                Q(nome__icontains=busca) |
                Q(responsavel__first_name__icontains=busca) |
                Q(responsavel__last_name__icontains=busca)
            )
        
        # Filtro por turma
        turma = request.GET.get('turma', '')
        if turma:
            alunas = alunas.filter(turma_atual=turma)
        
        # Filtro por status
        status = request.GET.get('status', '')
        if status == 'ativas':
            alunas = alunas.filter(ativa=True)
        elif status == 'inativas':
            alunas = alunas.filter(ativa=False)
        
        # Ordenacao
        alunas = alunas.order_by('nome')
        
        # Turmas unicas para o filtro
        turmas = Aluna.objects.values_list('turma_atual', flat=True).distinct()
        
    except Exception as e:
        print(f"Erro ao buscar alunas: {e}")
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
        'total_alunas': alunas.count() if alunas else 0,
    }
    
    return render(request, 'admin_dashboard/alunas/list.html', context)

@login_required
def aluna_criar(request):
    """Criar nova aluna"""
    
    if not request.user.is_staff:
        return redirect('home')
    
    if request.method == 'POST':
        try:
            from usuarios.models import Aluna
            from django.contrib.auth.models import User
            from django.contrib import messages
            
            # Pega dados do form
            nome = request.POST.get('nome')
            data_nascimento = request.POST.get('data_nascimento')
            turma_atual = request.POST.get('turma_atual')
            responsavel_id = request.POST.get('responsavel')
            ativa = request.POST.get('ativa') == 'on'
            observacoes = request.POST.get('observacoes', '')
            
            # Validacao basica
            if not all([nome, data_nascimento, responsavel_id]):
                messages.error(request, 'Preencha todos os campos obrigatorios!')
                return redirect('admin_dashboard:aluna_criar')
            
            # Cria aluna
            responsavel = User.objects.get(id=responsavel_id)
            aluna = Aluna.objects.create(
                nome=nome,
                data_nascimento=data_nascimento,
                turma_atual=turma_atual,
                responsavel=responsavel,
                ativa=ativa,
                observacoes=observacoes
            )
            
            messages.success(request, f'Aluna {nome} criada com sucesso!')
            return redirect('admin_dashboard:alunas_list')
            
        except Exception as e:
            messages.error(request, f'Erro ao criar aluna: {e}')
            return redirect('admin_dashboard:aluna_criar')
    
    # GET - mostra form
    try:
        from django.contrib.auth.models import User
        responsaveis = User.objects.filter(is_staff=False).order_by('first_name')
    except Exception as e:
        print(f"Erro ao buscar responsaveis: {e}")
        responsaveis = []
    
    context = {
        'responsaveis': responsaveis,
    }
    
    return render(request, 'admin_dashboard/alunas/criar.html', context)

@login_required
def aluna_detalhes(request, pk):
    """Detalhes de uma aluna"""
    
    if not request.user.is_staff:
        return redirect('home')
    
    try:
        from usuarios.models import Aluna
        from pagamentos.models import Mensalidade
        from django.db.models import Sum
        
        aluna = Aluna.objects.select_related('responsavel').get(pk=pk)
        
        # Mensalidades da aluna
        mensalidades = Mensalidade.objects.filter(aluna=aluna).order_by('-mes_referencia')
        
        # Estatisticas
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
        'mensalidades': mensalidades[:12],  # Ultimas 12 mensalidades
        'total_pago': total_pago,
        'total_pendente': total_pendente,
    }
    
    return render(request, 'admin_dashboard/alunas/detalhes.html', context)


@login_required
def aluna_editar(request, pk):
    """Editar aluna existente"""
    
    if not request.user.is_staff:
        return redirect('home')
    
    try:
        from usuarios.models import Aluna
        aluna = Aluna.objects.get(pk=pk)
    except Exception as e:
        from django.contrib import messages
        messages.error(request, f'Aluna nao encontrada: {e}')
        return redirect('admin_dashboard:alunas_list')
    
    if request.method == 'POST':
        try:
            from django.contrib.auth.models import User
            from django.contrib import messages
            
            # Atualiza dados
            aluna.nome = request.POST.get('nome')
            aluna.data_nascimento = request.POST.get('data_nascimento')
            aluna.turma_atual = request.POST.get('turma_atual')
            aluna.ativa = request.POST.get('ativa') == 'on'
            aluna.observacoes = request.POST.get('observacoes', '')
            
            # Atualiza responsavel se mudou
            responsavel_id = request.POST.get('responsavel')
            if responsavel_id:
                aluna.responsavel = User.objects.get(id=responsavel_id)
            
            aluna.save()
            
            messages.success(request, f'Aluna {aluna.nome} atualizada com sucesso!')
            return redirect('admin_dashboard:aluna_detalhes', pk=aluna.pk)
            
        except Exception as e:
            from django.contrib import messages
            messages.error(request, f'Erro ao atualizar aluna: {e}')
            return redirect('admin_dashboard:aluna_editar', pk=pk)
    
    # GET - mostra form preenchido
    try:
        from django.contrib.auth.models import User
        responsaveis = User.objects.filter(is_staff=False).order_by('first_name')
    except Exception as e:
        print(f"Erro ao buscar responsaveis: {e}")
        responsaveis = []
    
    context = {
        'aluna': aluna,
        'responsaveis': responsaveis,
    }
    
    return render(request, 'admin_dashboard/alunas/editar.html', context)