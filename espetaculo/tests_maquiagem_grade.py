"""
Agenda de maquiagem: grade por horário, criação de horários em lote, agendar
e remover pelo painel, e a área da aluna (só vê o que é dela).
"""

from datetime import date, datetime, time, timedelta

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from espetaculo.maquiagem_agenda import (
    MAX_HORARIOS_POR_MAQUIADORA,
    ErroAgendamento,
    agendar_aluna,
    alunas_sem_horario,
    gerar_horarios,
    horarios_da_familia,
    montar_grade,
    remover_agendamento,
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
        self.turma_a = Turma.objects.create(nome='Turma A')
        self.turma_b = Turma.objects.create(nome='Turma B')

        self.resp_ana = User.objects.create_user('resp_ana', 'a@x.com', 'senha123')
        self.resp_bia = User.objects.create_user('resp_bia', 'b@x.com', 'senha123')

        self.ana = self._aluna('Ana', self.turma_a, self.resp_ana)
        self.bia = self._aluna('Bia', self.turma_a, self.resp_bia)
        self.clara = self._aluna('Clara', self.turma_a)
        self.dora = self._aluna('Dora', self.turma_a, ativa=False)
        self.eva = self._aluna('Eva', self.turma_b)

        self.maria = self._agenda('Maria')
        self.joana = self._agenda('Joana')
        self.url = reverse(
            'admin_dashboard:espetaculo_maquiagens', args=[self.espetaculo.pk]
        )

    # ---------- atalhos ----------

    def _aluna(self, nome, turma, responsavel=None, ativa=True):
        aluna = Aluna.objects.create(
            nome=nome, responsavel=responsavel, ativa=ativa
        )
        aluna.turmas.add(turma)
        return aluna

    def _agenda(self, maquiadora, turma=None, **extra):
        return AgendaMaquiagemTurma.objects.create(
            espetaculo=extra.pop('espetaculo', self.espetaculo),
            turma=turma or self.turma_a,
            maquiadora=maquiadora,
            ativo=extra.pop('ativo', True),
        )

    def _h(self, agenda, hora, minuto=0, dia=DIA, status='disponivel'):
        return HorarioMaquiagem.objects.create(
            agenda=agenda, horario=_dt(hora, minuto, dia), status=status,
        )

    def _agendar(self, aluna, horario, tipo='maquiagem'):
        return agendar_aluna(
            self.espetaculo, horario.agenda.turma, horario.pk, aluna.pk, tipo
        )


# ===========================================================================
# B. Criar horários em lote
# ===========================================================================

class GerarHorariosServicoTests(BaseTests):
    def _gerar(self, agendas=None, inicio=time(9, 0), fim=time(11, 0),
               duracao=30, intervalo=0, dia=DIA, hoje=None):
        return gerar_horarios(
            agendas if agendas is not None else [self.maria, self.joana],
            dia, inicio, fim, duracao, intervalo, hoje=hoje,
        )

    def test_cria_os_horarios_do_periodo_para_cada_maquiadora(self):
        resultado = self._gerar()

        self.assertEqual(
            resultado, {'criados': 8, 'existentes': 0, 'por_agenda': 4}
        )
        for agenda in (self.maria, self.joana):
            horas = [
                timezone.localtime(h.horario).strftime('%H:%M')
                for h in agenda.horarios.order_by('horario')
            ]
            self.assertEqual(horas, ['09:00', '09:30', '10:00', '10:30'])
            self.assertTrue(
                all(h.duracao_minutos == 30 for h in agenda.horarios.all())
            )

    def test_o_horario_e_gravado_no_fuso_local_e_nao_em_utc(self):
        self._gerar(inicio=time(9, 0), fim=time(9, 30))
        horario = self.maria.horarios.get()
        self.assertEqual(timezone.localtime(horario.horario).hour, 9)

    def test_o_ultimo_horario_termina_exatamente_no_fim(self):
        self._gerar(inicio=time(9, 0), fim=time(10, 0))
        self.assertEqual(self.maria.horarios.count(), 2)  # 09:00 e 09:30

    def test_intervalo_entre_horarios(self):
        # 30 min + 15 de intervalo: 09:00, 09:45, 10:30
        resultado = self._gerar(
            inicio=time(9, 0), fim=time(11, 0), duracao=30, intervalo=15
        )
        horas = [
            timezone.localtime(h.horario).strftime('%H:%M')
            for h in self.maria.horarios.order_by('horario')
        ]
        self.assertEqual(horas, ['09:00', '09:45', '10:30'])
        self.assertEqual(resultado['por_agenda'], 3)

    def test_so_as_agendas_escolhidas_recebem(self):
        self._gerar(agendas=[self.maria])
        self.assertEqual(self.maria.horarios.count(), 4)
        self.assertEqual(self.joana.horarios.count(), 0)

    def test_repetir_nao_duplica(self):
        self._gerar()
        resultado = self._gerar()
        self.assertEqual(resultado['criados'], 0)
        self.assertEqual(resultado['existentes'], 8)
        self.assertEqual(HorarioMaquiagem.objects.count(), 8)

    def test_completa_so_o_que_falta(self):
        self._h(self.maria, 9, 0)
        resultado = self._gerar(agendas=[self.maria])
        self.assertEqual(resultado['criados'], 3)
        self.assertEqual(resultado['existentes'], 1)

    def test_nao_mexe_em_horario_ja_agendado(self):
        horario = self._h(self.maria, 9, 0)
        self._agendar(self.ana, horario)

        self._gerar(agendas=[self.maria])

        horario.refresh_from_db()
        self.assertEqual(horario.status, 'agendado')
        self.assertTrue(AgendamentoMaquiagem.objects.filter(aluna=self.ana).exists())

    def test_erros_nao_criam_nada(self):
        casos = {
            'sem maquiadora': dict(agendas=[]),
            'data passada': dict(
                dia=timezone.localdate() - timedelta(days=1)
            ),
            'fim antes do inicio': dict(inicio=time(11, 0), fim=time(9, 0)),
            'fim igual ao inicio': dict(inicio=time(9, 0), fim=time(9, 0)),
            'duracao curta': dict(duracao=4),
            'duracao longa': dict(duracao=241),
            'intervalo negativo': dict(intervalo=-1),
            'intervalo grande': dict(intervalo=121),
            'periodo curto demais': dict(
                inicio=time(9, 0), fim=time(9, 10), duracao=30
            ),
        }
        for nome, kwargs in casos.items():
            with self.subTest(nome):
                with self.assertRaises(ErroAgendamento):
                    self._gerar(**kwargs)
        self.assertEqual(HorarioMaquiagem.objects.count(), 0)

    def test_trava_contra_excesso_de_horarios(self):
        with self.assertRaises(ErroAgendamento):
            self._gerar(
                inicio=time(0, 0), fim=time(23, 59), duracao=5, intervalo=0
            )
        self.assertEqual(HorarioMaquiagem.objects.count(), 0)
        self.assertGreater(MAX_HORARIOS_POR_MAQUIADORA, 50)

    def test_hoje_e_permitido(self):
        hoje = timezone.localdate()
        resultado = self._gerar(dia=hoje, hoje=hoje)
        self.assertEqual(resultado['criados'], 8)


@override_settings(STORAGES=STORAGES_TESTE)
class GerarHorariosViewTests(BaseTests):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.staff)

    def _post(self, **dados):
        base = {
            'acao': 'gerar_horarios', 'turma': self.turma_a.pk,
            'agendas': [self.maria.pk, self.joana.pk],
            'dia': DIA.isoformat(), 'inicio': '09:00', 'fim': '11:00',
            'duracao': '30', 'intervalo': '0',
        }
        base.update(dados)
        return self.client.post(self.url, base)

    def test_cria_e_volta_para_a_grade_do_dia(self):
        resposta = self._post()

        self.assertEqual(HorarioMaquiagem.objects.count(), 8)
        self.assertRedirects(
            resposta,
            f'{self.url}?turma={self.turma_a.pk}&dia={DIA.isoformat()}',
            fetch_redirect_response=False,
        )
        pagina = self.client.get(resposta['Location'])
        self.assertContains(pagina, '8 horário(s) criado(s)')

    def test_mensagem_conta_os_que_ja_existiam(self):
        self._post()
        resposta = self._post()
        pagina = self.client.get(resposta['Location'])
        self.assertContains(pagina, '0 horário(s) criado(s)')
        self.assertContains(pagina, '8 já existia(m)')

    def test_agenda_de_outra_turma_ou_espetaculo_e_ignorada(self):
        outra_turma = self._agenda('Outra', turma=self.turma_b)
        outro = Espetaculo.objects.create(
            titulo='Outro', descricao='x', tipo='evento',
            data_apresentacao=timezone.now(), local='L', endereco='E',
        )
        alheia = self._agenda('Alheia', espetaculo=outro)

        self._post(agendas=[outra_turma.pk, alheia.pk])

        self.assertEqual(HorarioMaquiagem.objects.count(), 0)

    def test_campos_vazios_ou_invalidos_nao_quebram_nem_criam(self):
        casos = [
            {'dia': ''}, {'dia': 'xx'}, {'inicio': ''}, {'fim': 'abc'},
            {'duracao': ''}, {'duracao': 'abc'}, {'intervalo': 'x'},
            {'agendas': ['abc']}, {'turma': 'abc'},
            {'turma': 999999},
        ]
        for dados in casos:
            with self.subTest(dados=dados):
                resposta = self._post(**dados)
                self.assertEqual(resposta.status_code, 302)
        self.assertEqual(HorarioMaquiagem.objects.count(), 0)

    def test_data_passada_e_recusada_com_mensagem(self):
        resposta = self._post(
            dia=(timezone.localdate() - timedelta(days=2)).isoformat()
        )
        self.assertEqual(HorarioMaquiagem.objects.count(), 0)
        pagina = self.client.get(resposta['Location'])
        self.assertContains(pagina, 'já passou')


