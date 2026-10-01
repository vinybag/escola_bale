from django.core.management.base import BaseCommand
from django.db import transaction

from espetaculo.models import PedidoIngressoEvento
from espetaculo.views import liberar_reservas_expiradas_do_pedido


class Command(BaseCommand):
    help = (
        'Expira pedidos "pendente" cuja reserva de assento já passou do '
        'prazo (15 min), liberando o(s) assento(s) E a gratuidade '
        'reservada juntos — exatamente como já aconteceria sozinho se '
        'alguém tivesse visitado a página do mapa nesse meio tempo. '
        'Útil quando as vendas estão fechadas (venda_aberta=False), '
        'porque nesse caso ninguém mais visita a página e a limpeza '
        'automática para de rodar.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Só mostra o que seria feito, sem alterar nada no banco.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        pendentes = PedidoIngressoEvento.objects.filter(
            status='pendente',
        ).select_related('evento')

        self.stdout.write(f'Pedidos "pendente" encontrados: {pendentes.count()}')

        total_expirados = 0

        for pedido in pendentes:
            if dry_run:
                assentos_presos = [
                    a for a in pedido.evento.mapa_assentos.assentos.filter(
                        status='reservado_temporario',
                        reservado_por_sessao=f'pedido:{pedido.id}',
                    )
                    if a.esta_reservado_expirado
                ] if hasattr(pedido.evento, 'mapa_assentos') else []

                if assentos_presos:
                    self.stdout.write(
                        f'  [simulação] Pedido #{pedido.id} ({pedido.nome_completo}, '
                        f'evento #{pedido.evento_id}) SERIA expirado — '
                        f'{len(assentos_presos)} assento(s) presos além do prazo.'
                    )
                    total_expirados += 1
                continue

            with transaction.atomic():
                expirou = liberar_reservas_expiradas_do_pedido(pedido)

            if expirou:
                total_expirados += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f'  Pedido #{pedido.id} ({pedido.nome_completo}, '
                        f'evento #{pedido.evento_id}) expirado: assento(s) e '
                        f'gratuidade liberados.'
                    )
                )

        if dry_run:
            self.stdout.write(
                f'\n[simulação] Total que seria expirado agora: {total_expirados}. '
                'Rode sem --dry-run para aplicar de verdade.'
            )
        else:
            self.stdout.write(f'\nTotal expirado agora: {total_expirados}.')
