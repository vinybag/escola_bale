from django.core.management.base import BaseCommand

from espetaculo.models import PedidoIngressoEvento, Assento


class Command(BaseCommand):
    help = (
        'Diagnóstico somente leitura: procura pedidos PAGOS, de eventos com '
        'assentos numerados, com assentos_ids preenchido, cujos ingressos '
        'gerados NÃO estão vinculados a nenhum assento específico — o que '
        'significaria que o assento nunca foi marcado como vendido de '
        'verdade (risco de venda duplicada do mesmo lugar).'
    )

    def handle(self, *args, **options):
        self.stdout.write('\n========== INGRESSOS PAGOS SEM ASSENTO VINCULADO ==========\n')

        pedidos = (
            PedidoIngressoEvento.objects
            .filter(status='pago')
            .exclude(assentos_ids=[])
            .select_related('evento')
        )

        self.stdout.write(
            f'Pedidos "pago" com assentos_ids preenchido: {pedidos.count()}'
        )

        total_problema = 0
        total_ok = 0

        for pedido in pedidos:
            ingressos = list(pedido.ingressos.all())
            sem_assento = [i for i in ingressos if i.assento_id is None]

            if sem_assento:
                total_problema += 1
                self.stdout.write(
                    f'\n  - Pedido #{pedido.id} ({pedido.nome_completo}, '
                    f'evento #{pedido.evento_id}) | assentos_ids no pedido: '
                    f'{pedido.assentos_ids} | '
                    f'{len(sem_assento)} de {len(ingressos)} ingresso(s) SEM assento vinculado.'
                )

                assentos_reais = Assento.objects.filter(id__in=pedido.assentos_ids)
                for a in assentos_reais:
                    self.stdout.write(
                        f'      -> Assento {a.identificador}: status atual = {a.status}'
                    )
            elif ingressos:
                total_ok += 1

        self.stdout.write(
            f'\nTotal de pedidos com problema (ingresso sem assento): {total_problema}'
        )
        self.stdout.write(
            f'Total de pedidos OK (assento vinculado corretamente): {total_ok}'
        )

        self.stdout.write('\n========== FIM DO DIAGNÓSTICO ==========')
