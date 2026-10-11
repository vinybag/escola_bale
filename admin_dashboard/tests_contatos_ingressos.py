from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from admin_dashboard.contatos_ingressos import (
    COMPROU,
    EM_ANDAMENTO,
    NAO_FINALIZOU,
    VERIFICAR,
    contar_por_status,
    filtrar_contatos,
    montar_contatos,
    normalizar_whatsapp,
)
from espetaculo.models import (
    Assento,
    Espetaculo,
    MapaAssentos,
    PedidoIngressoEvento,
)


class NormalizarWhatsappTests(TestCase):
    def test_formatos_comuns(self):
        esperado = '5511912345678'
        for texto in (
            '(11) 91234-5678',
            '11 91234 5678',
            '11912345678',
            '+55 11 91234-5678',
            '5511912345678',
        ):
            self.assertEqual(normalizar_whatsapp(texto), esperado, texto)

    def test_invalidos(self):
        for texto in ('', None, '-', 'abc', '123', '(00) 91234-5678'):
            self.assertIsNone(normalizar_whatsapp(texto), texto)


class ContatosIngressosTests(TestCase):
    def setUp(self):
        self.evento = Espetaculo.objects.create(
            titulo='Quebra-Nozes',
            descricao='x',
            tipo='evento',
            data_apresentacao=timezone.now() + timedelta(days=10),
            local='Teatro',
            endereco='Rua A',
            preco_ingresso=Decimal('50.00'),
        )

    def _pedido(self, whatsapp='(11) 91234-5678', status='pendente',
                minutos_atras=60, pix=True, **extra):
        pedido = PedidoIngressoEvento.objects.create(
            evento=self.evento,
            nome_completo=extra.pop('nome_completo', 'Maria Silva'),
            whatsapp=whatsapp,
            quantidade=extra.pop('quantidade', 2),
            valor_unitario=Decimal('50.00'),
            valor_total=extra.pop('valor_total', Decimal('100.00')),
            status=status,
            codigo_pix='000201...' if pix else None,
            **extra,
        )
        # criado_em é auto_now_add: ajusta direto no banco.
        PedidoIngressoEvento.objects.filter(pk=pedido.pk).update(
            criado_em=timezone.now() - timedelta(minutes=minutos_atras)
        )
        pedido.refresh_from_db()
        return pedido

    def _status(self):
        contatos, _ = montar_contatos(self.evento)
        return {c['whatsapp_numero']: c['status'] for c in contatos}

    def test_expirado_e_cancelado_sao_nao_finalizou(self):
        self._pedido(status='expirado')
        self._pedido(whatsapp='(21) 98888-7777', status='cancelado')

        self.assertEqual(
            self._status(),
            {'5511912345678': NAO_FINALIZOU, '5521988887777': NAO_FINALIZOU},
        )

    def test_pendente_antigo_e_nao_finalizou_e_recente_e_em_andamento(self):
        self._pedido(status='pendente', minutos_atras=120)
        self._pedido(whatsapp='(21) 98888-7777', status='pendente',
                     minutos_atras=3)

        self.assertEqual(
            self._status(),
            {'5511912345678': NAO_FINALIZOU, '5521988887777': EM_ANDAMENTO},
        )

    def test_sem_pix_nao_entra(self):
        self._pedido(status='expirado', pix=False)
        self.assertEqual(self._status(), {})

    def test_pago_entra_como_comprou_mesmo_sem_codigo_pix(self):
        self._pedido(status='pago', pix=False)
        self.assertEqual(self._status(), {'5511912345678': COMPROU})

    def test_cortesia_e_gratuito_nao_entram(self):
        self._pedido(status='pago', valor_total=Decimal('0.00'))
        self._pedido(
            whatsapp='(21) 98888-7777',
            status='pago',
            external_reference='ingresso_gratuito_aluna:1',
        )
        self.assertEqual(self._status(), {})

    def test_status_muda_quando_quem_nao_comprou_compra_depois(self):
        self._pedido(status='expirado', minutos_atras=300)
        self.assertEqual(self._status(), {'5511912345678': NAO_FINALIZOU})

        # Mesma pessoa (WhatsApp escrito de outro jeito) paga depois.
        self._pedido(whatsapp='11912345678', status='pago', minutos_atras=10)

        contatos, _ = montar_contatos(self.evento)
        self.assertEqual(len(contatos), 1)
        self.assertEqual(contatos[0]['status'], COMPROU)
        self.assertTrue(contatos[0]['tentou_antes'])
        self.assertEqual(contar_por_status(contatos)[NAO_FINALIZOU], 0)

    def test_varias_tentativas_viram_uma_pessoa(self):
        self._pedido(status='expirado', minutos_atras=300)
        self._pedido(status='cancelado', minutos_atras=200)
        self._pedido(status='expirado', minutos_atras=100)

        contatos, _ = montar_contatos(self.evento)
        self.assertEqual(len(contatos), 1)
        self.assertEqual(contatos[0]['tentativas_sem_pagar'], 3)

    def test_pago_no_asaas_mas_nao_no_sistema_pede_verificacao(self):
        self._pedido(status='expirado', asaas_status='RECEIVED')
        self.assertEqual(self._status(), {'5511912345678': VERIFICAR})

    def test_sem_whatsapp_valido_e_contado_a_parte(self):
        self._pedido(whatsapp='-', status='expirado')
        contatos, sem_whatsapp = montar_contatos(self.evento)
        self.assertEqual(contatos, [])
        self.assertEqual(sem_whatsapp, 1)

    def test_outro_evento_nao_aparece(self):
        outro = Espetaculo.objects.create(
            titulo='Outro', descricao='x', tipo='evento',
            data_apresentacao=timezone.now(), local='L', endereco='E',
        )
        PedidoIngressoEvento.objects.create(
            evento=outro, nome_completo='Ana', whatsapp='11999998888',
            quantidade=1, valor_unitario=Decimal('50'),
            valor_total=Decimal('50'), status='expirado', codigo_pix='x',
        )
        self.assertEqual(self._status(), {})

    def test_assentos_aparecem_pelo_rotulo(self):
        mapa = MapaAssentos.objects.create(evento=self.evento)
        a1 = Assento.objects.create(
            mapa=mapa, identificador='C18', fileira='C', numero=18,
            x_pct=Decimal('1'), y_pct=Decimal('1'),
        )
        a2 = Assento.objects.create(
            mapa=mapa, identificador='C19', fileira='C', numero=19,
            x_pct=Decimal('2'), y_pct=Decimal('1'),
        )
        self._pedido(status='expirado', assentos_ids=[a1.id, a2.id])

        contatos, _ = montar_contatos(self.evento)
        self.assertEqual(contatos[0]['assentos'], ['C18', 'C19'])

    def test_link_whatsapp_tem_mensagem_so_para_quem_nao_finalizou(self):
        self._pedido(status='expirado')
        self._pedido(whatsapp='(21) 98888-7777', status='pago')

        contatos, _ = montar_contatos(self.evento)
        por_numero = {c['whatsapp_numero']: c for c in contatos}

        self.assertIn(
            '?text=', por_numero['5511912345678']['whatsapp_link']
        )
        self.assertEqual(
            por_numero['5521988887777']['whatsapp_link'],
            'https://wa.me/5521988887777',
        )

    def test_filtros(self):
        self._pedido(status='expirado', nome_completo='Maria Silva')
        self._pedido(whatsapp='(21) 98888-7777', status='pago',
                     nome_completo='João Souza')

        contatos, _ = montar_contatos(self.evento)

        self.assertEqual(
            [c['nome'] for c in filtrar_contatos(contatos, status=COMPROU)],
            ['João Souza'],
        )
        self.assertEqual(
            [c['nome'] for c in filtrar_contatos(contatos, busca='maria')],
            ['Maria Silva'],
        )
        self.assertEqual(
            [c['nome'] for c in filtrar_contatos(contatos, busca='98888')],
            ['João Souza'],
        )


