"""
Testes do botão "Enviar agora por WhatsApp" (edição do aviso).
"""

from datetime import date, timedelta
from io import StringIO
from unittest import mock

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from calendario_avisos.envio_whatsapp import (
    JANELA_ANTIDUPLICIDADE,
    TEMPLATE_DIA,
    TEMPLATE_SEMANA,
    EnvioNaoPermitido,
    ReenvioPrecisaConfirmacao,
    contatos_sem_whatsapp,
    enviar_agora,
)
from calendario_avisos.models import Aviso, AvisoEnvioManual
from usuarios.models import Aluna, Perfil

SENDER = 'calendario_avisos.envio_whatsapp.enviar_whatsapp_template'
CRON_SENDER = (
    'calendario_avisos.management.commands.enviar_avisos_ensaio'
    '.enviar_whatsapp_template'
)
CRON_HOJE = (
    'calendario_avisos.management.commands.enviar_avisos_ensaio'
    '.timezone.localdate'
)

STORAGES_TESTE = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'
    },
}


def _usuario(username, telefone, nome='Maria', sobrenome='Silva', **extra):
    user = User.objects.create_user(
        username, f'{username}@example.com', 'senha123',
        first_name=nome, last_name=sobrenome, **extra,
    )
    Perfil.objects.create(user=user, telefone=telefone)
    return user


class BaseEnvioTests(TestCase):
    def setUp(self):
        self.hoje = timezone.localdate()
        self.futuro = self.hoje + timedelta(days=3)

        self.staff = _usuario(
            'staff', '(11) 90000-0000', 'Sec', 'Retaria', is_staff=True
        )
        self.responsavel = _usuario('resp', '(11) 91234-5678')
        self.aluna = Aluna.objects.create(
            nome='Ana', responsavel=self.responsavel
        )

    def _aviso(self, data_evento='futuro', horario='19h', **extra):
        if data_evento == 'futuro':
            data_evento = self.futuro
        aviso = Aviso.objects.create(
            titulo=extra.pop('titulo', 'Ensaio Geral'),
            descricao='x',
            tipo=extra.pop('tipo', 'ensaio'),
            data_evento=data_evento,
            horario=horario,
            enviar_whatsapp=extra.pop('enviar_whatsapp', True),
            ativo=extra.pop('ativo', True),
        )
        aviso.alunas.add(self.aluna)
        return aviso

    def _recente_para_antiga(self, aviso):
        """Faz os envios manuais já feitos parecerem antigos (fora da janela
        de proteção contra clique duplo)."""
        AvisoEnvioManual.objects.filter(aviso=aviso).update(
            criado_em=timezone.now() - JANELA_ANTIDUPLICIDADE * 5
        )


