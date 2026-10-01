from django.core.management.base import BaseCommand
from django.db.models import Q

from espetaculo.models import PedidoIngressoEvento, IngressoGratuitoAluna


class Command(BaseCommand):
    help = (
        'Corrige o e-mail de pedidos PAGOS sem e-mail cadastrado, usando '
        'o e-mail da responsável (ou da própria aluna, se ela tiver login '
        'próprio) — só funciona para pedidos de cortesia vinculados a uma '
        'aluna (via IngressoGratuitoAluna), que são os únicos onde dá '
        'para saber com segurança de quem é o e-mail. Sem isso, esses '
        'ingressos ficam invisíveis na página "Meus Ingressos" de '
        'qualquer pessoa.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Só mostra o que seria corrigido, sem alterar nada no banco.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        pedidos_sem_email = (
            PedidoIngressoEvento.objects
            .filter(status='pago')
            .filter(Q(email__isnull=True) | Q(email=''))
        )

        self.stdout.write(
            f'Pedidos pagos sem e-mail encontrados: {pedidos_sem_email.count()}'
        )

        total_corrigidos = 0
        total_sem_solucao = 0

        for pedido in pedidos_sem_email:
            gratuidade = (
                IngressoGratuitoAluna.objects
                .filter(pedido=pedido)
                .select_related('aluna', 'aluna__responsavel', 'aluna__usuario')
                .first()
            )

            if not gratuidade:
                total_sem_solucao += 1
                self.stdout.write(
                    f'  [sem solução] Pedido #{pedido.id} ({pedido.nome_completo}) '
                    'não tem aluna vinculada — não há como descobrir o e-mail '
                    'automaticamente.'
                )
                continue

            aluna = gratuidade.aluna
            email_encontrado = None

            if aluna.responsavel_id and aluna.responsavel.email:
                email_encontrado = aluna.responsavel.email
            elif aluna.usuario_id and aluna.usuario.email:
                email_encontrado = aluna.usuario.email

            if not email_encontrado:
                total_sem_solucao += 1
                self.stdout.write(
                    f'  [sem solução] Pedido #{pedido.id} ({pedido.nome_completo}) '
                    f'é cortesia de "{aluna.nome}", mas nem a responsável nem a '
                    'aluna têm e-mail cadastrado.'
                )
                continue

            if dry_run:
                self.stdout.write(
                    f'  [simulação] Pedido #{pedido.id} ({pedido.nome_completo}) '
                    f'receberia o e-mail: {email_encontrado}'
                )
            else:
                pedido.email = email_encontrado
                pedido.save(update_fields=['email', 'atualizado_em'])
                self.stdout.write(
                    self.style.SUCCESS(
                        f'  Pedido #{pedido.id} ({pedido.nome_completo}) '
                        f'corrigido com o e-mail: {email_encontrado}'
                    )
                )

            total_corrigidos += 1

        if dry_run:
            self.stdout.write(
                f'\n[simulação] Corrigiria: {total_corrigidos}. '
                f'Sem solução automática: {total_sem_solucao}. '
                'Rode sem --dry-run para aplicar de verdade.'
            )
        else:
            self.stdout.write(
                f'\nCorrigidos: {total_corrigidos}. '
                f'Sem solução automática: {total_sem_solucao}.'
            )
