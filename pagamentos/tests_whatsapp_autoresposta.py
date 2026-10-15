import hashlib
import hmac
import json
import time
from datetime import timedelta
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from pagamentos.models import WhatsAppMensagemRecebida
from pagamentos.services_whatsapp import enviar_whatsapp_texto
from pagamentos.whatsapp_autoresposta import (
    formatar_numero_br,
    montar_texto_autoresposta,
    normalizar_numero_br,
)

SEGREDO = 'segredo-do-app'
TOKEN = 'token-de-verificacao'
PHONE_ID = '1234567890'
ATENDIMENTO = '(11) 98888-7777'  # número de atendimento da escola
CLIENTE = '5521977776666'

ENVIAR = 'pagamentos.whatsapp_autoresposta.enviar_whatsapp_texto'


def _mensagem(wamid='wamid.1', de=CLIENTE, tipo='text', idade_segundos=5):
    return {
        'id': wamid,
        'from': de,
        'type': tipo,
        'timestamp': str(int(time.time()) - idade_segundos),
        'text': {'body': 'oi, quando é o ensaio?'},
    }


def _payload(*mensagens, phone_id=PHONE_ID, statuses=None):
    valor = {
        'messaging_product': 'whatsapp',
        'metadata': {
            'display_phone_number': '5511900000000',
            'phone_number_id': phone_id,
        },
    }
    if mensagens:
        valor['messages'] = list(mensagens)
    if statuses:
        valor['statuses'] = statuses
    return {
        'object': 'whatsapp_business_account',
        'entry': [{'id': 'waba', 'changes': [{'field': 'messages', 'value': valor}]}],
    }


def _assinar(corpo, segredo=SEGREDO):
    return 'sha256=' + hmac.new(
        segredo.encode(), corpo, hashlib.sha256
    ).hexdigest()