class EnviarAgoraServicoTests(BaseEnvioTests):
    @mock.patch(SENDER, return_value=(200, {}))
    def test_ensaio_futuro_envia_o_aviso_com_data_e_horario(self, enviar):
        aviso = self._aviso()

        resultado = enviar_agora(aviso, self.staff)

        enviar.assert_called_once_with(
            '5511912345678',
            TEMPLATE_SEMANA,
            [
                'Maria Silva',
                'Ensaio Geral',
                self.futuro.strftime('%d/%m/%Y'),
                '19h',
            ],
        )
        self.assertEqual(
            (resultado.total, resultado.enviados, resultado.erros), (1, 1, 0)
        )

        aviso.refresh_from_db()
        self.assertTrue(aviso.notificacao_semana_enviada)
        self.assertFalse(aviso.notificacao_dia_enviada)

        registro = AvisoEnvioManual.objects.get()
        self.assertEqual(registro.aviso, aviso)
        self.assertEqual(registro.enviado_por, self.staff)
        self.assertEqual(registro.template, TEMPLATE_SEMANA)
        self.assertEqual((registro.enviados, registro.erros), (1, 0))
        self.assertTrue(registro.concluido)

    @mock.patch(SENDER, return_value=(200, {}))
    def test_ensaio_de_hoje_envia_o_lembrete_do_dia(self, enviar):
        aviso = self._aviso(data_evento=self.hoje)

        enviar_agora(aviso, self.staff)

        enviar.assert_called_once_with(
            '5511912345678',
            TEMPLATE_DIA,
            ['Maria Silva', 'Ensaio Geral', '19h'],
        )
        aviso.refresh_from_db()
        self.assertTrue(aviso.notificacao_dia_enviada)
        self.assertTrue(aviso.notificacao_semana_enviada)

    @mock.patch(SENDER, return_value=(200, {}))
    def test_horario_vazio_vira_a_confirmar(self, enviar):
        enviar_agora(self._aviso(horario=''), self.staff)
        self.assertEqual(enviar.call_args.args[2][-1], 'horário a confirmar')

    # ---------- quando NÃO pode enviar ----------

    @mock.patch(SENDER, return_value=(200, {}))
    def test_bloqueios(self, enviar):
        casos = {
            'tipo': self._aviso(tipo='geral', titulo='A'),
            'inativo': self._aviso(ativo=False, titulo='B'),
            'sem_flag': self._aviso(enviar_whatsapp=False, titulo='C'),
            'sem_data': self._aviso(data_evento=None, titulo='D'),
            'passado': self._aviso(
                data_evento=self.hoje - timedelta(days=1), titulo='E'
            ),
        }
        for nome, aviso in casos.items():
            with self.subTest(nome):
                with self.assertRaises(EnvioNaoPermitido):
                    enviar_agora(aviso, self.staff)

        enviar.assert_not_called()
        self.assertEqual(AvisoEnvioManual.objects.count(), 0)

    @mock.patch(SENDER, return_value=(200, {}))
    def test_sem_destinatarios_com_whatsapp_nao_envia(self, enviar):
        Perfil.objects.filter(user=self.responsavel).update(telefone='')
        aviso = self._aviso()

        with self.assertRaises(EnvioNaoPermitido):
            enviar_agora(aviso, self.staff)

        enviar.assert_not_called()
        self.assertEqual(AvisoEnvioManual.objects.count(), 0)

    # ---------- clique duplo e reenvio ----------

    @mock.patch(SENDER, return_value=(200, {}))
    def test_clique_duplo_nao_envia_duas_vezes(self, enviar):
        aviso = self._aviso()

        enviar_agora(aviso, self.staff)
        with self.assertRaises(EnvioNaoPermitido):
            enviar_agora(aviso, self.staff)

        self.assertEqual(enviar.call_count, 1)
        self.assertEqual(AvisoEnvioManual.objects.count(), 1)

    @mock.patch(SENDER, return_value=(200, {}))
    def test_reenvio_exige_confirmacao(self, enviar):
        aviso = self._aviso()
        enviar_agora(aviso, self.staff)
        self._recente_para_antiga(aviso)

        with self.assertRaises(ReenvioPrecisaConfirmacao):
            enviar_agora(aviso, self.staff)
        self.assertEqual(enviar.call_count, 1)

        enviar_agora(aviso, self.staff, confirmou_reenvio=True)
        self.assertEqual(enviar.call_count, 2)

    @mock.patch(SENDER, return_value=(200, {}))
    def test_quem_o_cron_ja_avisou_tambem_exige_confirmacao(self, enviar):
        aviso = self._aviso()
        Aviso.objects.filter(pk=aviso.pk).update(
            notificacao_semana_enviada=True
        )

        with self.assertRaises(ReenvioPrecisaConfirmacao):
            enviar_agora(aviso, self.staff)
        enviar.assert_not_called()

    @mock.patch(SENDER, return_value=(200, {}))
    def test_lembrete_do_dia_nao_conta_como_reenvio_do_resumo(self, enviar):
        # O cron mandou o resumo no domingo; hoje é o dia do ensaio e a
        # mensagem manual é OUTRA (lembrete de hoje): não é repetição.
        aviso = self._aviso(data_evento=self.hoje)
        Aviso.objects.filter(pk=aviso.pk).update(
            notificacao_semana_enviada=True
        )

        enviar_agora(aviso, self.staff)

        enviar.assert_called_once()

    # ---------- falhas ----------

    @mock.patch(SENDER, return_value=(400, {'error': {'message': 'sem template'}}))
    def test_falha_total_nao_marca_os_controles_do_cron(self, enviar):
        aviso = self._aviso()

        resultado = enviar_agora(aviso, self.staff)

        self.assertEqual((resultado.enviados, resultado.erros), (0, 1))
        aviso.refresh_from_db()
        self.assertFalse(aviso.notificacao_semana_enviada)

        registro = AvisoEnvioManual.objects.get()
        self.assertEqual(registro.erros, 1)
        self.assertIn('sem template', registro.detalhe_erros)
        self.assertTrue(registro.concluido)

    def test_falha_parcial_marca_os_controles_e_lista_quem_falhou(self):
        outra = _usuario('resp2', '(21) 98888-7777', 'Joana', 'Costa')
        aviso = self._aviso()
        aviso.alunas.add(Aluna.objects.create(nome='Bia', responsavel=outra))

        def sender(numero, template, parametros):
            if numero == '5521988887777':
                return 500, {'error': {'message': 'falhou'}}
            return 200, {}

        with mock.patch(SENDER, side_effect=sender):
            resultado = enviar_agora(aviso, self.staff)

        self.assertEqual(
            (resultado.total, resultado.enviados, resultado.erros), (2, 1, 1)
        )
        self.assertEqual(resultado.falhas[0][0], 'Joana Costa')
        aviso.refresh_from_db()
        self.assertTrue(aviso.notificacao_semana_enviada)

    def test_excecao_ao_enviar_nao_para_os_demais(self):
        outra = _usuario('resp2', '(21) 98888-7777', 'Joana', 'Costa')
        aviso = self._aviso()
        aviso.alunas.add(Aluna.objects.create(nome='Bia', responsavel=outra))

        def sender(numero, template, parametros):
            if numero == '5511912345678':
                raise RuntimeError('rede caiu')
            return 200, {}

        with mock.patch(SENDER, side_effect=sender):
            resultado = enviar_agora(aviso, self.staff)

        self.assertEqual((resultado.enviados, resultado.erros), (1, 1))
        self.assertTrue(AvisoEnvioManual.objects.get().concluido)

    @mock.patch(SENDER, return_value=(500, {'error': {'message': 'x'}}))
    def test_registro_nao_guarda_telefone(self, enviar):
        enviar_agora(self._aviso(), self.staff)
        registro = AvisoEnvioManual.objects.get()
        self.assertNotIn('91234', registro.detalhe_erros)
        self.assertNotIn('5511', registro.detalhe_erros)

    # ---------- auxiliares ----------

    def test_contatos_sem_whatsapp_lista_quem_nao_recebera(self):
        sem_tel = _usuario('resp3', '', 'Sem', 'Telefone')
        aviso = self._aviso()
        aviso.alunas.add(Aluna.objects.create(nome='Bia', responsavel=sem_tel))
        aviso.alunas.add(Aluna.objects.create(nome='Cris'))  # sem responsável

        self.assertEqual(
            sorted(contatos_sem_whatsapp(aviso)), ['Bia', 'Cris']
        )


