"""
Pin "Já enviado" nos avisos enviados por WhatsApp (listagem e edição).

O ponto central: o pin só diz "enviado" se mensagens realmente saíram. A
marca antiga "já enviei" do aviso não prova isso (o resumo de domingo é
marcado mesmo que todas as mensagens falhem), então o pin se baseia no
registro do resultado de cada envio.
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
    PIN_ENVIADO,
    PIN_FALHAS,
    TEMPLATE_DIA,
    TEMPLATE_SEMANA,
    TEMPLATE_VESPERA,
    anexar_pin_de_envio,
    historico_completo,
    pin_de_envio_por_aviso,
)
from calendario_avisos.models import (
    Aviso,
    AvisoEnvioAutomatico,
    AvisoEnvioManual,
)
from usuarios.models import Aluna, Perfil

SENDER = (
    'calendario_avisos.management.commands.enviar_avisos_ensaio'
    '.enviar_whatsapp_template'
)
HOJE = (
    'calendario_avisos.management.commands.enviar_avisos_ensaio'
    '.timezone.localdate'
)

DOM_18 = date(2026, 10, 18)
QUA = date(2026, 10, 21)
QUI = date(2026, 10, 22)

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

    def _aviso(self, data_evento=None, **extra):
        aviso = Aviso.objects.create(
            titulo=extra.pop('titulo', 'Ensaio Geral'),
            descricao='x',
            tipo='ensaio',
            data_evento=data_evento or (timezone.localdate() + timedelta(days=3)),
            horario='19h',
            enviar_whatsapp=extra.pop('enviar_whatsapp', True),
            lembrar_vespera=extra.pop('lembrar_vespera', False),
            notificacao_semana_enviada=extra.pop('semana', False),
            notificacao_dia_enviada=extra.pop('dia', False),
            notificacao_vespera_enviada=extra.pop('vespera', False),
        )
        aviso.alunas.add(self.aluna)
        return aviso

    def _auto(self, aviso, template=TEMPLATE_SEMANA, enviados=1, erros=0,
              quando=None):
        envio = AvisoEnvioAutomatico.objects.create(
            aviso=aviso, template=template,
            total_destinatarios=enviados + erros,
            enviados=enviados, erros=erros,
        )
        if quando:
            AvisoEnvioAutomatico.objects.filter(pk=envio.pk).update(
                criado_em=quando
            )
        return envio

    def _manual(self, aviso, template=TEMPLATE_SEMANA, enviados=1, erros=0,
                concluido=True, quando=None, por=None):
        envio = AvisoEnvioManual.objects.create(
            aviso=aviso, template=template, enviado_por=por,
            total_destinatarios=enviados + erros,
            enviados=enviados, erros=erros, concluido=concluido,
        )
        if quando:
            AvisoEnvioManual.objects.filter(pk=envio.pk).update(
                criado_em=quando
            )
        return envio

    def _pin(self, aviso):
        return pin_de_envio_por_aviso([aviso])[aviso.pk]


class RegraDoPinTests(BaseTests):
    def test_aviso_nunca_enviado_nao_tem_pin(self):
        self.assertIsNone(self._pin(self._aviso()))

    def test_envio_automatico_sem_falhas_e_verde(self):
        aviso = self._aviso()
        self._auto(aviso, enviados=5)

        pin = self._pin(aviso)

        self.assertEqual(pin.estado, PIN_ENVIADO)
        self.assertEqual(pin.rotulo, 'Já enviado')

    def test_envio_manual_sem_falhas_e_verde(self):
        aviso = self._aviso()
        self._manual(aviso, enviados=3)
        self.assertEqual(self._pin(aviso).estado, PIN_ENVIADO)

    def test_envio_com_falhas_parciais_e_amarelo(self):
        aviso = self._aviso()
        self._auto(aviso, enviados=40, erros=2)

        pin = self._pin(aviso)

        self.assertEqual(pin.estado, PIN_FALHAS)
        self.assertEqual(pin.rotulo, 'Enviado com falhas')

    def test_falha_total_nao_tem_pin_mesmo_com_a_marca_antiga(self):
        # O resumo de domingo marca o aviso como enviado mesmo que TODAS as
        # mensagens falhem. O pin não pode acreditar nessa marca.
        aviso = self._aviso(semana=True)
        self._auto(aviso, enviados=0, erros=7)

        self.assertIsNone(self._pin(aviso))

    def test_reenvio_manual_que_resolveu_as_falhas_vira_verde(self):
        aviso = self._aviso()
        agora = timezone.now()
        self._auto(aviso, enviados=40, erros=2, quando=agora - timedelta(days=2))
        self._manual(aviso, enviados=42, erros=0, quando=agora - timedelta(days=1))

        self.assertEqual(self._pin(aviso).estado, PIN_ENVIADO)

    def test_sucesso_seguido_de_falhas_na_ultima_tentativa_vira_amarelo(self):
        aviso = self._aviso()
        agora = timezone.now()
        self._auto(aviso, enviados=10, erros=0, quando=agora - timedelta(days=2))
        self._manual(aviso, enviados=8, erros=2, quando=agora - timedelta(days=1))

        self.assertEqual(self._pin(aviso).estado, PIN_FALHAS)

    def test_falha_em_um_tipo_de_mensagem_pesa_mesmo_que_outro_tenha_ido_bem(self):
        aviso = self._aviso()
        self._auto(aviso, template=TEMPLATE_SEMANA, enviados=10, erros=0)
        self._auto(aviso, template=TEMPLATE_VESPERA, enviados=9, erros=1)

        self.assertEqual(self._pin(aviso).estado, PIN_FALHAS)

    def test_tipos_diferentes_todos_bem_e_verde(self):
        aviso = self._aviso()
        for template in (TEMPLATE_SEMANA, TEMPLATE_VESPERA, TEMPLATE_DIA):
            self._auto(aviso, template=template, enviados=10)

        self.assertEqual(self._pin(aviso).estado, PIN_ENVIADO)

    def test_envio_manual_em_andamento_ou_interrompido_nao_conta(self):
        aviso = self._aviso()
        self._manual(aviso, enviados=0, concluido=False)

        self.assertIsNone(self._pin(aviso))

    # ---------- avisos antigos (sem registro de entrega) ----------

    def test_aviso_antigo_so_com_a_marca_aparece_como_enviado_com_aviso_na_dica(self):
        for campo in ('semana', 'dia', 'vespera'):
            with self.subTest(campo):
                Aviso.objects.all().delete()
                aviso = self._aviso(**{campo: True})

                pin = self._pin(aviso)

                self.assertEqual(pin.estado, PIN_ENVIADO)
                self.assertIn('antes do registro de entrega', pin.dica)

    def test_registro_de_entrega_vale_mais_que_a_marca_antiga(self):
        aviso = self._aviso(semana=True)
        self._auto(aviso, enviados=3)

        self.assertNotIn(
            'antes do registro de entrega', self._pin(aviso).dica
        )

    # ---------- varios avisos de uma vez ----------

    def test_calcula_o_pin_de_varios_avisos_de_uma_vez(self):
        ok = self._aviso(titulo='ok')
        falhas = self._aviso(titulo='falhas')
        nada = self._aviso(titulo='nada')
        self._auto(ok, enviados=3)
        self._auto(falhas, enviados=3, erros=1)

        pins = pin_de_envio_por_aviso([ok, falhas, nada])

        self.assertEqual(pins[ok.pk].estado, PIN_ENVIADO)
        self.assertEqual(pins[falhas.pk].estado, PIN_FALHAS)
        self.assertIsNone(pins[nada.pk])

    def test_numero_de_consultas_nao_cresce_com_a_quantidade_de_avisos(self):
        for i in range(8):
            aviso = self._aviso(titulo=f'A{i}')
            self._auto(aviso, enviados=1)
        avisos = list(Aviso.objects.all())

        with self.assertNumQueries(2):
            pin_de_envio_por_aviso(avisos)

    def test_lista_vazia(self):
        self.assertEqual(pin_de_envio_por_aviso([]), {})

    def test_anexar_nunca_derruba_a_listagem(self):
        aviso = self._aviso()

        with mock.patch(
            'calendario_avisos.envio_whatsapp.pin_de_envio_por_aviso',
            side_effect=RuntimeError('quebrou'),
        ):
            avisos = anexar_pin_de_envio([aviso])

        self.assertEqual(len(avisos), 1)
        self.assertIsNone(avisos[0].pin)


class RegistroDoCronTests(BaseTests):
    def _rodar(self, hoje, retorno=(200, {}), sender=None):
        with mock.patch(HOJE, return_value=hoje), \
                mock.patch(SENDER, return_value=retorno, side_effect=sender) as enviar:
            call_command('enviar_avisos_ensaio', stdout=StringIO())
        return enviar

    def test_o_cron_registra_quantas_mensagens_sairam(self):
        aviso = self._aviso(data_evento=QUI)

        self._rodar(DOM_18)

        registro = AvisoEnvioAutomatico.objects.get()
        self.assertEqual(registro.aviso, aviso)
        self.assertEqual(registro.template, TEMPLATE_SEMANA)
        self.assertEqual(
            (registro.total_destinatarios, registro.enviados, registro.erros),
            (1, 1, 0),
        )

    def test_o_registro_nao_guarda_telefone_nem_nome(self):
        self._aviso(data_evento=QUI)
        self._rodar(DOM_18)

        registro = AvisoEnvioAutomatico.objects.get()
        guardado = ' '.join(
            str(getattr(registro, c.name)) for c in registro._meta.fields
        )
        self.assertNotIn('91234', guardado)
        self.assertNotIn('Maria', guardado)

    def test_registra_falhas_parciais(self):
        outra = _usuario('resp2', '(21) 98888-7777', 'Joana', 'Costa')
        aviso = self._aviso(data_evento=QUI)
        aviso.alunas.add(Aluna.objects.create(nome='Bia', responsavel=outra))

        def sender(numero, template, parametros):
            return (500, {}) if numero == '5521988887777' else (200, {})

        self._rodar(DOM_18, sender=sender)

        registro = AvisoEnvioAutomatico.objects.get()
        self.assertEqual((registro.enviados, registro.erros), (1, 1))

    def test_resumo_de_domingo_marcado_mas_todo_mundo_falhou_nao_vira_pin(self):
        # O comportamento antigo do cron: marca o resumo como enviado mesmo
        # com falha total. O pin tem que enxergar isso.
        aviso = self._aviso(data_evento=QUI)

        self._rodar(DOM_18, retorno=(500, {'error': {'message': 'x'}}))

        aviso.refresh_from_db()
        self.assertTrue(aviso.notificacao_semana_enviada)  # marca "mentirosa"
        self.assertIsNone(pin_de_envio_por_aviso([aviso])[aviso.pk])

    def test_cada_tipo_de_mensagem_gera_o_seu_registro(self):
        self._aviso(data_evento=QUI, lembrar_vespera=True, semana=True)

        self._rodar(QUA)   # véspera
        self._rodar(QUI)   # lembrete do dia

        self.assertEqual(
            sorted(AvisoEnvioAutomatico.objects.values_list('template', flat=True)),
            sorted([TEMPLATE_VESPERA, TEMPLATE_DIA]),
        )

    def test_sem_destinatarios_nao_gera_registro(self):
        Perfil.objects.filter(user=self.responsavel).update(telefone='')
        self._aviso(data_evento=QUI)

        self._rodar(DOM_18)

        self.assertEqual(AvisoEnvioAutomatico.objects.count(), 0)

    def test_falha_ao_registrar_nao_atrapalha_o_envio(self):
        aviso = self._aviso(data_evento=QUI)

        with mock.patch(
            'calendario_avisos.management.commands.enviar_avisos_ensaio'
            '.AvisoEnvioAutomatico.objects.create',
            side_effect=RuntimeError('banco fora'),
        ):
            enviar = self._rodar(DOM_18)

        self.assertEqual(enviar.call_count, 1)
        aviso.refresh_from_db()
        self.assertTrue(aviso.notificacao_semana_enviada)

    def test_do_envio_ao_pin_de_ponta_a_ponta(self):
        aviso = self._aviso(data_evento=QUI)
        self.assertIsNone(self._pin(aviso))

        self._rodar(DOM_18)

        self.assertEqual(self._pin(aviso).estado, PIN_ENVIADO)


class HistoricoCompletoTests(BaseTests):
    def test_junta_envios_automaticos_e_manuais_do_mais_recente_ao_mais_antigo(self):
        staff = _usuario('staff', '(11) 90000-0000', 'Sec', 'Retaria', is_staff=True)
        aviso = self._aviso()
        agora = timezone.now()
        self._auto(aviso, TEMPLATE_SEMANA, enviados=40, erros=2,
                   quando=agora - timedelta(days=3))
        self._manual(aviso, TEMPLATE_SEMANA, enviados=2, por=staff,
                     quando=agora - timedelta(days=1))
        self._auto(aviso, TEMPLATE_VESPERA, enviados=42,
                   quando=agora - timedelta(hours=2))

        historico = historico_completo(aviso)

        self.assertEqual(
            [(i['rotulo'], i['por']) for i in historico],
            [
                ('Véspera', 'automático'),
                ('Resumo da semana', 'por Sec Retaria'),
                ('Resumo da semana', 'automático'),
            ],
        )
        self.assertEqual(historico[2]['erros'], 2)

    def test_respeita_o_limite(self):
        aviso = self._aviso()
        for _ in range(12):
            self._auto(aviso)
        self.assertEqual(len(historico_completo(aviso, limite=8)), 8)


@override_settings(STORAGES=STORAGES_TESTE)
class TelasTests(BaseTests):
    def setUp(self):
        super().setUp()
        self.staff = _usuario('staff', '(11) 90000-0000', is_staff=True)
        self.client.force_login(self.staff)
        self.url_lista = reverse('admin_dashboard:avisos_list')

    def _editar(self, aviso):
        return self.client.get(
            reverse('admin_dashboard:aviso_editar', args=[aviso.pk])
        )

    # ---------- listagem ----------

    def test_listagem_mostra_o_pin_verde_so_nos_avisos_enviados(self):
        enviado = self._aviso(titulo='Aviso enviado')
        self._aviso(titulo='Aviso nao enviado')
        self._auto(enviado, enviados=5)

        resposta = self.client.get(self.url_lista)

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'Aviso enviado')
        self.assertContains(resposta, 'Aviso nao enviado')
        self.assertContains(resposta, 'class="aviso-pin enviado"', count=1)
        self.assertContains(resposta, 'Já enviado', count=1)

    def test_listagem_mostra_o_pin_amarelo_quando_houve_falhas(self):
        aviso = self._aviso()
        self._auto(aviso, enviados=5, erros=1)

        resposta = self.client.get(self.url_lista)

        self.assertContains(resposta, 'class="aviso-pin falhas"')
        self.assertContains(resposta, 'Enviado com falhas')
        self.assertNotContains(resposta, 'class="aviso-pin enviado"')

    def test_listagem_nao_mostra_pin_em_aviso_que_so_falhou(self):
        aviso = self._aviso(semana=True)
        self._auto(aviso, enviados=0, erros=4)

        resposta = self.client.get(self.url_lista)

        self.assertNotContains(resposta, 'class="aviso-pin')

    def test_listagem_sem_pin_quando_nada_foi_enviado(self):
        self._aviso()
        resposta = self.client.get(self.url_lista)
        self.assertNotContains(resposta, 'class="aviso-pin')

    def test_listagem_continua_funcionando_se_o_pin_quebrar(self):
        self._aviso(titulo='Aviso importante')

        with mock.patch(
            'calendario_avisos.envio_whatsapp.pin_de_envio_por_aviso',
            side_effect=RuntimeError('quebrou'),
        ):
            resposta = self.client.get(self.url_lista)

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'Aviso importante')

    def test_listagem_de_passados_tambem_mostra_o_pin(self):
        aviso = self._aviso(data_evento=timezone.localdate() - timedelta(days=5))
        self._auto(aviso, enviados=5)

        resposta = self.client.get(self.url_lista, {'tipo_data': 'passados'})

        self.assertContains(resposta, 'class="aviso-pin enviado"')

    def test_numero_de_consultas_da_listagem_nao_cresce_com_os_avisos(self):
        def consultas():
            from django.db import connection
            from django.test.utils import CaptureQueriesContext
            with CaptureQueriesContext(connection) as ctx:
                self.client.get(self.url_lista)
            return len(ctx)

        for i in range(2):
            self._auto(self._aviso(titulo=f'A{i}'), enviados=1)
        poucos = consultas()

        for i in range(2, 10):
            self._auto(self._aviso(titulo=f'A{i}'), enviados=1)
        muitos = consultas()

        self.assertEqual(poucos, muitos)

    # ---------- edição ----------

    def test_edicao_mostra_o_pin_no_cabecalho(self):
        aviso = self._aviso()
        self._auto(aviso, enviados=5)

        resposta = self._editar(aviso)

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'class="aviso-pin enviado"')
        self.assertContains(resposta, 'Já enviado')

    def test_edicao_nao_mostra_pin_em_aviso_nao_enviado(self):
        resposta = self._editar(self._aviso())
        self.assertNotContains(resposta, 'class="aviso-pin')

    def test_edicao_mostra_o_historico_completo_com_automaticos_e_falhas(self):
        aviso = self._aviso()
        self._auto(aviso, TEMPLATE_SEMANA, enviados=40, erros=2)

        resposta = self._editar(aviso)

        self.assertContains(resposta, 'Resumo da semana')
        self.assertContains(resposta, 'automático')
        self.assertContains(resposta, '40 enviada(s)')
        self.assertContains(resposta, '2 falha(s)')
        self.assertContains(resposta, 'class="aviso-pin falhas"')

    def test_apos_enviar_pelo_botao_o_pin_aparece(self):
        aviso = self._aviso()

        with mock.patch(
            'calendario_avisos.envio_whatsapp.enviar_whatsapp_template',
            return_value=(200, {}),
        ):
            resposta = self.client.post(
                reverse('admin_dashboard:aviso_enviar_agora', args=[aviso.pk]),
                follow=True,
            )

        self.assertContains(resposta, 'class="aviso-pin enviado"')
        # o usuário staff deste teste se chama Maria Silva
        self.assertContains(resposta, 'por Maria Silva')
