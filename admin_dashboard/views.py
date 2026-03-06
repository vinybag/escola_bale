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