"""
Abrir uma maquiadora (professora) no painel de maquiagens.

Antes, clicar no nome da professora abria um cartão só com os horários dela e
sem nenhum lugar para escolher a aluna: a escolha ficava só na "agenda por
horário", em outra tela. Agora abrir a professora mostra, no topo, a grade
para agendar as alunas da turma dela.
"""

import re
from datetime import datetime, time, timedelta

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from espetaculo.maquiagem_agenda import agendar_aluna
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


@override_settings(STORAGES=STORAGES_TESTE)
class AbrirAProfessoraTests(TestCase):
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
        self.ana = self._aluna('Ana', self.turma_a)
        self.bia = self._aluna('Bia', self.turma_a)
        self.eva = self._aluna('Eva', self.turma_b)

        self.maria = AgendaMaquiagemTurma.objects.create(
            espetaculo=self.espetaculo, turma=self.turma_a,
            maquiadora='Professora Maria',
        )
        self.joana = AgendaMaquiagemTurma.objects.create(
            espetaculo=self.espetaculo, turma=self.turma_a,
            maquiadora='Professora Joana',
        )
        self.url = reverse(
            'admin_dashboard:espetaculo_maquiagens', args=[self.espetaculo.pk]
        )
        self.client.force_login(self.staff)

    def _aluna(self, nome, turma):
        aluna = Aluna.objects.create(nome=nome)
        aluna.turmas.add(turma)
        return aluna

    def _h(self, agenda, hora, minuto=0):
        return HorarioMaquiagem.objects.create(
            agenda=agenda, horario=_dt(hora, minuto)
        )

    # ---------- o beco sem saída acabou ----------

    def test_abrir_a_professora_mostra_a_grade_para_escolher_a_aluna(self):
        self._h(self.maria, 9)

        resposta = self.client.get(self.url, {'agenda_id': self.maria.pk})

        self.assertEqual(resposta.context['turma_grade'], self.turma_a)
        self.assertContains(resposta, 'Agenda por horário · Turma A')
        self.assertContains(resposta, 'name="aluna"')       # onde escolhe a aluna
        self.assertContains(resposta, 'name="agendar"')     # onde clica no horário
        self.assertEqual(
            [a.nome for a in resposta.context['pendentes']], ['Ana', 'Bia']
        )

    def test_o_clique_no_nome_da_professora_leva_a_grade_e_ao_cartao_dela(self):
        resposta = self.client.get(self.url)

        self.assertContains(
            resposta,
            f'href="?turma={self.turma_a.pk}&agenda_id={self.maria.pk}"',
        )

        aberta = self.client.get(
            self.url, {'turma': self.turma_a.pk, 'agenda_id': self.maria.pk}
        )
        self.assertContains(aberta, 'Agenda por horário · Turma A')
        self.assertContains(aberta, 'value="renomear_agenda"')

    def test_a_coluna_da_professora_aberta_fica_destacada(self):
        self._h(self.maria, 9)
        self._h(self.joana, 9)

        resposta = self.client.get(self.url, {'agenda_id': self.maria.pk})

        conteudo = resposta.content.decode()
        self.assertEqual(conteudo.count('maq-grade-cab destaque'), 1)
        destaque = re.search(
            r'maq-grade-cab destaque">([^<]*)<', conteudo
        ).group(1)
        self.assertIn('Professora Maria', destaque)

    def test_o_cartao_da_professora_nao_promete_um_formulario_que_nao_existe(self):
        resposta = self.client.get(self.url, {'agenda_id': self.maria.pk})
        self.assertNotContains(resposta, 'Agendar alunas desta turma')
        self.assertNotContains(
            resposta, 'Use "Criar horários de um dia" na agenda por horário'
        )
        self.assertContains(resposta, 'logo acima')

    def test_turma_pedida_tem_prioridade_sobre_a_da_professora(self):
        resposta = self.client.get(
            self.url, {'turma': self.turma_b.pk, 'agenda_id': self.maria.pk}
        )
        self.assertEqual(resposta.context['turma_grade'], self.turma_b)

    def test_professora_desativada_tambem_mostra_a_grade(self):
        AgendaMaquiagemTurma.objects.filter(pk=self.maria.pk).update(ativo=False)
        self._h(self.maria, 9)

        resposta = self.client.get(self.url, {'agenda_id': self.maria.pk})

        self.assertContains(resposta, 'Agenda por horário · Turma A')
        self.assertContains(resposta, 'desativada')

    def test_agenda_id_invalido_nao_quebra(self):
        for valor in ('abc', '999999'):
            resposta = self.client.get(self.url, {'agenda_id': valor})
            self.assertIn(resposta.status_code, (200, 404))

    def test_sem_horarios_o_formulario_de_criar_ja_vem_aberto(self):
        resposta = self.client.get(self.url, {'agenda_id': self.maria.pk})
        self.assertContains(resposta, '<details class="maq-gerar" open>')

    def test_depois_de_criar_a_professora_a_pessoa_cai_na_grade(self):
        resposta = self.client.post(self.url, {
            'acao': 'criar_agenda', 'turma': self.turma_b.pk,
            'maquiadora': 'Professora Nova',
        })

        pagina = self.client.get(resposta['Location'])

        self.assertEqual(pagina.context['turma_grade'], self.turma_b)
        self.assertContains(pagina, 'Agenda por horário · Turma B')

    def test_os_redirecionamentos_das_telas_antigas_tambem_caem_na_grade(self):
        livre = self._h(self.maria, 9)

        resposta = self.client.post(
            reverse('admin_dashboard:excluir_horario_maquiagem', args=[livre.pk])
        )
        pagina = self.client.get(resposta['Location'])

        self.assertEqual(pagina.context['turma_grade'], self.turma_a)
        self.assertContains(pagina, 'Agenda por horário · Turma A')

    # ---------- do clique no nome da professora até a aluna agendada ----------

    def test_caminho_completo_como_o_navegador_faz(self):
        """Abre a professora, lê a tela e agenda usando só o que ela oferece."""
        self._h(self.maria, 9)
        self._h(self.maria, 9, 30)

        pagina = self.client.get(
            self.url, {'turma': self.turma_a.pk, 'agenda_id': self.maria.pk}
        )
        html = pagina.content.decode()

        # a aluna que vem marcada, o serviço e o primeiro horário livre
        aluna_marcada = re.search(
            r'name="aluna" value="(\d+)" checked', html
        ).group(1)
        primeiro_livre = re.search(
            r'name="agendar" value="(\d+)"', html
        ).group(1)
        turma_campo = re.search(
            r'name="turma" value="(\d+)"', html[html.index('id="form-grade"'):]
        ).group(1)
        dia_campo = re.search(
            r'name="dia" value="([\d-]+)"', html[html.index('id="form-grade"'):]
        ).group(1)

        resposta = self.client.post(self.url, {
            'acao': 'grade', 'turma': turma_campo, 'dia': dia_campo,
            'aluna': aluna_marcada, 'tipo_servico': 'maquiagem',
            'agendar': primeiro_livre,
        })

        agendamento = AgendamentoMaquiagem.objects.get()
        self.assertEqual(agendamento.aluna, self.ana)
        self.assertEqual(agendamento.horario.agenda, self.maria)
        pagina = self.client.get(resposta['Location'])
        self.assertContains(pagina, 'Ana agendada')

    # ---------- quem já tem horário ----------

    def test_lista_quem_ja_esta_agendada_e_onde(self):
        horario = self._h(self.maria, 10)
        agendar_aluna(
            self.espetaculo, self.turma_a, horario.pk, self.ana.pk, 'cabelo'
        )

        resposta = self.client.get(self.url, {'agenda_id': self.maria.pk})

        self.assertContains(resposta, 'Já agendadas (1)')
        conteudo = resposta.content.decode()
        bloco = conteudo[conteudo.index('Já agendadas'):]
        bloco = bloco[:bloco.index('</details>')]
        self.assertIn('Ana', bloco)
        self.assertIn('Professora Maria', bloco)
        self.assertIn('10:00', bloco)
        self.assertNotIn('Bia', bloco)

    def test_quem_ja_esta_agendada_nao_aparece_para_escolher(self):
        horario = self._h(self.maria, 10)
        agendar_aluna(
            self.espetaculo, self.turma_a, horario.pk, self.ana.pk, 'cabelo'
        )

        resposta = self.client.get(self.url, {'agenda_id': self.maria.pk})

        self.assertEqual(
            [a.nome for a in resposta.context['pendentes']], ['Bia']
        )

    def test_a_lista_de_agendadas_junta_todas_as_professoras_da_turma(self):
        h1 = self._h(self.maria, 9)
        h2 = self._h(self.joana, 9)
        agendar_aluna(self.espetaculo, self.turma_a, h1.pk, self.ana.pk, 'cabelo')
        agendar_aluna(self.espetaculo, self.turma_a, h2.pk, self.bia.pk, 'cabelo')

        resposta = self.client.get(self.url, {'agenda_id': self.maria.pk})

        self.assertContains(resposta, 'Já agendadas (2)')
        self.assertContains(resposta, 'Professora Joana')

    def test_nao_mostra_agendadas_de_outra_turma(self):
        outra = AgendaMaquiagemTurma.objects.create(
            espetaculo=self.espetaculo, turma=self.turma_b, maquiadora='Outra'
        )
        h = self._h(outra, 9)
        agendar_aluna(self.espetaculo, self.turma_b, h.pk, self.eva.pk, 'cabelo')

        resposta = self.client.get(self.url, {'agenda_id': self.maria.pk})

        self.assertNotContains(resposta, 'Já agendadas')
        self.assertEqual(resposta.context['agendadas'], [])

    def test_sem_agendadas_nao_mostra_a_lista(self):
        self._h(self.maria, 9)
        resposta = self.client.get(self.url, {'agenda_id': self.maria.pk})
        self.assertNotContains(resposta, 'Já agendadas')