# ===========================================================================
# A. A grade
# ===========================================================================

class MontarGradeTests(BaseTests):
    def test_uma_coluna_por_maquiadora_e_uma_linha_por_horario(self):
        self._h(self.maria, 9)
        self._h(self.joana, 9)
        self._h(self.maria, 9, 30)

        grade = montar_grade(self.espetaculo, self.turma_a, DIA)

        self.assertEqual(
            [a.maquiadora for a in grade['agendas']], ['Joana', 'Maria']
        )
        self.assertEqual(
            [l['hora'] for l in grade['linhas']], [time(9, 0), time(9, 30)]
        )

    def test_estados_das_celulas(self):
        livre = self._h(self.maria, 9)
        ocupado = self._h(self.maria, 9, 30)
        self._agendar(self.ana, ocupado)
        self._h(self.maria, 10, status='reservado_temporario')
        HorarioMaquiagem.objects.filter(
            agenda=self.maria, horario=_dt(10)
        ).update(reservado_em=timezone.now())
        self._h(self.maria, 10, 30, status='bloqueado_manual')
        self._h(self.joana, 9)  # Joana só tinha 09:00; o resto vem da turma

        grade = montar_grade(self.espetaculo, self.turma_a, DIA)
        por_hora = {
            l['hora']: {c['agenda'].maquiadora: c for c in l['celulas']}
            for l in grade['linhas']
        }

        self.assertEqual(por_hora[time(9, 0)]['Maria']['estado'], 'livre')
        self.assertEqual(por_hora[time(9, 0)]['Maria']['horario'], livre)
        self.assertEqual(por_hora[time(9, 30)]['Maria']['estado'], 'ocupado')
        self.assertEqual(
            por_hora[time(9, 30)]['Maria']['agendamento'].aluna, self.ana
        )
        self.assertEqual(por_hora[time(10, 0)]['Maria']['estado'], 'reservado')
        self.assertEqual(por_hora[time(10, 30)]['Maria']['estado'], 'bloqueado')
        # Os horários são da turma: a Joana também ganha o 09:30 (livre)...
        self.assertEqual(por_hora[time(9, 30)]['Joana']['estado'], 'livre')
        self.assertEqual(por_hora[time(9, 0)]['Joana']['estado'], 'livre')

    def test_maquiadora_desativada_nao_recebe_os_horarios_da_turma(self):
        AgendaMaquiagemTurma.objects.filter(pk=self.joana.pk).update(ativo=False)
        self._h(self.maria, 9)

        grade = montar_grade(self.espetaculo, self.turma_a, DIA)
        celulas = {c['agenda'].maquiadora: c['estado']
                   for c in grade['linhas'][0]['celulas']}

        self.assertEqual(celulas, {'Joana': 'ausente', 'Maria': 'livre'})

    def test_dias_com_contagem_de_livres(self):
        self._h(self.maria, 9)
        ocupado = self._h(self.maria, 10)
        self._agendar(self.ana, ocupado)
        self._h(self.maria, 9, dia=DIA + timedelta(days=1))

        grade = montar_grade(self.espetaculo, self.turma_a, DIA)

        # Maria tem 2 horários no dia 1 (um ocupado) e 1 no dia 2; a Joana
        # recebe os mesmos 3, todos livres.
        self.assertEqual(
            [(d['data'], d['total'], d['livres']) for d in grade['dias']],
            [(DIA, 4, 3), (DIA + timedelta(days=1), 2, 2)],
        )
        self.assertEqual(grade['livres_total'], 5)

    def test_dia_padrao_e_o_primeiro_com_horario_livre(self):
        AgendaMaquiagemTurma.objects.filter(pk=self.joana.pk).update(ativo=False)
        lotado = self._h(self.maria, 9)
        self._agendar(self.ana, lotado)
        self._h(self.maria, 9, dia=DIA + timedelta(days=1))

        grade = montar_grade(self.espetaculo, self.turma_a)

        self.assertEqual(grade['dia'], DIA + timedelta(days=1))

    def test_dia_pedido_e_respeitado_e_dia_invalido_cai_no_padrao(self):
        self._h(self.maria, 9)
        self._h(self.maria, 9, dia=DIA + timedelta(days=1))

        pedido = montar_grade(
            self.espetaculo, self.turma_a, DIA + timedelta(days=1)
        )
        invalido = montar_grade(
            self.espetaculo, self.turma_a, DIA + timedelta(days=9)
        )

        self.assertEqual(pedido['dia'], DIA + timedelta(days=1))
        self.assertEqual(invalido['dia'], DIA)

    def test_sem_horarios_nao_quebra(self):
        grade = montar_grade(self.espetaculo, self.turma_a)
        self.assertIsNone(grade['dia'])
        self.assertEqual(grade['linhas'], [])
        self.assertEqual(grade['livres_total'], 0)

    def test_reserva_expirada_volta_a_ficar_livre(self):
        h = self._h(self.maria, 9, status='reservado_temporario')
        HorarioMaquiagem.objects.filter(pk=h.pk).update(
            reservado_em=timezone.now() - timedelta(minutes=40),
            reservado_por_sessao='x',
        )

        grade = montar_grade(self.espetaculo, self.turma_a, DIA)

        self.assertEqual(grade['linhas'][0]['celulas'][1]['estado'], 'livre')

    def test_turma_sem_agenda(self):
        grade = montar_grade(self.espetaculo, self.turma_b, DIA)
        self.assertEqual(grade['agendas'], [])

    def test_nao_mistura_horarios_de_outra_turma(self):
        outra = self._agenda('Outra', turma=self.turma_b)
        self._h(outra, 9)
        self._h(self.maria, 10)

        grade = montar_grade(self.espetaculo, self.turma_a, DIA)

        self.assertEqual([l['hora'] for l in grade['linhas']], [time(10, 0)])


