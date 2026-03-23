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

def esqueci_senha(request):
    """Página de esqueci minha senha"""
    
    if request.method == 'POST':
        email = request.POST.get('email')
        
        try:
            user = User.objects.get(email=email, is_staff=False)
            
            # Cria token de recuperação
            from usuarios.models import RecuperacaoSenha
            recuperacao = RecuperacaoSenha.criar_token(user)
            
            # Gera link de recuperação
            link = request.build_absolute_uri(
                f'/conta/redefinir-senha/{recuperacao.token}/'
            )
            
            # AQUI VOCÊ ENVIARIA EMAIL (por enquanto mostra na tela)
            messages.success(
                request, 
                f'Link de recuperacao gerado! Copie e envie para o responsavel: {link}'
            )
            
            # Em produção, você enviaria email assim:
            # send_mail(
            #     'Recuperação de Senha - BAILAH',
            #     f'Clique no link para redefinir sua senha: {link}',
            #     'noreply@bailah.com',
            #     [email],
            # )
            
        except User.DoesNotExist:
            # Por segurança, não revela se email existe ou não
            messages.success(
                request,
                'Se o email existir em nossa base, você receberá as instruções.'
            )
        except Exception as e:
            messages.error(request, f'Erro ao processar solicitação: {e}')
        
        return redirect('esqueci_senha')
    
    return render(request, 'usuarios/esqueci_senha.html')


def redefinir_senha(request, token):
    """Página de redefinir senha com token"""
    
    try:
        from usuarios.models import RecuperacaoSenha
        recuperacao = RecuperacaoSenha.objects.get(token=token)
        
        # Verifica se token é válido
        if not recuperacao.is_valido():
            messages.error(request, 'Link expirado ou já utilizado!')
            return redirect('login')
        
        if request.method == 'POST':
            nova_senha = request.POST.get('nova_senha')
            confirma_senha = request.POST.get('confirma_senha')
            
            if not nova_senha or not confirma_senha:
                messages.error(request, 'Preencha todos os campos!')
                return redirect('redefinir_senha', token=token)
            
            if nova_senha != confirma_senha:
                messages.error(request, 'As senhas não coincidem!')
                return redirect('redefinir_senha', token=token)
            
            if len(nova_senha) < 6:
                messages.error(request, 'A senha deve ter no mínimo 6 caracteres!')
                return redirect('redefinir_senha', token=token)
            
            # Redefine a senha
            user = recuperacao.user
            user.set_password(nova_senha)
            user.save()
            
            # Marca token como usado
            recuperacao.usado = True
            recuperacao.save()
            
            messages.success(request, 'Senha redefinida com sucesso! Faça login.')
            return redirect('login')
        
        context = {
            'token': token,
            'email': recuperacao.user.email,
        }
        return render(request, 'usuarios/redefinir_senha.html', context)
        
    except RecuperacaoSenha.DoesNotExist:
        messages.error(request, 'Link inválido!')
        return redirect('login')