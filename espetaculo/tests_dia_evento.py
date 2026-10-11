from datetime import datetime, timezone as dt_timezone
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from espetaculo.models import (
    Assento,
    Espetaculo,
    MapaAssentos,
    PedidoIngressoEvento,
)


# O storage de estáticos de produção (manifesto) exige `collectstatic`
# antes de renderizar templates com {% static %}; nos testes usamos o
# storage simples só para as páginas poderem ser renderizadas.
STORAGES_TESTE = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
    },
}


@override_settings(STORAGES=STORAGES_TESTE)
class DiaDoEventoNosMapasTests(TestCase):
    """
    Há mais de um dia de apresentação, e as pessoas se confundiam sobre
    de qual dia estavam comprando. A data e o horário do evento precisam
    aparecer nas telas em que elas escolhem os assentos e pagam.
    """

    def setUp(self):
        # 14/11/2026 22:30 UTC == Sábado, 14/11/2026 19:30 em São Paulo.
        self.evento = Espetaculo.objects.create(
            titulo='Quebra-Nozes',
            descricao='x',
            tipo='evento',
            data_apresentacao=datetime(
                2026, 11, 14, 22, 30, tzinfo=dt_timezone.utc
            ),
            local='Teatro',
            endereco='Rua A',
            preco_ingresso=Decimal('50.00'),
            venda_aberta=True,
            venda_com_assentos_numerados=True,
        )
        mapa = MapaAssentos.objects.create(evento=self.evento)
        Assento.objects.create(
            mapa=mapa, identificador='A1', fileira='A', numero=1,
            x_pct=Decimal('1'), y_pct=Decimal('1'),
        )

    def _sessao_de_compra(self):
        sessao = self.client.session
        pk = self.evento.pk
        sessao[f'compra_evento_{pk}_nome_completo'] = 'Maria Silva'
        sessao[f'compra_evento_{pk}_whatsapp'] = '11912345678'
        sessao[f'compra_evento_{pk}_valor_unitario'] = '50.00'
        sessao.save()

    def test_mapa_publico_mostra_dia_da_semana_data_e_horario(self):
        self._sessao_de_compra()

        resposta = self.client.get(
            reverse('espetaculo:mapa_assentos_publico', args=[self.evento.pk])
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'class="mapa-publico-dia"')
        self.assertContains(resposta, 'Sábado, 14/11')
        self.assertContains(resposta, '19:30')

    def test_horario_usa_fuso_de_sao_paulo_e_nao_utc(self):
        # 15/11 01:00 UTC ainda é sábado 14/11, 22:00 em São Paulo.
        Espetaculo.objects.filter(pk=self.evento.pk).update(
            data_apresentacao=datetime(
                2026, 11, 15, 1, 0, tzinfo=dt_timezone.utc
            )
        )
        self._sessao_de_compra()

        resposta = self.client.get(
            reverse('espetaculo:mapa_assentos_publico', args=[self.evento.pk])
        )

        self.assertContains(resposta, 'Sábado, 14/11')
        self.assertContains(resposta, '22:00')
        self.assertNotContains(resposta, 'Domingo, 15/11')

    def test_dois_dias_mostram_cada_um_o_seu_dia(self):
        domingo = Espetaculo.objects.create(
            titulo='Quebra-Nozes',
            descricao='x',
            tipo='evento',
            data_apresentacao=datetime(
                2026, 11, 15, 17, 0, tzinfo=dt_timezone.utc
            ),
            local='Teatro',
            endereco='Rua A',
            preco_ingresso=Decimal('50.00'),
            venda_aberta=True,
            venda_com_assentos_numerados=True,
        )
        mapa = MapaAssentos.objects.create(evento=domingo)
        Assento.objects.create(
            mapa=mapa, identificador='A1', fileira='A', numero=1,
            x_pct=Decimal('1'), y_pct=Decimal('1'),
        )
        sessao = self.client.session
        sessao[f'compra_evento_{domingo.pk}_nome_completo'] = 'Maria'
        sessao[f'compra_evento_{domingo.pk}_whatsapp'] = '11912345678'
        sessao.save()

        resposta = self.client.get(
            reverse('espetaculo:mapa_assentos_publico', args=[domingo.pk])
        )

        self.assertContains(resposta, 'Domingo, 15/11')
        self.assertContains(resposta, '14:00')
        self.assertNotContains(resposta, 'Sábado, 14/11')

    def test_formulario_antes_do_mapa_mostra_o_dia(self):
        resposta = self.client.get(
            reverse('espetaculo:comprar_ingresso', args=[self.evento.pk])
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertTemplateUsed(
            resposta, 'espetaculo/comprar_ingresso_assentos.html'
        )
        self.assertContains(resposta, 'Sábado, 14/11/2026 às 19:30')

    def test_tela_do_pix_mostra_o_dia(self):
        pedido = PedidoIngressoEvento.objects.create(
            evento=self.evento,
            nome_completo='Maria Silva',
            whatsapp='11912345678',
            quantidade=1,
            valor_unitario=Decimal('50.00'),
            valor_total=Decimal('50.00'),
            status='pendente',
        )

        html = render_to_string(
            'espetaculo/pix_ingresso.html',
            {
                'pedido': pedido,
                'evento': self.evento,
                'payment_id': 'pay_123',
                'pix_data': {'payload': '000201', 'encoded': ''},
                'valor': pedido.valor_total,
                'reserva_expira_em': timezone.now().isoformat(),
            },
        )

        self.assertIn('Sábado, 14/11/2026 às 19:30', html)


@override_settings(STORAGES=STORAGES_TESTE)
class DiaDoEventoNosMapasDoAdminTests(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user(
            'staff', 'staff@example.com', 'senha123', is_staff=True
        )
        self.evento = Espetaculo.objects.create(
            titulo='Quebra-Nozes',
            descricao='x',
            tipo='evento',
            data_apresentacao=datetime(
                2026, 11, 14, 22, 30, tzinfo=dt_timezone.utc
            ),
            local='Teatro',
            endereco='Rua A',
            venda_com_assentos_numerados=True,
        )
        MapaAssentos.objects.create(evento=self.evento)
        self.client.force_login(self.staff)

    def test_mapa_do_admin_mostra_o_dia(self):
        resposta = self.client.get(
            reverse(
                'admin_dashboard:espetaculo_mapa_assentos',
                args=[self.evento.pk],
            )
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'Sábado, 14/11/2026 às 19:30')

    def test_gerenciar_assentos_mostra_o_dia(self):
        resposta = self.client.get(
            reverse(
                'admin_dashboard:espetaculo_assentos_gerenciar',
                args=[self.evento.pk],
            )
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'Sábado, 14/11/2026 às 19:30')
