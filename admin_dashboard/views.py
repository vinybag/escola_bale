from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from datetime import datetime
from decimal import Decimal
from django.db import models

@login_required
def dashboard(request):
    """Dashboard com dados reais do banco e graficos"""
    
    if not request.user.is_staff:
        return redirect('home')
    
    meses_pt = {
        1: 'Janeiro', 2: 'Fevereiro', 3: 'Marco', 4: 'Abril',
        5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto',
        9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
    }
    
    total_alunas = 0
    total_recebido = Decimal('0.00')
    mensalidades_pendentes = 0
    mensalidades_pagas = 0
    hoje = datetime.now()
    mes_atual = f"{meses_pt[hoje.month]} {hoje.year}"
    total_turmas = 0
    
    faturamento_meses = []
    faturamento_valores = []
    turmas_labels = []
    turmas_valores = []
    status_labels = ['Pagas', 'Pendentes', 'Atrasadas']
    status_valores = [0, 0, 0]
    
    try:
        from usuarios.models import Aluna, Turma
        from pagamentos.models import Mensalidade
        from django.db.models import Sum, Count, Q
        from datetime import timedelta
        
        hoje = datetime.now().date()
        mes = hoje.month
        ano = hoje.year
        
        total_alunas = Aluna.objects.filter(ativa=True).count()
        total_turmas = Turma.objects.filter(ativa=True).count()
        
        mensalidades_mes = Mensalidade.objects.filter(
            mes_referencia__month=mes,
            mes_referencia__year=ano
        )
        
        total_recebido = mensalidades_mes.filter(
            status='pago'
        ).aggregate(total=Sum('valor'))['total'] or Decimal('0.00')
        
        mensalidades_pendentes = mensalidades_mes.filter(status='pendente').count()
        mensalidades_pagas = mensalidades_mes.filter(status='pago').count()
        
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
        
        turmas = Turma.objects.filter(ativa=True).order_by('nome')
        
        for turma in turmas:
            total_alunas_turma = Aluna.objects.filter(
                turmas=turma,
                ativa=True
            ).count()
            
            if total_alunas_turma > 0:
                turmas_labels.append(turma.nome)
                turmas_valores.append(total_alunas_turma)
        
        status_valores[0] = mensalidades_mes.filter(status='pago').count()
        status_valores[1] = mensalidades_mes.filter(status='pendente').count()
        status_valores[2] = mensalidades_mes.filter(status='atrasado').count()
        
    except Exception as e:
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
        
        # Query base - REMOVA select_related('turma') porque não existe mais
        alunas = Aluna.objects.select_related('responsavel').all()  # Só responsavel
        
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
            alunas = alunas.filter(turmas__nome=turma)
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
        'total_alunas': len(alunas) if alunas else 0,
    }
    
    return render(request, 'admin_dashboard/alunas/list.html', context)

