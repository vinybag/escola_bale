from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth import logout
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

def logout_view(request):
    logout(request)
    return redirect('home')

def esqueci_senha(request):
    """Pagina de esqueci minha senha - via SMS"""
    
    if request.method == 'POST':
        telefone = request.POST.get('telefone')
        
        # Remove caracteres não numéricos
        telefone_limpo = ''.join(filter(str.isdigit, telefone))
        
        try:
            from usuarios.models import Perfil, RecuperacaoSenha
            
            # Busca pelo telefone
            perfil = Perfil.objects.get(telefone__icontains=telefone_limpo)
            user = perfil.user
            
            # Cria token de recuperacao
            recuperacao = RecuperacaoSenha.criar_token(user)
            
            # Gera código de 6 dígitos
            import random
            codigo = str(random.randint(100000, 999999))
            
            # Salva código no token
            recuperacao.codigo_sms = codigo
            recuperacao.save()
            
            # AQUI VOCÊ ENVIARIA SMS (por enquanto mostra na tela)
            messages.success(
                request, 
                f'CODIGO DE RECUPERACAO: {codigo} - Envie este codigo para o telefone {perfil.telefone}'
            )
            
            # Redireciona para página de inserir código
            return redirect('validar_codigo', token=recuperacao.token)
            
        except Perfil.DoesNotExist:
            # Por segurança, não revela se telefone existe
            messages.error(
                request,
                'Telefone nao encontrado em nossa base de dados.'
            )
        except Exception as e:
            messages.error(request, f'Erro ao processar solicitacao: {e}')
            import traceback
            traceback.print_exc()
        
        return redirect('esqueci_senha')
    
    return render(request, 'usuarios/esqueci_senha.html')


def validar_codigo(request, token):
    """Valida codigo SMS"""
    
    try:
        from usuarios.models import RecuperacaoSenha
        recuperacao = RecuperacaoSenha.objects.get(token=token)
        
        if not recuperacao.is_valido():
            messages.error(request, 'Codigo expirado!')
            return redirect('esqueci_senha')
        
        if request.method == 'POST':
            codigo = request.POST.get('codigo')
            
            if codigo == recuperacao.codigo_sms:
                # Código correto - vai para redefinir senha
                return redirect('redefinir_senha', token=token)
            else:
                messages.error(request, 'Codigo incorreto! Tente novamente.')
                return redirect('validar_codigo', token=token)
        
        context = {
            'token': token,
            'telefone': recuperacao.user.perfil.telefone if hasattr(recuperacao.user, 'perfil') else '',
        }
        return render(request, 'usuarios/validar_codigo.html', context)
        
    except RecuperacaoSenha.DoesNotExist:
        messages.error(request, 'Link invalido!')
        return redirect('esqueci_senha')


def redefinir_senha(request, token):
    """Pagina de redefinir senha com token"""
    
    try:
        from usuarios.models import RecuperacaoSenha
        recuperacao = RecuperacaoSenha.objects.get(token=token)
        
        # Verifica se token e valido
        if not recuperacao.is_valido():
            messages.error(request, 'Link expirado ou ja utilizado!')
            return redirect('login')
        
        if request.method == 'POST':
            nova_senha = request.POST.get('nova_senha')
            confirma_senha = request.POST.get('confirma_senha')
            
            if not nova_senha or not confirma_senha:
                messages.error(request, 'Preencha todos os campos!')
                return redirect('redefinir_senha', token=token)
            
            if nova_senha != confirma_senha:
                messages.error(request, 'As senhas nao coincidem!')
                return redirect('redefinir_senha', token=token)
            
            if len(nova_senha) < 6:
                messages.error(request, 'A senha deve ter no minimo 6 caracteres!')
                return redirect('redefinir_senha', token=token)
            
            # Redefine a senha
            user = recuperacao.user
            user.set_password(nova_senha)
            user.save()
            
            # Marca token como usado
            recuperacao.usado = True
            recuperacao.save()
            
            messages.success(request, 'Senha redefinida com sucesso! Faca login.')
            return redirect('login')
        
        context = {
            'token': token,
            'email': recuperacao.user.email,
        }
        return render(request, 'usuarios/redefinir_senha.html', context)
        
    except RecuperacaoSenha.DoesNotExist:
        messages.error(request, 'Link invalido!')
        return redirect('login')