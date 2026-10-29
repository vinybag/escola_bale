"""
Os horários de maquiagem são DA TURMA: toda maquiadora da turma pode atender
em qualquer um deles.

Antes, cada maquiadora tinha os próprios horários. Quem criava os horários com
uma maquiadora e depois adicionava a segunda deixava a segunda sem nenhum
horário, e só dava para agendar com a primeira.
"""

from datetime import datetime, time, timedelta

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from espetaculo.maquiagem_agenda import (
    ErroAgendamento,
    agendar_aluna,
    gerar_horarios,
    montar_grade,
    remover_horario_da_turma,
    sincronizar_horarios_da_turma,
)
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

DIA = timezone.localdate() + timedelta(days=20)


def _dt(hora, minuto=0, dia=DIA):
    return timezone.make_aware(datetime.combine(dia, time(hora, minuto)))


class BaseTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            'staff', 'staff@example.com', 'senha123', is_staff=True
        )
        self.espetaculo = Espetaculo.objects.create(
            titulo='Quebra-Nozes', descricao='x', tipo='evento',
            data_apresentacao=timezone.now() + timedelta(days=40),
            local='Teatro', endereco='Rua A',
        )
        self.turma = Turma.objects.create(nome='Turma A')
        self.outra_turma = Turma.objects.create(nome='Turma B')
        self.ana = self._aluna('Ana')
        self.bia = self._aluna('Bia')
        self.url = reverse(
            'admin_dashboard:espetaculo_maquiagens', args=[self.espetaculo.pk]
        )

    def _aluna(self, nome, turma=None):
        aluna = Aluna.objects.create(nome=nome)
        aluna.turmas.add(turma or self.turma)
        return aluna

    def _agenda(self, nome, turma=None, ativo=True, espetaculo=None):
        return AgendaMaquiagemTurma.objects.create(
            espetaculo=espetaculo or self.espetaculo,
            turma=turma or self.turma, maquiadora=nome, ativo=ativo,
        )

    def _horas(self, agenda):
        return [
            timezone.localtime(h.horario).strftime('%d %H:%M')
            for h in agenda.horarios.order_by('horario')
        ]

    def _criar_horarios(self, agendas, inicio=time(9, 0), fim=time(11, 0)):
        return gerar_horarios(agendas, DIA, inicio, fim, 30)


class SincronizacaoTests(BaseTests):
    def test_a_maquiadora_que_entra_depois_recebe_os_horarios_da_turma(self):
        maria = self._agenda('Maria')
        self._criar_horarios([maria])
        joana = self._agenda('Joana')

        criados = sincronizar_horarios_da_turma(self.espetaculo, self.turma)

        self.assertEqual(criados, 4)
        self.assertEqual(self._horas(joana), self._horas(maria))

    def test_e_idempotente(self):
        maria = self._agenda('Maria')
        self._criar_horarios([maria])
        joana = self._agenda('Joana')

        sincronizar_horarios_da_turma(self.espetaculo, self.turma)
        de_novo = sincronizar_horarios_da_turma(self.espetaculo, self.turma)

        self.assertEqual(de_novo, 0)
        self.assertEqual(joana.horarios.count(), 4)

    def test_nao_mexe_no_que_ja_existe_nem_nos_agendados(self):
        maria = self._agenda('Maria')
        self._criar_horarios([maria])
        joana = self._agenda('Joana')
        horario = maria.horarios.order_by('horario').first()
        agendar_aluna(
            self.espetaculo, self.turma, horario.pk, self.ana.pk, 'cabelo'
        )

        sincronizar_horarios_da_turma(self.espetaculo, self.turma)

        horario.refresh_from_db()
        self.assertEqual(horario.status, 'agendado')
        self.assertEqual(maria.horarios.count(), 4)
        # a cópia da Joana nasce LIVRE: a aluna é da Maria naquele horário
        copia = joana.horarios.get(horario=horario.horario)
        self.assertEqual(copia.status, 'disponivel')

    def test_copia_tambem_a_duracao(self):
        maria = self._agenda('Maria')
        gerar_horarios([maria], DIA, time(9, 0), time(10, 0), 20)
        joana = self._agenda('Joana')

        sincronizar_horarios_da_turma(self.espetaculo, self.turma)

        self.assertTrue(all(h.duracao_minutos == 20 for h in joana.horarios.all()))

    def test_cada_uma_completa_o_que_falta(self):
        maria = self._agenda('Maria')
        joana = self._agenda('Joana')
        HorarioMaquiagem.objects.create(agenda=maria, horario=_dt(9))
        HorarioMaquiagem.objects.create(agenda=joana, horario=_dt(10))

        sincronizar_horarios_da_turma(self.espetaculo, self.turma)

        for agenda in (maria, joana):
            self.assertEqual(self._horas(agenda), [
                f'{DIA:%d} 09:00', f'{DIA:%d} 10:00'
            ])

    def test_maquiadora_desativada_nao_recebe(self):
        maria = self._agenda('Maria')
        self._criar_horarios([maria])
        joana = self._agenda('Joana', ativo=False)

        sincronizar_horarios_da_turma(self.espetaculo, self.turma)

        self.assertEqual(joana.horarios.count(), 0)

    def test_os_horarios_de_uma_desativada_valem_como_origem(self):
        antiga = self._agenda('Antiga', ativo=False)
        self._criar_horarios([antiga])
        nova = self._agenda('Nova')

        sincronizar_horarios_da_turma(self.espetaculo, self.turma)

        self.assertEqual(nova.horarios.count(), 4)

    def test_com_uma_so_maquiadora_nao_faz_nada(self):
        maria = self._agenda('Maria')
        self._criar_horarios([maria])
        self.assertEqual(
            sincronizar_horarios_da_turma(self.espetaculo, self.turma), 0
        )

    def test_nao_vaza_entre_turmas_nem_espetaculos(self):
        maria = self._agenda('Maria')
        self._criar_horarios([maria])
        da_outra_turma = self._agenda('Outra', turma=self.outra_turma)
        outro = Espetaculo.objects.create(
            titulo='Outro', descricao='x', tipo='evento',
            data_apresentacao=timezone.now(), local='L', endereco='E',
        )
        de_outro_espetaculo = self._agenda('Maria', espetaculo=outro)
        self._agenda('Joana')

        sincronizar_horarios_da_turma(self.espetaculo, self.turma)

        self.assertEqual(da_outra_turma.horarios.count(), 0)
        self.assertEqual(de_outro_espetaculo.horarios.count(), 0)

    def test_tres_maquiadoras(self):
        maria = self._agenda('Maria')
        self._criar_horarios([maria])
        joana = self._agenda('Joana')
        clara = self._agenda('Clara')

        sincronizar_horarios_da_turma(self.espetaculo, self.turma)

        self.assertEqual(joana.horarios.count(), 4)
        self.assertEqual(clara.horarios.count(), 4)


