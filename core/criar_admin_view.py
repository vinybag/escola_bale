from django.http import HttpResponse
from django.contrib.auth.models import User

def criar_admin_secreto(request):
    senha_secreta = request.GET.get('senha', '')
    
    if senha_secreta != 'minhaSenhaSecreta123':
        return HttpResponse('Acesso negado', status=403)
    
    try:
        if not User.objects.filter(username='admin').exists():
            User.objects.create_superuser(
                username='admin',
                email='vinybag@gmail.com',
                password='Pomboobeso9798!'
            )
            return HttpResponse('✅ Superusuário criado com sucesso!')
        else:
            return HttpResponse('⚠️ Superusuário já existe!')
    except Exception as e:
        return HttpResponse(f'❌ Erro: {e}')