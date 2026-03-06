from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required


@login_required
def dashboard(request):
    """Dashboard basico - sem queries complexas ainda"""
    
    # Apenas staff pode acessar
    if not request.user.is_staff:
        return redirect('home')
    
    # Dados hardcoded para teste
    context = {
        'total_alunas': 0,
        'total_recebido': 0,
        'mensalidades_pendentes': 0,
        'mensalidades_pagas': 0,
    }
    
    return render(request, 'admin_dashboard/dashboard.html', context)
