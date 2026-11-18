"""Cobrança única: filhas (e mãe aluna) do mesmo login pagam um pix só."""

import json
from datetime import date, timedelta
from decimal import Decimal
from io import StringIO
from unittest import mock

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from usuarios.models import Aluna, Perfil

from . import cobranca
from .models import Mensalidade

D = Decimal
MES = date(2026, 12, 1)
VENC = date(2026, 12, 10)

ESTATICOS = override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})


class Base(TestCase):
    def setUp(self):
        self.mae = User.objects.create_user('mae', email='mae@x.com', password='x', first_name='Maria')
        Perfil.objects.create(user=self.mae, is_responsavel=True, telefone='11999990000', cpf='529.982.247-25')
        self.outra = User.objects.create_user('tia', email='tia@x.com', password='x')
        Perfil.objects.create(user=self.outra, is_responsavel=True, telefone='11988880000')

    def mensalidade(self, nome, valor, responsavel=None, vencimento=VENC, mes=MES, **kw):
        responsavel = responsavel or self.mae
        aluna = Aluna.objects.create(nome=nome, responsavel=responsavel)
        return Mensalidade.objects.create(
            aluna=aluna, responsavel=responsavel, mes_referencia=mes, valor=D(valor), data_vencimento=vencimento, **kw,
        )


class AgrupamentoTests(Base):
    def test_filhas_do_mesmo_login_mes_e_vencimento_viram_uma_cobranca(self):
        a = self.mensalidade('Ana', '110')
        b = self.mensalidade('Bia', '93.50')

        grupos = cobranca.agrupar(Mensalidade.objects.all())

        self.assertEqual(len(grupos), 1)
        self.assertEqual(grupos[0].valor, D('203.50'))
        self.assertEqual(grupos[0].nomes_alunas, 'Ana e Bia')
        self.assertEqual(grupos[0].descricao, 'Mensalidade Ana e Bia - 12/2026')
        self.assertEqual(sorted(grupos[0].ids), sorted([a.pk, b.pk]))

    def test_tres_alunas_descricao_com_virgula_e_e(self):
        for nome in ('Ana', 'Bia', 'Cléo'):
            self.mensalidade(nome, '100')

        self.assertEqual(cobranca.agrupar(Mensalidade.objects.all())[0].descricao, 'Mensalidade Ana, Bia e Cléo - 12/2026')

    def test_mae_que_tambem_e_aluna_entra_junto_com_as_filhas(self):
        self.mensalidade('Filha', '110')
        mae_aluna = Aluna.objects.create(nome='Maria Aluna', usuario=self.mae, tipo_aluna='adulto')
        Mensalidade.objects.create(
            aluna=mae_aluna, responsavel=self.mae, mes_referencia=MES, valor=D('120'), data_vencimento=VENC,
        )

        grupos = cobranca.agrupar(Mensalidade.objects.all())

        self.assertEqual(len(grupos), 1)
        self.assertEqual(grupos[0].valor, D('230.00'))

    def test_primas_com_logins_diferentes_ficam_separadas(self):
        self.mensalidade('Ana', '110')
        self.mensalidade('Lia', '110', responsavel=self.outra)

        self.assertEqual(len(cobranca.agrupar(Mensalidade.objects.all())), 2)

    def test_vencimentos_diferentes_ficam_separados(self):
        self.mensalidade('Ana', '110')
        self.mensalidade('Bia', '110', vencimento=date(2026, 12, 20))

        self.assertEqual(len(cobranca.agrupar(Mensalidade.objects.all())), 2)

    def test_meses_diferentes_ficam_separados(self):
        self.mensalidade('Ana', '110')
        self.mensalidade('Bia', '110', mes=date(2027, 1, 1), vencimento=date(2027, 1, 10))

        self.assertEqual(len(cobranca.agrupar(Mensalidade.objects.all())), 2)

    def test_cancelada_nunca_entra_na_cobranca(self):
        a = self.mensalidade('Ana', '110')
        self.mensalidade('Bia', '110', status='cancelado')

        self.assertEqual(cobranca.cobranca_da_mensalidade(a).valor, D('110.00'))

    def test_paga_em_dinheiro_sai_da_cobranca_das_outras(self):
        from django.utils import timezone

        a = self.mensalidade('Ana', '110')
        self.mensalidade('Bia', '110', data_pagamento=timezone.now(), forma_pagamento='dinheiro')

        c = cobranca.cobranca_da_mensalidade(a)

        self.assertEqual((c.valor, c.nomes_alunas), (D('110.00'), 'Ana'))

    def test_acrescimo_de_atraso_segue_a_regra_de_cada_mensalidade(self):
        vencida = date.today() - timedelta(days=3)
        self.mensalidade('Ana', '110', vencimento=vencida)
        self.mensalidade('Bia', '100', vencimento=vencida)

        c = cobranca.agrupar(Mensalidade.objects.all())[0]

        self.assertEqual(c.valor, D('210.00'))
        self.assertEqual(c.acrescimo_atraso, D('20.00'))   # R$ 10 por mensalidade, como sempre foi
        self.assertEqual(c.valor_atualizado, D('230.00'))
        self.assertEqual(c.status_atual, 'atrasado')

    def test_referencia_externa_e_ids(self):
        a = self.mensalidade('Ana', '110')
        self.assertEqual(cobranca.cobranca_da_mensalidade(a).referencia_externa, f'mensalidade:{a.pk}')

        b = self.mensalidade('Bia', '110')
        ref = cobranca.cobranca_da_mensalidade(a).referencia_externa

        self.assertEqual(sorted(cobranca.ids_da_referencia(ref)), sorted([a.pk, b.pk]))
        self.assertEqual(cobranca.ids_da_referencia('ingresso_evento:5'), [])
        self.assertEqual(cobranca.ids_da_referencia(None), [])


