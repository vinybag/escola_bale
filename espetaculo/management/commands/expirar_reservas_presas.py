from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from espetaculo.models import Assento, PedidoIngressoEvento
from espetaculo.views import (
    liberar_gratuidade_reservada_do_pedido,
    liberar_reservas_expiradas_do_pedido,
)


def forcar_expiracao_pedido(pedido):
    """
    Expira um pedido "pendente" à força, independente do status atual
    dos assentos vinculados a ele.

    Necessário para pedidos cujo assento já foi liberado manualmente
    por fora (ex.: clicando para deixá-lo verde de novo no mapa interno
    do admin) — nesse caso o assento não está mais 'reservado_temporario'
    e `liberar_reservas_expiradas_do_pedido` não encontra nada para
    liberar, deixando o pedido (e a gratuidade) órfãos para sempre.
    """
    assentos_ainda_presos = Assento.objects.filter(
        mapa__evento=pedido.evento,
        status='reservado_temporario',
        reservado_por_sessao=f'pedido:{pedido.id}',
    )

    for assento in assentos_ainda_presos:
        assento.liberar()

    pedido.status = 'expirado'
    liberar_gratuidade_reservada_do_pedido(pedido)

    pedido.save(
        update_fields=['status', 'atualizado_em'],
    )


class Command(BaseCommand):
    help = (
        'Expira pedidos "pendente" antigos, liberando o(s) assento(s) '
        '(se ainda estiverem presos) E a gratuidade reservada juntos — '
        'exatamente como já aconteceria sozinho se alguém tivesse '
        'visitado a página do mapa nesse meio tempo. Útil quando as '
        'vendas estão fechadas (venda_aberta=False), porque nesse caso '
        'ninguém mais visita a página e a limpeza automática para de '
        'rodar.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Só mostra o que seria feito, sem alterar nada no banco.',
        )
        parser.add_argument(
            '--forcar-mais-antigos-que',
            type=int,
            default=None,
            metavar='MINUTOS',
            help=(
                'Além dos pedidos com assento preso além do prazo, '
                'força a expiração de QUALQUER pedido "pendente" criado '
                'há mais de MINUTOS minutos — mesmo que o assento já '
                'tenha sido liberado manualmente por fora (ex.: pelo '
                'botão de liberar assento no mapa interno do admin). '
                'Use um valor generoso (ex.: 60) para não arriscar '
                'mexer em algo que ainda esteja em andamento de verdade.'
            ),
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        forcar_minutos = options['forcar_mais_antigos_que']

        pendentes = PedidoIngressoEvento.objects.filter(
            status='pendente',
        ).select_related('evento')

        self.stdout.write(f'Pedidos "pendente" encontrados: {pendentes.count()}')

        total_expirados = 0
        total_forcados = 0

        limite_forcar = (
            timezone.now() - timezone.timedelta(minutes=forcar_minutos)
            if forcar_minutos is not None
            else None
        )

        for pedido in pendentes:
            assentos_presos_qs = Assento.objects.filter(
                mapa__evento=pedido.evento,
                status='reservado_temporario',
                reservado_por_sessao=f'pedido:{pedido.id}',
            )

            assentos_presos_expirados = [
                a for a in assentos_presos_qs if a.esta_reservado_expirado
            ]

            elegivel_por_assento = bool(assentos_presos_expirados)

            elegivel_por_idade = (
                limite_forcar is not None
                and pedido.criado_em < limite_forcar
                and not assentos_presos_qs.exists()
                # (se ainda tem assento preso mas NÃO expirado, não força:
                # pode ser uma tentativa genuína ainda dentro dos 15 min)
            )

            if dry_run:
                if elegivel_por_assento:
                    self.stdout.write(
                        f'  [simulação] Pedido #{pedido.id} ({pedido.nome_completo}, '
                        f'evento #{pedido.evento_id}) SERIA expirado — '
                        f'{len(assentos_presos_expirados)} assento(s) presos além do prazo.'
                    )
                    total_expirados += 1
                elif elegivel_por_idade:
                    self.stdout.write(
                        f'  [simulação] Pedido #{pedido.id} ({pedido.nome_completo}, '
                        f'evento #{pedido.evento_id}) SERIA FORÇADO — criado em '
                        f'{pedido.criado_em}, sem assento preso (provavelmente já '
                        f'liberado manualmente por fora), mas a gratuidade continua presa.'
                    )
                    total_forcados += 1
                continue

            if elegivel_por_assento:
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
            elif elegivel_por_idade:
                with transaction.atomic():
                    forcar_expiracao_pedido(pedido)

                total_forcados += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f'  Pedido #{pedido.id} ({pedido.nome_completo}, '
                        f'evento #{pedido.evento_id}) FORÇADO: gratuidade liberada '
                        f'(assento já não estava mais preso).'
                    )
                )

        if dry_run:
            self.stdout.write(
                f'\n[simulação] Expiraria por assento preso: {total_expirados}. '
                f'Forçaria por idade: {total_forcados}. '
                'Rode sem --dry-run para aplicar de verdade.'
            )
        else:
            self.stdout.write(
                f'\nExpirado por assento preso: {total_expirados}. '
                f'Forçado por idade: {total_forcados}.'
            )