class AlunasSemHorarioTests(BaseTests):
    def test_so_ativas_da_turma_ordenadas_por_nome(self):
        nomes = [a.nome for a in alunas_sem_horario(self.espetaculo, self.turma_a)]
        self.assertEqual(nomes, ['Ana', 'Bia', 'Clara'])  # sem Dora (inativa) e Eva

    def test_quem_ja_tem_horario_sai_da_lista(self):
        self._agendar(self.ana, self._h(self.maria, 9))
        nomes = [a.nome for a in alunas_sem_horario(self.espetaculo, self.turma_a)]
        self.assertEqual(nomes, ['Bia', 'Clara'])

    def test_horario_em_outro_espetaculo_nao_conta(self):
        outro = Espetaculo.objects.create(
            titulo='Outro', descricao='x', tipo='evento',
            data_apresentacao=timezone.now(), local='L', endereco='E',
        )
        agenda = self._agenda('Z', espetaculo=outro)
        horario = HorarioMaquiagem.objects.create(
            agenda=agenda, horario=_dt(9)
        )
        agendar_aluna(outro, self.turma_a, horario.pk, self.ana.pk, 'cabelo')

        nomes = [a.nome for a in alunas_sem_horario(self.espetaculo, self.turma_a)]
        self.assertIn('Ana', nomes)

    def test_aluna_em_duas_turmas_aparece_uma_vez(self):
        self.ana.turmas.add(self.turma_b)
        nomes = [a.nome for a in alunas_sem_horario(self.espetaculo, self.turma_b)]
        self.assertEqual(nomes.count('Ana'), 1)


# ===========================================================================
# A. Agendar e remover (serviço)
# ===========================================================================