@override_settings(STORAGES=STORAGES_TESTE)
class SeuCenarioTests(BaseTests):
    """Criar os horários, escolher a turma, escolher QUALQUER maquiadora, agendar."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.staff)

    def _post(self, **dados):
        return self.client.post(self.url, dados)

    def test_horarios_criados_antes_da_segunda_maquiadora_servem_para_as_duas(self):
        # 1) a turma tem só a Maria e cria os horários
        self._post(acao='criar_agenda', turma=self.turma.pk, maquiadora='Maria')
        self._post(
            acao='gerar_horarios', turma=self.turma.pk, dia=DIA.isoformat(),
            inicio='09:00', fim='11:00', duracao='30', intervalo='0',
        )
        # 2) só DEPOIS entra a Joana
        resposta = self._post(
            acao='criar_agenda', turma=self.turma.pk, maquiadora='Joana'
        )

        pagina = self.client.get(resposta['Location'])
        self.assertContains(pagina, 'Joana já recebeu os 4 horário(s)')

        # 3) a grade mostra os horários livres para as DUAS
        grade = pagina.context['grade']
        for linha in grade['linhas']:
            self.assertEqual(
                {c['agenda'].maquiadora: c['estado'] for c in linha['celulas']},
                {'Joana': 'livre', 'Maria': 'livre'},
            )

    def test_da_para_agendar_com_qualquer_uma_das_duas(self):
        maria = self._agenda('Maria')
        self._criar_horarios([maria])
        joana = self._agenda('Joana')

        pagina = self.client.get(self.url, {'turma': self.turma.pk})
        celulas = pagina.context['grade']['linhas'][0]['celulas']
        horario_da_maria = next(c['horario'] for c in celulas if c['agenda'] == maria)
        horario_da_joana = next(c['horario'] for c in celulas if c['agenda'] == joana)

        for aluna, horario in ((self.ana, horario_da_maria), (self.bia, horario_da_joana)):
            self._post(
                acao='grade', turma=self.turma.pk, dia=DIA.isoformat(),
                aluna=aluna.pk, tipo_servico='maquiagem', agendar=horario.pk,
            )

        # a mesma hora, duas alunas, uma com cada maquiadora
        self.assertEqual(
            {a.aluna.nome: a.horario.agenda.maquiadora
             for a in AgendamentoMaquiagem.objects.all()},
            {'Ana': 'Maria', 'Bia': 'Joana'},
        )

    def test_abrir_a_grade_conserta_dados_que_ja_estavam_assim(self):
        """A situação real: a Joana já existe, sem nenhum horário."""
        maria = self._agenda('Maria')
        self._criar_horarios([maria])
        joana = self._agenda('Joana')
        self.assertEqual(joana.horarios.count(), 0)

        self.client.get(self.url, {'turma': self.turma.pk})

        self.assertEqual(joana.horarios.count(), 4)

    def test_abrir_a_grade_varias_vezes_nao_duplica(self):
        maria = self._agenda('Maria')
        self._criar_horarios([maria])
        joana = self._agenda('Joana')

        for _ in range(3):
            self.client.get(self.url, {'turma': self.turma.pk})

        self.assertEqual(joana.horarios.count(), 4)
        self.assertEqual(maria.horarios.count(), 4)

    def test_criar_horarios_vale_para_todas_sem_escolher_maquiadora(self):
        maria = self._agenda('Maria')
        joana = self._agenda('Joana')

        resposta = self._post(
            acao='gerar_horarios', turma=self.turma.pk, dia=DIA.isoformat(),
            inicio='09:00', fim='10:00', duracao='30', intervalo='0',
        )

        self.assertEqual(maria.horarios.count(), 2)
        self.assertEqual(joana.horarios.count(), 2)
        pagina = self.client.get(resposta['Location'])
        self.assertContains(pagina, '4 horário(s) criado(s)')
        self.assertContains(pagina, 'Joana, Maria')

    def test_criar_horarios_nao_inclui_maquiadora_desativada(self):
        maria = self._agenda('Maria')
        joana = self._agenda('Joana', ativo=False)

        self._post(
            acao='gerar_horarios', turma=self.turma.pk, dia=DIA.isoformat(),
            inicio='09:00', fim='10:00', duracao='30', intervalo='0',
        )

        self.assertEqual(maria.horarios.count(), 2)
        self.assertEqual(joana.horarios.count(), 0)

    def test_reativar_a_maquiadora_devolve_os_horarios_que_ela_perdeu(self):
        maria = self._agenda('Maria')
        joana = self._agenda('Joana', ativo=False)
        self._criar_horarios([maria])
        self.assertEqual(joana.horarios.count(), 0)

        self._post(acao='criar_agenda', turma=self.turma.pk, maquiadora='joana')

        joana.refresh_from_db()
        self.assertTrue(joana.ativo)
        self.assertEqual(joana.horarios.count(), 4)

    def test_criar_horarios_com_a_agenda_antiga_explicita_ainda_funciona(self):
        maria = self._agenda('Maria')
        self._agenda('Joana')
        self._post(
            acao='gerar_horarios', turma=self.turma.pk, agendas=[maria.pk],
            dia=DIA.isoformat(), inicio='09:00', fim='10:00', duracao='30',
        )
        self.assertEqual(maria.horarios.count(), 2)


@override_settings(STORAGES=STORAGES_TESTE)
class TelaTests(BaseTests):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.staff)
        self.maria = self._agenda('Maria')
        self.joana = self._agenda('Joana')
        self._criar_horarios([self.maria, self.joana])

    def test_seletor_de_turma_no_topo(self):
        pagina = self.client.get(self.url)

        self.assertContains(pagina, 'Agendar alunas da turma')
        conteudo = pagina.content.decode()
        inicio = conteudo.index('id="id_turma_agenda"')
        seletor = conteudo[inicio:conteudo.index('</select>', inicio)]
        self.assertIn('Turma A</option>', seletor)
        # só aparecem turmas que já têm maquiadora (a B não tem)
        self.assertNotIn('Turma B', seletor)

    def test_seletor_marca_a_turma_aberta(self):
        pagina = self.client.get(self.url, {'turma': self.turma.pk})
        self.assertContains(
            pagina, f'<option value="{self.turma.pk}" selected>Turma A</option>'
        )

    def test_o_formulario_de_criar_nao_pergunta_a_maquiadora(self):
        pagina = self.client.get(self.url, {'turma': self.turma.pk})

        self.assertNotContains(pagina, 'name="agendas"')
        self.assertNotContains(pagina, 'Maquiadoras que atendem nesse dia')
        self.assertContains(pagina, 'valem para todas as maquiadoras')
        self.assertContains(pagina, 'Joana, Maria')
        self.assertContains(pagina, 'data-maquiadoras="2"')

    def test_o_cartao_da_maquiadora_nao_lista_mais_horarios_soltos(self):
        pagina = self.client.get(
            self.url, {'turma': self.turma.pk, 'agenda_id': self.maria.pk}
        )
        # (o nome ainda existe no CSS da página; o que não pode haver é o botão)
        self.assertNotContains(pagina, 'class="maq-slot-excluir"')
        self.assertContains(pagina, 'Os horários são da turma')

    def test_cada_linha_da_grade_tem_o_botao_de_remover_o_horario(self):
        pagina = self.client.get(self.url, {'turma': self.turma.pk})
        self.assertContains(pagina, 'name="remover_horario"', count=4)
        self.assertContains(
            pagina, f'value="{DIA.isoformat()}T09:00"'
        )
        self.assertContains(
            pagina, 'para todas as maquiadoras da turma?'
        )


@override_settings(STORAGES=STORAGES_TESTE)
class RemoverHorarioDaTurmaTests(BaseTests):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.staff)
        self.maria = self._agenda('Maria')
        self.joana = self._agenda('Joana')
        self._criar_horarios([self.maria, self.joana])
        self.chave = f'{DIA.isoformat()}T09:00'

    def test_remove_o_horario_de_todas_as_maquiadoras(self):
        removidos = remover_horario_da_turma(
            self.espetaculo, self.turma, self.chave
        )

        self.assertEqual(removidos, 2)
        for agenda in (self.maria, self.joana):
            self.assertNotIn(f'{DIA:%d} 09:00', self._horas(agenda))
            self.assertEqual(agenda.horarios.count(), 3)

    def test_e_nao_volta_na_proxima_sincronizacao(self):
        remover_horario_da_turma(self.espetaculo, self.turma, self.chave)

        sincronizar_horarios_da_turma(self.espetaculo, self.turma)
        montar_grade(self.espetaculo, self.turma, DIA)

        self.assertEqual(self.maria.horarios.count(), 3)
        self.assertEqual(self.joana.horarios.count(), 3)

    def test_recusa_se_alguma_aluna_estiver_agendada_nele(self):
        horario = self.joana.horarios.get(horario=_dt(9))
        agendar_aluna(
            self.espetaculo, self.turma, horario.pk, self.ana.pk, 'cabelo'
        )

        with self.assertRaises(ErroAgendamento) as ctx:
            remover_horario_da_turma(self.espetaculo, self.turma, self.chave)

        self.assertIn('aluna agendada', str(ctx.exception))
        self.assertEqual(self.maria.horarios.count(), 4)  # nada foi apagado
        self.assertEqual(self.joana.horarios.count(), 4)

    def test_chave_invalida_ou_inexistente(self):
        for chave in ('abc', '', None, '2026-13-45T99:99'):
            with self.subTest(chave=chave):
                with self.assertRaises(ErroAgendamento):
                    remover_horario_da_turma(self.espetaculo, self.turma, chave)
        with self.assertRaises(ErroAgendamento):
            remover_horario_da_turma(
                self.espetaculo, self.turma, f'{DIA.isoformat()}T23:00'
            )

    def test_nao_remove_de_outra_turma(self):
        outra = self._agenda('Outra', turma=self.outra_turma)
        HorarioMaquiagem.objects.create(agenda=outra, horario=_dt(9))

        remover_horario_da_turma(self.espetaculo, self.turma, self.chave)

        self.assertEqual(outra.horarios.count(), 1)

    def test_pela_grade(self):
        resposta = self.client.post(self.url, {
            'acao': 'grade', 'turma': self.turma.pk, 'dia': DIA.isoformat(),
            'remover_horario': self.chave,
        })

        self.assertEqual(self.maria.horarios.count(), 3)
        pagina = self.client.get(resposta['Location'])
        self.assertContains(pagina, 'Horário removido para todas as maquiadoras')

    def test_pela_grade_com_aluna_agendada_explica(self):
        horario = self.maria.horarios.get(horario=_dt(9))
        agendar_aluna(
            self.espetaculo, self.turma, horario.pk, self.ana.pk, 'cabelo'
        )

        resposta = self.client.post(self.url, {
            'acao': 'grade', 'turma': self.turma.pk, 'dia': DIA.isoformat(),
            'remover_horario': self.chave,
        })

        self.assertEqual(self.maria.horarios.count(), 4)
        pagina = self.client.get(resposta['Location'])
        self.assertContains(pagina, 'Há uma aluna agendada')

    def test_o_endpoint_antigo_de_excluir_tambem_apaga_da_turma_toda(self):
        livre = self.maria.horarios.get(horario=_dt(9))

        self.client.post(
            reverse('admin_dashboard:excluir_horario_maquiagem', args=[livre.pk])
        )

        self.assertEqual(self.maria.horarios.count(), 3)
        self.assertEqual(self.joana.horarios.count(), 3)

    def test_o_endpoint_antigo_recusa_se_houver_aluna(self):
        livre = self.maria.horarios.get(horario=_dt(9))
        ocupado = self.joana.horarios.get(horario=_dt(9))
        agendar_aluna(
            self.espetaculo, self.turma, ocupado.pk, self.ana.pk, 'cabelo'
        )

        self.client.post(
            reverse('admin_dashboard:excluir_horario_maquiagem', args=[livre.pk])
        )

        self.assertEqual(self.maria.horarios.count(), 4)
