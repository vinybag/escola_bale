"""
Agenda de maquiagem/cabelo dos espetáculos: a mesma turma pode ter mais de
uma maquiadora.

Antes, adicionar a mesma turma de novo trocava a maquiadora da agenda que já
existia (regra de uma agenda por turma). Agora cada maquiadora tem a sua
agenda, e as alunas veem os horários de todas.
"""

from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from espetaculo.models import (
    AgendaMaquiagemTurma,
    AgendamentoMaquiagem,
    Espetaculo,
    HorarioMaquiagem,
)
from usuarios.models import Aluna, Turma

STORAGES_TESTE = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'
    },
}


class BaseTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            'staff', 'staff@example.com', 'senha123', is_staff=True
        )
        self.responsavel = User.objects.create_user(
            'resp', 'resp@example.com', 'senha123'
        )
        self.espetaculo = Espetaculo.objects.create(
            titulo='Quebra-Nozes', descricao='x', tipo='evento',
            data_apresentacao=timezone.now() + timedelta(days=30),
            local='Teatro', endereco='Rua A',
        )
        self.turma_a = Turma.objects.create(nome='Turma A')
        self.turma_b = Turma.objects.create(nome='Turma B')

        self.aluna = Aluna.objects.create(
            nome='Ana', responsavel=self.responsavel
        )
        self.aluna.turmas.add(self.turma_a)

        self.url_admin = reverse(
            'admin_dashboard:espetaculo_maquiagens', args=[self.espetaculo.pk]
        )
        self.base = timezone.now() + timedelta(days=10)

    # ---------- atalhos ----------

    def _agenda(self, turma=None, maquiadora='Ana Maq', **extra):
        return AgendaMaquiagemTurma.objects.create(
            espetaculo=extra.pop('espetaculo', self.espetaculo),
            turma=turma or self.turma_a,
            maquiadora=maquiadora,
            ativo=extra.pop('ativo', True),
        )

    def _horario(self, agenda, horas=0, **extra):
        return HorarioMaquiagem.objects.create(
            agenda=agenda,
            horario=self.base + timedelta(hours=horas),
            status=extra.pop('status', 'disponivel'),
        )

    def _post_admin(self, **dados):
        return self.client.post(self.url_admin, dados)

    def _criar(self, turma, maquiadora):
        return self._post_admin(
            acao='criar_agenda', turma=turma.pk, maquiadora=maquiadora
        )