@override_settings(
    WHATSAPP_VERIFY_TOKEN=TOKEN,
    WHATSAPP_APP_SECRET=SEGREDO,
    WHATSAPP_NUMERO_ATENDIMENTO=ATENDIMENTO,
    WHATSAPP_PHONE_NUMBER_ID=PHONE_ID,
    WHATSAPP_ACCESS_TOKEN='token-de-acesso',
    WHATSAPP_AUTORESPOSTA_ATIVA=True,
)
class WebhookWhatsAppTests(TestCase):
    def setUp(self):
        self.url = reverse('webhook_whatsapp')

    def _post(self, payload, assinatura='auto', segredo=SEGREDO):
        corpo = json.dumps(payload).encode()
        extra = {}
        if assinatura == 'auto':
            extra['HTTP_X_HUB_SIGNATURE_256'] = _assinar(corpo, segredo)
        elif assinatura is not None:
            extra['HTTP_X_HUB_SIGNATURE_256'] = assinatura
        return self.client.post(
            self.url, data=corpo, content_type='application/json', **extra
        )

    # ---------- verificação (GET) ----------

    def test_verificacao_devolve_o_desafio(self):
        resposta = self.client.get(self.url, {
            'hub.mode': 'subscribe',
            'hub.verify_token': TOKEN,
            'hub.challenge': '98765',
        })
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.content, b'98765')

    def test_verificacao_com_token_errado_e_negada(self):
        resposta = self.client.get(self.url, {
            'hub.mode': 'subscribe',
            'hub.verify_token': 'errado',
            'hub.challenge': '98765',
        })
        self.assertEqual(resposta.status_code, 403)

    @override_settings(WHATSAPP_VERIFY_TOKEN=None)
    def test_verificacao_sem_token_configurado_e_negada(self):
        resposta = self.client.get(self.url, {
            'hub.mode': 'subscribe',
            'hub.verify_token': 'None',
            'hub.challenge': '98765',
        })
        self.assertEqual(resposta.status_code, 403)

    # ---------- assinatura (POST) ----------

    @mock.patch(ENVIAR, return_value=(200, {}))
    def test_sem_assinatura_e_negado_e_nao_responde(self, enviar):
        resposta = self._post(_payload(_mensagem()), assinatura=None)
        self.assertEqual(resposta.status_code, 403)
        enviar.assert_not_called()
        self.assertEqual(WhatsAppMensagemRecebida.objects.count(), 0)

    @mock.patch(ENVIAR, return_value=(200, {}))
    def test_assinatura_falsa_e_negada(self, enviar):
        resposta = self._post(_payload(_mensagem()), segredo='outro-segredo')
        self.assertEqual(resposta.status_code, 403)
        enviar.assert_not_called()

    @override_settings(WHATSAPP_APP_SECRET=None)
    @mock.patch(ENVIAR, return_value=(200, {}))
    def test_sem_segredo_configurado_nada_e_aceito(self, enviar):
        resposta = self._post(_payload(_mensagem()), assinatura='sha256=qualquer')
        self.assertEqual(resposta.status_code, 403)
        enviar.assert_not_called()

    def test_metodo_nao_permitido(self):
        self.assertEqual(self.client.put(self.url).status_code, 405)

    # ---------- resposta automática ----------

    @mock.patch(ENVIAR, return_value=(200, {}))
    def test_mensagem_recebida_gera_uma_resposta_com_o_numero_certo(self, enviar):
        resposta = self._post(_payload(_mensagem()))

        self.assertEqual(resposta.status_code, 200)
        enviar.assert_called_once()
        destino, texto = enviar.call_args.args
        self.assertEqual(destino, CLIENTE)
        self.assertIn('(11) 98888-7777', texto)
        self.assertIn('https://wa.me/5511988887777', texto)

        registro = WhatsAppMensagemRecebida.objects.get()
        self.assertEqual(registro.status, 'respondida')
        self.assertEqual(registro.telefone, CLIENTE)

    @mock.patch(ENVIAR, return_value=(200, {}))
    def test_texto_da_mensagem_recebida_nao_e_guardado(self, enviar):
        self._post(_payload(_mensagem()))
        registro = WhatsAppMensagemRecebida.objects.get()
        guardado = ' '.join(
            str(getattr(registro, c.name)) for c in registro._meta.fields
        )
        self.assertNotIn('quando é o ensaio', guardado)

    @mock.patch(ENVIAR, return_value=(200, {}))
    def test_reenvio_do_mesmo_aviso_pela_meta_nao_responde_de_novo(self, enviar):
        self._post(_payload(_mensagem(wamid='wamid.IGUAL')))
        self._post(_payload(_mensagem(wamid='wamid.IGUAL')))
        self.assertEqual(enviar.call_count, 1)
        self.assertEqual(WhatsAppMensagemRecebida.objects.count(), 1)

    @mock.patch(ENVIAR, return_value=(200, {}))
    def test_nova_mensagem_dentro_de_24h_nao_responde_de_novo(self, enviar):
        self._post(_payload(_mensagem(wamid='wamid.A')))
        self._post(_payload(_mensagem(wamid='wamid.B')))
        self.assertEqual(enviar.call_count, 1)

        segunda = WhatsAppMensagemRecebida.objects.get(wamid='wamid.B')
        self.assertEqual(segunda.status, 'ignorada')
        self.assertEqual(segunda.motivo, 'ja_respondida_nas_ultimas_24h')

    @mock.patch(ENVIAR, return_value=(200, {}))
    def test_depois_de_24h_responde_de_novo(self, enviar):
        self._post(_payload(_mensagem(wamid='wamid.A')))
        WhatsAppMensagemRecebida.objects.filter(wamid='wamid.A').update(
            criado_em=timezone.now() - timedelta(hours=25)
        )
        self._post(_payload(_mensagem(wamid='wamid.B')))
        self.assertEqual(enviar.call_count, 2)

    @mock.patch(ENVIAR, return_value=(200, {}))
    def test_pessoas_diferentes_recebem_cada_uma_a_sua(self, enviar):
        self._post(_payload(
            _mensagem(wamid='wamid.A', de='5521977776666'),
            _mensagem(wamid='wamid.B', de='5531966665555'),
        ))
        self.assertEqual(enviar.call_count, 2)

    @mock.patch(ENVIAR, return_value=(200, {}))
    def test_duas_mensagens_no_mesmo_aviso_respondem_uma_vez(self, enviar):
        self._post(_payload(
            _mensagem(wamid='wamid.A'),
            _mensagem(wamid='wamid.B'),
        ))
        self.assertEqual(enviar.call_count, 1)

    # ---------- o que NÃO deve ser respondido ----------

    @mock.patch(ENVIAR, return_value=(200, {}))
    def test_avisos_de_status_entregue_lido_sao_ignorados(self, enviar):
        resposta = self._post(_payload(statuses=[
            {'id': 'wamid.X', 'status': 'delivered', 'recipient_id': CLIENTE},
            {'id': 'wamid.X', 'status': 'read', 'recipient_id': CLIENTE},
        ]))
        self.assertEqual(resposta.status_code, 200)
        enviar.assert_not_called()
        self.assertEqual(WhatsAppMensagemRecebida.objects.count(), 0)

    @mock.patch(ENVIAR, return_value=(200, {}))
    def test_reacao_com_emoji_nao_gera_resposta(self, enviar):
        self._post(_payload(_mensagem(tipo='reaction')))
        enviar.assert_not_called()
        self.assertEqual(
            WhatsAppMensagemRecebida.objects.get().motivo,
            'tipo_ignorado:reaction',
        )

    @mock.patch(ENVIAR, return_value=(200, {}))
    def test_audio_imagem_e_botao_tambem_recebem_resposta(self, enviar):
        for i, tipo in enumerate(('audio', 'image', 'button', 'interactive')):
            self._post(_payload(_mensagem(
                wamid=f'wamid.{i}', de=f'55219777766{i:02d}', tipo=tipo
            )))
        self.assertEqual(enviar.call_count, 4)

    @mock.patch(ENVIAR, return_value=(200, {}))
    def test_nao_responde_a_propria_escola(self, enviar):
        self._post(_payload(_mensagem(de='5511988887777')))
        enviar.assert_not_called()
        self.assertEqual(
            WhatsAppMensagemRecebida.objects.get().motivo,
            'remetente_e_a_propria_escola',
        )

    @mock.patch(ENVIAR, return_value=(200, {}))
    def test_nao_responde_a_escola_mesmo_sem_o_nono_digito(self, enviar):
        # A Meta às vezes entrega números brasileiros antigos sem o 9.
        self._post(_payload(_mensagem(de='551188887777')))
        enviar.assert_not_called()

    @mock.patch(ENVIAR, return_value=(200, {}))
    def test_mensagem_para_outro_numero_da_conta_e_ignorada(self, enviar):
        self._post(_payload(_mensagem(), phone_id='999'))
        enviar.assert_not_called()
        self.assertEqual(WhatsAppMensagemRecebida.objects.count(), 0)

    @mock.patch(ENVIAR, return_value=(200, {}))
    def test_mensagem_antiga_nao_recebe_resposta(self, enviar):
        self._post(_payload(_mensagem(idade_segundos=7 * 3600)))
        enviar.assert_not_called()
        self.assertEqual(
            WhatsAppMensagemRecebida.objects.get().motivo, 'mensagem_antiga'
        )

    @override_settings(WHATSAPP_AUTORESPOSTA_ATIVA=False)
    @mock.patch(ENVIAR, return_value=(200, {}))
    def test_desligada_pela_configuracao(self, enviar):
        resposta = self._post(_payload(_mensagem()))
        self.assertEqual(resposta.status_code, 200)
        enviar.assert_not_called()
        self.assertEqual(
            WhatsAppMensagemRecebida.objects.get().motivo,
            'autoresposta_desativada',
        )

    @override_settings(WHATSAPP_NUMERO_ATENDIMENTO=None)
    @mock.patch(ENVIAR, return_value=(200, {}))
    def test_sem_numero_de_atendimento_nao_responde(self, enviar):
        # Melhor ficar em silêncio do que mandar uma resposta sem o número.
        self._post(_payload(_mensagem()))
        enviar.assert_not_called()

    @override_settings(
        WHATSAPP_NUMERO_ATENDIMENTO=None,
        WHATSAPP_NUMERO_ESCOLA='(11) 90000-0000',
    )
    @mock.patch(ENVIAR, return_value=(200, {}))
    def test_variavel_antiga_de_disparos_nao_e_usada_como_atendimento(self, enviar):
        # WHATSAPP_NUMERO_ESCOLA guarda o número de disparos: nunca pode
        # virar o número informado às famílias.
        self._post(_payload(_mensagem()))
        enviar.assert_not_called()

    @override_settings(WHATSAPP_NUMERO_ATENDIMENTO='(11) 90000-0000')
    @mock.patch(ENVIAR, return_value=(200, {}))
    def test_atendimento_igual_ao_numero_de_disparos_nao_responde(self, enviar):
        # O número que recebeu a mensagem (metadata.display_phone_number) é
        # 5511900000000. Se alguém configurar esse mesmo número como
        # "atendimento", a resposta mandaria a pessoa de volta para ele.
        self._post(_payload(_mensagem()))
        enviar.assert_not_called()
        self.assertEqual(
            WhatsAppMensagemRecebida.objects.get().motivo,
            'numero_de_atendimento_igual_ao_numero_de_avisos',
        )

    @override_settings(WHATSAPP_NUMERO_ATENDIMENTO='(11) 9000-00000')
    @mock.patch(ENVIAR, return_value=(200, {}))
    def test_numero_de_disparos_com_formato_diferente_tambem_e_reconhecido(self, enviar):
        # Mesma pessoa/número escrito com formatação diferente.
        self._post(_payload(_mensagem()))
        enviar.assert_not_called()

    @override_settings(WHATSAPP_NUMERO_ATENDIMENTO='abc')
    @mock.patch(ENVIAR, return_value=(200, {}))
    def test_numero_de_atendimento_invalido_nao_responde(self, enviar):
        self._post(_payload(_mensagem()))
        enviar.assert_not_called()

    # ---------- falhas ----------

    @mock.patch(
        ENVIAR,
        return_value=(400, {'error': {'message': 'fora da janela de 24h'}}),
    )
    def test_falha_da_meta_e_registrada_e_o_webhook_continua_200(self, enviar):
        resposta = self._post(_payload(_mensagem()))
        self.assertEqual(resposta.status_code, 200)

        registro = WhatsAppMensagemRecebida.objects.get()
        self.assertEqual(registro.status, 'erro')
        self.assertIn('fora da janela de 24h', registro.motivo)

    def test_falha_nao_impede_nova_tentativa_na_proxima_mensagem(self):
        with mock.patch(ENVIAR, return_value=(0, {'error': {'message': 'rede'}})):
            self._post(_payload(_mensagem(wamid='wamid.A')))

        with mock.patch(ENVIAR, return_value=(200, {})) as enviar:
            self._post(_payload(_mensagem(wamid='wamid.B')))

        enviar.assert_called_once()
        self.assertEqual(
            WhatsAppMensagemRecebida.objects.get(wamid='wamid.B').status,
            'respondida',
        )

    @mock.patch(ENVIAR, side_effect=RuntimeError('quebrou'))
    def test_excecao_ao_enviar_nao_derruba_o_webhook(self, enviar):
        resposta = self._post(_payload(_mensagem()))
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(WhatsAppMensagemRecebida.objects.get().status, 'erro')

    def test_json_invalido_com_assinatura_correta_e_400(self):
        corpo = b'isso nao e json'
        resposta = self.client.post(
            self.url, data=corpo, content_type='application/json',
            HTTP_X_HUB_SIGNATURE_256=_assinar(corpo),
        )
        self.assertEqual(resposta.status_code, 400)

    @mock.patch(ENVIAR, return_value=(200, {}))
    def test_payload_estranho_nao_derruba(self, enviar):
        for payload in ({}, {'entry': None}, {'entry': [{}]},
                        {'entry': [{'changes': [{'field': 'outro'}]}]}):
            self.assertEqual(self._post(payload).status_code, 200)
        enviar.assert_not_called()


