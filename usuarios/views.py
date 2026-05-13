from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib import messages
from django.core.mail import send_mail
from django.conf import settings
from .models import Perfil, Aluna, RecuperacaoSenha

def user_login(request):
    """Pagina de login"""
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        # Tenta autenticar pelo username
        user = authenticate(request, username=username, password=password)
        
        # Se não funcionar, tenta pelo email
        if user is None:
            try:
                user_obj = User.objects.get(email=username)
                user = authenticate(request, username=user_obj.username, password=password)
            except User.DoesNotExist:
                pass
        
        if user is not None:
            login(request, user)
            return redirect('dashboard')
        else:
            messages.error(request, 'Usuario ou senha incorretos!')
    
    return render(request, 'usuarios/login.html')

def user_logout(request):
    """Logout"""
    logout(request)
    return redirect('home')

def cadastro(request):
    if request.method == 'POST':
        # Implementaremos depois
        pass
    return render(request, 'usuarios/cadastro.html')

@login_required
def dashboard(request):
    """Dashboard do responsavel"""
    alunas = Aluna.objects.filter(responsavel=request.user, ativa=True)
    return render(request, 'usuarios/dashboard.html', {'alunas': alunas})

@login_required
def perfil(request):
    """Perfil do responsavel"""
    return render(request, 'usuarios/perfil.html')

@login_required
def alterar_senha(request):
    """Responsavel altera sua propria senha (logado)"""
    
    if request.method == 'POST':
        senha_atual = request.POST.get('senha_atual')
        nova_senha = request.POST.get('nova_senha')
        confirma_senha = request.POST.get('confirma_senha')
        
        # Validacoes
        if not all([senha_atual, nova_senha, confirma_senha]):
            messages.error(request, 'Preencha todos os campos!')
            return redirect('alterar_senha')
        
        # Verifica se senha atual esta correta
        if not request.user.check_password(senha_atual):
            messages.error(request, 'Senha atual incorreta!')
            return redirect('alterar_senha')
        
        # Verifica se senhas novas coincidem
        if nova_senha != confirma_senha:
            messages.error(request, 'As senhas novas nao coincidem!')
            return redirect('alterar_senha')
        
        # Verifica tamanho minimo
        if len(nova_senha) < 6:
            messages.error(request, 'A senha deve ter no minimo 6 caracteres!')
            return redirect('alterar_senha')
        
        # Altera a senha
        request.user.set_password(nova_senha)
        request.user.save()
        
        # Mantem usuario logado apos trocar senha
        update_session_auth_hash(request, request.user)
        
        messages.success(request, 'Senha alterada com sucesso!')
        return redirect('dashboard')
    
    return render(request, 'usuarios/alterar_senha.html')

def esqueci_senha(request):
    """Recuperacao de senha via email"""
    
    if request.method == 'POST':
        email = request.POST.get('email')
        
        try:
            # Busca usuario pelo email
            user = User.objects.get(email=email, is_staff=False)
            
            # Cria token de recuperacao
            recuperacao = RecuperacaoSenha.criar_token(user)
            
            # Gera link de recuperacao
            link = request.build_absolute_uri(
                f'/conta/redefinir-senha/{recuperacao.token}/'
            )
            
            # Envia email
            try:
                send_mail(
                    subject='Recuperacao de Senha - BAILAH',
                    message=f'''Ola {user.get_full_name() or user.username},

Recebemos uma solicitacao para redefinir sua senha.

Clique no link abaixo para criar uma nova senha:
{link}

Este link expira em 24 horas.

Se voce nao solicitou esta alteracao, ignore este email.

Atenciosamente,
Equipe BAILAH
''',
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[email],
                    fail_silently=False,
                )
                
                messages.success(
                    request,
                    'Email enviado! Verifique sua caixa de entrada.'
                )
                
            except Exception as e:
                print(f"Erro ao enviar email: {e}")
                messages.error(
                    request,
                    'Erro ao enviar email. Contate o suporte.'
                )
            
        except User.DoesNotExist:
            # Por seguranca, nao revela se email existe
            messages.success(
                request,
                'Se o email existir, voce recebera as instrucoes.'
            )
        except Exception as e:
            print(f"Erro: {e}")
            messages.error(request, 'Erro ao processar solicitacao.')
        
        return redirect('esqueci_senha')
    
    return render(request, 'usuarios/esqueci_senha.html')

def redefinir_senha(request, token):
    """Redefine senha com token do email"""
    
    try:
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
    
@login_required
def redirecionar_dashboard(request):
    """Redireciona o usuário para o dashboard correto baseado no seu tipo"""
    
    # Verifica se é professor
    if request.user.groups.filter(name='Professores').exists():
        return redirect('admin_dashboard:professor_dashboard')
    
    # Verifica se é admin/staff
    if request.user.is_staff:
        return redirect('admin_dashboard:dashboard')
    
    # Caso contrário, é responsável/aluno
    return redirect('dashboard')
