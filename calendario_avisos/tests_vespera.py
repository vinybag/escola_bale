"""
Lembrete de véspera: caixinha "Lembrar também um dia antes" no aviso.
"""

from datetime import date, datetime, timedelta
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
    TEMPLATE_VESPERA,
    avisos_para_vespera,
    parametros_base_template,
    previsao_envio_automatico,
)
from calendario_avisos.models import Aviso, AvisoEnvioManual
from usuarios.models import Aluna, Perfil

SENDER = (
    'calendario_avisos.management.commands.enviar_avisos_ensaio'
    '.enviar_whatsapp_template'
)
HOJE = (
    'calendario_avisos.management.commands.enviar_avisos_ensaio'
    '.timezone.localdate'
)

# Outubro de 2026: dom 18 | seg 19 ter 20 qua 21 qui 22 sex 23 sáb 24 | dom 25
DOM_18 = date(2026, 10, 18)
SEG = date(2026, 10, 19)
TER = date(2026, 10, 20)
QUA = date(2026, 10, 21)
QUI = date(2026, 10, 22)
SEX = date(2026, 10, 23)
SAB = date(2026, 10, 24)
DOM_25 = date(2026, 10, 25)
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

    def _aviso(self, data_evento=QUI, horario='14h às 15h', **extra):
        aviso = Aviso.objects.create(
            titulo=extra.pop('titulo', 'Cora e Dora'),
            descricao='x',
            tipo=extra.pop('tipo', 'ensaio'),
            data_evento=data_evento,
            horario=horario,
            enviar_whatsapp=extra.pop('enviar_whatsapp', True),
            ativo=extra.pop('ativo', True),
            lembrar_vespera=extra.pop('lembrar_vespera', True),
            notificacao_semana_enviada=extra.pop(
                'notificacao_semana_enviada', True
            ),
            notificacao_vespera_enviada=extra.pop(
                'notificacao_vespera_enviada', False
            ),
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


class VesperaComandoTests(BaseTests):
    def test_envia_o_lembrete_um_dia_antes(self):
        aviso = self._aviso(data_evento=QUI)

        enviar = self._rodar(QUA)

        enviar.assert_called_once_with(
            '5511912345678',
            TEMPLATE_VESPERA,
            ['Maria Silva', 'Cora e Dora', '14h às 15h'],
        )
        aviso.refresh_from_db()
        self.assertTrue(aviso.notificacao_vespera_enviada)

    def test_so_envia_se_a_caixinha_estiver_marcada(self):
        self._aviso(data_evento=QUI, lembrar_vespera=False)
        self.assertEqual(self._rodar(QUA).call_count, 0)

    def test_so_na_vespera_e_nao_em_outros_dias(self):
        self._aviso(data_evento=QUI)

        for hoje in (SEG, TER):  # 3 e 2 dias antes
            self.assertEqual(self._rodar(hoje).call_count, 0, hoje)

    def test_no_dia_do_ensaio_so_vale_o_lembrete_do_dia(self):
        self._aviso(data_evento=QUI, notificacao_vespera_enviada=True)

        enviar = self._rodar(QUI)

        enviar.assert_called_once()
        self.assertEqual(enviar.call_args.args[1], TEMPLATE_DIA)

    def test_nao_repete_se_o_comando_rodar_de_novo_no_mesmo_dia(self):
        self._aviso(data_evento=QUI)

        self.assertEqual(self._rodar(QUA).call_count, 1)
        self.assertEqual(self._rodar(QUA).call_count, 0)

    def test_sequencia_completa_resumo_vespera_e_dia(self):
        """Domingo -> resumo; quarta -> véspera; quinta -> lembrete do dia."""
        self._aviso(data_evento=QUI, notificacao_semana_enviada=False)

        dom = self._rodar(DOM_18)
        self.assertEqual([c.args[1] for c in dom.call_args_list], [TEMPLATE_SEMANA])

        qua = self._rodar(QUA)
        self.assertEqual([c.args[1] for c in qua.call_args_list], [TEMPLATE_VESPERA])

        qui = self._rodar(QUI)
        self.assertEqual([c.args[1] for c in qui.call_args_list], [TEMPLATE_DIA])

    # ---------- não repetir a mesma informação no mesmo dia ----------

    def test_resumo_de_ultima_hora_no_mesmo_dia_dispensa_a_vespera(self):
        # Aviso criado na quarta para quinta, com a caixinha marcada: o
        # resumo de última hora já avisa; mandar a véspera junto seria repetir.
        aviso = self._aviso(data_evento=QUI, notificacao_semana_enviada=False)

        enviar = self._rodar(QUA)

        self.assertEqual(
            [c.args[1] for c in enviar.call_args_list], [TEMPLATE_SEMANA]
        )
        aviso.refresh_from_db()
        self.assertTrue(aviso.notificacao_semana_enviada)
        self.assertTrue(aviso.notificacao_vespera_enviada)  # tratada

        # Na quinta, só o lembrete do dia.
        qui = self._rodar(QUI)
        self.assertEqual([c.args[1] for c in qui.call_args_list], [TEMPLATE_DIA])

    def test_resumo_de_domingo_para_ensaio_de_segunda_dispensa_a_vespera(self):
        aviso = self._aviso(
            data_evento=SEG, notificacao_semana_enviada=False
        )

        enviar = self._rodar(DOM_18)

        self.assertEqual(
            [c.args[1] for c in enviar.call_args_list], [TEMPLATE_SEMANA]
        )
        aviso.refresh_from_db()
        self.assertTrue(aviso.notificacao_vespera_enviada)

    def test_envio_manual_no_mesmo_dia_dispensa_a_vespera(self):
        aviso = self._aviso(data_evento=QUI)
        envio = AvisoEnvioManual.objects.create(
            aviso=aviso, template=TEMPLATE_SEMANA,
            total_destinatarios=1, enviados=1, concluido=True,
        )
        AvisoEnvioManual.objects.filter(pk=envio.pk).update(
            criado_em=timezone.make_aware(datetime(2026, 10, 21, 9, 0))
        )

        enviar = self._rodar(QUA)

        enviar.assert_not_called()
        aviso.refresh_from_db()
        self.assertTrue(aviso.notificacao_vespera_enviada)

    def test_envio_manual_de_outro_dia_nao_dispensa_a_vespera(self):
        aviso = self._aviso(data_evento=QUI)
        envio = AvisoEnvioManual.objects.create(
            aviso=aviso, template=TEMPLATE_SEMANA,
            total_destinatarios=1, enviados=1, concluido=True,
        )
        AvisoEnvioManual.objects.filter(pk=envio.pk).update(
            criado_em=timezone.make_aware(datetime(2026, 10, 19, 9, 0))
        )

        self.assertEqual(self._rodar(QUA).call_count, 1)

    def test_envio_manual_que_falhou_nao_dispensa_a_vespera(self):
        aviso = self._aviso(data_evento=QUI)
        envio = AvisoEnvioManual.objects.create(
            aviso=aviso, template=TEMPLATE_SEMANA,
            total_destinatarios=1, enviados=0, erros=1, concluido=True,
        )
        AvisoEnvioManual.objects.filter(pk=envio.pk).update(
            criado_em=timezone.make_aware(datetime(2026, 10, 21, 9, 0))
        )

        self.assertEqual(self._rodar(QUA).call_count, 1)

    # ---------- falhas ----------

    def test_falha_total_permite_nova_tentativa(self):
        aviso = self._aviso(data_evento=QUI)

        self._rodar(QUA, retorno=(500, {'error': {'message': 'x'}}))
        aviso.refresh_from_db()
        self.assertFalse(aviso.notificacao_vespera_enviada)

        self.assertEqual(self._rodar(QUA).call_count, 1)

    def test_falha_parcial_nao_repete_para_quem_ja_recebeu(self):
        outra = _usuario('resp2', '(21) 98888-7777', 'Joana', 'Costa')
        aviso = self._aviso(data_evento=QUI)
        aviso.alunas.add(Aluna.objects.create(nome='Bia', responsavel=outra))

        def sender(numero, template, parametros):
            return (500, {}) if numero == '5521988887777' else (200, {})

        with mock.patch(HOJE, return_value=QUA), \
                mock.patch(SENDER, side_effect=sender):
            call_command('enviar_avisos_ensaio', stdout=StringIO())

        aviso.refresh_from_db()
        self.assertTrue(aviso.notificacao_vespera_enviada)
        self.assertEqual(self._rodar(QUA).call_count, 0)

    # ---------- quem entra ----------

    def test_nao_ensaio_inativo_ou_sem_whatsapp_nao_envia(self):
        self._aviso(tipo='geral', titulo='A')
        self._aviso(ativo=False, titulo='B')
        self._aviso(enviar_whatsapp=False, titulo='C')

        self.assertEqual(self._rodar(QUA).call_count, 0)

    def test_dois_avisos_marcados_cada_um_recebe_o_seu(self):
        self._aviso(titulo='A')
        self._aviso(titulo='B')

        enviar = self._rodar(QUA)

        titulos = sorted(c.args[2][1] for c in enviar.call_args_list)
        self.assertEqual(titulos, ['A', 'B'])

    def test_saida_do_comando_informa_os_lembretes_de_vespera(self):
        self._aviso()
        saida = StringIO()

        self._rodar(QUA, saida=saida)

        self.assertIn('Lembretes de véspera enviados: 1', saida.getvalue())
        self.assertIn('Avisos de ensaio enviados: 1 | Erros: 0', saida.getvalue())

    def test_sem_vespera_a_saida_nao_muda(self):
        saida = StringIO()
        self._rodar(QUA, saida=saida)
        self.assertNotIn('véspera', saida.getvalue())

    def test_vespera_nao_interfere_nos_avisos_sem_a_caixinha(self):
        # Aviso comum, sem a caixinha: comportamento de sempre.
        self._aviso(lembrar_vespera=False, notificacao_semana_enviada=False)
        enviar = self._rodar(QUA)
        self.assertEqual(
            [c.args[1] for c in enviar.call_args_list], [TEMPLATE_SEMANA]
        )


class FuncoesDaVesperaTests(BaseTests):
    def test_parametros_do_modelo_de_vespera_sao_os_mesmos_do_lembrete_do_dia(self):
        aviso = self._aviso()
        self.assertEqual(
            parametros_base_template(aviso, TEMPLATE_VESPERA),
            parametros_base_template(aviso, TEMPLATE_DIA),
        )
        self.assertEqual(
            parametros_base_template(aviso, TEMPLATE_VESPERA),
            ['Cora e Dora', '14h às 15h'],
        )

    def test_horario_vazio_vira_a_confirmar(self):
        aviso = self._aviso(horario='')
        self.assertEqual(
            parametros_base_template(aviso, TEMPLATE_VESPERA)[-1],
            'horário a confirmar',
        )

    def test_selecao_considera_so_amanha(self):
        a = self._aviso(data_evento=QUI)
        self._aviso(data_evento=SEX, titulo='outro dia')

        self.assertEqual(list(avisos_para_vespera(QUA)), [a])

    def test_previsao_menciona_a_vespera_quando_ainda_vai_sair(self):
        aviso = self._aviso(data_evento=TER_27, notificacao_semana_enviada=False)
        texto = previsao_envio_automatico(aviso, SEG)
        self.assertIn('Lembrete de véspera: 26/10', texto)

    def test_previsao_nao_menciona_a_vespera_sem_a_caixinha(self):
        aviso = self._aviso(data_evento=TER_27, lembrar_vespera=False)
        self.assertNotIn('véspera', previsao_envio_automatico(aviso, SEG))

    def test_previsao_nao_menciona_a_vespera_se_ela_ja_saiu_ou_e_hoje(self):
        ja_saiu = self._aviso(data_evento=TER_27, notificacao_vespera_enviada=True)
        self.assertNotIn('véspera', previsao_envio_automatico(ja_saiu, SEG))

        # véspera de um ensaio de amanhã é HOJE: o aviso do dia já está
        # coberto pelo resumo/lembrete e a frase só confundiria
        amanha = self._aviso(data_evento=QUI)
        self.assertNotIn('véspera', previsao_envio_automatico(amanha, QUA))


@override_settings(STORAGES=STORAGES_TESTE)
class FormulariosDaVesperaTests(BaseTests):
    def setUp(self):
        super().setUp()
        self.staff = _usuario('staff', '(11) 90000-0000', is_staff=True)
        self.client.force_login(self.staff)

    def _post_editar(self, aviso, **campos):
        dados = {
            'titulo': aviso.titulo,
            'descricao': 'x',
            'data_evento': str(aviso.data_evento),
            'horario': aviso.horario,
            'tipo': 'ensaio',
            'enviar_whatsapp': 'on',
        }
        dados.update(campos)
        return self.client.post(
            reverse('admin_dashboard:aviso_editar', args=[aviso.pk]), dados
        )

    def test_criar_aviso_com_a_caixinha_marcada(self):
        resposta = self.client.post(reverse('admin_dashboard:aviso_criar'), {
            'titulo': 'Cora e Dora',
            'descricao': 'x',
            'data_evento': '2026-10-22',
            'horario': '14h às 15h',
            'tipo': 'ensaio',
            'enviar_whatsapp': 'on',
            'lembrar_vespera': 'on',
        })

        self.assertEqual(resposta.status_code, 302)
        aviso = Aviso.objects.get()
        self.assertTrue(aviso.lembrar_vespera)
        self.assertFalse(aviso.notificacao_vespera_enviada)

    def test_criar_aviso_sem_marcar_nao_ativa(self):
        self.client.post(reverse('admin_dashboard:aviso_criar'), {
            'titulo': 'A', 'descricao': 'x', 'data_evento': '2026-10-22',
            'tipo': 'ensaio', 'enviar_whatsapp': 'on',
        })
        self.assertFalse(Aviso.objects.get().lembrar_vespera)

    def test_editar_liga_e_desliga_a_caixinha(self):
        aviso = self._aviso(lembrar_vespera=False)

        self._post_editar(aviso, lembrar_vespera='on')
        aviso.refresh_from_db()
        self.assertTrue(aviso.lembrar_vespera)

        self._post_editar(aviso)  # sem a caixinha
        aviso.refresh_from_db()
        self.assertFalse(aviso.lembrar_vespera)

    def test_editar_mostra_a_caixinha_marcada(self):
        aviso = self._aviso(lembrar_vespera=True)
        resposta = self.client.get(
            reverse('admin_dashboard:aviso_editar', args=[aviso.pk])
        )
        self.assertContains(resposta, 'Lembrar também um dia antes')
        self.assertRegex(
            resposta.content.decode(),
            r'name="lembrar_vespera"\s+checked',
        )

    def test_editar_mostra_a_caixinha_desmarcada(self):
        aviso = self._aviso(lembrar_vespera=False)
        resposta = self.client.get(
            reverse('admin_dashboard:aviso_editar', args=[aviso.pk])
        )
        self.assertNotRegex(
            resposta.content.decode(),
            r'name="lembrar_vespera"\s+checked',
        )

    def test_criar_mostra_a_caixinha(self):
        resposta = self.client.get(reverse('admin_dashboard:aviso_criar'))
        self.assertContains(resposta, 'name="lembrar_vespera"')

    def test_mudar_a_data_reabilita_a_vespera(self):
        aviso = self._aviso(
            data_evento=QUI, notificacao_vespera_enviada=True
        )

        self._post_editar(aviso, data_evento='2026-10-29', lembrar_vespera='on')

        aviso.refresh_from_db()
        self.assertEqual(aviso.data_evento, date(2026, 10, 29))
        self.assertFalse(aviso.notificacao_vespera_enviada)

    def test_salvar_sem_mudar_a_data_nao_reabilita_a_vespera(self):
        aviso = self._aviso(
            data_evento=QUI, notificacao_vespera_enviada=True
        )

        self._post_editar(aviso, lembrar_vespera='on', horario='15h')

        aviso.refresh_from_db()
        self.assertTrue(aviso.notificacao_vespera_enviada)