class FuncoesAuxiliaresTests(TestCase):
    def test_normalizar_numero_br(self):
        for texto in ('(11) 91234-5678', '11 91234 5678', '+55 11 91234-5678',
                      '5511912345678'):
            self.assertEqual(normalizar_numero_br(texto), '5511912345678')
        for texto in (None, '', 'abc', '123', '(00) 91234-5678'):
            self.assertIsNone(normalizar_numero_br(texto))

    def test_formatar_numero_br(self):
        self.assertEqual(formatar_numero_br('5511912345678'), '(11) 91234-5678')
        self.assertEqual(formatar_numero_br('551112345678'), '(11) 1234-5678')

    def test_texto_tem_numero_formatado_e_link(self):
        texto = montar_texto_autoresposta('5511912345678')
        self.assertIn('(11) 91234-5678', texto)
        self.assertIn('https://wa.me/5511912345678', texto)
        self.assertIn('não recebe', texto)


@override_settings(
    WHATSAPP_PHONE_NUMBER_ID=PHONE_ID, WHATSAPP_ACCESS_TOKEN='token-de-acesso'
)
class EnviarTextoTests(TestCase):
    @mock.patch('pagamentos.services_whatsapp.requests.post')
    def test_monta_a_requisicao_de_texto_livre(self, post):
        post.return_value = mock.Mock(status_code=200, json=lambda: {'ok': 1})

        status, _ = enviar_whatsapp_texto('5521977776666', 'olá')

        self.assertEqual(status, 200)
        url = post.call_args.args[0]
        self.assertIn(f'/{PHONE_ID}/messages', url)
        enviado = post.call_args.kwargs['json']
        self.assertEqual(enviado['type'], 'text')
        self.assertEqual(enviado['to'], '5521977776666')
        self.assertEqual(enviado['text']['body'], 'olá')
        self.assertEqual(
            post.call_args.kwargs['headers']['Authorization'],
            'Bearer token-de-acesso',
        )

    @override_settings(WHATSAPP_ACCESS_TOKEN=None)
    @mock.patch('pagamentos.services_whatsapp.requests.post')
    def test_sem_credenciais_nao_chama_a_meta(self, post):
        status, resposta = enviar_whatsapp_texto('5521977776666', 'olá')
        self.assertEqual(status, 0)
        self.assertIn('error', resposta)
        post.assert_not_called()
