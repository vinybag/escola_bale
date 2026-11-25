from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core import demo


class Command(BaseCommand):
    help = (
        'Apaga TUDO e recria a escola de demonstração. Só funciona com DEMO_MODE=1 '
        '(a instalação de demonstração) e exige --apagar-tudo.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--apagar-tudo', action='store_true', help='Confirma que o banco inteiro pode ser apagado.')

    def handle(self, *args, **opcoes):
        if not settings.DEMO_MODE:
            raise CommandError('DEMO_MODE não está ligado. Este comando apaga o banco inteiro e só roda na demonstração.')

        if not opcoes['apagar_tudo']:
            raise CommandError('Use --apagar-tudo para confirmar: o banco inteiro será apagado e recriado.')

        demo.apagar_tudo()
        resumo = demo.popular()
        self.stdout.write(self.style.SUCCESS(f'Demonstração pronta: {resumo}'))