class AgendarAlunaServicoTests(BaseTests):
    def test_agenda_e_ocupa_o_horario(self):
        horario = self._h(self.maria, 9)

        agendamento = self._agendar(self.ana, horario, 'cabelo')

        horario.refresh_from_db()
        self.assertEqual(horario.status, 'agendado')
        self.assertEqual(agendamento.aluna, self.ana)
        self.assertEqual(agendamento.tipo_servico, 'cabelo')
        self.assertTrue(agendamento.criado_por_admin)

    def test_aluna_nao_pode_ter_dois_horarios_no_mesmo_espetaculo(self):
        primeiro = self._h(self.maria, 9)
        segundo = self._h(self.joana, 10)
        self._agendar(self.ana, primeiro)

        with self.assertRaises(ErroAgendamento) as ctx:
            self._agendar(self.ana, segundo)

        mensagem = str(ctx.exception)
        self.assertIn('Ana já tem horário', mensagem)
        self.assertIn('Maria', mensagem)  # diz onde ela já está
        segundo.refresh_from_db()
        self.assertEqual(segundo.status, 'disponivel')
        self.assertEqual(AgendamentoMaquiagem.objects.count(), 1)

    def test_horario_ocupado_e_recusado(self):
        horario = self._h(self.maria, 9)
        self._agendar(self.ana, horario)

        with self.assertRaises(ErroAgendamento) as ctx:
            self._agendar(self.bia, horario)

        self.assertIn('não está mais disponível', str(ctx.exception))
        self.assertEqual(
            AgendamentoMaquiagem.objects.filter(aluna=self.bia).count(), 0
        )

    def test_aluna_de_outra_turma_e_recusada(self):
        with self.assertRaises(ErroAgendamento):
            self._agendar(self.eva, self._h(self.maria, 9))

    def test_aluna_inativa_e_recusada(self):
        with self.assertRaises(ErroAgendamento):
            self._agendar(self.dora, self._h(self.maria, 9))

    def test_horario_de_outra_turma_e_recusado(self):
        outra = self._agenda('Outra', turma=self.turma_b)
        horario = self._h(outra, 9)
        with self.assertRaises(ErroAgendamento):
            agendar_aluna(
                self.espetaculo, self.turma_a, horario.pk, self.ana.pk, 'cabelo'
            )

    def test_horario_de_outro_espetaculo_e_recusado(self):
        outro = Espetaculo.objects.create(
            titulo='Outro', descricao='x', tipo='evento',
            data_apresentacao=timezone.now(), local='L', endereco='E',
        )
        agenda = self._agenda('Z', espetaculo=outro)
        horario = HorarioMaquiagem.objects.create(agenda=agenda, horario=_dt(9))
        with self.assertRaises(ErroAgendamento):
            agendar_aluna(
                self.espetaculo, self.turma_a, horario.pk, self.ana.pk, 'cabelo'
            )

    def test_servico_invalido(self):
        with self.assertRaises(ErroAgendamento):
            agendar_aluna(
                self.espetaculo, self.turma_a, self._h(self.maria, 9).pk,
                self.ana.pk, 'inexistente',
            )

    def test_ids_invalidos(self):
        for aluna_id, horario_id in [('abc', 1), (None, 1), ('1', 'x'), ('', '')]:
            with self.subTest(aluna=aluna_id, horario=horario_id):
                with self.assertRaises(ErroAgendamento):
                    agendar_aluna(
                        self.espetaculo, self.turma_a, horario_id, aluna_id,
                        'maquiagem',
                    )

    def test_reserva_expirada_pode_receber_a_aluna(self):
        horario = self._h(self.maria, 9, status='reservado_temporario')
        HorarioMaquiagem.objects.filter(pk=horario.pk).update(
            reservado_em=timezone.now() - timedelta(minutes=40),
            reservado_por_sessao='x',
        )

        self._agendar(self.ana, horario)

        horario.refresh_from_db()
        self.assertEqual(horario.status, 'agendado')

    def test_reserva_ainda_valida_bloqueia(self):
        horario = self._h(self.maria, 9, status='reservado_temporario')
        HorarioMaquiagem.objects.filter(pk=horario.pk).update(
            reservado_em=timezone.now(), reservado_por_sessao='x',
        )
        with self.assertRaises(ErroAgendamento):
            self._agendar(self.ana, horario)

    def test_remover_libera_o_horario_e_a_aluna_volta_para_a_lista(self):
        horario = self._h(self.maria, 9)
        agendamento = self._agendar(self.ana, horario)

        nome = remover_agendamento(self.espetaculo, agendamento.pk)

        self.assertEqual(nome, 'Ana')
        horario.refresh_from_db()
        self.assertEqual(horario.status, 'disponivel')
        self.assertIn(
            self.ana, alunas_sem_horario(self.espetaculo, self.turma_a)
        )

    def test_remover_de_outro_espetaculo_e_recusado(self):
        agendamento = self._agendar(self.ana, self._h(self.maria, 9))
        outro = Espetaculo.objects.create(
            titulo='Outro', descricao='x', tipo='evento',
            data_apresentacao=timezone.now(), local='L', endereco='E',
        )
        with self.assertRaises(ErroAgendamento):
            remover_agendamento(outro, agendamento.pk)
        self.assertTrue(AgendamentoMaquiagem.objects.filter(pk=agendamento.pk).exists())

    def test_remover_inexistente(self):
        with self.assertRaises(ErroAgendamento):
            remover_agendamento(self.espetaculo, 999999)


# ===========================================================================
# A. A grade no painel (tela)
# ===========================================================================

