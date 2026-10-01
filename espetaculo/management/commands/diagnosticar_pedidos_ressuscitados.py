from django.core.management.base import BaseCommand

from espetaculo.models import Assento, PedidoIngressoEvento


class Command(BaseCommand):
    help = (
        'Diagnóstico somente leitura: procura pedidos que JÁ geraram '
        'ingresso (pagamento confirmado) mas cujo status não é mais '
        '"pago" sozinho de forma consistente, ou cujo assento pode ter '
        'sido vendido duas vezes (double-booking) por causa de um '
        'pagamento PIX atrasado chegando depois do pedido já ter sido '
        'expirado manualmente.'
    )

    def handle(self, *args, **options):
        self.stdout.write('\n========== PEDIDOS "EXPIRADO" QUE JÁ TÊM INGRESSO GERADO ==========\n')

        suspeitos = (
            PedidoIngressoEvento.objects
            .filter(status='expirado')
            .select_related('evento')
        )

        total_suspeitos = 0

        for pedido in suspeitos:
            qtd_ingressos = pedido.ingressos.count()

            if qtd_ingressos > 0:
                total_suspeitos += 1
                self.stdout.write(
                    f'  - Pedido #{pedido.id} ({pedido.nome_completo}, '
                    f'evento #{pedido.evento_id}) | status: {pedido.status} | '
                    f'TEM {qtd_ingressos} ingresso(s) gerado(s) mesmo expirado! '
                    f'(provável pagamento atrasado "ressuscitando" o pedido)'
                )

                for ingresso in pedido.ingressos.all():
                    self.stdout.write(
                        f'      -> Ingresso #{ingresso.id} | '
                        f'assento: {ingresso.assento} | '
                        f'status do ingresso: {ingresso.status}'
                    )

        self.stdout.write(f'\nTotal de pedidos expirados com ingresso gerado: {total_suspeitos}')

        self.stdout.write(
            '\n========== POSSÍVEIS ASSENTOS VENDIDOS DUAS VEZES ==========\n'
        )

        total_double_booking = 0

        todos_assentos_vendidos_ou_ocupados = Assento.objects.exclude(
            status='disponivel',
        ).select_related('mapa__evento')

        for assento in todos_assentos_vendidos_ou_ocupados:
            ingressos_vinculados = assento.ingressos.filter(
                status__in=['ativo', 'usado'],
            ).select_related('pedido')

            if ingressos_vinculados.count() > 1:
                total_double_booking += 1
                self.stdout.write(
                    f'  - Assento {assento.identificador} '
                    f'(evento #{assento.mapa.evento_id}) tem '
                    f'{ingressos_vinculados.count()} ingressos ATIVOS vinculados!'
                )
                for ing in ingressos_vinculados:
                    self.stdout.write(
                        f'      -> Ingresso #{ing.id} | pedido #{ing.pedido_id} '
                        f'({ing.pedido.nome_completo}) | status pedido: {ing.pedido.status}'
                    )

        if total_double_booking == 0:
            self.stdout.write('Nenhum assento com mais de um ingresso ativo encontrado. Boa notícia.')

        self.stdout.write('\n========== FIM DO DIAGNÓSTICO ==========')
