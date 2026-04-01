from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from datetime import datetime
from decimal import Decimal
from django.db import models


@login_required
def dashboard(request):
    """Dashboard com dados reais do banco e graficos"""
    
    # Apenas staff pode acessar
    if not request.user.is_staff:
        return redirect('home')
    
    # Valores default (caso de erro)
    total_alunas = 0
    total_recebido = Decimal('0.00')
    mensalidades_pendentes = 0
    mensalidades_pagas = 0
    mes_atual = datetime.now().strftime('%B %Y')
    total_turmas = 0
    
    # Dados para gráficos
    faturamento_meses = []
    faturamento_valores = []
    turmas_labels = []
    turmas_valores = []
    status_labels = ['Pagas', 'Pendentes', 'Vencidas']
    status_valores = [0, 0, 0]
    
    try:
        # Imports DENTRO do try (evita quebrar o Django se der erro)
        from usuarios.models import Aluna, Turma
        from pagamentos.models import Mensalidade
        from django.db.models import Sum, Count, Q
        from datetime import timedelta
        
        # Estatisticas
        hoje = datetime.now().date()
        mes = hoje.month
        ano = hoje.year
        
        # Total de alunas ativas
        total_alunas = Aluna.objects.filter(ativa=True).count()
        
        # Total de turmas ativas
        total_turmas = Turma.objects.filter(ativa=True).count()
        
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
        
        # GRAFICO 1 - Faturamento ultimos 6 meses
        for i in range(5, -1, -1):
            mes_calc = hoje - timedelta(days=30 * i)
            mes_nome = mes_calc.strftime('%b/%y')
            
            valor = Mensalidade.objects.filter(
                mes_referencia__month=mes_calc.month,
                mes_referencia__year=mes_calc.year,
                status='pago'
            ).aggregate(total=Sum('valor'))['total'] or 0
            
            faturamento_meses.append(mes_nome)
            faturamento_valores.append(float(valor))
        
        # GRAFICO 2 - Alunas por turma (CORRIGIDO!)
        turmas = Turma.objects.filter(ativa=True).order_by('nome')
        
        for turma in turmas:
            total_alunas_turma = Aluna.objects.filter(
                turma=turma,
                ativa=True
            ).count()
            
            if total_alunas_turma > 0:  # Só adiciona turmas com alunas
                turmas_labels.append(turma.nome)
                turmas_valores.append(total_alunas_turma)
        
        # GRAFICO 3 - Status mensalidades mes atual
        status_valores[0] = mensalidades_mes.filter(status='pago').count()
        status_valores[1] = mensalidades_mes.filter(status='pendente').count()
        status_valores[2] = mensalidades_mes.filter(status='vencido').count()
        
    except Exception as e:
        # Se der erro, mostra no console mas nao quebra
        print(f"Erro no dashboard: {e}")
        import traceback
        traceback.print_exc()
    
    context = {
        'total_alunas': total_alunas,
        'total_turmas': total_turmas,
        'total_recebido': total_recebido,
        'mensalidades_pendentes': mensalidades_pendentes,
        'mensalidades_pagas': mensalidades_pagas,
        'mes_atual': mes_atual,
        
        # Dados para graficos
        'faturamento_meses': faturamento_meses,
        'faturamento_valores': faturamento_valores,
        'turmas_labels': turmas_labels,
        'turmas_valores': turmas_valores,
        'status_labels': status_labels,
        'status_valores': status_valores,
    }
    
    return render(request, 'admin_dashboard/dashboard.html', context)