@override_settings(STORAGES=STORAGES_TESTE)
class AdicionarMaquiadoraNaMesmaTurmaTests(BaseTests):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.staff)

    def test_mesma_turma_com_outra_maquiadora_adiciona_em_vez_de_trocar(self):
        # O problema relatado: antes, isto TROCAVA a maquiadora da agenda.
        self._criar(self.turma_a, 'Maria')
        self._criar(self.turma_a, 'Joana')

        agendas = AgendaMaquiagemTurma.objects.filter(turma=self.turma_a)
        self.assertEqual(
            sorted(a.maquiadora for a in agendas), ['Joana', 'Maria']
        )

    def test_a_primeira_agenda_continua_com_os_seus_horarios(self):
        primeira = self._agenda(maquiadora='Maria')
        self._horario(primeira, 0)

        self._criar(self.turma_a, 'Joana')

        primeira.refresh_from_db()
        self.assertEqual(primeira.maquiadora, 'Maria')
        self.assertEqual(primeira.horarios.count(), 1)

    def test_redireciona_para_a_agenda_criada(self):
        resposta = self._criar(self.turma_a, 'Maria')
        agenda = AgendaMaquiagemTurma.objects.get()
        self.assertRedirects(
            resposta,
            f'{self.url_admin}?agenda_id={agenda.pk}',
            fetch_redirect_response=False,
        )

    def test_mensagem_avisa_que_a_turma_agora_tem_mais_de_uma_maquiadora(self):
        self._criar(self.turma_a, 'Maria')
        resposta = self._criar(self.turma_a, 'Joana')
        resposta = self.client.get(resposta['Location'])
        self.assertContains(resposta, 'agora tem 2 maquiadoras')

    def test_mesma_maquiadora_na_mesma_turma_nao_duplica(self):
        self._criar(self.turma_a, 'Maria')
        self._criar(self.turma_a, 'Maria')
        self.assertEqual(AgendaMaquiagemTurma.objects.count(), 1)

    def test_comparacao_ignora_maiuscula_e_espacos_sobrando(self):
        self._criar(self.turma_a, 'Maria Silva')
        self._criar(self.turma_a, '  maria   SILVA ')
        agenda = AgendaMaquiagemTurma.objects.get()
        self.assertEqual(agenda.maquiadora, 'Maria Silva')

    def test_nome_e_guardado_sem_espacos_sobrando(self):
        self._criar(self.turma_a, '  Joana    Costa  ')
        self.assertEqual(
            AgendaMaquiagemTurma.objects.get().maquiadora, 'Joana Costa'
        )

    def test_repetir_uma_agenda_desativada_reativa(self):
        agenda = self._agenda(maquiadora='Maria', ativo=False)

        self._criar(self.turma_a, 'maria')

        agenda.refresh_from_db()
        self.assertTrue(agenda.ativo)
        self.assertEqual(AgendaMaquiagemTurma.objects.count(), 1)

    def test_repetir_nao_mexe_nos_horarios(self):
        agenda = self._agenda(maquiadora='Maria')
        self._horario(agenda, 0)
        self._criar(self.turma_a, 'Maria')
        self.assertEqual(agenda.horarios.count(), 1)

    def test_mesma_maquiadora_pode_atender_turmas_diferentes(self):
        self._criar(self.turma_a, 'Maria')
        self._criar(self.turma_b, 'Maria')
        self.assertEqual(AgendaMaquiagemTurma.objects.count(), 2)

    def test_mesma_maquiadora_e_turma_em_outro_espetaculo_e_permitido(self):
        outro = Espetaculo.objects.create(
            titulo='Outro', descricao='x', tipo='evento',
            data_apresentacao=timezone.now(), local='L', endereco='E',
        )
        self._agenda(maquiadora='Maria', espetaculo=outro)

        self._criar(self.turma_a, 'Maria')

        self.assertEqual(AgendaMaquiagemTurma.objects.count(), 2)

    def test_entradas_invalidas_nao_criam_nada_nem_quebram(self):
        casos = [
            {'acao': 'criar_agenda', 'turma': '', 'maquiadora': 'Maria'},
            {'acao': 'criar_agenda', 'turma': self.turma_a.pk, 'maquiadora': '   '},
            {'acao': 'criar_agenda', 'turma': 'abc', 'maquiadora': 'Maria'},
            {'acao': 'criar_agenda', 'turma': 999999, 'maquiadora': 'Maria'},
            {'acao': 'criar_agenda', 'turma': self.turma_a.pk, 'maquiadora': 'x' * 121},
            {'acao': 'qualquer_outra_coisa'},
            {},
        ]
        for dados in casos:
            with self.subTest(dados=dados):
                resposta = self._post_admin(**dados)
                self.assertEqual(resposta.status_code, 302)

        self.assertEqual(AgendaMaquiagemTurma.objects.count(), 0)

    def test_chips_mostram_as_duas_maquiadoras_da_mesma_turma(self):
        self._agenda(maquiadora='Maria')
        self._agenda(maquiadora='Joana')

        resposta = self.client.get(self.url_admin)

        self.assertContains(resposta, 'Maria')
        self.assertContains(resposta, 'Joana')
        self.assertContains(resposta, 'Adicionar maquiadora a uma turma')

    def test_a_mesma_data_e_hora_pode_existir_em_duas_maquiadoras_da_turma(self):
        a = self._agenda(maquiadora='Maria')
        b = self._agenda(maquiadora='Joana')
        self._horario(a, 0)
        self._horario(b, 0)  # mesmo dia/hora, outra maquiadora
        self.assertEqual(HorarioMaquiagem.objects.count(), 2)


