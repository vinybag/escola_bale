from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from .models import Perfil, Aluna

def cadastro(request):
    if request.method == 'POST':
        # Implementaremos depois
        pass
    return render(request, 'usuarios/cadastro.html')

@login_required
def dashboard(request):
    # Busca as alunas do responsável logado
    alunas = Aluna.objects.filter(responsavel=request.user, ativa=True)
    return render(request, 'usuarios/dashboard.html', {'alunas': alunas})

@login_required
def perfil(request):
    return render(request, 'usuarios/perfil.html')

from django.contrib.auth import logout
from django.shortcuts import redirect

def logout_view(request):
    logout(request)
    return redirect('home')