@override_settings(STORAGES=STORAGES_TESTE)
class GradeNoPainelTests(BaseTests):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.staff)
        for hora, minuto in ((9, 0), (9, 30), (10, 0)):
            self._h(self.maria, hora, minuto)
            self._h(self.joana, hora, minuto)

    def _grade(self, **params):
        base = {'turma': self.turma_a.pk}
        base.update(params)
        return self.client.get(self.url, base)

    def _post_grade(self, **dados):
        base = {
            'acao': 'grade', 'turma': self.turma_a.pk, 'dia': DIA.isoformat(),
            'tipo_servico': 'maquiagem', 'aluna': self.ana.pk,
        }
        base.update(dados)
        return self.client.post(self.url, base)

    def _h_de(self, agenda, hora, minuto=0):
        return HorarioMaquiagem.objects.get(agenda=agenda, horario=_dt(hora, minuto))

    # ---------- o que a tela mostra ----------

    def test_mostra_as_colunas_os_horarios_e_as_alunas_sem_horario(self):
        resposta = self._grade()

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'Agenda por horário · Turma A')
        self.assertContains(resposta, 'Joana')
        self.assertContains(resposta, 'Maria')
        self.assertContains(resposta, '09:30')
        self.assertContains(resposta, 'name="agendar"', count=6)
        self.assertEqual(
            [a.nome for a in resposta.context['pendentes']],
            ['Ana', 'Bia', 'Clara'],
        )

    def test_nao_mostra_aluna_inativa_nem_de_outra_turma(self):
        resposta = self._grade()
        nomes = [a.nome for a in resposta.context['pendentes']]
        self.assertNotIn('Dora', nomes)
        self.assertNotIn('Eva', nomes)

    def test_a_primeira_aluna_ja_vem_selecionada(self):
        resposta = self._grade()
        self.assertContains(
            resposta,
            f'name="aluna" value="{self.ana.pk}" checked',
        )

    def test_aluna_agendada_some_da_lista_e_aparece_no_horario(self):
        self._agendar(self.ana, self._h_de(self.maria, 9))

        resposta = self._grade()

        self.assertEqual(
            [a.nome for a in resposta.context['pendentes']], ['Bia', 'Clara']
        )
        self.assertContains(resposta, 'name="remover"')
        self.assertContains(resposta, 'Ana')
        # a próxima da lista já fica selecionada
        self.assertContains(
            resposta, f'name="aluna" value="{self.bia.pk}" checked'
        )

    def test_avisa_quando_faltam_horarios(self):
        for h in HorarioMaquiagem.objects.all()[:5]:
            h.delete()  # sobra 1 horário livre para 3 alunas

        resposta = self._grade()

        self.assertContains(resposta, 'Faltam horários livres')

    def test_nao_avisa_quando_ha_horarios_de_sobra(self):
        resposta = self._grade()
        self.assertNotContains(resposta, 'Faltam horários livres')

    def test_turma_sem_maquiadora_explica(self):
        resposta = self.client.get(self.url, {'turma': self.turma_b.pk})
        self.assertContains(resposta, 'ainda não tem maquiadora')

    def test_turma_invalida_nao_quebra(self):
        for valor in ('abc', '999999', ''):
            self.assertEqual(
                self.client.get(self.url, {'turma': valor}).status_code, 200
            )

    def test_o_servico_escolhido_e_mantido(self):
        resposta = self._grade(tipo='cabelo')
        self.assertContains(resposta, '<option value="cabelo" selected>')

    def test_servico_invalido_cai_em_maquiagem(self):
        resposta = self._grade(tipo='xxx')
        self.assertContains(resposta, '<option value="maquiagem" selected>')

    def test_dias_aparecem_como_abas(self):
        self._h(self.maria, 9, dia=DIA + timedelta(days=1))
        resposta = self._grade()
        self.assertContains(resposta, f'dia={DIA.isoformat()}')
        self.assertContains(resposta, f'dia={(DIA + timedelta(days=1)).isoformat()}')

    def test_sem_horarios_abre_o_formulario_de_criar(self):
        HorarioMaquiagem.objects.all().delete()
        resposta = self._grade()
        self.assertContains(resposta, '<details class="maq-gerar" open>')
        self.assertNotContains(resposta, 'name="agendar"')

    def test_um_botao_escondido_evita_acao_acidental_com_enter(self):
        resposta = self._grade()
        conteudo = resposta.content.decode()
        escondido = conteudo.index('name="nada"')
        primeiro_agendar = conteudo.index('name="agendar"')
        self.assertLess(escondido, primeiro_agendar)

    # ---------- agendar pela grade ----------

    def test_clicar_no_horario_livre_agenda_e_volta_para_a_grade(self):
        horario = self._h_de(self.joana, 9, 30)

        resposta = self._post_grade(agendar=horario.pk, tipo_servico='cabelo')

        agendamento = AgendamentoMaquiagem.objects.get()
        self.assertEqual(agendamento.aluna, self.ana)
        self.assertEqual(agendamento.horario, horario)
        self.assertEqual(agendamento.tipo_servico, 'cabelo')
        self.assertRedirects(
            resposta,
            f'{self.url}?turma={self.turma_a.pk}&dia={DIA.isoformat()}&tipo=cabelo',
            fetch_redirect_response=False,
        )
        pagina = self.client.get(resposta['Location'])
        self.assertContains(pagina, 'Ana agendada')
        self.assertContains(pagina, 'com Joana')

    def test_agendar_a_mesma_aluna_de_novo_e_barrado(self):
        self._post_grade(agendar=self._h_de(self.maria, 9).pk)
        resposta = self._post_grade(agendar=self._h_de(self.joana, 9).pk)

        self.assertEqual(AgendamentoMaquiagem.objects.count(), 1)
        pagina = self.client.get(resposta['Location'])
        self.assertContains(pagina, 'Ana já tem horário')

    def test_horario_ja_ocupado_e_barrado(self):
        horario = self._h_de(self.maria, 9)
        self._post_grade(agendar=horario.pk, aluna=self.ana.pk)
        resposta = self._post_grade(agendar=horario.pk, aluna=self.bia.pk)

        self.assertEqual(AgendamentoMaquiagem.objects.count(), 1)
        pagina = self.client.get(resposta['Location'])
        self.assertContains(pagina, 'não está mais disponível')

    def test_sem_aluna_selecionada_explica(self):
        resposta = self._post_grade(
            agendar=self._h_de(self.maria, 9).pk, aluna=''
        )
        pagina = self.client.get(resposta['Location'])
        self.assertContains(pagina, 'Escolha uma aluna')
        self.assertEqual(AgendamentoMaquiagem.objects.count(), 0)

    def test_aluna_de_outra_turma_e_barrada(self):
        self._post_grade(
            agendar=self._h_de(self.maria, 9).pk, aluna=self.eva.pk
        )
        self.assertEqual(AgendamentoMaquiagem.objects.count(), 0)

    def test_entradas_invalidas_nao_quebram(self):
        casos = [
            {'agendar': 'abc'}, {'agendar': 999999}, {'remover': 'abc'},
            {'remover': 999999}, {'tipo_servico': 'xxx', 'agendar': 1},
            {'turma': 'abc'}, {'turma': 999999}, {'aluna': 'abc', 'agendar': 1},
        ]
        for dados in casos:
            with self.subTest(dados=dados):
                self.assertEqual(self._post_grade(**dados).status_code, 302)
        self.assertEqual(AgendamentoMaquiagem.objects.count(), 0)

    def test_enter_no_formulario_nao_faz_nada(self):
        # O navegador usa o botão escondido "nada" quando alguém aperta Enter.
        horario = self._h_de(self.maria, 9)
        resposta = self._post_grade(nada='1')

        self.assertEqual(resposta.status_code, 302)
        horario.refresh_from_db()
        self.assertEqual(horario.status, 'disponivel')
        self.assertEqual(AgendamentoMaquiagem.objects.count(), 0)

    # ---------- remover pela grade ----------

    def test_remover_devolve_a_aluna_para_a_lista(self):
        agendamento = self._agendar(self.ana, self._h_de(self.maria, 9))

        resposta = self._post_grade(remover=agendamento.pk)

        self.assertEqual(AgendamentoMaquiagem.objects.count(), 0)
        self.assertEqual(self._h_de(self.maria, 9).status, 'disponivel')
        pagina = self.client.get(resposta['Location'])
        self.assertContains(pagina, 'Ana voltou para a lista')
        self.assertIn(self.ana, pagina.context['pendentes'])

    def test_o_botao_remover_pede_confirmacao(self):
        self._agendar(self.ana, self._h_de(self.maria, 9))
        resposta = self._grade()
        self.assertContains(resposta, "return confirm('Remover Ana deste horário?')")

    # ---------- quem escolhe ----------

    def test_alternar_quem_escolhe_os_horarios(self):
        self.assertFalse(self.espetaculo.maquiagem_familia_escolhe_horario)

        self.client.post(self.url, {'acao': 'alternar_escolha_familia'})
        self.espetaculo.refresh_from_db()
        self.assertTrue(self.espetaculo.maquiagem_familia_escolhe_horario)

        self.client.post(self.url, {'acao': 'alternar_escolha_familia'})
        self.espetaculo.refresh_from_db()
        self.assertFalse(self.espetaculo.maquiagem_familia_escolhe_horario)

    def test_a_tela_explica_quem_escolhe(self):
        resposta = self.client.get(self.url)
        self.assertContains(resposta, 'Hoje só a escola agenda')
        self.assertContains(resposta, 'Permitir que as famílias escolham')

    # ---------- o resto da tela continua ----------

    def test_pagina_sem_turma_mostra_as_turmas_com_o_botao_de_agendar(self):
        resposta = self.client.get(self.url)
        self.assertContains(resposta, 'Agendar alunas')
        self.assertContains(resposta, f'?turma={self.turma_a.pk}')
        self.assertNotContains(resposta, 'id="agenda-por-horario"')

    def test_a_tela_antiga_de_agendar_manualmente_saiu(self):
        resposta = self._grade()
        self.assertNotContains(resposta, 'Agendar manualmente')
        self.assertNotContains(resposta, 'form-agendar-manual')

    def test_download_do_png_continua_na_pagina(self):
        self._agendar(self.ana, self._h_de(self.maria, 9))

        resposta = self._grade()

        self.assertContains(resposta, 'id="btn-exportar-png"')
        self.assertContains(resposta, 'html2canvas')
        self.assertContains(resposta, 'Ana')
        # o botão só fica ativo quando há agendamentos
        self.assertNotContains(
            resposta, 'id="btn-exportar-png" class="maq-exportar-btn" disabled'
        )

    def test_png_sem_agendamentos_fica_desativado_como_antes(self):
        resposta = self._grade()
        self.assertContains(resposta, 'id="btn-exportar-png"')
        self.assertContains(resposta, 'maq-exportar-btn" disabled')


