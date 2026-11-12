from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


class Command(BaseCommand):
    help = (
        "Mostra a situação da conta 'admin' (criada pelo antigo init_db.py com uma "
        "senha que ficou pública no código) e, com --bloquear, impede que alguém "
        "entre com ela. Sem --bloquear, só mostra: não altera nada."
    )

    def add_arguments(self, parser):
        parser.add_argument('--usuario', default='admin', help='Nome de usuário da conta (padrão: admin).')
        parser.add_argument(
            '--bloquear',
            action='store_true',
            help=(
                'Tira a senha da conta: ninguém consegue entrar com ela. '
                'Para desfazer: python manage.py changepassword <usuario>'
            ),
        )
        parser.add_argument(
            '--forcar',
            action='store_true',
            help='Bloqueia mesmo que seja o único administrador ativo (cuidado: você pode ficar sem acesso).',
        )

    def handle(self, *args, **opcoes):
        nome = opcoes['usuario']
        conta = User.objects.filter(username=nome).first()

        if conta is None:
            self.stdout.write(f"A conta '{nome}' NÃO existe neste site. Não há nada a fazer.")
            return

        outros_staff = User.objects.filter(is_active=True, is_staff=True).exclude(pk=conta.pk).count()
        outros_super = User.objects.filter(is_active=True, is_superuser=True).exclude(pk=conta.pk).count()
        ultimo_login = (
            timezone.localtime(conta.last_login).strftime('%d/%m/%Y às %H:%M')
            if conta.last_login else 'nunca fez login'
        )

        self.stdout.write(f"Conta '{nome}':")
        self.stdout.write(f"  Ativa: {'sim' if conta.is_active else 'não'}")
        self.stdout.write(f"  Administradora (equipe): {'sim' if conta.is_staff else 'não'}")
        self.stdout.write(f"  Superusuária: {'sim' if conta.is_superuser else 'não'}")
        self.stdout.write(f"  Criada em: {timezone.localtime(conta.date_joined).strftime('%d/%m/%Y')}")
        self.stdout.write(f"  Último login: {ultimo_login}")
        self.stdout.write(
            f"  Senha: {'em uso (pode entrar)' if conta.has_usable_password() else 'BLOQUEADA (ninguém entra com ela)'}"
        )
        self.stdout.write(f"  Outros administradores ativos (equipe): {outros_staff}")
        self.stdout.write(f"  Outros superusuários ativos: {outros_super}")

        if not opcoes['bloquear']:
            if conta.has_usable_password():
                self.stdout.write(
                    '\nNada foi alterado. Se você NÃO usa esta conta, bloqueie-a rodando de novo com --bloquear. '
                    'Se usa, troque a senha: python manage.py changepassword ' + nome
                )
            return

        if not conta.has_usable_password():
            self.stdout.write('\nEsta conta já está bloqueada. Nada a fazer.')
            return

        so_ela_na_equipe = conta.is_staff and outros_staff == 0
        so_ela_superusuaria = conta.is_superuser and outros_super == 0

        if (so_ela_na_equipe or so_ela_superusuaria) and not opcoes['forcar']:
            raise CommandError(
                'Não bloqueei: esta parece ser a única conta de administração ativa, e você ficaria sem acesso. '
                'Use outra conta de administração, ou troque a senha com: '
                f'python manage.py changepassword {nome}. (Para bloquear mesmo assim, use --forcar.)'
            )

        conta.set_unusable_password()
        conta.save(update_fields=['password'])
        self.stdout.write(self.style.SUCCESS(
            f"\nPronto: a conta '{nome}' foi bloqueada. Para liberar de novo com uma senha nova: "
            f'python manage.py changepassword {nome}'
        ))