@override_settings(STORAGES=STORAGES_TESTE)
class RenomearEAtivarAgendaTests(BaseTests):
    """Sem 'salvar de novo' trocando o nome, a correção passa a ser explícita."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.staff)
        self.maria = self._agenda(maquiadora='Maria')
        self.joana = self._agenda(maquiadora='Joana')

    def test_renomear(self):
        self._post_admin(
            acao='renomear_agenda', agenda_id=self.maria.pk,
            maquiadora='Maria Souza',
        )
        self.maria.refresh_from_db()
        self.joana.refresh_from_db()
        self.assertEqual(self.maria.maquiadora, 'Maria Souza')
        self.assertEqual(self.joana.maquiadora, 'Joana')

    def test_renomear_para_o_nome_de_outra_agenda_da_turma_e_barrado(self):
        resposta = self._post_admin(
            acao='renomear_agenda', agenda_id=self.maria.pk, maquiadora='joana'
        )
        self.maria.refresh_from_db()
        self.assertEqual(self.maria.maquiadora, 'Maria')
        resposta = self.client.get(resposta['Location'])
        self.assertContains(resposta, 'já tem outra agenda com o nome')

    def test_renomear_mantendo_o_proprio_nome_com_outra_caixa_e_permitido(self):
        self._post_admin(
            acao='renomear_agenda', agenda_id=self.maria.pk, maquiadora='MARIA'
        )
        self.maria.refresh_from_db()
        self.assertEqual(self.maria.maquiadora, 'MARIA')

    def test_renomear_com_nome_vazio_e_barrado(self):
        self._post_admin(
            acao='renomear_agenda', agenda_id=self.maria.pk, maquiadora='  '
        )
        self.maria.refresh_from_db()
        self.assertEqual(self.maria.maquiadora, 'Maria')

    def test_agenda_de_outro_espetaculo_nao_e_alterada(self):
        outro = Espetaculo.objects.create(
            titulo='Outro', descricao='x', tipo='evento',
            data_apresentacao=timezone.now(), local='L', endereco='E',
        )
        alheia = self._agenda(maquiadora='Alheia', espetaculo=outro)

        self._post_admin(
            acao='renomear_agenda', agenda_id=alheia.pk, maquiadora='Invasora'
        )
        self._post_admin(acao='alternar_agenda', agenda_id=alheia.pk)

        alheia.refresh_from_db()
        self.assertEqual(alheia.maquiadora, 'Alheia')
        self.assertTrue(alheia.ativo)

    def test_agenda_id_invalido_nao_quebra(self):
        for valor in ('abc', '', '999999'):
            resposta = self._post_admin(
                acao='alternar_agenda', agenda_id=valor
            )
            self.assertEqual(resposta.status_code, 302)

    def test_desativar_e_reativar(self):
        self._post_admin(acao='alternar_agenda', agenda_id=self.maria.pk)
        self.maria.refresh_from_db()
        self.assertFalse(self.maria.ativo)

        self._post_admin(acao='alternar_agenda', agenda_id=self.maria.pk)
        self.maria.refresh_from_db()
        self.assertTrue(self.maria.ativo)

    def test_tela_mostra_os_controles_e_o_aviso_de_desativada(self):
        self.maria.ativo = False
        self.maria.save()

        resposta = self.client.get(f'{self.url_admin}?agenda_id={self.maria.pk}')

        self.assertContains(resposta, 'value="renomear_agenda"')
        self.assertContains(resposta, 'Ativar agenda')
        self.assertContains(resposta, 'desativada')

    def test_agenda_id_invalido_na_url_nao_quebra_a_tela(self):
        resposta = self.client.get(f'{self.url_admin}?agenda_id=abc')
        self.assertEqual(resposta.status_code, 200)


@override_settings(STORAGES=STORAGES_TESTE)
class AlunaVeHorariosDeTodasAsMaquiadorasTests(BaseTests):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.responsavel)
        self.url = reverse('espetaculo:agendar_maquiagem', args=[self.espetaculo.pk])

    def test_com_duas_maquiadoras_a_aluna_ve_os_horarios_das_duas(self):
        maria = self._agenda(maquiadora='Maria')
        joana = self._agenda(maquiadora='Joana')
        h1 = self._horario(maria, 0)
        h2 = self._horario(joana, 1)

        resposta = self.client.get(self.url)

        self.assertEqual(resposta.status_code, 200)
        ids = [h.pk for h in resposta.context['horarios_disponiveis']]
        self.assertEqual(ids, [h1.pk, h2.pk])
        self.assertContains(resposta, 'Maquiadoras: Joana, Maria')
        self.assertContains(resposta, '· Maria</span>')
        self.assertContains(resposta, '· Joana</span>')

    def test_horarios_ficam_em_ordem_de_hora_misturando_as_maquiadoras(self):
        maria = self._agenda(maquiadora='Maria')
        joana = self._agenda(maquiadora='Joana')
        tarde = self._horario(maria, 5)
        manha = self._horario(joana, 1)
        meio = self._horario(maria, 3)

        resposta = self.client.get(self.url)

        self.assertEqual(
            [h.pk for h in resposta.context['horarios_disponiveis']],
            [manha.pk, meio.pk, tarde.pk],
        )

    def test_com_uma_so_maquiadora_a_tela_continua_igual(self):
        maria = self._agenda(maquiadora='Maria')
        self._horario(maria, 0)

        resposta = self.client.get(self.url)

        self.assertContains(resposta, 'Maquiadora: Maria')
        self.assertNotContains(resposta, '<span class="agmaq-horario-maquiadora">')
        self.assertFalse(resposta.context['varias_maquiadoras'])

    def test_agenda_desativada_nao_aparece(self):
        maria = self._agenda(maquiadora='Maria')
        joana = self._agenda(maquiadora='Joana', ativo=False)
        visivel = self._horario(maria, 0)
        self._horario(joana, 1)

        resposta = self.client.get(self.url)

        self.assertEqual(
            [h.pk for h in resposta.context['horarios_disponiveis']],
            [visivel.pk],
        )
        self.assertNotContains(resposta, 'Joana')

    def test_sem_nenhuma_agenda_ativa_avisa_e_volta(self):
        self._agenda(maquiadora='Maria', ativo=False)
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 302)

    def test_horarios_ocupados_nao_aparecem(self):
        maria = self._agenda(maquiadora='Maria')
        joana = self._agenda(maquiadora='Joana')
        self._horario(maria, 0, status='agendado')
        livre = self._horario(joana, 1)

        resposta = self.client.get(self.url)

        self.assertEqual(
            [h.pk for h in resposta.context['horarios_disponiveis']],
            [livre.pk],
        )

    def test_reserva_expirada_de_qualquer_maquiadora_volta_a_ficar_livre(self):
        maria = self._agenda(maquiadora='Maria')
        joana = self._agenda(maquiadora='Joana')
        expirado = self._horario(joana, 1, status='reservado_temporario')
        HorarioMaquiagem.objects.filter(pk=expirado.pk).update(
            reservado_em=timezone.now() - timedelta(minutes=30),
            reservado_por_sessao='outra-sessao',
        )
        self._horario(maria, 0)

        resposta = self.client.get(self.url)

        self.assertIn(
            expirado.pk,
            [h.pk for h in resposta.context['horarios_disponiveis']],
        )

    def test_aluna_de_outra_turma_nao_ve_horarios_desta(self):
        maria = self._agenda(maquiadora='Maria')
        self._horario(maria, 0)
        outra = Aluna.objects.create(nome='Bia', responsavel=self.responsavel)
        outra.turmas.add(self.turma_b)
        self.aluna.ativa = False
        self.aluna.save()

        resposta = self.client.get(self.url)

        self.assertEqual(resposta.status_code, 302)  # turma B sem agenda

    def test_reservar_e_confirmar_horario_da_segunda_maquiadora(self):
        self._agenda(maquiadora='Maria')
        joana = self._agenda(maquiadora='Joana')
        horario = self._horario(joana, 1)

        reserva = self.client.post(
            reverse('espetaculo:reservar_horario_maquiagem',
                    args=[self.espetaculo.pk, horario.pk]),
            {'aluna_id': self.aluna.pk},
        )
        self.assertEqual(reserva.status_code, 200)
        self.assertEqual(reserva.json()['maquiadora'], 'Joana')

        confirmacao = self.client.post(
            reverse('espetaculo:confirmar_agendamento_maquiagem',
                    args=[self.espetaculo.pk, horario.pk]),
            {'aluna_id': self.aluna.pk, 'tipo_servico': 'maquiagem'},
        )
        self.assertEqual(confirmacao.status_code, 302)

        agendamento = AgendamentoMaquiagem.objects.get()
        self.assertEqual(agendamento.maquiadora, 'Joana')
        horario.refresh_from_db()
        self.assertEqual(horario.status, 'agendado')

    def test_nao_da_para_reservar_horario_de_agenda_desativada(self):
        joana = self._agenda(maquiadora='Joana', ativo=False)
        horario = self._horario(joana, 1)

        resposta = self.client.post(
            reverse('espetaculo:reservar_horario_maquiagem',
                    args=[self.espetaculo.pk, horario.pk]),
            {'aluna_id': self.aluna.pk},
        )

        self.assertEqual(resposta.status_code, 404)
        horario.refresh_from_db()
        self.assertEqual(horario.status, 'disponivel')

    def test_duas_alunas_nao_reservam_o_mesmo_horario(self):
        joana = self._agenda(maquiadora='Joana')
        horario = self._horario(joana, 1)
        url = reverse('espetaculo:reservar_horario_maquiagem',
                      args=[self.espetaculo.pk, horario.pk])

        primeira = self.client.post(url, {'aluna_id': self.aluna.pk})
        self.assertEqual(primeira.status_code, 200)

        outra_resp = User.objects.create_user('resp2', 'r2@example.com', 'senha123')
        outra = Aluna.objects.create(nome='Bia', responsavel=outra_resp)
        outra.turmas.add(self.turma_a)
        self.client.force_login(outra_resp)

        segunda = self.client.post(url, {'aluna_id': outra.pk})
        self.assertEqual(segunda.status_code, 409)


@override_settings(STORAGES=STORAGES_TESTE)
class EditarAgendamentoTests(BaseTests):
    """A tela de editar estava quebrada (FieldError) e usava um template antigo."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.staff)
        self.maria = self._agenda(maquiadora='Maria')
        self.joana = self._agenda(maquiadora='Joana')
        self.h_maria = self._horario(self.maria, 0)
        self.h_joana = self._horario(self.joana, 1)
        self.agendamento = AgendamentoMaquiagem.objects.create(
            horario=self.h_maria, aluna=self.aluna, tipo_servico='maquiagem',
        )
        self.h_maria.marcar_como_agendado()
        self.url = reverse(
            'admin_dashboard:maquiagem_editar', args=[self.agendamento.pk]
        )

    def _post(self, **dados):
        base = {
            'aluna': self.aluna.pk,
            'tipo_servico': 'maquiagem',
            'horario': self.agendamento.horario_id,
        }
        base.update(dados)
        return self.client.post(self.url, base)

    def test_a_tela_abre(self):
        resposta = self.client.get(self.url)

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'Editar agendamento')
        self.assertContains(resposta, 'Ana')

    def test_lista_os_horarios_livres_de_todas_as_maquiadoras_da_turma(self):
        resposta = self.client.get(self.url)

        self.assertContains(resposta, '· Maria · atual')
        self.assertContains(resposta, '· Joana')

    def test_nao_lista_horarios_de_outra_turma(self):
        outra = self._agenda(turma=self.turma_b, maquiadora='Outra')
        self._horario(outra, 2)

        resposta = self.client.get(self.url)

        self.assertNotContains(resposta, 'Outra')

    def test_nao_lista_horarios_ja_ocupados(self):
        ocupado = self._horario(self.joana, 4, status='agendado')
        resposta = self.client.get(self.url)
        ids = [h.pk for h in resposta.context['horarios_disponiveis_para_troca']]
        self.assertNotIn(ocupado.pk, ids)

    def test_aluna_atual_aparece_mesmo_inativa(self):
        self.aluna.ativa = False
        self.aluna.save()

        resposta = self.client.get(self.url)

        self.assertIn(
            self.aluna.pk,
            [a.pk for a in resposta.context['alunas_da_turma']],
        )

    def test_trocar_para_o_horario_de_outra_maquiadora_da_mesma_turma(self):
        resposta = self._post(horario=self.h_joana.pk)

        self.agendamento.refresh_from_db()
        self.h_maria.refresh_from_db()
        self.h_joana.refresh_from_db()
        self.assertEqual(self.agendamento.horario_id, self.h_joana.pk)
        self.assertEqual(self.agendamento.maquiadora, 'Joana')
        self.assertEqual(self.h_maria.status, 'disponivel')
        self.assertEqual(self.h_joana.status, 'agendado')
        # volta para a agenda do novo horário
        self.assertRedirects(
            resposta,
            f'{self.url_admin}?agenda_id={self.joana.pk}',
            fetch_redirect_response=False,
        )

    def test_trocar_so_o_tipo_de_servico(self):
        self._post(tipo_servico='cabelo')

        self.agendamento.refresh_from_db()
        self.assertEqual(self.agendamento.tipo_servico, 'cabelo')
        self.assertEqual(self.agendamento.horario_id, self.h_maria.pk)
        self.h_maria.refresh_from_db()
        self.assertEqual(self.h_maria.status, 'agendado')

    def test_trocar_a_aluna(self):
        outra = Aluna.objects.create(nome='Bia')
        outra.turmas.add(self.turma_a)

        self._post(aluna=outra.pk)

        self.agendamento.refresh_from_db()
        self.assertEqual(self.agendamento.aluna_id, outra.pk)

    def test_horario_de_outra_turma_e_recusado(self):
        outra = self._agenda(turma=self.turma_b, maquiadora='Outra')
        estranho = self._horario(outra, 2)

        self._post(horario=estranho.pk)

        self.agendamento.refresh_from_db()
        self.assertEqual(self.agendamento.horario_id, self.h_maria.pk)
        estranho.refresh_from_db()
        self.assertEqual(estranho.status, 'disponivel')

    def test_horario_ja_agendado_e_recusado(self):
        ocupado = self._horario(self.joana, 4, status='agendado')

        self._post(horario=ocupado.pk)

        self.agendamento.refresh_from_db()
        self.assertEqual(self.agendamento.horario_id, self.h_maria.pk)

    def test_horario_com_reserva_expirada_pode_receber_a_aluna(self):
        expirado = self._horario(self.joana, 5, status='reservado_temporario')
        HorarioMaquiagem.objects.filter(pk=expirado.pk).update(
            reservado_em=timezone.now() - timedelta(minutes=40),
            reservado_por_sessao='x',
        )

        self._post(horario=expirado.pk)

        self.agendamento.refresh_from_db()
        self.assertEqual(self.agendamento.horario_id, expirado.pk)

    def test_aluna_de_fora_da_turma_e_recusada(self):
        estranha = Aluna.objects.create(nome='Estranha')
        estranha.turmas.add(self.turma_b)

        self._post(aluna=estranha.pk)

        self.agendamento.refresh_from_db()
        self.assertEqual(self.agendamento.aluna_id, self.aluna.pk)

    def test_entradas_invalidas_nao_quebram_nem_alteram(self):
        casos = [
            {'aluna': 'abc'},
            {'horario': ''},
            {'horario': 'xyz'},
            {'tipo_servico': 'inexistente'},
            {'aluna': 999999},
            {'horario': 999999},
        ]
        for dados in casos:
            with self.subTest(dados=dados):
                resposta = self._post(**dados)
                self.assertEqual(resposta.status_code, 302)

        self.agendamento.refresh_from_db()
        self.assertEqual(self.agendamento.horario_id, self.h_maria.pk)
        self.assertEqual(self.agendamento.aluna_id, self.aluna.pk)
        self.assertEqual(self.agendamento.tipo_servico, 'maquiagem')

    def test_excluir_libera_o_horario(self):
        self.client.post(
            reverse('admin_dashboard:maquiagem_excluir', args=[self.agendamento.pk])
        )
        self.assertEqual(AgendamentoMaquiagem.objects.count(), 0)
        self.h_maria.refresh_from_db()
        self.assertEqual(self.h_maria.status, 'disponivel')


