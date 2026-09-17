from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.contrib.auth.models import User
from django.conf import settings
from django.http import Http404
from django.contrib import messages

def home(request):
    from usuarios.models import Turma
    from core.models import ConfiguracaoEscola

    turmas = Turma.objects.filter(ativa=True).order_by('dia_semana', 'horario')
    config = ConfiguracaoEscola.obter()

    return render(request, 'core/home.html', {
        'turmas': turmas,
        'config': config,
    })

def sobre(request):
    return render(request, 'core/sobre.html')


def configuracao_inicial(request, token):
    """
    Tela de configuração inicial: cria o primeiro usuário administrador
    (is_staff=True) de uma instância recém-implantada, direto pela web,
    sem precisar de terminal e sem nenhuma senha fixa no código.

    Segurança, por camadas:
    - Só responde (em vez de 404) se SETUP_TOKEN estiver configurado no
      ambiente e o token da URL bater exatamente com ele. Cada deploy
      deve ter o seu próprio SETUP_TOKEN, único.
    - Assim que já existir qualquer usuário staff no sistema, a tela se
      desativa sozinha (sempre 404 dali em diante) — ou seja, só pode
      ser usada uma única vez, na primeira configuração da instância.
    - A senha nunca é definida por você: quem digita é a própria pessoa
      que vai usar a conta, e fica salva só com ela (com hash, como
      qualquer senha do Django).
    """
    setup_token = getattr(settings, 'SETUP_TOKEN', '')

    if not setup_token or token != setup_token:
        raise Http404()

    if User.objects.filter(is_staff=True).exists():
        raise Http404()

    erro = None

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')
        password_confirmacao = request.POST.get('password_confirmacao', '')

        if not username or not email or not password:
            erro = 'Preencha todos os campos.'
        elif password != password_confirmacao:
            erro = 'As senhas não coincidem.'
        elif len(password) < 8:
            erro = 'A senha precisa ter pelo menos 8 caracteres.'
        elif User.objects.filter(username=username).exists():
            erro = 'Esse nome de usuário já está em uso.'
        elif User.objects.filter(is_staff=True).exists():
            # Proteção extra contra duas pessoas enviando o formulário
            # ao mesmo tempo na mesma janela de configuração.
            raise Http404()
        else:
            user = User.objects.create_superuser(
                username=username,
                email=email,
                password=password,
            )
            login(request, user)
            messages.success(request, 'Conta criada com sucesso! Bem-vindo(a).')
            return redirect('admin_dashboard:dashboard')

    return render(request, 'core/setup_inicial.html', {'erro': erro})