@login_required
def aluna_criar(request):
    """Criar nova aluna (suporta infantil com responsável e adulto sem responsável)"""
    
    if not request.user.is_staff:
        return redirect('home')
    
    if request.method == 'POST':
        try:
            from decimal import Decimal, InvalidOperation
            from usuarios.models import Aluna, Turma, Perfil
            from django.contrib.auth.models import User
            from django.contrib import messages
            
            # Pega dados da aluna
            nome = request.POST.get('nome')
            genero = request.POST.get('genero') or None
            data_nascimento = request.POST.get('data_nascimento') or None
            turmas_ids = request.POST.getlist('turmas')
            ativa = request.POST.get('ativa') == 'on'
            observacoes = request.POST.get('observacoes', '')
            tipo_aluna = request.POST.get('tipo_aluna', 'infantil')

            # NOVOS CAMPOS FINANCEIROS
            valor_mensalidade = request.POST.get('valor_mensalidade')
            dia_vencimento = request.POST.get('dia_vencimento') or 10
            gerar_mensalidade_automatica = request.POST.get('gerar_mensalidade_automatica') == 'on'
            
            # Valida dados básicos
            if not nome:
                messages.error(request, 'O nome da aluna e obrigatorio!')
                return redirect('admin_dashboard:aluna_criar')

            # Validação financeira
            valor_mensalidade_decimal = None
            if valor_mensalidade:
                try:
                    valor_mensalidade_decimal = Decimal(valor_mensalidade)
                    if valor_mensalidade_decimal < 0:
                        messages.error(request, 'O valor da mensalidade nao pode ser negativo!')
                        return redirect('admin_dashboard:aluna_criar')
                except (InvalidOperation, ValueError):
                    messages.error(request, 'Informe um valor de mensalidade valido!')
                    return redirect('admin_dashboard:aluna_criar')

            try:
                dia_vencimento = int(dia_vencimento)
                if dia_vencimento < 1 or dia_vencimento > 31:
                    messages.error(request, 'O dia de vencimento deve estar entre 1 e 31!')
                    return redirect('admin_dashboard:aluna_criar')
            except (TypeError, ValueError):
                messages.error(request, 'Informe um dia de vencimento valido!')
                return redirect('admin_dashboard:aluna_criar')
            
            responsavel = None
            
            # Só processa responsável se for aluna infantil
            if tipo_aluna == 'infantil':
                tipo_responsavel = request.POST.get('tipo_responsavel')
                
                if tipo_responsavel == 'existente':
                    responsavel_id = request.POST.get('responsavel_existente')
                    if not responsavel_id:
                        messages.error(request, 'Selecione um responsavel!')
                        return redirect('admin_dashboard:aluna_criar')
                    responsavel = User.objects.get(id=responsavel_id)
                    
                else:
                    resp_nome = request.POST.get('responsavel_nome', '')
                    resp_sobrenome = request.POST.get('responsavel_sobrenome', '')
                    resp_email = request.POST.get('responsavel_email', '')
                    resp_senha = request.POST.get('responsavel_senha', '')
                    resp_telefone = request.POST.get('responsavel_telefone', '')
                    
                    if not resp_nome:
                        messages.error(request, 'Nome do responsavel e obrigatorio!')
                        return redirect('admin_dashboard:aluna_criar')
                    
                    if not resp_email:
                        messages.error(request, 'Email do responsavel e obrigatorio!')
                        return redirect('admin_dashboard:aluna_criar')
                    
                    if User.objects.filter(email=resp_email).exists():
                        messages.error(request, f'Ja existe um usuario com o email {resp_email}!')
                        return redirect('admin_dashboard:aluna_criar')
                    
                    username = resp_email.split('@')[0]
                    base_username = username
                    counter = 1
                    while User.objects.filter(username=username).exists():
                        username = f"{base_username}{counter}"
                        counter += 1
                    
                    if not resp_senha:
                        resp_senha = User.objects.make_random_password()
                    
                    responsavel = User.objects.create_user(
                        username=username,
                        email=resp_email,
                        password=resp_senha,
                        first_name=resp_nome,
                        last_name=resp_sobrenome
                    )
                    
                    perfil, created = Perfil.objects.get_or_create(
                        user=responsavel,
                        defaults={'telefone': resp_telefone or '', 'is_responsavel': True}
                    )
                    if not created and resp_telefone:
                        perfil.telefone = resp_telefone
                        perfil.is_responsavel = True
                        perfil.save()
                    
                    messages.success(request, f'Responsavel {resp_nome} {resp_sobrenome} cadastrado! Login: {resp_email} / Senha: {resp_senha}')
            
            else:
                adulto_email = request.POST.get('adulto_email', '')
                adulto_senha = request.POST.get('adulto_senha', '')
                
                if not adulto_email:
                    messages.error(request, 'Email da aluna adulta e obrigatorio!')
                    return redirect('admin_dashboard:aluna_criar')
                
                if User.objects.filter(email=adulto_email).exists():
                    messages.error(request, f'Ja existe um usuario com o email {adulto_email}!')
                    return redirect('admin_dashboard:aluna_criar')
                
                username = adulto_email.split('@')[0]
                base_username = username
                counter = 1
                while User.objects.filter(username=username).exists():
                    username = f"{base_username}{counter}"
                    counter += 1
                
                if not adulto_senha:
                    adulto_senha = User.objects.make_random_password()
                
                responsavel = User.objects.create_user(
                    username=username,
                    email=adulto_email,
                    password=adulto_senha,
                    first_name=nome.split()[0] if ' ' in nome else nome,
                    last_name=nome.split()[-1] if ' ' in nome else ''
                )
                
                perfil, created = Perfil.objects.get_or_create(
                    user=responsavel,
                    defaults={'telefone': '', 'is_responsavel': False}
                )
                if not created:
                    perfil.is_responsavel = False
                    perfil.save()
                
                messages.success(request, f'Aluna adulta {nome} cadastrada! Login: {adulto_email} / Senha: {adulto_senha}')
            
            # Busca as turmas selecionadas
            turmas_selecionadas = []
            for turma_id in turmas_ids:
                try:
                    turma = Turma.objects.get(id=turma_id)
                    turmas_selecionadas.append(turma)
                except Turma.DoesNotExist:
                    pass
            
            # Cria a aluna
            aluna = Aluna.objects.create(
                nome=nome,
                genero=genero,
                data_nascimento=data_nascimento,
                responsavel=responsavel,
                tipo_aluna=tipo_aluna,
                ativa=ativa,
                observacoes=observacoes,
                valor_mensalidade=valor_mensalidade_decimal,
                dia_vencimento=dia_vencimento,
                gerar_mensalidade_automatica=gerar_mensalidade_automatica,
            )
            
            # Adiciona as turmas (ManyToMany)
            aluna.turmas.set(turmas_selecionadas)
            
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
            from decimal import Decimal, InvalidOperation
            from django.contrib.auth.models import User
            from usuarios.models import Turma
            from django.contrib import messages
            
            # Atualiza dados básicos
            aluna.nome = request.POST.get('nome')
            aluna.genero = request.POST.get('genero') or None
            aluna.data_nascimento = request.POST.get('data_nascimento') or None
            aluna.ativa = request.POST.get('ativa') == 'on'
            aluna.observacoes = request.POST.get('observacoes', '')

            # NOVOS CAMPOS FINANCEIROS
            valor_mensalidade = request.POST.get('valor_mensalidade')
            dia_vencimento = request.POST.get('dia_vencimento') or 10
            gerar_mensalidade_automatica = request.POST.get('gerar_mensalidade_automatica') == 'on'

            if valor_mensalidade:
                try:
                    valor_mensalidade_decimal = Decimal(valor_mensalidade)
                    if valor_mensalidade_decimal < 0:
                        messages.error(request, 'O valor da mensalidade nao pode ser negativo!')
                        return redirect('admin_dashboard:aluna_editar', pk=pk)
                    aluna.valor_mensalidade = valor_mensalidade_decimal
                except (InvalidOperation, ValueError):
                    messages.error(request, 'Informe um valor de mensalidade valido!')
                    return redirect('admin_dashboard:aluna_editar', pk=pk)
            else:
                aluna.valor_mensalidade = None

            try:
                dia_vencimento = int(dia_vencimento)
                if dia_vencimento < 1 or dia_vencimento > 31:
                    messages.error(request, 'O dia de vencimento deve estar entre 1 e 31!')
                    return redirect('admin_dashboard:aluna_editar', pk=pk)
                aluna.dia_vencimento = dia_vencimento
            except (TypeError, ValueError):
                messages.error(request, 'Informe um dia de vencimento valido!')
                return redirect('admin_dashboard:aluna_editar', pk=pk)

            aluna.gerar_mensalidade_automatica = gerar_mensalidade_automatica
            
            # Atualiza responsavel se mudou
            responsavel_id = request.POST.get('responsavel')
            if responsavel_id:
                aluna.responsavel = User.objects.get(id=responsavel_id)
            else:
                aluna.responsavel = None
            
            # Atualiza as turmas
            turmas_ids = request.POST.getlist('turmas')
            turmas_selecionadas = []
            for turma_id in turmas_ids:
                try:
                    turma = Turma.objects.get(id=turma_id)
                    turmas_selecionadas.append(turma)
                except Turma.DoesNotExist:
                    pass

            aluna.save()
            aluna.turmas.set(turmas_selecionadas)
            
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
            
            # Arquivo informações (já existente)
            arquivo_informacoes = request.FILES.get('arquivo_informacoes')
            if arquivo_informacoes:
                espetaculo.arquivo_informacoes = arquivo_informacoes
            
            # NOVO: Arquivo Edital
            arquivo_edital = request.FILES.get('arquivo_edital')
            if arquivo_edital:
                espetaculo.arquivo_edital = arquivo_edital
            
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
        
        # Pega ou cria perfil
        perfil, created = Perfil.objects.get_or_create(user=responsavel)
        
        # Lista de alunas vinculadas a este responsável
        alunas_vinculadas = Aluna.objects.filter(responsavel=responsavel).order_by('nome')
        
        # Lista de alunas não vinculadas a nenhum responsável (para adicionar)
        alunas_nao_vinculadas = Aluna.objects.filter(responsavel__isnull=True, tipo_aluna='infantil').order_by('nome')
        
        # Busca a aluna associada a este responsável (se existir)
        aluna_associada = Aluna.objects.filter(responsavel=responsavel, tipo_aluna='adulto').first()
        
        if request.method == 'POST':
            # Atualiza dados do User
            responsavel.first_name = request.POST.get('first_name', '')
            responsavel.last_name = request.POST.get('last_name', '')
            responsavel.email = request.POST.get('email', '')
            responsavel.save()
            
            # Atualiza dados do Perfil
            perfil.telefone = request.POST.get('telefone', '')
            perfil.cpf = request.POST.get('cpf', '')
            perfil.endereco = request.POST.get('endereco', '')
            
            data_nascimento = request.POST.get('data_nascimento')
            if data_nascimento:
                perfil.data_nascimento = data_nascimento
            
            # NOVO CAMPO: Este responsável também é aluno
            is_tambem_aluno = request.POST.get('is_tambem_aluno') == 'on'
            perfil.is_tambem_aluno = is_tambem_aluno
            perfil.save()
            
            # Se marcou "também é aluno", criar/atualizar a aluna associada
            if is_tambem_aluno:
                # Busca as turmas selecionadas
                turmas_ids = request.POST.getlist('turmas_aluno')
                turmas_selecionadas = []
                for turma_id in turmas_ids:
                    try:
                        turma = Turma.objects.get(id=turma_id)
                        turmas_selecionadas.append(turma)
                    except Turma.DoesNotExist:
                        pass
                
                if aluna_associada:
                    # Atualiza aluna existente
                    aluna_associada.nome = responsavel.get_full_name() or responsavel.username
                    aluna_associada.data_nascimento = data_nascimento or None
                    aluna_associada.ativa = True
                    aluna_associada.save()
                    aluna_associada.turmas.set(turmas_selecionadas)
                    messages.success(request, f'Aluno {aluna_associada.nome} atualizado como aluno da escola!')
                else:
                    # Cria nova aluna
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
                # Se desmarcou "também é aluno", remove a associação (mas não deleta a aluna)
                if aluna_associada:
                    aluna_associada.responsavel = None
                    aluna_associada.ativa = False
                    aluna_associada.save()
                    messages.info(request, f'Aluno {aluna_associada.nome} foi desvinculado')
            
            # Vincular nova aluna (se selecionada)
            vincular_aluna_id = request.POST.get('vincular_aluna')
            if vincular_aluna_id:
                try:
                    aluna = Aluna.objects.get(id=vincular_aluna_id)
                    aluna.responsavel = responsavel
                    aluna.save()
                    messages.success(request, f'Aluna {aluna.nome} vinculada com sucesso!')
                except Aluna.DoesNotExist:
                    messages.error(request, 'Aluna não encontrada!')
            
            # Remover vínculo de aluna (se solicitado)
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
        
        # GET - mostra form
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
        messages.error(request, f'Responsavel nao encontrado: {e}')
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
            
            if not nome:
                messages.error(request, 'O nome da turma e obrigatorio!')
                return redirect('admin_dashboard:turma_criar')
            
            turma = Turma.objects.create(
                nome=nome,
                descricao=descricao,
                horario=horario,
                professor=professor,
                capacidade_maxima=int(capacidade_maxima),
                ativa=ativa,
                disponivel_experimental=disponivel_experimental
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
            turma.disponivel_experimental = request.POST.get('disponivel_experimental') == 'on'
            
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
    
    # Filtro por personagem
    personagem_filtro = request.GET.get('personagem', '')
    if personagem_filtro:
        inscricoes = inscricoes.filter(personagens__icontains=personagem_filtro)
    
    context = {
        'inscricoes': inscricoes,
        'personagem_filtro': personagem_filtro,
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

@login_required
def agendamentos_list(request):
    """Lista de agendamentos de aula experimental"""
    if not request.user.is_staff:
        return redirect('home')
    
    from agenda.models import Agendamento
    from datetime import date
    
    hoje = date.today()
    
    tipo = request.GET.get('tipo', 'proximos')
    mes = request.GET.get('mes', '')
    semana = request.GET.get('semana', '')
    
    agendamentos = Agendamento.objects.all()
    
    if tipo == 'antigos':
        agendamentos = agendamentos.filter(data__lt=hoje)
    else:
        tipo = 'proximos'
        agendamentos = agendamentos.filter(data__gte=hoje)
    
    if mes:
        try:
            ano, mes_num = mes.split('-')
            agendamentos = agendamentos.filter(
                data__year=int(ano),
                data__month=int(mes_num)
            )
        except ValueError:
            pass
    
    if semana:
        try:
            ano_str, semana_str = semana.split('-W')
            ano = int(ano_str)
            num_semana = int(semana_str)

            inicio_semana = date.fromisocalendar(ano, num_semana, 1)
            fim_semana = date.fromisocalendar(ano, num_semana, 7)

            agendamentos = agendamentos.filter(
                data__gte=inicio_semana,
                data__lte=fim_semana
            )
        except (ValueError, TypeError):
            pass
    
    agendamentos = agendamentos.order_by('data', 'horario')
    
    meses_disponiveis = Agendamento.objects.dates('data', 'month', order='DESC')

    total_geral = Agendamento.objects.count()
    total_proximos = Agendamento.objects.filter(data__gte=hoje).count()
    total_antigos = Agendamento.objects.filter(data__lt=hoje).count()

    context = {
        'agendamentos': agendamentos,
        'tipo': tipo,
        'mes': mes,
        'semana': semana,
        'hoje': hoje,
        'meses_disponiveis': meses_disponiveis,
        'total_geral': total_geral,
        'total_proximos': total_proximos,
        'total_antigos': total_antigos,
    }
    
    return render(request, 'admin_dashboard/agendamentos/list.html', context)

@login_required
def agendamento_detalhes(request, pk):
    """Detalhes do agendamento"""
    if not request.user.is_staff:
        return redirect('home')
    
    from agenda.models import Agendamento
    agendamento = get_object_or_404(Agendamento, pk=pk)
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
    
    avisos = Aviso.objects.filter(ativo=True).order_by('-data_publicacao')
    
    return render(request, 'admin_dashboard/professor/avisos.html', {'avisos': avisos})

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
    
    professores = User.objects.filter(groups__name='Professores').annotate(
        total_turmas=Count('turmas_ministradas')
    ).order_by('first_name')
    
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
def professor_avisos(request):
    """Lista de avisos para professor"""
    
    if not request.user.groups.filter(name='Professores').exists():
        return redirect('home')
    
    from calendario_avisos.models import Aviso
    
    avisos = Aviso.objects.filter(ativo=True).order_by('-data_publicacao')
    
    return render(request, 'admin_dashboard/professor/avisos.html', {'avisos': avisos})

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

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages

@login_required
def espetaculo_participacoes(request, pk):
    if not request.user.is_staff:
        return redirect('home')

    try:
        from espetaculo.models import Espetaculo, ParticipacaoEspetaculo
        from usuarios.models import Aluna

        espetaculo = get_object_or_404(Espetaculo, pk=pk)

        if request.method == 'POST':
            aluna_id = request.POST.get('aluna_id')

            if not aluna_id:
                messages.error(request, 'Selecione uma aluna.')
                return redirect('admin_dashboard:espetaculo_participacoes', pk=pk)

            aluna = get_object_or_404(Aluna, pk=aluna_id)

            participacao, created = ParticipacaoEspetaculo.objects.get_or_create(
                espetaculo=espetaculo,
                aluna=aluna,
                defaults={'vai_dancar': True}
            )

            if created:
                messages.success(request, f'{aluna.nome} foi adicionada ao espetáculo com sucesso!')
            else:
                messages.warning(request, f'{aluna.nome} já está vinculada a este espetáculo.')

            return redirect('admin_dashboard:espetaculo_participacoes', pk=pk)

        participacoes = (
            ParticipacaoEspetaculo.objects
            .select_related('aluna', 'aluna__responsavel')
            .filter(espetaculo=espetaculo)
            .prefetch_related('cobrancas')
            .order_by('aluna__nome')
        )

        alunas_disponiveis = (
            Aluna.objects
            .filter(ativa=True)
            .exclude(participacoes_espetaculo__espetaculo=espetaculo)
            .order_by('nome')
        )

        context = {
            'espetaculo': espetaculo,
            'participacoes': participacoes,
            'total_participacoes': participacoes.count(),
            'alunas_disponiveis': alunas_disponiveis,
        }

        return render(request, 'admin_dashboard/espetaculos/participacoes.html', context)

    except Exception as e:
        messages.error(request, f'Erro ao carregar participações: {e}')
        return redirect('admin_dashboard:espetaculos_list')
    
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
        from espetaculo.models import ParticipacaoEspetaculo, CobrancaEspetaculo

        participacao = get_object_or_404(
            ParticipacaoEspetaculo.objects.select_related(
                'espetaculo',
                'aluna',
                'aluna__responsavel'
            ),
            pk=pk
        )

        if request.method == 'POST':
            tipo = request.POST.get('tipo')
            descricao = request.POST.get('descricao')
            valor_total = request.POST.get('valor_total')
            permitir_parcelamento = request.POST.get('permitir_parcelamento') == 'on'
            max_parcelas = request.POST.get('max_parcelas') or 1
            vencimento_primeira_parcela = request.POST.get('vencimento_primeira_parcela')

            if not tipo or not descricao or not valor_total:
                messages.error(request, 'Preencha os campos obrigatórios da cobrança.')
                return redirect('admin_dashboard:participacao_cobrancas', pk=pk)

            try:
                valor_total = Decimal(valor_total)
            except Exception:
                messages.error(request, 'Valor total inválido.')
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

            CobrancaEspetaculo.objects.create(
                participacao=participacao,
                tipo=tipo,
                descricao=descricao,
                valor_total=valor_total,
                permitir_parcelamento=permitir_parcelamento,
                max_parcelas=max_parcelas,
                vencimento_primeira_parcela=data_vencimento,
            )

            messages.success(request, 'Cobrança criada com sucesso.')
            return redirect('admin_dashboard:participacao_cobrancas', pk=pk)

        cobrancas = (
            CobrancaEspetaculo.objects
            .filter(participacao=participacao)
            .prefetch_related('parcelas')
            .order_by('-criado_em')
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
    
from django.db import transaction


@login_required
def cobranca_espetaculo_enviar_asaas(request, pk):
    if not request.user.is_staff:
        return redirect('home')

    if request.method != 'POST':
        messages.error(request, 'Método inválido.')
        return redirect('admin_dashboard:espetaculos_list')

    try:
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

        responsavel = cobranca.participacao.aluna.responsavel
        if not responsavel:
            messages.error(request, 'A aluna não possui responsável vinculado.')
            return redirect(
                'admin_dashboard:participacao_cobrancas',
                pk=cobranca.participacao.pk
            )

        if not cobranca.vencimento_primeira_parcela:
            messages.error(request, 'Defina o vencimento da primeira parcela antes de enviar ao Asaas.')
            return redirect(
                'admin_dashboard:participacao_cobrancas',
                pk=cobranca.participacao.pk
            )

        customer = get_or_create_customer(responsavel)

        descricao_base = (
            f'{cobranca.get_tipo_display()} - '
            f'{cobranca.participacao.espetaculo.titulo} - '
            f'{cobranca.participacao.aluna.nome}'
        )

        billing_type = request.POST.get('billing_type') or 'UNDEFINED'

        if cobranca.permitir_parcelamento and cobranca.max_parcelas > 1:
            retorno = create_installment_payment(
                customer_id=customer['id'],
                total_value=cobranca.valor_total,
                installment_count=cobranca.max_parcelas,
                due_date=cobranca.vencimento_primeira_parcela,
                description=descricao_base,
                external_reference=f'cobranca_espetaculo:{cobranca.pk}',
                billing_type=billing_type,
            )

            installment_id = retorno.get('installment')
            if not installment_id:
                raise AsaasError('O Asaas não retornou o installment da cobrança parcelada.')

            parcelas_response = list_installment_payments(installment_id)
            parcelas_asaas = parcelas_response.get('data', [])

            with transaction.atomic():
                cobranca.asaas_customer_id = customer.get('id')
                cobranca.billing_type = billing_type
                cobranca.enviado_asaas = True
                cobranca.save(update_fields=['asaas_customer_id', 'billing_type', 'enviado_asaas'])

                for idx, item in enumerate(parcelas_asaas, start=1):
                    ParcelaCobrancaEspetaculo.objects.update_or_create(
                        cobranca=cobranca,
                        numero_parcela=idx,
                        defaults={
                            'total_parcelas': len(parcelas_asaas),
                            'valor': item.get('value') or 0,
                            'vencimento': item.get('dueDate'),
                            'asaas_payment_id': item.get('id'),
                            'asaas_installment_id': installment_id,
                            'asaas_invoice_url': item.get('invoiceUrl'),
                            'asaas_bank_slip_url': item.get('bankSlipUrl'),
                            'asaas_transaction_receipt_url': item.get('transactionReceiptUrl'),
                            'asaas_nosso_numero': item.get('nossoNumero'),
                            'asaas_status': item.get('status'),
                            'billing_type': item.get('billingType') or billing_type,
                            'status': 'pago' if item.get('status') == 'RECEIVED' else 'pendente',
                        }
                    )

                cobranca.atualizar_status()

            messages.success(request, 'Cobrança parcelada enviada ao Asaas com sucesso.')

        else:
            retorno = create_payment(
                customer_id=customer['id'],
                value=cobranca.valor_total,
                due_date=cobranca.vencimento_primeira_parcela,
                description=descricao_base,
                external_reference=f'cobranca_espetaculo:{cobranca.pk}',
                billing_type=billing_type,
            )

            with transaction.atomic():
                cobranca.asaas_customer_id = customer.get('id')
                cobranca.billing_type = billing_type
                cobranca.enviado_asaas = True
                cobranca.save(update_fields=['asaas_customer_id', 'billing_type', 'enviado_asaas'])

                ParcelaCobrancaEspetaculo.objects.update_or_create(
                    cobranca=cobranca,
                    numero_parcela=1,
                    defaults={
                        'total_parcelas': 1,
                        'valor': retorno.get('value') or cobranca.valor_total,
                        'vencimento': retorno.get('dueDate') or cobranca.vencimento_primeira_parcela,
                        'asaas_payment_id': retorno.get('id'),
                        'asaas_invoice_url': retorno.get('invoiceUrl'),
                        'asaas_bank_slip_url': retorno.get('bankSlipUrl'),
                        'asaas_transaction_receipt_url': retorno.get('transactionReceiptUrl'),
                        'asaas_nosso_numero': retorno.get('nossoNumero'),
                        'asaas_status': retorno.get('status'),
                        'billing_type': retorno.get('billingType') or billing_type,
                        'status': 'pago' if retorno.get('status') == 'RECEIVED' else 'pendente',
                    }
                )

                cobranca.atualizar_status()

            messages.success(request, 'Cobrança enviada ao Asaas com sucesso.')

        return redirect(
            'admin_dashboard:participacao_cobrancas',
            pk=cobranca.participacao.pk
        )

    except Exception as e:
        messages.error(request, f'Erro ao enviar cobrança ao Asaas: {e}')
        return redirect('admin_dashboard:espetaculos_list')