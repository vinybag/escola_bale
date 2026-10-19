"""
Resumo de última hora: ensaios da semana em curso que o domingo não cobriu.

Antes, um aviso criado (ou ligado ao WhatsApp) depois do domingo só chegava
no dia do ensaio. Agora o cron diário também manda o resumo desses avisos.
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
    TEMPLATE_DIA,
    TEMPLATE_SEMANA,
    avisos_para_resumo_atrasado,
    domingo_do_resumo,
    enviar_agora,
    fim_da_semana_em_curso,
    previsao_envio_automatico,
)
from calendario_avisos.models import Aviso
from usuarios.models import Aluna, Perfil

SENDER = (
    'calendario_avisos.management.commands.enviar_avisos_ensaio'
    '.enviar_whatsapp_template'
)
HOJE = (
    'calendario_avisos.management.commands.enviar_avisos_ensaio'
    '.timezone.localdate'
)
SENDER_BOTAO = 'calendario_avisos.envio_whatsapp.enviar_whatsapp_template'

# Outubro de 2026: dom 18 | seg 19 ter 20 qua 21 qui 22 sex 23 sáb 24 | dom 25
DOM_18 = date(2026, 10, 18)
SEG = date(2026, 10, 19)
TER = date(2026, 10, 20)
QUA = date(2026, 10, 21)
QUI = date(2026, 10, 22)
SEX = date(2026, 10, 23)
SAB = date(2026, 10, 24)
DOM_25 = date(2026, 10, 25)
SEG_26 = date(2026, 10, 26)
TER_27 = date(2026, 10, 27)

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


class BaseTests(TestCase):
    def setUp(self):
        self.responsavel = _usuario('resp', '(11) 91234-5678')
        self.aluna = Aluna.objects.create(
            nome='Ana', responsavel=self.responsavel
        )

    def _aviso(self, data_evento=QUI, horario='19h', **extra):
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

    def _rodar(self, hoje, retorno=(200, {}), saida=None):
        with mock.patch(HOJE, return_value=hoje), \
                mock.patch(SENDER, return_value=retorno) as enviar:
            call_command(
                'enviar_avisos_ensaio',
                stdout=saida if saida is not None else StringIO(),
            )
        return enviar


class ResumoAtrasadoComandoTests(BaseTests):
    def test_aviso_criado_depois_do_domingo_recebe_resumo_no_proximo_disparo(self):
        aviso = self._aviso(data_evento=QUI)

        enviar = self._rodar(SEG)

        enviar.assert_called_once_with(
            '5511912345678',
            TEMPLATE_SEMANA,
            ['Maria Silva', 'Ensaio Geral', '22/10/2026', '19h'],
        )
        aviso.refresh_from_db()
        self.assertTrue(aviso.notificacao_semana_enviada)
        self.assertFalse(aviso.notificacao_dia_enviada)

    def test_funciona_de_segunda_a_sabado(self):
        for hoje in (SEG, TER, QUA, QUI, SEX, SAB):
            with self.subTest(hoje=hoje):
                Aviso.objects.all().delete()
                self._aviso(data_evento=DOM_25)  # último dia da semana

                enviar = self._rodar(hoje)

                self.assertEqual(enviar.call_count, 1)

    def test_o_que_o_domingo_ja_mandou_nao_e_repetido(self):
        aviso = self._aviso(data_evento=QUI)
        self._rodar(DOM_18)  # resumo normal de domingo
        aviso.refresh_from_db()
        self.assertTrue(aviso.notificacao_semana_enviada)

        enviar = self._rodar(SEG)

        enviar.assert_not_called()

    def test_so_envia_uma_vez(self):
        self._aviso(data_evento=QUI)

        self.assertEqual(self._rodar(SEG).call_count, 1)
        self.assertEqual(self._rodar(SEG).call_count, 0)
        self.assertEqual(self._rodar(TER).call_count, 0)

    # ---------- limites da janela ----------

    def test_ensaio_da_semana_seguinte_espera_o_domingo(self):
        aviso = self._aviso(data_evento=TER_27)

        for hoje in (SEG, QUA, SAB):
            self.assertEqual(self._rodar(hoje).call_count, 0)

        # No domingo, o resumo normal cuida dele, uma única vez.
        enviar = self._rodar(DOM_25)
        self.assertEqual(enviar.call_count, 1)
        self.assertEqual(enviar.call_args.args[1], TEMPLATE_SEMANA)
        aviso.refresh_from_db()
        self.assertTrue(aviso.notificacao_semana_enviada)

    def test_domingo_e_o_ultimo_dia_da_semana_em_curso(self):
        self._aviso(data_evento=DOM_25)
        self.assertEqual(self._rodar(SEG).call_count, 1)

    def test_segunda_seguinte_nao_entra(self):
        self._aviso(data_evento=SEG_26)
        self.assertEqual(self._rodar(SEG).call_count, 0)

    def test_ensaio_de_hoje_recebe_so_o_lembrete_do_dia(self):
        self._aviso(data_evento=QUI)

        enviar = self._rodar(QUI)

        enviar.assert_called_once_with(
            '5511912345678',
            TEMPLATE_DIA,
            ['Maria Silva', 'Ensaio Geral', '19h'],
        )

    def test_aos_domingos_so_vale_o_resumo_normal(self):
        # Domingo 18: o ensaio de segunda 26 não é da semana seguinte, e o da
        # quinta 22 sim. Cada um sai por UMA regra só, sem duplicar.
        a = self._aviso(data_evento=QUI, titulo='A')
        b = self._aviso(data_evento=SEG_26, titulo='B')

        enviar = self._rodar(DOM_18)

        self.assertEqual(enviar.call_count, 1)
        self.assertEqual(enviar.call_args.args[2][1], 'A')
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertTrue(a.notificacao_semana_enviada)
        self.assertFalse(b.notificacao_semana_enviada)

    # ---------- depois do resumo, o lembrete do dia continua ----------

    def test_resumo_de_ultima_hora_e_depois_o_lembrete_do_dia(self):
        self._aviso(data_evento=QUI)

        resumo = self._rodar(SEG)
        self.assertEqual(resumo.call_args.args[1], TEMPLATE_SEMANA)

        lembrete = self._rodar(QUI)
        lembrete.assert_called_once()
        self.assertEqual(lembrete.call_args.args[1], TEMPLATE_DIA)

    # ---------- falhas ----------

    def test_falha_total_tenta_de_novo_no_disparo_seguinte(self):
        aviso = self._aviso(data_evento=QUI)

        self._rodar(SEG, retorno=(500, {'error': {'message': 'x'}}))
        aviso.refresh_from_db()
        self.assertFalse(aviso.notificacao_semana_enviada)

        enviar = self._rodar(TER)
        self.assertEqual(enviar.call_count, 1)
        aviso.refresh_from_db()
        self.assertTrue(aviso.notificacao_semana_enviada)

    def test_falha_parcial_nao_repete_para_quem_ja_recebeu(self):
        outra = _usuario('resp2', '(21) 98888-7777', 'Joana', 'Costa')
        aviso = self._aviso(data_evento=QUI)
        aviso.alunas.add(Aluna.objects.create(nome='Bia', responsavel=outra))

        def sender(numero, template, parametros):
            return (500, {}) if numero == '5521988887777' else (200, {})

        with mock.patch(HOJE, return_value=SEG), \
                mock.patch(SENDER, side_effect=sender):
            call_command('enviar_avisos_ensaio', stdout=StringIO())

        aviso.refresh_from_db()
        self.assertTrue(aviso.notificacao_semana_enviada)
        self.assertEqual(self._rodar(TER).call_count, 0)

    def test_sem_destinatarios_com_telefone_nao_marca_como_enviado(self):
        Perfil.objects.filter(user=self.responsavel).update(telefone='')
        aviso = self._aviso(data_evento=QUI)

        enviar = self._rodar(SEG)

        enviar.assert_not_called()
        aviso.refresh_from_db()
        self.assertFalse(aviso.notificacao_semana_enviada)

    # ---------- quem entra ----------

    def test_nao_ensaio_inativo_ou_sem_whatsapp_nao_envia(self):
        self._aviso(tipo='geral', titulo='A')
        self._aviso(ativo=False, titulo='B')
        self._aviso(enviar_whatsapp=False, titulo='C')

        self.assertEqual(self._rodar(SEG).call_count, 0)

    def test_whatsapp_ligado_no_meio_da_semana_e_recuperado(self):
        aviso = self._aviso(data_evento=QUI, enviar_whatsapp=False)
        self.assertEqual(self._rodar(SEG).call_count, 0)

        Aviso.objects.filter(pk=aviso.pk).update(enviar_whatsapp=True)

        self.assertEqual(self._rodar(TER).call_count, 1)

    def test_domingo_em_que_o_cron_nao_rodou_e_recuperado(self):
        # Nenhum disparo de domingo aconteceu: o aviso segue sem resumo.
        self._aviso(data_evento=QUI)
        self.assertEqual(self._rodar(TER).call_count, 1)

    def test_data_mudada_para_esta_semana_e_recuperada(self):
        aviso = self._aviso(data_evento=TER_27)  # semana seguinte
        self.assertEqual(self._rodar(SEG).call_count, 0)

        Aviso.objects.filter(pk=aviso.pk).update(data_evento=QUI)

        self.assertEqual(self._rodar(TER).call_count, 1)

    def test_resumo_enviado_pelo_botao_nao_e_repetido(self):
        staff = _usuario('staff', '(11) 90000-0000', is_staff=True)
        aviso = self._aviso(data_evento=QUI)
        with mock.patch(SENDER_BOTAO, return_value=(200, {})):
            with mock.patch(
                'calendario_avisos.envio_whatsapp.timezone.localdate',
                return_value=SEG,
            ):
                enviar_agora(aviso, staff, hoje=SEG)

        self.assertEqual(self._rodar(TER).call_count, 0)

    # ---------- chave de desligamento e saída ----------

    @override_settings(AVISOS_ENSAIO_ENVIO_ATRASADO_ATIVO=False)
    def test_pode_ser_desligado_pela_configuracao(self):
        self._aviso(data_evento=QUI)

        self.assertEqual(self._rodar(SEG).call_count, 0)

    @override_settings(AVISOS_ENSAIO_ENVIO_ATRASADO_ATIVO=False)
    def test_desligado_nao_afeta_o_resumo_de_domingo_nem_o_lembrete(self):
        self._aviso(data_evento=QUI)
        self.assertEqual(self._rodar(DOM_18).call_count, 1)

        Aviso.objects.all().delete()
        self._aviso(data_evento=QUI)
        self.assertEqual(self._rodar(QUI).call_count, 1)

    def test_saida_do_comando_informa_o_resumo_de_ultima_hora(self):
        self._aviso(data_evento=QUI)
        saida = StringIO()

        self._rodar(SEG, saida=saida)

        texto = saida.getvalue()
        self.assertIn('Resumos de última hora enviados: 1', texto)
        # A linha final de sempre continua igual (logs/monitoramento).
        self.assertIn('Avisos de ensaio enviados: 1 | Erros: 0', texto)

    def test_sem_resumo_de_ultima_hora_a_saida_nao_muda(self):
        saida = StringIO()
        self._rodar(SEG, saida=saida)
        self.assertNotIn('última hora', saida.getvalue())
        self.assertIn('Avisos de ensaio enviados: 0 | Erros: 0', saida.getvalue())


class FuncoesDeSemanaTests(TestCase):
    def test_fim_da_semana_em_curso(self):
        self.assertEqual(fim_da_semana_em_curso(SEG), DOM_25)
        self.assertEqual(fim_da_semana_em_curso(QUA), DOM_25)
        self.assertEqual(fim_da_semana_em_curso(SAB), DOM_25)
        self.assertEqual(fim_da_semana_em_curso(DOM_25), DOM_25)

    def test_domingo_do_resumo(self):
        # Todo o intervalo seg 26/10 .. dom 01/11 é resumido no domingo 25/10.
        for dia in range(26, 32):
            self.assertEqual(
                domingo_do_resumo(date(2026, 10, dia)), DOM_25, dia
            )
        self.assertEqual(domingo_do_resumo(date(2026, 11, 1)), DOM_25)

    def test_nada_aos_domingos(self):
        self.assertEqual(avisos_para_resumo_atrasado(DOM_25).count(), 0)


class PrevisaoDoEnvioAutomaticoTests(BaseTests):
    def test_ensaio_desta_semana_sem_resumo(self):
        texto = previsao_envio_automatico(self._aviso(data_evento=QUI), SEG)
        self.assertIn('é desta semana', texto)
        self.assertIn('próximo disparo automático', texto)

    def test_ensaio_da_semana_seguinte_diz_o_domingo(self):
        texto = previsao_envio_automatico(self._aviso(data_evento=TER_27), SEG)
        self.assertIn('domingo, 25/10', texto)

    def test_domingo_de_hoje(self):
        texto = previsao_envio_automatico(self._aviso(data_evento=TER_27), DOM_25)
        self.assertIn('domingo (hoje)', texto)

    def test_resumo_ja_enviado(self):
        aviso = self._aviso(data_evento=QUI)
        aviso.notificacao_semana_enviada = True
        self.assertIn('já foi enviado', previsao_envio_automatico(aviso, SEG))

    def test_dia_do_ensaio(self):
        aviso = self._aviso(data_evento=SEG)
        self.assertIn('Hoje é o dia', previsao_envio_automatico(aviso, SEG))
        aviso.notificacao_dia_enviada = True
        self.assertIn('já foi enviado', previsao_envio_automatico(aviso, SEG))

    def test_ensaio_passado_ou_sem_data(self):
        self.assertEqual(
            previsao_envio_automatico(self._aviso(data_evento=SEG), TER), ''
        )
        self.assertEqual(
            previsao_envio_automatico(self._aviso(data_evento=None), SEG), ''
        )


@override_settings(STORAGES=STORAGES_TESTE)
class TelaDeEdicaoMostraAPrevisaoTests(BaseTests):
    def test_edicao_mostra_quando_o_sistema_envia_sozinho(self):
        staff = _usuario('staff', '(11) 90000-0000', is_staff=True)
        self.client.force_login(staff)
        # ensaio daqui a 3 dias: sempre dentro da semana em curso OU da
        # seguinte; o texto muda, mas sempre informa o envio automático
        aviso = self._aviso(data_evento=timezone.localdate() + timedelta(days=3))

        resposta = self.client.get(
            reverse('admin_dashboard:aviso_editar', args=[aviso.pk])
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'Envio automático:')