class IntegracaoComOCronTests(BaseEnvioTests):
    """O botão e o cron dividem os mesmos controles: não podem se atropelar."""

    def _cron(self, hoje):
        with mock.patch(CRON_HOJE, return_value=hoje), \
                mock.patch(CRON_SENDER, return_value=(200, {})) as enviar:
            call_command('enviar_avisos_ensaio', stdout=StringIO())
        return enviar

    @mock.patch(SENDER, return_value=(200, {}))
    def test_cron_do_domingo_nao_repete_o_que_o_botao_ja_enviou(self, _):
        domingo = date(2026, 10, 18)
        aviso = self._aviso(data_evento=date(2026, 10, 22))

        # Botão usado antes do domingo (a data real de "hoje" aqui não importa:
        # o envio manual só marca os controles).
        Aviso.objects.filter(pk=aviso.pk).update(
            notificacao_semana_enviada=True
        )

        self._cron(domingo).assert_not_called()

    @mock.patch(SENDER, return_value=(200, {}))
    def test_cron_ainda_manda_o_lembrete_do_dia_depois_do_botao(self, _):
        aviso = self._aviso()
        enviar_agora(aviso, self.staff)  # resumo manual hoje
        aviso.refresh_from_db()

        enviar = self._cron(self.futuro)

        enviar.assert_called_once()
        self.assertEqual(enviar.call_args.args[1], TEMPLATE_DIA)

    @mock.patch(SENDER, return_value=(400, {'error': {'message': 'x'}}))
    def test_botao_que_falhou_nao_impede_o_cron_de_enviar(self, _):
        domingo = date(2026, 10, 18)
        aviso = self._aviso(data_evento=date(2026, 10, 22))
        with mock.patch(
            'calendario_avisos.envio_whatsapp.timezone.localdate',
            return_value=date(2026, 10, 16),
        ):
            enviar_agora(aviso, self.staff)

        enviar = self._cron(domingo)

        enviar.assert_called_once()
        self.assertEqual(enviar.call_args.args[1], TEMPLATE_SEMANA)


