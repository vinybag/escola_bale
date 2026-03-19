from django.shortcuts import render
from .models import Espetaculo

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
