from django.core.management.base import BaseCommand, CommandError

from espetaculo.models import IngressoGratuitoAluna


class Command(BaseCommand):
    help = (
        'Libera (apaga) um registro de IngressoGratuitoAluna órfão — '
        'identificado pelo comando diagnosticar_gratuidades_orfas — '
        'devolvendo a gratuidade daquela aluna para aquele evento. '
        'Por segurança, RECUSA apagar se o pedido já tiver algum ingresso '
        'gerado (ou seja, só mexe em casos realmente órfãos).'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            'ingresso_gratuito_aluna_id',
            type=int,
            help='O id do IngressoGratuitoAluna a liberar (mostrado pelo diagnóstico).',
        )

    def handle(self, *args, **options):
        pk = options['ingresso_gratuito_aluna_id']

        try:
            registro = (
                IngressoGratuitoAluna.objects
                .select_related('aluna', 'evento', 'pedido')
                .get(pk=pk)
            )
        except IngressoGratuitoAluna.DoesNotExist:
            raise CommandError(
                f'Não existe nenhum IngressoGratuitoAluna com id {pk}. '
                'Rode "python manage.py diagnosticar_gratuidades_orfas" '
                'para ver os ids corretos.'
            )

        qtd_ingressos = registro.pedido.ingressos.count()

        if qtd_ingressos > 0:
            raise CommandError(
                f'RECUSADO: o pedido #{registro.pedido.id} vinculado a este '
                f'registro já tem {qtd_ingressos} ingresso(s) gerado(s). '
                'Isso não parece um caso órfão — nada foi apagado, por '
                'segurança. Confira manualmente antes de prosseguir.'
            )

        self.stdout.write(
            f'Liberando gratuidade: aluna "{registro.aluna.nome}" '
            f'(aluna #{registro.aluna.id}) | evento "{registro.evento.titulo}" '
            f'(evento #{registro.evento.id}) | pedido #{registro.pedido.id} '
            f'(sem nenhum ingresso gerado, confirmado).'
        )

        registro.delete()

        self.stdout.write(
            self.style.SUCCESS(
                'Pronto: a gratuidade dessa aluna para esse evento está '
                'disponível de novo. Agora você já pode gerar o ingresso '
                'certinho pelo admin, vinculando a esta mesma aluna.'
            )
        )
