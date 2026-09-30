from django.core.management.base import BaseCommand

from espetaculo.models import IngressoGratuitoAluna


class Command(BaseCommand):
    help = (
        'Diagnóstico somente leitura: encontra gratuidades (IngressoGratuitoAluna) '
        'já marcadas como usadas, mas cujo pedido não tem nenhum ingresso gerado '
        '(vítimas do bug corrigido pelo patch fix-gratuidade-atomica).'
    )

    def handle(self, *args, **options):
        self.stdout.write('\n========== GRATUIDADES ÓRFÃS (sem ingresso gerado) ==========\n')

        gratuidades = (
            IngressoGratuitoAluna.objects
            .select_related('aluna', 'evento', 'pedido')
            .order_by('evento_id', 'criado_em')
        )

        total_gratuidades = gratuidades.count()
        orfas = []

        for g in gratuidades:
            qtd_ingressos = g.pedido.ingressos.count()

            if qtd_ingressos == 0:
                orfas.append(g)

        self.stdout.write(f'Total de gratuidades registradas no sistema: {total_gratuidades}')
        self.stdout.write(f'Total de gratuidades ÓRFÃS (sem nenhum ingresso gerado): {len(orfas)}\n')

        if not orfas:
            self.stdout.write('Nenhuma gratuidade órfã encontrada. Nada a corrigir.')
        else:
            for g in orfas:
                self.stdout.write(
                    f'  - IngressoGratuitoAluna #{g.id} | aluna: {g.aluna.nome} '
                    f'(aluna #{g.aluna.id}) | evento: {g.evento.titulo} '
                    f'(evento #{g.evento.id}) | pedido #{g.pedido.id} '
                    f'(status do pedido: {g.pedido.status}) | '
                    f'criado em: {g.criado_em}'
                )

            self.stdout.write(
                '\nPara CADA linha acima, a aluna teve a gratuidade marcada como '
                '"usada" para aquele evento, mas nenhum ingresso chegou a ser '
                'gerado (provável vítima do bug). Para corrigir cada caso:\n'
                '  1. Confirme com a família se ela realmente não tem o ingresso.\n'
                '  2. Rode (trocando o número pelo id do IngressoGratuitoAluna '
                'listado acima):\n'
                '     python manage.py liberar_gratuidade_orfa <id>\n'
                '  3. Gere o ingresso certinho pelo seu admin (tela de gerar '
                'ingresso manual, vinculando a esta mesma aluna).'
            )

        self.stdout.write('\n========== FIM DO DIAGNÓSTICO ==========')