class FalsoAsaas:
    """Asaas de mentira: guarda o que foi pedido."""

    criadas = []
    existente = None

    def criar_cobranca_pix(self, valor, descricao, customer_id=None, customer_data=None, external_reference=None):
        FalsoAsaas.criadas.append({'valor': valor, 'descricao': descricao, 'ref': external_reference})
        return {'id': 'pay_nova', 'customer': 'cus_1', 'status': 'PENDING', 'value': float(valor)}

    def consultar_cobranca(self, payment_id):
        return FalsoAsaas.existente

    def obter_qrcode_pix(self, payment_id):
        return {'payload': 'PIXCOPIAECOLA', 'encodedImage': 'x', 'expirationDate': '2026-12-11'}


@ESTATICOS
@mock.patch('pagamentos.views.AsaasAPI', FalsoAsaas)
class PagamentoPixTests(Base):
    def setUp(self):
        super().setUp()
        FalsoAsaas.criadas = []
        FalsoAsaas.existente = None
        self.c = Client()
        self.c.force_login(self.mae)
        self.a = self.mensalidade('Ana', '110')
        self.b = self.mensalidade('Bia', '93.50')

    def test_um_unico_pix_com_o_total_e_a_descricao_das_duas(self):
        resposta = self.c.get(reverse('pagar_pix', args=[self.a.pk]))

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(len(FalsoAsaas.criadas), 1)
        pedido = FalsoAsaas.criadas[0]
        self.assertEqual(D(str(pedido['valor'])), D('203.50'))
        self.assertEqual(pedido['descricao'], 'Mensalidade Ana e Bia - 12/2026')
        self.assertTrue(pedido['ref'].startswith('mensalidades:'))
        self.assertContains(resposta, 'Ana e Bia')
        self.assertContains(resposta, 'PIXCOPIAECOLA')

    def test_numero_do_pagamento_fica_gravado_nas_duas(self):
        self.c.get(reverse('pagar_pix', args=[self.a.pk]))

        self.assertEqual(
            set(Mensalidade.objects.values_list('asaas_payment_id', flat=True)), {'pay_nova'},
        )

    def test_clicar_pela_outra_filha_gera_o_mesmo_pix_total(self):
        self.c.get(reverse('pagar_pix', args=[self.b.pk]))

        self.assertEqual(D(str(FalsoAsaas.criadas[0]['valor'])), D('203.50'))

    def test_reaproveita_o_pix_quando_o_valor_bate(self):
        Mensalidade.objects.update(asaas_payment_id='pay_antigo')
        FalsoAsaas.existente = {'status': 'PENDING', 'value': 203.5}

        resposta = self.c.get(reverse('pagar_pix', args=[self.a.pk]))

        self.assertEqual(FalsoAsaas.criadas, [])
        self.assertEqual(resposta.context['payment_id'], 'pay_antigo')

    def test_cria_novo_pix_quando_o_valor_antigo_era_de_uma_so_filha(self):
        Mensalidade.objects.filter(pk=self.a.pk).update(asaas_payment_id='pay_so_ana')
        FalsoAsaas.existente = {'status': 'PENDING', 'value': 110.0}

        self.c.get(reverse('pagar_pix', args=[self.a.pk]))

        self.assertEqual(len(FalsoAsaas.criadas), 1)
        self.assertEqual(set(Mensalidade.objects.values_list('asaas_payment_id', flat=True)), {'pay_nova'})

    def test_pix_ja_recebido_baixa_as_duas(self):
        Mensalidade.objects.update(asaas_payment_id='pay_antigo')
        FalsoAsaas.existente = {'status': 'RECEIVED', 'value': 203.5}

        resposta = self.c.get(reverse('pagar_pix', args=[self.a.pk]))

        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(set(Mensalidade.objects.values_list('status', flat=True)), {'pago'})

    def test_filha_sozinha_continua_funcionando_como_antes(self):
        Mensalidade.objects.filter(pk=self.b.pk).delete()
        self.c.get(reverse('pagar_pix', args=[self.a.pk]))

        pedido = FalsoAsaas.criadas[0]
        self.assertEqual(pedido['descricao'], 'Mensalidade Ana - 12/2026')
        self.assertEqual(pedido['ref'], f'mensalidade:{self.a.pk}')

    def test_outra_familia_nao_consegue_pagar_a_cobranca_dos_outros(self):
        intruso = Client()
        intruso.force_login(self.outra)

        self.assertEqual(intruso.get(reverse('pagar_pix', args=[self.a.pk])).status_code, 404)

    def test_verificar_pagamento_baixa_todas(self):
        Mensalidade.objects.update(asaas_payment_id='pay_x')
        FalsoAsaas.existente = {'status': 'RECEIVED'}

        resposta = self.c.get(reverse('verificar_pagamento_pix', args=['pay_x']))

        self.assertEqual(resposta.json()['status'], 'paid')
        self.assertEqual(set(Mensalidade.objects.values_list('status', flat=True)), {'pago'})

    def test_tela_de_mensalidades_mostra_uma_cobranca_so(self):
        pagina = self.c.get(reverse('mensalidades'))

        self.assertContains(pagina, 'Ana e Bia')
        self.assertContains(pagina, 'Pagar Agora', count=1)
        self.assertContains(pagina, '203,50')

    def test_tela_de_sucesso_mostra_as_duas(self):
        Mensalidade.objects.update(asaas_payment_id='pay_x')
        FalsoAsaas.existente = {'status': 'RECEIVED'}
        self.c.get(reverse('verificar_pagamento_pix', args=['pay_x']))

        pagina = self.c.get(reverse('pagamento_sucesso') + f'?mensalidade_id={self.a.pk}')

        self.assertContains(pagina, 'Ana e Bia')
        self.assertContains(pagina, '203,50')


