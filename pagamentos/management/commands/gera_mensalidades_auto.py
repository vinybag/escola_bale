from datetime import date
import calendar

from django.core.management.base import BaseCommand
from django.db import IntegrityError

from usuarios.models import Aluna
from pagamentos.models import Mensalidade


class Command(BaseCommand):
    help = "Gera mensalidades do mês atual apenas para alunas elegíveis que ainda não possuem mensalidade."

    def handle(self, *args, **options):
        hoje = date.today()
        mes_referencia = date(hoje.year, hoje.month, 1)

        self.stdout.write(
            self.style.WARNING(
                f"Verificando mensalidades automáticas para {mes_referencia.strftime('%m/%Y')}..."
            )
        )

        alunas = Aluna.objects.filter(
            ativa=True,
            gerar_mensalidade_automatica=True,
        ).select_related("responsavel").order_by("nome")

        geradas = 0
        puladas_sem_responsavel = 0
        puladas_sem_valor = 0
        puladas_mes_matricula = 0
        ja_existiam = 0

        ultimo_dia_mes = calendar.monthrange(hoje.year, hoje.month)[1]

        for aluna in alunas:
            if not aluna.responsavel:
                self.stdout.write(
                    self.style.WARNING(
                        f"[PULADA] {aluna.nome}: sem responsável vinculado."
                    )
                )
                puladas_sem_responsavel += 1
                continue

            if aluna.valor_mensalidade is None:
                self.stdout.write(
                    self.style.WARNING(
                        f"[PULADA] {aluna.nome}: sem valor_mensalidade definido."
                    )
                )
                puladas_sem_valor += 1
                continue

            if (
                aluna.data_matricula
                and aluna.data_matricula.year == hoje.year
                and aluna.data_matricula.month == hoje.month
            ):
                self.stdout.write(
                    f"[PULADA] {aluna.nome}: matrícula no mês atual ({aluna.data_matricula.strftime('%d/%m/%Y')})."
                )
                puladas_mes_matricula += 1
                continue

            existe = Mensalidade.objects.filter(
                aluna=aluna,
                mes_referencia=mes_referencia
            ).exists()

            if existe:
                self.stdout.write(
                    f"[OK] {aluna.nome}: já possui mensalidade de {mes_referencia.strftime('%m/%Y')}."
                )
                ja_existiam += 1
                continue

            dia_vencimento = min(aluna.dia_vencimento or 10, ultimo_dia_mes)
            data_vencimento = date(hoje.year, hoje.month, dia_vencimento)

            try:
                Mensalidade.objects.create(
                    aluna=aluna,
                    responsavel=aluna.responsavel,
                    mes_referencia=mes_referencia,
                    valor=aluna.valor_mensalidade,
                    data_vencimento=data_vencimento,
                    status="pendente",
                )
                self.stdout.write(
                    self.style.SUCCESS(
                        f"[GERADA] {aluna.nome}: mensalidade criada com vencimento em {data_vencimento.strftime('%d/%m/%Y')}."
                    )
                )
                geradas += 1
            except IntegrityError:
                self.stdout.write(
                    self.style.WARNING(
                        f"[IGNORADA] {aluna.nome}: mensalidade já existia."
                    )
                )
                ja_existiam += 1

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Resumo da execução:"))
        self.stdout.write(f"- Mês de referência: {mes_referencia.strftime('%m/%Y')}")
        self.stdout.write(f"- Mensalidades geradas: {geradas}")
        self.stdout.write(f"- Já existiam: {ja_existiam}")
        self.stdout.write(f"- Puladas sem responsável: {puladas_sem_responsavel}")
        self.stdout.write(f"- Puladas sem valor: {puladas_sem_valor}")
        self.stdout.write(f"- Puladas por matrícula no mês atual: {puladas_mes_matricula}")