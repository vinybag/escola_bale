from django.shortcuts import render, get_object_or_404, redirect
from .models import Espetaculo, InscricaoAudicao
from .forms import InscricaoAudicaoForm
from django.contrib import messages
from django.http import JsonResponse

def espetaculo_home(request):
    """Página inicial do espetáculo"""
    
    # Pega espetáculo ativo
    try:
        espetaculo = Espetaculo.objects.filter(ativo=True).first()
    except:
        espetaculo = None
    
    context = {
        'espetaculo': espetaculo,
    }
    
    return render(request, 'espetaculo/home.html', context)


# NOVAS VIEWS PÚBLICAS

def espetaculos_lista_publica(request):
    """Página pública com lista de TODOS os espetáculos ativos"""
    espetaculos = Espetaculo.objects.filter(ativo=True).order_by('-data_apresentacao')
    return render(request, 'espetaculo/public_list.html', {'espetaculos': espetaculos})

def espetaculo_detalhes_publico(request, pk):
    """Página pública com detalhes de um espetáculo específico"""
    espetaculo = get_object_or_404(Espetaculo, pk=pk, ativo=True)
    return render(request, 'espetaculo/public_detalhes.html', {'espetaculo': espetaculo})

def personagens_publicos(request):
    """Página pública com os personagens clicáveis"""
    from .models import Espetaculo
    espetaculo = Espetaculo.objects.filter(ativo=True).first()
    return render(request, 'espetaculo/personagens_publicos.html', {'espetaculo': espetaculo})

def inscricao_audicao(request):
    """Processa a inscrição para audição"""
    if request.method == 'POST':
        form = InscricaoAudicaoForm(request.POST)
        if form.is_valid():
            inscricao = form.save(commit=False)
            # Pega o espetáculo ativo
            from .models import Espetaculo
            espetaculo = Espetaculo.objects.filter(ativo=True).first()
            inscricao.espetaculo = espetaculo
            inscricao.save()
            messages.success(request, 'Inscrição realizada com sucesso! Entraremos em contato em breve.')
            return redirect('/espetaculos/inscricao-sucesso/')
        else:
            messages.error(request, 'Erro ao realizar inscrição. Verifique os dados.')
    
    return redirect('/espetaculos/personagens/')

def inscricao_sucesso(request):
    """Página de confirmação de inscrição"""
    return render(request, 'espetaculo/inscricao_sucesso.html')

def get_personagens_por_idade(request):
    """Retorna os personagens disponíveis para a idade informada"""
    idade = int(request.GET.get('idade', 0))
    
    # Regras de idade por personagem
    regras = {
        'thessalia': idade >= 15,
        'zyara': idade >= 8,
        'zyar': idade >= 8,
        'astela_nur': idade >= 16,
        'kai_ignus': idade >= 15,
        'eldrick_felicius': idade >= 10,
        'florine': 8 <= idade <= 20,
        'odessa': idade >= 10,
        'aurelia': idade >= 10,
        'cora_del_amour': idade >= 8,
        '3_marias': 6 <= idade <= 12,
    }
    
    personagens_disponiveis = []
    for personagem_id, disponivel in regras.items():
        if disponivel:
            # Pega o nome do dicionário PERSONAGENS_CHOICES do modelo
            dict_choices = dict(InscricaoAudicao.PERSONAGENS_CHOICES)
            nome = dict_choices.get(personagem_id, personagem_id)
            personagens_disponiveis.append({'id': personagem_id, 'nome': nome})
    
    return JsonResponse({'personagens': personagens_disponiveis})