@override_settings(ASAAS_WEBHOOK_TOKEN='segredo')
@mock.patch('pagamentos.views.ASAAS_WEBHOOK_TOKEN', 'segredo')
class WebhookTests(Base):
    def setUp(self):
        super().setUp()
        self.a = self.mensalidade('Ana', '110')
        self.b = self.mensalidade('Bia', '93.50')
        self.lia = self.mensalidade('Lia', '110', responsavel=self.outra)

    def avisar(self, payment_id, referencia, status='RECEIVED'):
        return Client().post(
            reverse('webhook_asaas'),
            data=json.dumps({'event': 'PAYMENT_RECEIVED', 'payment': {
                'id': payment_id, 'externalReference': referencia, 'status': status, 'customer': 'cus_1',
            }}),
            content_type='application/json', HTTP_ASAAS_ACCESS_TOKEN='segredo',
        )

    def status(self):
        return {m.aluna.nome: m.status for m in Mensalidade.objects.select_related('aluna')}

    def test_pagamento_pelo_numero_baixa_todas_as_do_mesmo_pix(self):
        Mensalidade.objects.filter(pk__in=[self.a.pk, self.b.pk]).update(asaas_payment_id='pay_1')

        self.assertEqual(self.avisar('pay_1', None).status_code, 200)
        self.assertEqual(self.status(), {'Ana': 'pago', 'Bia': 'pago', 'Lia': 'pendente'})

    def test_pagamento_pela_referencia_baixa_todas_e_grava_o_numero(self):
        referencia = cobranca.cobranca_da_mensalidade(self.a).referencia_externa

        self.assertEqual(self.avisar('pay_2', referencia).status_code, 200)
        self.assertEqual(self.status(), {'Ana': 'pago', 'Bia': 'pago', 'Lia': 'pendente'})
        self.assertEqual(Mensalidade.objects.get(pk=self.a.pk).asaas_payment_id, 'pay_2')

    def test_referencia_antiga_de_uma_so_mensalidade_continua_valendo(self):
        self.assertEqual(self.avisar('pay_3', f'mensalidade:{self.lia.pk}').status_code, 200)
        self.assertEqual(self.status(), {'Ana': 'pendente', 'Bia': 'pendente', 'Lia': 'pago'})

    def test_aviso_repetido_nao_da_erro(self):
        referencia = cobranca.cobranca_da_mensalidade(self.a).referencia_externa
        self.avisar('pay_2', referencia)

        self.assertEqual(self.avisar('pay_2', referencia).status_code, 200)

    def test_pagamento_ainda_nao_recebido_nao_baixa(self):
        referencia = cobranca.cobranca_da_mensalidade(self.a).referencia_externa
        self.avisar('pay_4', referencia, status='PENDING')

        self.assertEqual(self.status(), {'Ana': 'pendente', 'Bia': 'pendente', 'Lia': 'pendente'})

    def test_sem_token_certo_nao_baixa(self):
        resposta = Client().post(reverse('webhook_asaas'), data='{}', content_type='application/json')

        self.assertEqual(resposta.status_code, 401)


