from django.core.management.base import BaseCommand
from django.db import models

from espetaculo.models import (
    Espetaculo,
    ParticipacaoEspetaculo,
    IngressoGratuitoAluna,
    Assento,
    IngressoEvento,
    PedidoIngressoEvento,
)
from usuarios.models import Aluna


class Command(BaseCommand):
    help = 'Diagnóstico somente leitura: gratuidade e assentos vendidos manualmente.'

    def handle(self, *args, **options):
        self.stdout.write('\n========== PARTE 0: TODOS OS ESPETÁCULOS ==========')

        todos = Espetaculo.objects.all().order_by('data_apresentacao')
        for ev in todos:
            self.stdout.write(
                f'  - Evento #{ev.id}: {ev.titulo} | {ev.data_apresentacao} | '
                f'venda_aberta={ev.venda_aberta} | '
                f'assentos_numerados={ev.venda_com_assentos_numerados}'
            )

        self.stdout.write('\n========== PARTE 1: GRATUIDADE ==========')

        # CORREÇÃO: não filtra mais por venda_aberta=True (a usuária pode
        # fechar as vendas manualmente por decisão própria, o que não tem
        # nada a ver com a integridade dos dados de gratuidade). Em vez
        # disso, identifica os dias do MESMO espetáculo pelo título.
        titulo_mais_comum = (
            Espetaculo.objects
            .values('titulo')
            .annotate(qtd=models.Count('id'))
            .order_by('-qtd')
            .first()
        )

        if titulo_mais_comum and titulo_mais_comum['qtd'] > 1:
            eventos = Espetaculo.objects.filter(
                titulo=titulo_mais_comum['titulo']
            ).order_by('data_apresentacao')
        else:
            eventos = Espetaculo.objects.all().order_by('data_apresentacao')

        self.stdout.write(
            f'Eventos analisados (dias do espetáculo "{eventos.first().titulo if eventos else "-"}"): '
            f'{eventos.count()}'
        )

        for evento in eventos:
            self.stdout.write(
                f'\n--- Evento #{evento.id} ({evento.titulo} - {evento.data_apresentacao}) ---'
            )

            participacoes = ParticipacaoEspetaculo.objects.filter(
                espetaculo=evento
            ).select_related('aluna')
            self.stdout.write(f'Total de participações cadastradas: {participacoes.count()}')

            nao_vai_dancar = participacoes.filter(vai_dancar=False)
            self.stdout.write(
                f'Participações com vai_dancar=False (NÃO contam para gratuidade): '
                f'{nao_vai_dancar.count()}'
            )
            for p in nao_vai_dancar:
                self.stdout.write(f'    - {p.aluna.nome} (aluna #{p.aluna.id})')

            alunas_inativas = participacoes.filter(aluna__ativa=False)
            self.stdout.write(
                f'Participações de alunas INATIVAS (não contam para gratuidade): '
                f'{alunas_inativas.count()}'
            )
            for p in alunas_inativas:
                self.stdout.write(f'    - {p.aluna.nome} (aluna #{p.aluna.id})')

            sem_vinculo = participacoes.filter(
                aluna__responsavel__isnull=True,
                aluna__usuario__isnull=True,
            )
            self.stdout.write(
                f'Alunas SEM responsável E SEM login próprio vinculado '
                f'(gratuidade impossível de usar): {sem_vinculo.count()}'
            )
            for p in sem_vinculo:
                self.stdout.write(f'    - {p.aluna.nome} (aluna #{p.aluna.id})')

            ja_usaram = IngressoGratuitoAluna.objects.filter(evento=evento).count()
            self.stdout.write(
                f'Gratuidades já emitidas para este evento (site + manual): {ja_usaram}'
            )

        if eventos.count() == 2:
            ev1, ev2 = eventos[0], eventos[1]

            alunas_ev1 = set(
                ParticipacaoEspetaculo.objects.filter(espetaculo=ev1, vai_dancar=True)
                .values_list('aluna_id', flat=True)
            )
            alunas_ev2 = set(
                ParticipacaoEspetaculo.objects.filter(espetaculo=ev2, vai_dancar=True)
                .values_list('aluna_id', flat=True)
            )

            so_no_ev1 = alunas_ev1 - alunas_ev2
            so_no_ev2 = alunas_ev2 - alunas_ev1

            self.stdout.write(
                f'\n--- CRUZAMENTO ENTRE OS DOIS DIAS (evento #{ev1.id} vs #{ev2.id}) ---'
            )
            self.stdout.write(
                f"Alunas SÓ no evento #{ev1.id} ({ev1.titulo}), "
                f"faltando no #{ev2.id} ({ev2.titulo}): {len(so_no_ev1)}"
            )
            for aluna_id in so_no_ev1:
                a = Aluna.objects.get(pk=aluna_id)
                self.stdout.write(f"    - {a.nome} (aluna #{a.id}) -> SEM gratuidade em '{ev2.titulo}'")

            self.stdout.write(
                f"Alunas SÓ no evento #{ev2.id} ({ev2.titulo}), "
                f"faltando no #{ev1.id} ({ev1.titulo}): {len(so_no_ev2)}"
            )
            for aluna_id in so_no_ev2:
                a = Aluna.objects.get(pk=aluna_id)
                self.stdout.write(f"    - {a.nome} (aluna #{a.id}) -> SEM gratuidade em '{ev1.titulo}'")
        else:
            self.stdout.write(
                '\n(Aviso: número de eventos com venda aberta diferente de 2 — '
                'o cruzamento automático entre os dois dias foi pulado. '
                'Veja a PARTE 0 acima para checar o campo venda_aberta de cada evento.)'
            )

        self.stdout.write('\n========== PARTE 2: ASSENTOS VENDIDOS PELO ADMIN ==========')

        pedidos_manuais = PedidoIngressoEvento.objects.filter(
            external_reference__startswith='ingresso_manual_',
        ).order_by('-criado_em')

        self.stdout.write(f'Total de pedidos gerados manualmente pelo admin: {pedidos_manuais.count()}')

        for pedido in pedidos_manuais[:30]:
            self.stdout.write(
                f'\nPedido #{pedido.id} | {pedido.nome_completo} | '
                f'evento: {pedido.evento} | status: {pedido.status}'
            )
            self.stdout.write(f'  assentos_ids salvos no pedido: {pedido.assentos_ids}')

            if pedido.assentos_ids:
                assentos_reais = Assento.objects.filter(id__in=pedido.assentos_ids)
                for a in assentos_reais:
                    self.stdout.write(f'    -> Assento {a.identificador} | status atual no banco: {a.status}')

            ingressos = pedido.ingressos.all()
            self.stdout.write(f'  ingressos gerados para este pedido: {ingressos.count()}')
            for i in ingressos:
                self.stdout.write(f'    -> Ingresso #{i.id} | assento vinculado: {i.assento} | status ingresso: {i.status}')

        self.stdout.write('\n========== FIM DO DIAGNÓSTICO ==========')