# ===========================================================================
# Endpoints antigos também respeitam "uma aluna, um horário"
# ===========================================================================

@override_settings(STORAGES=STORAGES_TESTE)
class UmHorarioPorAlunaNosEndpointsAntigosTests(BaseTests):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.staff)
        self.h1 = self._h(self.maria, 9)
        self.h2 = self._h(self.maria, 10)
        self.h3 = self._h(self.maria, 11)
        self.ag = self._agendar(self.ana, self.h1)

    def test_agendar_maquiagem_admin_barra_aluna_que_ja_tem_horario(self):
        self.client.post(
            reverse('admin_dashboard:agendar_maquiagem_admin', args=[self.h2.pk]),
            {'aluna': self.ana.pk, 'tipo_servico': 'cabelo'},
        )
        self.assertEqual(AgendamentoMaquiagem.objects.count(), 1)

    def test_agendar_maquiagem_admin_barra_aluna_de_fora_da_turma(self):
        self.client.post(
            reverse('admin_dashboard:agendar_maquiagem_admin', args=[self.h2.pk]),
            {'aluna': self.eva.pk, 'tipo_servico': 'cabelo'},
        )
        self.assertEqual(AgendamentoMaquiagem.objects.count(), 1)

    def test_agendar_maquiagem_admin_continua_agendando_aluna_livre(self):
        self.client.post(
            reverse('admin_dashboard:agendar_maquiagem_admin', args=[self.h2.pk]),
            {'aluna': self.bia.pk, 'tipo_servico': 'cabelo'},
        )
        self.assertEqual(AgendamentoMaquiagem.objects.count(), 2)

    def test_editar_nao_troca_para_aluna_que_ja_tem_outro_horario(self):
        outro = self._agendar(self.bia, self.h2)
        self.client.post(
            reverse('admin_dashboard:maquiagem_editar', args=[self.ag.pk]),
            {'aluna': self.bia.pk, 'tipo_servico': 'maquiagem',
             'horario': self.h1.pk},
        )
        self.ag.refresh_from_db()
        self.assertEqual(self.ag.aluna, self.ana)
        outro.refresh_from_db()
        self.assertEqual(outro.aluna, self.bia)

    def test_editar_salvando_a_propria_aluna_nao_e_barrado(self):
        self.client.post(
            reverse('admin_dashboard:maquiagem_editar', args=[self.ag.pk]),
            {'aluna': self.ana.pk, 'tipo_servico': 'cabelo',
             'horario': self.h3.pk},
        )
        self.ag.refresh_from_db()
        self.assertEqual(self.ag.tipo_servico, 'cabelo')
        self.assertEqual(self.ag.horario, self.h3)


# ===========================================================================
# Acesso do painel
# ===========================================================================