@login_required
def alunas_list(request):
    """Lista de todas as alunas com busca e filtros"""
    
    if not request.user.is_staff:
        return redirect('home')
    
    try:
        from usuarios.models import Aluna, Turma
        from django.db.models import Q
        
        # Query base
        alunas = Aluna.objects.select_related('responsavel', 'turma').all()
        
        # Debug - mostra no console
        print(f"Total de alunas no banco: {alunas.count()}")
        
        # Busca
        busca = request.GET.get('busca', '')
        if busca:
            alunas = alunas.filter(
                Q(nome__icontains=busca) |
                Q(responsavel__first_name__icontains=busca) |
                Q(responsavel__last_name__icontains=busca)
            )
            print(f"Alunas após busca: {alunas.count()}")
        
        # Filtro por turma
        turma = request.GET.get('turma', '')
        if turma:
            alunas = alunas.filter(turma__nome=turma)
            print(f"Alunas após filtro turma: {alunas.count()}")
        
        # Filtro por status
        status = request.GET.get('status', '')
        if status == 'ativas':
            alunas = alunas.filter(ativa=True)
            print(f"Alunas após filtro ativas: {alunas.count()}")
        elif status == 'inativas':
            alunas = alunas.filter(ativa=False)
            print(f"Alunas após filtro inativas: {alunas.count()}")
        
        # Ordenacao
        alunas = alunas.order_by('nome')
        
        # Turmas unicas para o filtro
        turmas = Turma.objects.filter(ativa=True).values_list('nome', flat=True).distinct()
        
        print(f"Turmas disponíveis: {list(turmas)}")
        
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
            from usuarios.models import Aluna, Turma
            from django.contrib.auth.models import User
            from django.contrib import messages
            
            # Pega dados da aluna
            nome = request.POST.get('nome')
            data_nascimento = request.POST.get('data_nascimento')
            turma_id = request.POST.get('turma')
            ativa = request.POST.get('ativa') == 'on'
            observacoes = request.POST.get('observacoes', '')
            
            # Valida dados básicos
            if not all([nome, data_nascimento]):
                messages.error(request, 'Preencha todos os campos obrigatorios da aluna!')
                return redirect('admin_dashboard:aluna_criar')
            
            # VERIFICA TIPO DE RESPONSÁVEL
            tipo_responsavel = request.POST.get('tipo_responsavel')
            
            if tipo_responsavel == 'existente':
                # Usa responsável existente
                responsavel_id = request.POST.get('responsavel_existente')
                if not responsavel_id:
                    messages.error(request, 'Selecione um responsavel!')
                    return redirect('admin_dashboard:aluna_criar')
                responsavel = User.objects.get(id=responsavel_id)
                
            else:
                # Cria novo responsável
                resp_nome = request.POST.get('responsavel_nome')
                resp_sobrenome = request.POST.get('responsavel_sobrenome')
                resp_email = request.POST.get('responsavel_email')
                resp_senha = request.POST.get('responsavel_senha')
                resp_telefone = request.POST.get('responsavel_telefone', '')
                
                # Valida campos do responsável (TELEFONE OBRIGATÓRIO)
                if not all([resp_nome, resp_sobrenome, resp_email, resp_senha, resp_telefone]):
                    messages.error(request, 'Preencha todos os campos obrigatorios do responsavel (incluindo telefone)!')
                    return redirect('admin_dashboard:aluna_criar')
                
                # Verifica se email já existe
                if User.objects.filter(email=resp_email).exists():
                    messages.error(request, f'Ja existe um usuario com o email {resp_email}!')
                    return redirect('admin_dashboard:aluna_criar')
                
                # Cria username a partir do email
                username = resp_email.split('@')[0]
                
                # Se username já existe, adiciona número
                base_username = username
                counter = 1
                while User.objects.filter(username=username).exists():
                    username = f"{base_username}{counter}"
                    counter += 1
                
                # Cria o responsável
                responsavel = User.objects.create_user(
                    username=username,
                    email=resp_email,
                    password=resp_senha,
                    first_name=resp_nome,
                    last_name=resp_sobrenome
                )
                
                # Cria perfil com telefone
                from usuarios.models import Perfil
                perfil, created = Perfil.objects.get_or_create(
                    user=responsavel,
                    defaults={'telefone': resp_telefone}
                )
                if not created:
                    perfil.telefone = resp_telefone
                    perfil.save()
                
                messages.success(request, f'Responsavel {resp_nome} {resp_sobrenome} cadastrado! Login: {resp_email} / Senha: {resp_senha}')
            
            # Busca turma se foi selecionada
            turma = None
            if turma_id:
                try:
                    turma = Turma.objects.get(id=turma_id)
                except Turma.DoesNotExist:
                    pass
            
            # Cria a aluna
            aluna = Aluna.objects.create(
                nome=nome,
                data_nascimento=data_nascimento,
                turma=turma,
                responsavel=responsavel,
                ativa=ativa,
                observacoes=observacoes
            )
            
            messages.success(request, f'Aluna {nome} criada com sucesso!')
            return redirect('admin_dashboard:alunas_list')
            
        except Exception as e:
            messages.error(request, f'Erro ao criar aluna: {e}')
            print(f"Erro detalhado: {e}")
            import traceback
            traceback.print_exc()
            return redirect('admin_dashboard:aluna_criar')
    
    # GET - mostra form
    try:
        from django.contrib.auth.models import User
        from usuarios.models import Turma
        
        responsaveis = User.objects.filter(is_staff=False).order_by('first_name')
        turmas = Turma.objects.filter(ativa=True).order_by('nome')
        
    except Exception as e:
        print(f"Erro ao buscar dados: {e}")
        responsaveis = []
        turmas = []
    
    context = {
        'responsaveis': responsaveis,
        'turmas': turmas,
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
            from usuarios.models import Turma
            from django.contrib import messages
            
            # Atualiza dados
            aluna.nome = request.POST.get('nome')
            aluna.data_nascimento = request.POST.get('data_nascimento')
            aluna.ativa = request.POST.get('ativa') == 'on'
            aluna.observacoes = request.POST.get('observacoes', '')
            
            # Atualiza responsavel se mudou
            responsavel_id = request.POST.get('responsavel')
            if responsavel_id:
                aluna.responsavel = User.objects.get(id=responsavel_id)
            
            # Atualiza turma
            turma_id = request.POST.get('turma')
            if turma_id:
                try:
                    aluna.turma = Turma.objects.get(id=turma_id)
                except Turma.DoesNotExist:
                    aluna.turma = None
            else:
                aluna.turma = None
            
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
        from usuarios.models import Turma
        
        responsaveis = User.objects.filter(is_staff=False).order_by('first_name')
        turmas = Turma.objects.filter(ativa=True).order_by('nome')
        
    except Exception as e:
        print(f"Erro ao buscar dados: {e}")
        responsaveis = []
        turmas = []
    
    context = {
        'aluna': aluna,
        'responsaveis': responsaveis,
        'turmas': turmas,
    }
    
    return render(request, 'admin_dashboard/alunas/editar.html', context)

@login_required
def mensalidades_list(request):
    """Lista de mensalidades com filtros"""
    
    if not request.user.is_staff:
        return redirect('home')
    
    try:
        from pagamentos.models import Mensalidade
        from django.db.models import Q
        
        # Query base
        mensalidades = Mensalidade.objects.select_related('aluna', 'aluna__responsavel').all()
        
        # Busca
        busca = request.GET.get('busca', '')
        if busca:
            mensalidades = mensalidades.filter(
                Q(aluna__nome__icontains=busca) |
                Q(aluna__responsavel__first_name__icontains=busca) |
                Q(aluna__responsavel__last_name__icontains=busca)
            )
        
        # Filtro por status
        status = request.GET.get('status', '')
        if status:
            mensalidades = mensalidades.filter(status=status)
        
        # Filtro por mes
        mes = request.GET.get('mes', '')
        if mes:
            mensalidades = mensalidades.filter(mes_referencia__month=mes)
        
        # Ordenacao
        mensalidades = mensalidades.order_by('-mes_referencia', 'aluna__nome')
        
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
        'total_mensalidades': mensalidades.count() if mensalidades else 0,
    }
    
    return render(request, 'admin_dashboard/mensalidades/list.html', context)


