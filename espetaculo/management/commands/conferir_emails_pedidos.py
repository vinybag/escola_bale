from django.core.management.base import BaseCommand
from django.db.models import Q

from espetaculo.models import PedidoIngressoEvento


class Command(BaseCommand):
    help = (
        'Diagnóstico somente leitura: lista TODOS os pedidos pagos, '
        'mostrando o e-mail salvo e, quando há uma aluna vinculada, se '
        'esse e-mail bate com o e-mail da responsável dela (ou da '
        'própria aluna, se tiver login). Ajuda a achar pedidos vinculados '
        'que ficaram com um e-mail errado (preenchido antes do vínculo, '
        'por isso não foi sobrescrito automaticamente).'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--evento',
            type=int,
            default=None,
            help='Filtra só os pedidos de um evento específico (id).',
        )

    def handle(self, *args, **options):
        evento_id = options['evento']

        pedidos = (
            PedidoIngressoEvento.objects
            .filter(status='pago')
            .select_related('evento', 'aluna_vinculada', 'aluna_vinculada__responsavel', 'aluna_vinculada__usuario')
            .order_by('evento_id', '-criado_em')
        )

        if evento_id:
            pedidos = pedidos.filter(evento_id=evento_id)

        self.stdout.write(f'\nTotal de pedidos pagos analisados: {pedidos.count()}\n')

        sem_email = 0
        email_divergente = 0
        ok = 0

        for pedido in pedidos:
            if not pedido.email:
                sem_email += 1
                self.stdout.write(
                    f'  ❌ SEM E-MAIL | Pedido #{pedido.id} ({pedido.nome_completo}) | '
                    f'evento: {pedido.evento.titulo} | '
                    f'aluna vinculada: {pedido.aluna_vinculada.nome if pedido.aluna_vinculada else "(nenhuma)"}'
                )
                continue

            if pedido.aluna_vinculada:
                aluna = pedido.aluna_vinculada
                email_esperado = None

                if aluna.responsavel_id and aluna.responsavel.email:
                    email_esperado = aluna.responsavel.email
                elif aluna.usuario_id and aluna.usuario.email:
                    email_esperado = aluna.usuario.email

                if email_esperado and email_esperado.strip().lower() != pedido.email.strip().lower():
                    email_divergente += 1
                    self.stdout.write(
                        f'  ⚠️  E-MAIL DIVERGENTE | Pedido #{pedido.id} ({pedido.nome_completo}) | '
                        f'evento: {pedido.evento.titulo} | '
                        f'aluna: {aluna.nome} | '
                        f'e-mail salvo no pedido: {pedido.email} | '
                        f'e-mail da responsável: {email_esperado}'
                    )
                    continue

            ok += 1

        self.stdout.write(
            f'\nResumo: {ok} OK | {sem_email} sem e-mail | '
            f'{email_divergente} com e-mail divergente da aluna vinculada.'
        )

        if email_divergente:
            self.stdout.write(
                '\nPara os "E-MAIL DIVERGENTE", o vínculo com a aluna está certo, '
                'mas o e-mail salvo no pedido é diferente do e-mail da '
                'responsável — provavelmente foi preenchido antes do vínculo '
                'ser feito. Me avise os números dos pedidos que eu te ajudo a '
                'corrigir.'
            )
