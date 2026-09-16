from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User


class Command(BaseCommand):
    help = (
        'Cria um superusuário se não existir. Uso manual/administrativo — '
        'no dia a dia, prefira a tela de configuração inicial '
        '(/setup-inicial/<token>/), que é o fluxo pensado para o cliente.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--username', required=True, help='Nome de usuário')
        parser.add_argument('--email', required=True, help='E-mail do usuário')
        parser.add_argument(
            '--password',
            required=True,
            help='Senha do usuário (nunca deixe isso fixo em nenhum script versionado)',
        )

    def handle(self, *args, **options):
        username = options['username']
        email = options['email']
        password = options['password']

        if User.objects.filter(username=username).exists():
            raise CommandError(f'Já existe um usuário com o username "{username}".')

        User.objects.create_superuser(username=username, email=email, password=password)
        self.stdout.write(self.style.SUCCESS(f'Superusuário "{username}" criado com sucesso!'))