# O storage de estáticos de produção (manifesto) exige `collectstatic`
# antes de renderizar qualquer template que use {% static %}. Nos testes
# usamos o storage simples, só para a página poder ser renderizada.
@override_settings(
    STORAGES={
        'default': {
            'BACKEND': 'django.core.files.storage.FileSystemStorage',
        },
        'staticfiles': {
            'BACKEND': (
                'django.contrib.staticfiles.storage.StaticFilesStorage'
            ),
        },
    }
)
class ContatosIngressosViewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.staff = User.objects.create_user(
            'staff', 'staff@example.com', 'senha123', is_staff=True
        )
        self.comum = User.objects.create_user(
            'comum', 'comum@example.com', 'senha123'
        )
        self.evento = Espetaculo.objects.create(
            titulo='Quebra-Nozes', descricao='x', tipo='evento',
            data_apresentacao=timezone.now() + timedelta(days=10),
            local='Teatro', endereco='Rua A',
        )
        PedidoIngressoEvento.objects.create(
            evento=self.evento, nome_completo='Maria Silva',
            whatsapp='(11) 91234-5678', quantidade=1,
            valor_unitario=Decimal('50'), valor_total=Decimal('50'),
            status='expirado', codigo_pix='000201',
        )
        self.url = reverse(
            'admin_dashboard:espetaculo_contatos_ingressos',
            args=[self.evento.pk],
        )

    def test_staff_ve_a_lista(self):
        self.client.force_login(self.staff)
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'Maria Silva')
        self.assertContains(resposta, 'https://wa.me/5511912345678')

    def test_filtro_por_status_pela_url(self):
        self.client.force_login(self.staff)
        resposta = self.client.get(self.url, {'status': 'comprou'})
        self.assertEqual(resposta.status_code, 200)
        self.assertNotContains(resposta, 'Maria Silva')

    def test_nao_staff_e_barrado(self):
        self.client.force_login(self.comum)
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 302)

    def test_anonimo_vai_para_login(self):
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 302)
        self.assertIn('login', resposta['Location'])


