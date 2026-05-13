# usuarios/management/commands/criar_professor.py
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User, Group

class Command(BaseCommand):
    help = 'Cria um novo professor'

    def add_arguments(self, parser):
        parser.add_argument('nome', type=str, help='Nome do professor')
        parser.add_argument('email', type=str, help='Email do professor')
        parser.add_argument('senha', type=str, help='Senha do professor')

    def handle(self, *args, **options):
        nome = options['nome']
        email = options['email']
        senha = options['senha']
        
        user = User.objects.create_user(
            username=email.split('@')[0],
            email=email,
            password=senha,
            first_name=nome
        )
        
        grupo = Group.objects.get(name='Professores')
        user.groups.add(grupo)
        user.save()
        
        self.stdout.write(self.style.SUCCESS(f'Professor {nome} criado com sucesso!'))