@override_settings(STORAGES=STORAGES_TESTE)
class AcessoDasNovasAcoesTests(BaseTests):
    def setUp(self):
        super().setUp()
        self.horario = self._h(self.maria, 9)
        self.posts = {
            'gerar': {'acao': 'gerar_horarios', 'turma': self.turma_a.pk,
                      'agendas': [self.maria.pk], 'dia': DIA.isoformat(),
                      'inicio': '09:00', 'fim': '10:00', 'duracao': '30'},
            'agendar': {'acao': 'grade', 'turma': self.turma_a.pk,
                        'aluna': self.ana.pk, 'tipo_servico': 'cabelo',
                        'agendar': self.horario.pk},
            'alternar': {'acao': 'alternar_escolha_familia'},
        }

    def _nada_mudou(self):
        self.assertEqual(HorarioMaquiagem.objects.count(), 1)
        self.assertEqual(AgendamentoMaquiagem.objects.count(), 0)
        self.espetaculo.refresh_from_db()
        self.assertFalse(self.espetaculo.maquiagem_familia_escolhe_horario)

    def test_visitante_nao_faz_nada(self):
        for nome, dados in self.posts.items():
            with self.subTest(nome):
                resposta = self.client.post(self.url, dados)
                self.assertIn('login', resposta['Location'])
        self._nada_mudou()

    def test_usuario_comum_nao_faz_nada(self):
        self.client.force_login(self.resp_ana)
        for nome, dados in self.posts.items():
            with self.subTest(nome):
                self.assertEqual(self.client.post(self.url, dados).status_code, 302)
        self._nada_mudou()


# ===========================================================================
# A aluna só vê o que é dela
# ===========================================================================

@override_settings(STORAGES=STORAGES_TESTE)
class AreaDaAlunaTests(BaseTests):
    def setUp(self):
        super().setUp()
        self.h_ana = self._h(self.maria, 9)
        self.h_bia = self._h(self.joana, 9, 30)
        self.livre = self._h(self.maria, 10)
        self.ag_ana = self._agendar(self.ana, self.h_ana, 'cabelo_e_maquiagem')
        self.ag_bia = self._agendar(self.bia, self.h_bia)
        self.url_aluna = reverse(
            'espetaculo:agendar_maquiagem', args=[self.espetaculo.pk]
        )

    def test_a_familia_ve_so_o_horario_da_sua_aluna(self):
        self.client.force_login(self.resp_ana)

        resposta = self.client.get(self.url_aluna)

        self.assertEqual(resposta.status_code, 200)
        self.assertTemplateUsed(resposta, 'espetaculo/horarios_maquiagem_aluna.html')
        self.assertContains(resposta, 'Ana')
        self.assertContains(resposta, 'Cabelo e Maquiagem')
        self.assertContains(resposta, 'Maria')
        self.assertContains(resposta, 'Meus horários de maquiagem')

    def test_nao_aparece_nada_de_outras_alunas(self):
        self.client.force_login(self.resp_ana)

        resposta = self.client.get(self.url_aluna)

        self.assertNotContains(resposta, 'Bia')
        self.assertNotContains(resposta, 'Joana')  # a maquiadora da Bia
        self.assertNotContains(resposta, 'Clara')

    def test_nao_ha_lista_de_horarios_livres_para_escolher(self):
        self.client.force_login(self.resp_ana)

        resposta = self.client.get(self.url_aluna)

        self.assertNotContains(resposta, 'agmaq-horario-btn')
        self.assertNotContains(resposta, '10:00')  # o horário livre da Maria

    def test_aluna_sem_horario_ainda_ve_aviso_de_que_a_escola_vai_agendar(self):
        responsavel_clara = User.objects.create_user('rc', 'rc@x.com', 'senha123')
        self.clara.responsavel = responsavel_clara
        self.clara.save()
        self.client.force_login(responsavel_clara)

        resposta = self.client.get(self.url_aluna)

        self.assertContains(resposta, 'Clara')
        self.assertContains(resposta, 'Ainda sem horário')
        self.assertContains(resposta, 'A escola vai agendar')

    def test_familia_com_duas_alunas_ve_as_duas_e_so_elas(self):
        self.bia.responsavel = self.resp_ana
        self.bia.save()
        self.client.force_login(self.resp_ana)

        resposta = self.client.get(self.url_aluna)

        self.assertContains(resposta, 'Ana')
        self.assertContains(resposta, 'Bia')
        self.assertNotContains(resposta, 'Clara')

    def test_aluna_adulta_ve_o_proprio_horario(self):
        adulta_user = User.objects.create_user('adulta', 'ad@x.com', 'senha123')
        self.clara.usuario = adulta_user
        self.clara.save()
        self._agendar(self.clara, self.livre)
        self.client.force_login(adulta_user)

        resposta = self.client.get(self.url_aluna)

        self.assertContains(resposta, 'Clara')
        self.assertNotContains(resposta, 'Ana')

    def test_aluna_de_turma_sem_maquiagem_nao_aparece(self):
        resp_eva = User.objects.create_user('re', 're@x.com', 'senha123')
        self.eva.responsavel = resp_eva
        self.eva.save()
        self.client.force_login(resp_eva)

        resposta = self.client.get(self.url_aluna)

        self.assertNotContains(resposta, 'Eva')
        self.assertContains(resposta, 'Não há horário de maquiagem')

    def test_usuario_sem_alunas(self):
        sozinho = User.objects.create_user('so', 'so@x.com', 'senha123')
        self.client.force_login(sozinho)
        resposta = self.client.get(self.url_aluna)
        self.assertContains(resposta, 'Nenhuma aluna encontrada')

    def test_visitante_e_mandado_de_volta(self):
        resposta = self.client.get(self.url_aluna)
        self.assertEqual(resposta.status_code, 302)

    def test_ordem_dos_horarios_da_familia(self):
        self.bia.responsavel = self.resp_ana
        self.bia.save()
        itens = horarios_da_familia(self.resp_ana, self.espetaculo)
        self.assertEqual([i['aluna'].nome for i in itens], ['Ana', 'Bia'])

    def test_com_a_escolha_liberada_a_tela_antiga_volta(self):
        Espetaculo.objects.filter(pk=self.espetaculo.pk).update(
            maquiagem_familia_escolhe_horario=True
        )
        responsavel_clara = User.objects.create_user('rc', 'rc@x.com', 'senha123')
        self.clara.responsavel = responsavel_clara
        self.clara.save()
        self.client.force_login(responsavel_clara)

        resposta = self.client.get(self.url_aluna)

        self.assertTemplateUsed(resposta, 'espetaculo/agendar_maquiagem.html')
        self.assertContains(resposta, 'agmaq-horario-btn')

    # ---------- a família não consegue escolher por conta própria ----------

    def test_reservar_e_recusado_quando_so_a_escola_agenda(self):
        responsavel_clara = User.objects.create_user('rc', 'rc@x.com', 'senha123')
        self.clara.responsavel = responsavel_clara
        self.clara.save()
        self.client.force_login(responsavel_clara)

        resposta = self.client.post(
            reverse('espetaculo:reservar_horario_maquiagem',
                    args=[self.espetaculo.pk, self.livre.pk]),
            {'aluna_id': self.clara.pk},
        )

        self.assertEqual(resposta.status_code, 403)
        self.livre.refresh_from_db()
        self.assertEqual(self.livre.status, 'disponivel')

    def test_confirmar_e_recusado_quando_so_a_escola_agenda(self):
        responsavel_clara = User.objects.create_user('rc', 'rc@x.com', 'senha123')
        self.clara.responsavel = responsavel_clara
        self.clara.save()
        self.client.force_login(responsavel_clara)
        HorarioMaquiagem.objects.filter(pk=self.livre.pk).update(
            status='reservado_temporario', reservado_em=timezone.now(),
            reservado_por_sessao=self.client.session.session_key or 'x',
        )

        self.client.post(
            reverse('espetaculo:confirmar_agendamento_maquiagem',
                    args=[self.espetaculo.pk, self.livre.pk]),
            {'aluna_id': self.clara.pk, 'tipo_servico': 'maquiagem'},
        )

        self.assertFalse(
            AgendamentoMaquiagem.objects.filter(aluna=self.clara).exists()
        )


