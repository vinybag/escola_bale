from datetime import date
from django.core.management.base import BaseCommand
from django.core.management import call_command


class Command(BaseCommand):
    help = 'Geração automática: gera mensalidades do próximo mês. Usado pelo cron do Railway.'

    def handle(self, *args, **options):
        hoje = date.today()

        if hoje.month == 12:
            proximo_ano = hoje.year + 1
            proximo_mes = 1
        else:
            proximo_ano = hoje.year
            proximo_mes = hoje.month + 1

        self.stdout.write(
            self.style.WARNING(
                f'Cron automático: gerando para {proximo_mes:02d}/{proximo_ano}'
            )
        )

        call_command('gera_mensalidades', ano=proximo_ano, mes=proximo_mes)