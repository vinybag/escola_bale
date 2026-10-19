"""
Testes do comando que o cron do Railway executa (enviar_avisos_ensaio).

Fixam o comportamento atual: resumo da semana aos domingos, lembrete no dia
do ensaio, cada um enviado uma única vez por aviso.
"""

from datetime import date
from io import StringIO
from unittest import mock

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase

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

DOMINGO = date(2026, 10, 18)
QUARTA = date(2026, 10, 21)
QUINTA = date(2026, 10, 22)   # dentro da semana seguinte ao domingo 18/10
SEMANA_SEGUINTE_DOMINGO = date(2026, 10, 25)


def _usuario(username, telefone, nome='Maria', sobrenome='Silva'):
    user = User.objects.create_user(
        username, f'{username}@example.com', 'senha123',
        first_name=nome, last_name=sobrenome,
    )
    Perfil.objects.create(user=user, telefone=telefone)
    return user


class ComandoAvisosEnsaioTests(TestCase):
    def setUp(self):
        self.responsavel = _usuario('resp', '(11) 91234-5678')
        self.aluna = Aluna.objects.create(
            nome='Ana', responsavel=self.responsavel
        )

    def _aviso(self, data_evento=QUINTA, horario='19h', **extra):
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

    def _rodar(self, hoje, retorno=(200, {})):
        with mock.patch(HOJE, return_value=hoje), \
                mock.patch(SENDER, return_value=retorno) as enviar:
            call_command('enviar_avisos_ensaio', stdout=StringIO())
        return enviar

    # ---------- resumo da semana (domingo) ----------

    def test_domingo_envia_resumo_da_semana_seguinte(self):
        aviso = self._aviso()

        enviar = self._rodar(DOMINGO)

        enviar.assert_called_once_with(
            '5511912345678',
            'aviso_ensaio_semana',
            ['Maria Silva', 'Ensaio Geral', '22/10/2026', '19h'],
        )
        aviso.refresh_from_db()
        self.assertTrue(aviso.notificacao_semana_enviada)
        self.assertFalse(aviso.notificacao_dia_enviada)

    def test_resumo_so_e_enviado_uma_vez(self):
        self._aviso()
        self._rodar(DOMINGO)
        enviar = self._rodar(DOMINGO)
        enviar.assert_not_called()

    def test_fora_do_domingo_resumo_da_semana_seguinte_espera_o_domingo(self):
        # Ensaio da semana SEGUINTE a quarta 21/10 (terça 27/10): o resumo
        # continua saindo só no domingo. (Ensaios da semana em curso são
        # outro caso: ver tests_resumo_atrasado.py.)
        self._aviso(data_evento=date(2026, 10, 27))
        enviar = self._rodar(QUARTA)
        enviar.assert_not_called()

    def test_resumo_nao_inclui_ensaio_fora_da_semana_seguinte(self):
        self._aviso(data_evento=date(2026, 10, 26))  # segunda depois
        enviar = self._rodar(DOMINGO)
        enviar.assert_not_called()

    def test_ultimo_dia_da_semana_seguinte_entra(self):
        self._aviso(data_evento=SEMANA_SEGUINTE_DOMINGO)
        enviar = self._rodar(DOMINGO)
        enviar.assert_called_once()

    def test_horario_vazio_vira_a_confirmar(self):
        self._aviso(horario='')
        enviar = self._rodar(DOMINGO)
        self.assertEqual(
            enviar.call_args.args[2][-1], 'horário a confirmar'
        )

    def test_ensaio_do_proprio_domingo_so_recebe_lembrete_do_dia(self):
        aviso = self._aviso(data_evento=DOMINGO)

        enviar = self._rodar(DOMINGO)

        enviar.assert_called_once_with(
            '5511912345678',
            'aviso_ensaio_dia_certo',
            ['Maria Silva', 'Ensaio Geral', '19h'],
        )
        aviso.refresh_from_db()
        self.assertTrue(aviso.notificacao_semana_enviada)
        self.assertTrue(aviso.notificacao_dia_enviada)

    # ---------- lembrete do dia ----------

    def test_lembrete_do_dia_e_enviado_uma_vez(self):
        aviso = self._aviso(data_evento=QUARTA)

        enviar = self._rodar(QUARTA)
        enviar.assert_called_once_with(
            '5511912345678',
            'aviso_ensaio_dia_certo',
            ['Maria Silva', 'Ensaio Geral', '19h'],
        )
        aviso.refresh_from_db()
        self.assertTrue(aviso.notificacao_dia_enviada)

        self._rodar(QUARTA).assert_not_called()

    def test_falha_no_lembrete_do_dia_permite_nova_tentativa(self):
        aviso = self._aviso(data_evento=QUARTA)

        self._rodar(QUARTA, retorno=(500, {'error': {'message': 'x'}}))
        aviso.refresh_from_db()
        self.assertFalse(aviso.notificacao_dia_enviada)

        enviar = self._rodar(QUARTA)
        enviar.assert_called_once()

    def test_lembrete_usa_os_dados_atuais_do_aviso(self):
        aviso = self._aviso(data_evento=QUARTA, horario='19h')
        Aviso.objects.filter(pk=aviso.pk).update(
            horario='20h30', titulo='Ensaio Geral (alterado)'
        )

        enviar = self._rodar(QUARTA)

        self.assertEqual(
            enviar.call_args.args[2],
            ['Maria Silva', 'Ensaio Geral (alterado)', '20h30'],
        )

    # ---------- quem entra ----------

    def test_aviso_que_nao_e_ensaio_ou_sem_whatsapp_ou_inativo_nao_envia(self):
        self._aviso(tipo='geral', titulo='A')
        self._aviso(enviar_whatsapp=False, titulo='B')
        self._aviso(ativo=False, titulo='C')
        enviar = self._rodar(DOMINGO)
        enviar.assert_not_called()

    def test_telefone_e_normalizado_para_o_padrao_da_api(self):
        Perfil.objects.filter(user=self.responsavel).update(
            telefone='+55 (11) 91234-5678'
        )
        self._aviso()
        enviar = self._rodar(DOMINGO)
        self.assertEqual(enviar.call_args.args[0], '5511912345678')

    def test_pessoa_sem_telefone_nao_recebe(self):
        Perfil.objects.filter(user=self.responsavel).update(telefone='')
        self._aviso()
        enviar = self._rodar(DOMINGO)
        enviar.assert_not_called()

    def test_duas_alunas_do_mesmo_responsavel_geram_uma_mensagem(self):
        aviso = self._aviso()
        irma = Aluna.objects.create(nome='Bia', responsavel=self.responsavel)
        aviso.alunas.add(irma)

        enviar = self._rodar(DOMINGO)

        self.assertEqual(enviar.call_count, 1)

    def test_aluna_adulta_recebe_na_propria_conta(self):
        adulta_user = _usuario('adulta', '(21) 98888-7777', 'Carla', 'Souza')
        adulta = Aluna.objects.create(
            nome='Carla', usuario=adulta_user, tipo_aluna='adulto'
        )
        aviso = self._aviso()
        aviso.alunas.add(adulta)

        enviar = self._rodar(DOMINGO)

        numeros = {c.args[0] for c in enviar.call_args_list}
        self.assertEqual(numeros, {'5511912345678', '5521988887777'})

    def test_professora_recebe(self):
        professora = _usuario('prof', '(31) 97777-6666', 'Paula', 'Lima')
        aviso = self._aviso()
        aviso.professoras.add(professora)

        enviar = self._rodar(DOMINGO)

        numeros = {c.args[0] for c in enviar.call_args_list}
        self.assertIn('5531977776666', numeros)
