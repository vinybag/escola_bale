from calendar import monthrange
from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import IntegrityError

from pagamentos.models import Mensalidade
from usuarios.models import Aluna


class Command(BaseCommand):
    help = 'Gera mensalidades automáticas para o próximo mês das alunas ativas'

    def add_arguments(self, parser):
        parser.add_argument(
            '--ano',
            type=int,
            help='Ano de referência para geração'
        )
        parser.add_argument(
            '--mes',
            type=int,
            help='Mês de referência para geração'
        )

    def handle(self, *args, **options):
        hoje = date.today()

        ano = options.get('ano')
        mes = options.get('mes')

        if ano and mes:
            mes_referencia = date(ano, mes, 1)
        else:
            if hoje.month == 12:
                mes_referencia = date(hoje.year + 1, 1, 1)
            else:
                mes_referencia = date(hoje.year, hoje.month + 1, 1)

        self.stdout.write(
            self.style.WARNING(
                f'Gerando mensalidades para referência: {mes_referencia.strftime("%m/%Y")}'
            )
        )

        alunas = Aluna.objects.filter(
            ativa=True,
            gerar_mensalidade_automatica=True,
            valor_mensalidade__isnull=False,
            responsavel__isnull=False,
        ).select_related('responsavel')

        criadas = 0
        ignoradas = 0
        erros = 0

        for aluna in alunas:
            try:
                ja_existe = Mensalidade.objects.filter(
                    aluna=aluna,
                    mes_referencia=mes_referencia
                ).exists()

                if ja_existe:
                    ignoradas += 1
                    self.stdout.write(
                        f'Ignorada: {aluna.nome} já possui mensalidade de {mes_referencia.strftime("%m/%Y")}'
                    )
                    continue

                ultimo_dia_mes = monthrange(mes_referencia.year, mes_referencia.month)[1]
                dia_vencimento = min(aluna.dia_vencimento or 10, ultimo_dia_mes)

                data_vencimento = date(
                    mes_referencia.year,
                    mes_referencia.month,
                    dia_vencimento
                )

                mensalidade = Mensalidade.objects.create(
                    aluna=aluna,
                    responsavel=aluna.responsavel,
                    mes_referencia=mes_referencia,
                    valor=aluna.valor_mensalidade,
                    data_vencimento=data_vencimento,
                    status='pendente'
                )

                criadas += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Criada: {aluna.nome} - {mes_referencia.strftime("%m/%Y")} - vencimento {data_vencimento.strftime("%d/%m/%Y")}'
                    )
                )

            except IntegrityError:
                ignoradas += 1
                self.stdout.write(
                    self.style.WARNING(
                        f'Ignorada por duplicidade: {aluna.nome} - {mes_referencia.strftime("%m/%Y")}'
                    )
                )
            except Exception as e:
                erros += 1
                self.stdout.write(
                    self.style.ERROR(
                        f'Erro ao gerar mensalidade para {aluna.nome}: {str(e)}'
                    )
                )

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f'Mensalidades criadas: {criadas}'))
        self.stdout.write(self.style.WARNING(f'Mensalidades ignoradas: {ignoradas}'))
        self.stdout.write(self.style.ERROR(f'Erros: {erros}'))