@override_settings(
    STORAGES={
        'default': {
            'BACKEND': 'django.core.files.storage.FileSystemStorage',
        },
        'staticfiles': {
            'BACKEND': (
                'django.contrib.staticfiles.storage.StaticFilesStorage'
            ),
        },
    }
)
class IngressosVendidosAcessoTests(TestCase):
    """
    A tela de ingressos vendidos mostra dados pessoais dos compradores e
    precisa de login + staff. A compra pública (sem login) é outro fluxo.
    """

    def setUp(self):
        User = get_user_model()
        self.staff = User.objects.create_user(
            'staff', 'staff@example.com', 'senha123', is_staff=True
        )
        self.comum = User.objects.create_user(
            'comum', 'comum@example.com', 'senha123'
        )
        self.evento = Espetaculo.objects.create(
            titulo='Quebra-Nozes', descricao='x', tipo='evento',
            data_apresentacao=timezone.now() + timedelta(days=10),
            local='Teatro', endereco='Rua A',
        )
        PedidoIngressoEvento.objects.create(
            evento=self.evento, nome_completo='Maria Comprou',
            whatsapp='(11) 91234-5678', quantidade=1,
            valor_unitario=Decimal('50'), valor_total=Decimal('50'),
            status='pago',
        )
        self.url = reverse(
            'admin_dashboard:espetaculo_ingressos_vendidos',
            args=[self.evento.pk],
        )

    def test_anonimo_nao_ve_dados_dos_compradores(self):
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 302)
        self.assertIn('login', resposta['Location'])
        self.assertNotIn(b'Maria Comprou', resposta.content)

    def test_usuario_comum_nao_ve_dados_dos_compradores(self):
        self.client.force_login(self.comum)
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 302)
        self.assertNotIn(b'Maria Comprou', resposta.content)

    def test_staff_continua_vendo(self):
        self.client.force_login(self.staff)
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'Maria Comprou')