@login_required
def mensalidade_criar(request):
    """Criar mensalidade manual"""
    
    if not request.user.is_staff:
        return redirect('home')
    
    if request.method == 'POST':
        try:
            from pagamentos.models import Mensalidade
            from usuarios.models import Aluna
            from django.contrib import messages
            from datetime import datetime
            
            # Pega dados do form
            aluna_id = request.POST.get('aluna')
            mes_referencia = request.POST.get('mes_referencia')
            data_vencimento = request.POST.get('data_vencimento')
            valor = request.POST.get('valor')
            status = request.POST.get('status', 'pendente')
            
            # Validacao
            if not all([aluna_id, mes_referencia, data_vencimento, valor]):
                messages.error(request, 'Preencha todos os campos obrigatorios!')
                return redirect('admin_dashboard:mensalidade_criar')
            
            # Busca aluna
            aluna = Aluna.objects.get(id=aluna_id)
            
            # Converte mes_referencia de "2026-03" para date "2026-03-01"
            mes_ref_date = datetime.strptime(mes_referencia + '-01', '%Y-%m-%d').date()
            
            # Converte data_vencimento de string para date
            data_venc_date = datetime.strptime(data_vencimento, '%Y-%m-%d').date()
            
            # Cria mensalidade COM RESPONSAVEL
            mensalidade = Mensalidade.objects.create(
                aluna=aluna,
                responsavel=aluna.responsavel,
                mes_referencia=mes_ref_date,
                data_vencimento=data_venc_date,
                valor=Decimal(valor),
                status=status,
            )
            
            messages.success(request, f'Mensalidade criada com sucesso!')
            return redirect('admin_dashboard:mensalidades_list')
            
        except Exception as e:
            from django.contrib import messages
            messages.error(request, f'Erro ao criar mensalidade: {e}')
            print(f"Erro detalhado: {e}")
            import traceback
            traceback.print_exc()
            return redirect('admin_dashboard:mensalidade_criar')
    
    # GET - mostra form
    try:
        from usuarios.models import Aluna
        alunas = Aluna.objects.filter(ativa=True).order_by('nome')
    except Exception as e:
        print(f"Erro ao buscar alunas: {e}")
        alunas = []
    
    context = {
        'alunas': alunas,
    }
    
    return render(request, 'admin_dashboard/mensalidades/criar.html', context)