@override_settings(STORAGES=STORAGES_TESTE)
class ConfirmacaoProtegidaTests(BaseTests):
    """
    A tela de confirmação abria para qualquer pessoa, mesmo sem login: bastava
    trocar o número no endereço para ver o horário de outra aluna.
    """

    def setUp(self):
        super().setUp()
        self.ag_ana = self._agendar(self.ana, self._h(self.maria, 9))
        self.ag_bia = self._agendar(self.bia, self._h(self.joana, 9, 30))
        self.url_ana = reverse(
            'espetaculo:agendamento_maquiagem_sucesso', args=[self.ag_ana.pk]
        )
        self.url_bia = reverse(
            'espetaculo:agendamento_maquiagem_sucesso', args=[self.ag_bia.pk]
        )

    def test_visitante_vai_para_o_login_e_nao_ve_nada(self):
        resposta = self.client.get(self.url_ana)
        self.assertEqual(resposta.status_code, 302)
        self.assertIn('login', resposta['Location'])

    def test_a_familia_ve_o_proprio_agendamento(self):
        self.client.force_login(self.resp_ana)
        resposta = self.client.get(self.url_ana)
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'Ana')

    def test_outra_familia_nao_ve_e_a_pagina_nao_revela_que_existe(self):
        self.client.force_login(self.resp_bia)

        existente = self.client.get(self.url_ana)
        inexistente = self.client.get(
            reverse('espetaculo:agendamento_maquiagem_sucesso', args=[999999])
        )

        self.assertEqual(existente.status_code, 404)
        self.assertEqual(inexistente.status_code, 404)
        self.assertNotContains(existente, 'Ana', status_code=404)

    def test_a_familia_nao_ve_agendamentos_de_outras_alunas_na_lista(self):
        self.client.force_login(self.resp_ana)
        resposta = self.client.get(self.url_ana)
        self.assertNotContains(resposta, 'Bia')

    def test_usuario_sem_aluna_nao_ve_nada(self):
        sozinho = User.objects.create_user('so', 'so@x.com', 'senha123')
        self.client.force_login(sozinho)
        self.assertEqual(self.client.get(self.url_ana).status_code, 404)

    def test_a_equipe_da_escola_continua_vendo(self):
        staff = User.objects.create_user(
            'staff2', 's2@x.com', 'senha123', is_staff=True
        )
        self.client.force_login(staff)
        resposta = self.client.get(self.url_bia)
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'Bia')
        self.assertNotContains(resposta, 'Ana')

    def test_responsavel_de_duas_alunas_ve_as_duas(self):
        self.bia.responsavel = self.resp_ana
        self.bia.save()
        self.client.force_login(self.resp_ana)
        resposta = self.client.get(self.url_ana)
        self.assertContains(resposta, 'Ana')
        self.assertContains(resposta, 'Bia')


@override_settings(STORAGES=STORAGES_TESTE)
class BotaoNaListaPublicaTests(BaseTests):
    def setUp(self):
        super().setUp()
        self.sem_maquiagem = Espetaculo.objects.create(
            titulo='Sem maquiagem', descricao='x', tipo='espetaculo',
            data_apresentacao=timezone.now() + timedelta(days=30),
            local='L', endereco='E', publico=True,
        )
        Espetaculo.objects.filter(pk=self.espetaculo.pk).update(publico=True)
        self.url_lista = reverse('espetaculo:lista_publica')

    def test_aparece_so_no_espetaculo_que_tem_maquiagem(self):
        self.client.force_login(self.resp_ana)
        resposta = self.client.get(self.url_lista)

        self.assertContains(resposta, 'Meus horários de maquiagem', count=1)
        self.assertEqual(
            resposta.context['ids_com_maquiagem'], {self.espetaculo.pk}
        )

    def test_texto_muda_quando_a_familia_escolhe(self):
        Espetaculo.objects.filter(pk=self.espetaculo.pk).update(
            maquiagem_familia_escolhe_horario=True
        )
        self.client.force_login(self.resp_ana)
        resposta = self.client.get(self.url_lista)
        self.assertContains(resposta, 'Agendar maquiagem')
        self.assertNotContains(resposta, 'Meus horários de maquiagem')

    def test_visitante_nao_ve_o_botao(self):
        resposta = self.client.get(self.url_lista)
        self.assertNotContains(resposta, 'Meus horários de maquiagem')
        self.assertNotContains(resposta, 'Agendar maquiagem')
        self.assertEqual(resposta.context['ids_com_maquiagem'], set())