@override_settings(STORAGES=STORAGES_TESTE)
class EnviarAgoraViewTests(BaseEnvioTests):
    def _url(self, aviso):
        return reverse('admin_dashboard:aviso_enviar_agora', args=[aviso.pk])

    # ---------- acesso ----------

    @mock.patch(SENDER, return_value=(200, {}))
    def test_visitante_e_usuario_comum_nao_acessam_nem_enviam(self, enviar):
        aviso = self._aviso()

        resposta = self.client.get(self._url(aviso))
        self.assertEqual(resposta.status_code, 302)
        self.assertIn('login', resposta['Location'])
        self.assertEqual(self.client.post(self._url(aviso)).status_code, 302)

        self.client.force_login(self.responsavel)  # logado, mas não é staff
        self.assertEqual(self.client.get(self._url(aviso)).status_code, 302)
        self.assertEqual(self.client.post(self._url(aviso)).status_code, 302)

        enviar.assert_not_called()
        self.assertEqual(AvisoEnvioManual.objects.count(), 0)

    def test_metodo_nao_permitido(self):
        self.client.force_login(self.staff)
        self.assertEqual(
            self.client.put(self._url(self._aviso())).status_code, 405
        )

    # ---------- tela de confirmação ----------

    def test_confirmacao_mostra_quem_vai_receber_sem_expor_o_telefone(self):
        self.client.force_login(self.staff)
        aviso = self._aviso()

        resposta = self.client.get(self._url(aviso))

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'Maria Silva')
        self.assertContains(resposta, 'Ana')
        self.assertContains(resposta, 'final 5678')
        self.assertNotContains(resposta, '91234-5678')
        self.assertNotContains(resposta, '5511912345678')
        self.assertContains(resposta, 'Enviar para 1 pessoa(s)')
        self.assertNotContains(resposta, 'confirmo_reenvio')

    def test_confirmacao_avisa_quem_nao_tem_telefone(self):
        self.client.force_login(self.staff)
        aviso = self._aviso()
        sem_tel = _usuario('resp3', '', 'Sem', 'Telefone')
        aviso.alunas.add(Aluna.objects.create(nome='Bia', responsavel=sem_tel))

        resposta = self.client.get(self._url(aviso))

        self.assertContains(resposta, 'receberão')
        self.assertContains(resposta, 'Bia')

    def test_confirmacao_de_aviso_ja_enviado_pede_checkbox(self):
        self.client.force_login(self.staff)
        aviso = self._aviso()
        Aviso.objects.filter(pk=aviso.pk).update(
            notificacao_semana_enviada=True
        )

        resposta = self.client.get(self._url(aviso))

        self.assertContains(resposta, 'name="confirmo_reenvio"')
        self.assertContains(resposta, 'já receberam')

    def test_confirmacao_de_aviso_bloqueado_explica_o_motivo(self):
        self.client.force_login(self.staff)
        aviso = self._aviso(enviar_whatsapp=False)

        resposta = self.client.get(self._url(aviso))

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'Enviar por WhatsApp também')
        self.assertNotContains(resposta, 'id="btn-enviar-agora"')

    # ---------- envio ----------

    @mock.patch(SENDER, return_value=(200, {}))
    def test_post_envia_e_volta_para_a_edicao(self, enviar):
        self.client.force_login(self.staff)
        aviso = self._aviso()

        resposta = self.client.post(self._url(aviso), follow=True)

        self.assertRedirects(
            resposta,
            reverse('admin_dashboard:aviso_editar', args=[aviso.pk]),
        )
        enviar.assert_called_once()
        self.assertContains(resposta, 'enviado para 1 pessoa(s)')
        # histórico aparece na tela de edição
        self.assertContains(resposta, '1 enviada(s)')
        aviso.refresh_from_db()
        self.assertTrue(aviso.notificacao_semana_enviada)

    @mock.patch(SENDER, return_value=(200, {}))
    def test_post_de_aviso_ja_enviado_sem_confirmar_nao_envia(self, enviar):
        self.client.force_login(self.staff)
        aviso = self._aviso()
        Aviso.objects.filter(pk=aviso.pk).update(
            notificacao_semana_enviada=True
        )

        resposta = self.client.post(self._url(aviso))

        self.assertRedirects(
            resposta, self._url(aviso), fetch_redirect_response=False
        )
        enviar.assert_not_called()

    @mock.patch(SENDER, return_value=(200, {}))
    def test_post_de_aviso_ja_enviado_com_confirmacao_envia(self, enviar):
        self.client.force_login(self.staff)
        aviso = self._aviso()
        Aviso.objects.filter(pk=aviso.pk).update(
            notificacao_semana_enviada=True
        )

        self.client.post(self._url(aviso), {'confirmo_reenvio': 'on'})

        enviar.assert_called_once()

    @mock.patch(SENDER, return_value=(200, {}))
    def test_post_de_aviso_bloqueado_nao_envia(self, enviar):
        self.client.force_login(self.staff)
        aviso = self._aviso(tipo='geral')

        resposta = self.client.post(self._url(aviso), follow=True)

        enviar.assert_not_called()
        self.assertContains(resposta, 'Ensaio')

    def test_falha_parcial_mostra_quem_nao_recebeu(self):
        self.client.force_login(self.staff)
        outra = _usuario('resp2', '(21) 98888-7777', 'Joana', 'Costa')
        aviso = self._aviso()
        aviso.alunas.add(Aluna.objects.create(nome='Bia', responsavel=outra))

        def sender(numero, template, parametros):
            if numero == '5521988887777':
                return 500, {'error': {'message': 'falhou'}}
            return 200, {}

        with mock.patch(SENDER, side_effect=sender):
            resposta = self.client.post(self._url(aviso), follow=True)

        self.assertContains(resposta, 'Enviado para 1 de 2')
        self.assertContains(resposta, 'Joana Costa')

    @mock.patch(SENDER, return_value=(400, {'error': {'message': 'sem template'}}))
    def test_falha_total_mostra_o_motivo(self, enviar):
        self.client.force_login(self.staff)
        aviso = self._aviso()

        resposta = self.client.post(self._url(aviso), follow=True)

        self.assertContains(resposta, 'Nenhuma mensagem foi enviada')
        self.assertContains(resposta, 'sem template')

    # ---------- tela de edição ----------

    def test_edicao_mostra_o_botao_quando_pode_enviar(self):
        self.client.force_login(self.staff)
        aviso = self._aviso()

        resposta = self.client.get(
            reverse('admin_dashboard:aviso_editar', args=[aviso.pk])
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'Enviar agora por WhatsApp')
        self.assertContains(resposta, self._url(aviso))
        self.assertContains(resposta, 'Ainda não foi enviada')

    def test_edicao_explica_por_que_nao_pode_enviar(self):
        self.client.force_login(self.staff)
        aviso = self._aviso(enviar_whatsapp=False)

        resposta = self.client.get(
            reverse('admin_dashboard:aviso_editar', args=[aviso.pk])
        )

        self.assertContains(resposta, 'Enviar agora por WhatsApp')
        self.assertContains(resposta, 'salve o aviso para poder')
        self.assertNotContains(resposta, 'aviso-envio-botao">Enviar agora')