@override_settings(STORAGES=STORAGES_TESTE)
class AcessoRestritoTests(BaseTests):
    """
    As telas de maquiagem do painel não exigiam login: qualquer pessoa podia
    ver a lista de alunas agendadas e EXCLUIR agendamentos.
    """

    def setUp(self):
        super().setUp()
        self.agenda = self._agenda(maquiadora='Maria')
        self.horario = self._horario(self.agenda, 0)
        self.livre = self._horario(self.agenda, 1)
        self.agendamento = AgendamentoMaquiagem.objects.create(
            horario=self.horario, aluna=self.aluna, tipo_servico='maquiagem',
        )
        self.horario.marcar_como_agendado()

        self.gets = {
            'lista': self.url_admin,
            'editar': reverse('admin_dashboard:maquiagem_editar',
                              args=[self.agendamento.pk]),
        }
        self.posts = {
            'criar_agenda': (self.url_admin, {
                'acao': 'criar_agenda', 'turma': self.turma_b.pk,
                'maquiadora': 'Invasora',
            }),
            'renomear': (self.url_admin, {
                'acao': 'renomear_agenda', 'agenda_id': self.agenda.pk,
                'maquiadora': 'Invasora',
            }),
            'alternar': (self.url_admin, {
                'acao': 'alternar_agenda', 'agenda_id': self.agenda.pk,
            }),
            'adicionar_horario': (
                reverse('admin_dashboard:adicionar_horario_maquiagem',
                        args=[self.agenda.pk]),
                {'horario': '2030-01-01T10:00', 'duracao_minutos': '30'},
            ),
            'excluir_horario': (
                reverse('admin_dashboard:excluir_horario_maquiagem',
                        args=[self.livre.pk]), {},
            ),
            'agendar_admin': (
                reverse('admin_dashboard:agendar_maquiagem_admin',
                        args=[self.livre.pk]),
                {'aluna': self.aluna.pk, 'tipo_servico': 'cabelo'},
            ),
            'editar_post': (
                reverse('admin_dashboard:maquiagem_editar',
                        args=[self.agendamento.pk]),
                {'aluna': self.aluna.pk, 'tipo_servico': 'cabelo',
                 'horario': self.horario.pk},
            ),
            'excluir_agendamento': (
                reverse('admin_dashboard:maquiagem_excluir',
                        args=[self.agendamento.pk]), {},
            ),
        }

    def _nada_mudou(self):
        self.assertEqual(AgendamentoMaquiagem.objects.count(), 1)
        self.agenda.refresh_from_db()
        self.assertEqual(self.agenda.maquiadora, 'Maria')
        self.assertTrue(self.agenda.ativo)
        self.assertEqual(self.agenda.horarios.count(), 2)
        self.assertEqual(AgendaMaquiagemTurma.objects.count(), 1)
        self.agendamento.refresh_from_db()
        self.assertEqual(self.agendamento.tipo_servico, 'maquiagem')

    def test_visitante_e_redirecionado_para_o_login(self):
        for nome, url in self.gets.items():
            with self.subTest(get=nome):
                resposta = self.client.get(url)
                self.assertEqual(resposta.status_code, 302)
                self.assertIn('login', resposta['Location'])
        for nome, (url, dados) in self.posts.items():
            with self.subTest(post=nome):
                resposta = self.client.post(url, dados)
                self.assertEqual(resposta.status_code, 302)
                self.assertIn('login', resposta['Location'])
        self._nada_mudou()

    def test_usuario_comum_logado_nao_e_staff_e_nao_altera_nada(self):
        self.client.force_login(self.responsavel)
        for nome, url in self.gets.items():
            with self.subTest(get=nome):
                self.assertEqual(self.client.get(url).status_code, 302)
        for nome, (url, dados) in self.posts.items():
            with self.subTest(post=nome):
                self.assertEqual(self.client.post(url, dados).status_code, 302)
        self._nada_mudou()

    def test_staff_continua_com_acesso(self):
        self.client.force_login(self.staff)
        for nome, url in self.gets.items():
            with self.subTest(get=nome):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_staff_consegue_agendar_adicionar_e_excluir(self):
        self.client.force_login(self.staff)

        url, dados = self.posts['agendar_admin']
        self.client.post(url, dados)
        self.assertEqual(AgendamentoMaquiagem.objects.count(), 2)

        url, dados = self.posts['adicionar_horario']
        self.client.post(url, dados)
        self.assertEqual(self.agenda.horarios.count(), 3)

        url, dados = self.posts['excluir_agendamento']
        self.client.post(url, dados)
        self.assertEqual(AgendamentoMaquiagem.objects.count(), 1)
