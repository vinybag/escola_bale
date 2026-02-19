from django.http import HttpResponse
from django.contrib.auth.models import User

def criar_admin_secreto(request):
    senha_secreta = request.GET.get('senha', '')
    
    if senha_secreta != 'minhaSenhaSecreta123':
        return HttpResponse('Acesso negado', status=403)
    
    try:
        # Lista todos os usuários admin
        admins = User.objects.filter(is_superuser=True)
        
        if admins.exists():
            info = '<br>'.join([f'Username: {u.username}, Email: {u.email}' for u in admins])
            return HttpResponse(f'⚠️ Já existem superusuários:<br>{info}')
        else:
            User.objects.create_superuser(
                username='admin',
                email='vinybag@gmail.com',
                password='Pomboobeso9798!'
            )
            return HttpResponse('✅ Superusuário criado!')
    except Exception as e:
        return HttpResponse(f'❌ Erro: {e}')