class AvisosTests(Base):
    def rodar(self):
        with mock.patch(
            'pagamentos.management.commands.enviar_avisos_mensalidades.enviar_whatsapp_template',
            return_value=(200, {}),
        ) as envio:
            call_command('enviar_avisos_mensalidades', stdout=StringIO())

        return envio

    def test_vencimento_amanha_manda_um_aviso_so_para_as_duas_filhas(self):
        amanha = date.today() + timedelta(days=1)
        self.mensalidade('Ana', '110', vencimento=amanha)
        self.mensalidade('Bia', '93.50', vencimento=amanha)

        envio = self.rodar()

        self.assertEqual(envio.call_count, 1)
        _, modelo, parametros = envio.call_args[0]
        self.assertEqual(modelo, 'aviso_vencimento_amanha')
        self.assertEqual(parametros[3], 'Ana e Bia')
        self.assertEqual(parametros[4], '203,50')
        self.assertEqual(set(Mensalidade.objects.values_list('ultimo_aviso_enviado', flat=True)), {'vencimento_amanha'})

    def test_rodar_de_novo_no_mesmo_dia_nao_repete(self):
        amanha = date.today() + timedelta(days=1)
        self.mensalidade('Ana', '110', vencimento=amanha)
        self.mensalidade('Bia', '93.50', vencimento=amanha)
        self.rodar()

        self.assertEqual(self.rodar().call_count, 0)

    def test_atraso_soma_o_acrescimo_de_cada_uma(self):
        vencida = date.today() - timedelta(days=3)
        self.mensalidade('Ana', '110', vencimento=vencida)
        self.mensalidade('Bia', '100', vencimento=vencida)

        envio = self.rodar()

        self.assertEqual(envio.call_count, 1)
        _, modelo, parametros = envio.call_args[0]
        self.assertEqual(modelo, 'aviso_atraso')
        self.assertEqual(parametros[2], 'Ana e Bia')
        self.assertEqual(parametros[5], '230,00')

    def test_familias_diferentes_recebem_avisos_separados(self):
        amanha = date.today() + timedelta(days=1)
        self.mensalidade('Ana', '110', vencimento=amanha)
        self.mensalidade('Lia', '110', responsavel=self.outra, vencimento=amanha)

        self.assertEqual(self.rodar().call_count, 2)