@login_required
def avisos_list(request):
    """Lista de avisos"""
    
    if not request.user.is_staff:
        return redirect('home')
    
    try:
        from calendario_avisos.models import Aviso
        
        # Query base - ordena por data_publicacao (campo correto!)
        avisos = Aviso.objects.all().order_by('-data_publicacao', '-data_evento')
        
        # Debug - mostra quantos avisos existem
        print(f"Total de avisos no banco: {avisos.count()}")
        
        # Filtro por tipo
        tipo = request.GET.get('tipo', '')
        if tipo:
            avisos = avisos.filter(tipo=tipo)
            print(f"Avisos apos filtro por tipo '{tipo}': {avisos.count()}")
        
    except Exception as e:
        print(f"Erro ao buscar avisos: {e}")
        import traceback
        traceback.print_exc()
        avisos = []
        tipo = ''
    
    context = {
        'avisos': avisos,
        'tipo_filtro': tipo,
        'total_avisos': avisos.count() if avisos else 0,
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
    """Editar mensalidade (principalmente status)"""
    
    if not request.user.is_staff:
        return redirect('home')
    
    try:
        from pagamentos.models import Mensalidade
        mensalidade = Mensalidade.objects.get(pk=pk)
    except Exception as e:
        from django.contrib import messages
        messages.error(request, f'Mensalidade nao encontrada: {e}')
        return redirect('admin_dashboard:mensalidades_list')
    
    if request.method == 'POST':
        try:
            from django.contrib import messages
            from datetime import datetime
            
            # Atualiza dados
            mes_referencia = request.POST.get('mes_referencia')
            data_vencimento = request.POST.get('data_vencimento')
            valor = request.POST.get('valor')
            status = request.POST.get('status')
            
            # Converte datas
            mensalidade.mes_referencia = datetime.strptime(mes_referencia + '-01', '%Y-%m-%d').date()
            mensalidade.data_vencimento = datetime.strptime(data_vencimento, '%Y-%m-%d').date()
            mensalidade.valor = Decimal(valor)
            mensalidade.status = status
            
            mensalidade.save()
            
            messages.success(request, 'Mensalidade atualizada com sucesso!')
            return redirect('admin_dashboard:mensalidades_list')
            
        except Exception as e:
            from django.contrib import messages
            messages.error(request, f'Erro ao atualizar mensalidade: {e}')
            return redirect('admin_dashboard:mensalidade_editar', pk=pk)
    
    # GET - mostra form preenchido
    context = {
        'mensalidade': mensalidade,
    }
    
    return render(request, 'admin_dashboard/mensalidades/editar.html', context)


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
    """Lista de espetaculos"""
    
    if not request.user.is_staff:
        return redirect('home')
    
    try:
        from espetaculo.models import Espetaculo
        
        espetaculos = Espetaculo.objects.all().order_by('-data_apresentacao')
        
    except Exception as e:
        print(f"Erro ao buscar espetaculos: {e}")
        espetaculos = []
    
    context = {
        'espetaculos': espetaculos,
        'total_espetaculos': espetaculos.count() if espetaculos else 0,
    }
    
    return render(request, 'admin_dashboard/espetaculos/list.html', context)


@login_required
def espetaculo_criar(request):
    """Criar novo espetaculo"""
    
    if not request.user.is_staff:
        return redirect('home')
    
    if request.method == 'POST':
        try:
            from espetaculo.models import Espetaculo
            from django.contrib import messages
            from datetime import datetime
            
            # Pega dados do form
            titulo = request.POST.get('titulo')
            subtitulo = request.POST.get('subtitulo', '')
            descricao = request.POST.get('descricao')
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
            
            ativo = request.POST.get('ativo') == 'on'
            
            # ADICIONA: Pega o arquivo PDF
            arquivo_informacoes = request.FILES.get('arquivo_informacoes')
            
            # Validacao
            if not all([titulo, descricao, data_apresentacao, local, endereco]):
                messages.error(request, 'Preencha todos os campos obrigatorios!')
                return redirect('admin_dashboard:espetaculo_criar')
            
            # Converte data_apresentacao
            data_apres = datetime.strptime(data_apresentacao, '%Y-%m-%dT%H:%M')
            
            # Cria espetaculo
            espetaculo = Espetaculo.objects.create(
                titulo=titulo,
                subtitulo=subtitulo,
                descricao=descricao,
                data_apresentacao=data_apres,
                local=local,
                endereco=endereco,
                arquivo_informacoes=arquivo_informacoes,
                audicao_aberta=audicao_aberta,
                audicao_data_inicio=audicao_data_inicio if audicao_data_inicio else None,
                audicao_data_fim=audicao_data_fim if audicao_data_fim else None,
                audicao_instrucoes=audicao_instrucoes,
                venda_aberta=venda_aberta,
                venda_data_inicio=venda_data_inicio if venda_data_inicio else None,
                preco_ingresso=preco_ingresso,
                ativo=ativo
            )
            
            messages.success(request, f'Espetaculo "{titulo}" criado com sucesso!')
            return redirect('admin_dashboard:espetaculos_list')
            
        except Exception as e:
            from django.contrib import messages
            messages.error(request, f'Erro ao criar espetaculo: {e}')
            print(f"Erro detalhado: {e}")
            import traceback
            traceback.print_exc()
            return redirect('admin_dashboard:espetaculo_criar')
    
    # GET - mostra form
    context = {}
    return render(request, 'admin_dashboard/espetaculos/criar.html', context)


@login_required
def espetaculo_editar(request, pk):
    """Editar espetaculo existente"""
    
    if not request.user.is_staff:
        return redirect('home')
    
    try:
        from espetaculo.models import Espetaculo
        espetaculo = Espetaculo.objects.get(pk=pk)
    except Exception as e:
        from django.contrib import messages
        messages.error(request, f'Espetaculo nao encontrado: {e}')
        return redirect('admin_dashboard:espetaculos_list')
    
    if request.method == 'POST':
        try:
            from django.contrib import messages
            from datetime import datetime
            
            # Atualiza dados
            espetaculo.titulo = request.POST.get('titulo')
            espetaculo.subtitulo = request.POST.get('subtitulo', '')
            espetaculo.descricao = request.POST.get('descricao')
            
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
            
            espetaculo.ativo = request.POST.get('ativo') == 'on'
            
            # ADICIONA: Atualiza arquivo PDF se enviado
            arquivo_informacoes = request.FILES.get('arquivo_informacoes')
            if arquivo_informacoes:
                espetaculo.arquivo_informacoes = arquivo_informacoes
            
            espetaculo.save()
            
            messages.success(request, f'Espetaculo "{espetaculo.titulo}" atualizado com sucesso!')
            return redirect('admin_dashboard:espetaculos_list')
            
        except Exception as e:
            from django.contrib import messages
            messages.error(request, f'Erro ao atualizar espetaculo: {e}')
            return redirect('admin_dashboard:espetaculo_editar', pk=pk)
    
    # GET - mostra form preenchido
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
        from usuarios.models import Aluna
        from django.db.models import Count
        
        # Pega todos os responsáveis (não-staff)
        responsaveis = User.objects.filter(is_staff=False).annotate(
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
            
            if not nome:
                messages.error(request, 'O nome da turma e obrigatorio!')
                return redirect('admin_dashboard:turma_criar')
            
            turma = Turma.objects.create(
                nome=nome,
                descricao=descricao,
                horario=horario,
                professor=professor,
                capacidade_maxima=int(capacidade_maxima),
                ativa=ativa
            )
            
            messages.success(request, f'Turma "{nome}" criada com sucesso!')
            return redirect('admin_dashboard:turmas_list')
            
        except Exception as e:
            from django.contrib import messages
            messages.error(request, f'Erro ao criar turma: {e}')
            print(f"Erro detalhado: {e}")
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
        messages.error(request, f'Turma nao encontrada: {e}')
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
    