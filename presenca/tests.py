"""
Testes da lista de presença (QR Code, faltas, telas do admin personalizado).

Rodar:  python manage.py test presenca
"""
from contextlib import contextmanager
from datetime import date, datetime, time
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from usuarios.models import Aluna, Turma

from .horarios_parse import interpretar_horario
from .models import ConfiguracaoPresenca, DiaSemAula, HorarioTurma, Presenca
from .services import (
    anexar_faltas_do_mes,
    registros_periodo,
    salvar_horarios_turma,
    totais,
)

STORAGES_TESTE = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}

# Segundas-feiras de novembro/2026
SEG_02 = date(2026, 11, 2)
SEG_09 = date(2026, 11, 9)
SEG_16 = date(2026, 11, 16)


@contextmanager
def agora(ano, mes, dia, hora=12, minuto=0):
    """Congela o relógio do Django (fuso America/Sao_Paulo)."""
    momento = timezone.make_aware(datetime(ano, mes, dia, hora, minuto))
    with patch('django.utils.timezone.now', return_value=momento):
        yield momento


def cria_turma(nome='Ballet A', dia=0, inicio=(14, 0), fim=(15, 0), **extra):
    turma = Turma.objects.create(nome=nome, **extra)
    if dia is not None:
        HorarioTurma.objects.create(
            turma=turma, dia_semana=dia, hora_inicio=time(*inicio), hora_fim=time(*fim),
        )
    return turma


def cria_aluna(nome='Ana', turmas=(), responsavel=None, usuario=None, **extra):
    aluna = Aluna.objects.create(nome=nome, responsavel=responsavel, usuario=usuario, **extra)
    # data_matricula é auto_now_add: voltamos para antes do período dos testes
    Aluna.objects.filter(pk=aluna.pk).update(data_matricula=date(2026, 1, 1))
    aluna.refresh_from_db()
    for turma in turmas:
        aluna.turmas.add(turma)
    return aluna


def cria_usuario(username, staff=False):
    return User.objects.create_user(
        username, f'{username}@example.com', 'senha123',
        first_name=username.capitalize(), is_staff=staff,
    )


def define_inicio(dia):
    config = ConfiguracaoPresenca.obter()
    config.data_inicio_controle = dia
    config.save()
    return config


# ---------------------------------------------------------------------------
# Interpretação do horário escrito à mão
# ---------------------------------------------------------------------------

class InterpretarHorarioTests(TestCase):
    def test_formatos_comuns(self):
        self.assertEqual(
            interpretar_horario('14h-15h', 'Segunda'),
            [(0, time(14, 0), time(15, 0))],
        )
        self.assertEqual(
            interpretar_horario('Segunda e Quarta 14h-15h', ''),
            [(0, time(14, 0), time(15, 0)), (2, time(14, 0), time(15, 0))],
        )
        self.assertEqual(
            interpretar_horario('14:00 às 15:30', 'Sábado'),
            [(5, time(14, 0), time(15, 30))],
        )

    def test_ambiguos_ficam_pendentes(self):
        self.assertEqual(interpretar_horario('14h', 'Segunda'), [])
        self.assertEqual(interpretar_horario('a combinar', 'Segunda'), [])
        self.assertEqual(interpretar_horario('Segunda 14h-15h e Quarta 15h-16h', ''), [])
        self.assertEqual(interpretar_horario('15h-14h', 'Segunda'), [])
        self.assertEqual(interpretar_horario('14h-15h', ''), [])  # sem dia nenhum

    def test_migration_preenche_e_marca_como_automatico(self):
        from django.apps import apps
        from importlib import import_module

        migration = import_module('presenca.migrations.0002_horarios_e_configuracao_iniciais')
        ok = Turma.objects.create(nome='Ok', horario='14h-15h', dia_semana='Terça')
        ruim = Turma.objects.create(nome='Ruim', horario='a combinar', dia_semana='Terça')
        experimental = Turma.objects.create(
            nome='Exp', horario='14h-15h', dia_semana='Terça', tipo='aula_experimental',
        )

        migration.preencher(apps, None)

        self.assertEqual(ok.horarios_aula.count(), 1)
        horario = ok.horarios_aula.get()
        self.assertEqual((horario.dia_semana, horario.hora_inicio, horario.hora_fim), (1, time(14), time(15)))
        self.assertTrue(horario.preenchido_automaticamente)
        self.assertEqual(ruim.horarios_aula.count(), 0)
        self.assertEqual(experimental.horarios_aula.count(), 0)


# ---------------------------------------------------------------------------
# Cálculo de faltas
# ---------------------------------------------------------------------------

@override_settings(STORAGES=STORAGES_TESTE)
class FaltasTests(TestCase):
    def setUp(self):
        self.turma = cria_turma()  # segundas, 14h-15h
        self.aluna = cria_aluna('Ana', [self.turma])
        define_inicio(SEG_02)

    def _registros(self, ini=SEG_02, fim=SEG_16):
        return registros_periodo(Aluna.objects.filter(pk=self.aluna.pk), ini, fim)

    def test_falta_so_depois_que_a_aula_termina(self):
        with agora(2026, 11, 9, 14, 30):
            r = {x.data: x.status for x in self._registros()}
        self.assertEqual(r[SEG_02], 'falta')
        self.assertEqual(r[SEG_09], 'aguardando')

        with agora(2026, 11, 9, 15, 1):
            r = {x.data: x.status for x in self._registros()}
        self.assertEqual(r[SEG_09], 'falta')

    def test_presenca_tira_a_falta(self):
        Presenca.objects.create(aluna=self.aluna, turma=self.turma, data=SEG_02)
        with agora(2026, 11, 9, 16):
            r = {x.data: x.status for x in self._registros()}
        self.assertEqual(r[SEG_02], 'presente')
        self.assertEqual(r[SEG_09], 'falta')

    def test_presenca_desmarcada_volta_a_ser_falta(self):
        p = Presenca.objects.create(aluna=self.aluna, turma=self.turma, data=SEG_02)
        p.anular(None, 'não foi')
        with agora(2026, 11, 9, 16):
            registro = [x for x in self._registros() if x.data == SEG_02][0]
        self.assertEqual(registro.status, 'falta')
        self.assertTrue(registro.desmarcada)

    def test_dia_sem_aula_nao_gera_falta(self):
        DiaSemAula.objects.create(data=SEG_02, motivo='Feriado')
        with agora(2026, 11, 9, 16):
            datas = [x.data for x in self._registros()]
        self.assertEqual(datas, [SEG_09])

    def test_dia_sem_aula_so_de_uma_turma(self):
        outra = cria_turma('Outra', dia=0, inicio=(16, 0), fim=(17, 0))
        self.aluna.turmas.add(outra)
        DiaSemAula.objects.create(data=SEG_02, turma=outra)
        with agora(2026, 11, 9, 20):
            pares = [(x.turma.nome, x.data) for x in self._registros(fim=SEG_09)]
        self.assertIn(('Ballet A', SEG_02), pares)
        self.assertNotIn(('Outra', SEG_02), pares)

    def test_nada_antes_do_inicio_do_controle(self):
        define_inicio(SEG_09)
        with agora(2026, 11, 9, 16):
            datas = [x.data for x in self._registros()]
        self.assertEqual(datas, [SEG_09])

    def test_nada_antes_da_matricula(self):
        Aluna.objects.filter(pk=self.aluna.pk).update(data_matricula=SEG_09)
        with agora(2026, 11, 9, 16):
            datas = [x.data for x in self._registros()]
        self.assertEqual(datas, [SEG_09])

    def test_turma_sem_horario_ou_experimental_nao_gera_falta(self):
        sem_horario = cria_turma('Sem horário', dia=None)
        experimental = cria_turma('Exp', dia=0, tipo='aula_experimental')
        inativa = cria_turma('Inativa', dia=0, ativa=False)
        self.aluna.turmas.add(sem_horario, experimental, inativa)
        with agora(2026, 11, 9, 16):
            nomes = {x.turma.nome for x in self._registros()}
        self.assertEqual(nomes, {'Ballet A'})

    def test_cards_e_lista_usam_o_mesmo_numero(self):
        outra_turma = cria_turma('Quarta', dia=2, inicio=(10, 0), fim=(11, 0))
        self.aluna.turmas.add(outra_turma)
        Presenca.objects.create(aluna=self.aluna, turma=self.turma, data=SEG_02)
        with agora(2026, 11, 18, 18):
            definidos = [x for x in self._registros(date(2026, 11, 1), date(2026, 11, 30))]
            esperado = totais(definidos)['falta']
            card = anexar_faltas_do_mes([self.aluna])[0].faltas_mes
        # seg 9, seg 16 + qua 4, 11, 18 = 5 faltas  (seg 2 foi presente)
        self.assertEqual(esperado, 5)
        self.assertEqual(card, esperado)

    def test_card_conta_so_o_mes_atual(self):
        define_inicio(date(2026, 10, 1))
        with agora(2026, 11, 9, 16):
            faltas = anexar_faltas_do_mes([self.aluna])[0].faltas_mes
        # Só novembro: seg 2 e seg 9 (outubro não entra)
        self.assertEqual(faltas, 2)

    def test_aluna_inativa_fica_sem_contagem(self):
        Aluna.objects.filter(pk=self.aluna.pk).update(ativa=False)
        self.aluna.refresh_from_db()
        with agora(2026, 11, 9, 16):
            self.assertIsNone(anexar_faltas_do_mes([self.aluna])[0].faltas_mes)


# ---------------------------------------------------------------------------
# Registro pelo QR Code
# ---------------------------------------------------------------------------

@override_settings(STORAGES=STORAGES_TESTE)
class QrCodeTests(TestCase):
    def setUp(self):
        self.config = define_inicio(SEG_02)
        self.url = reverse('presenca:marcar', args=[self.config.token_qr])
        self.responsavel = cria_usuario('mae')
        self.turma = cria_turma('Ballet A', dia=0, inicio=(14, 0), fim=(15, 0))
        self.aluna = cria_aluna('Ana', [self.turma], responsavel=self.responsavel)
        self.client.force_login(self.responsavel)

    def test_sem_login_vai_para_login_e_volta(self):
        self.client.logout()
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(resposta.url, f'{reverse("login")}?next={self.url}')

        # a tela de login repassa o "next" e, ao entrar, volta para a página do QR
        with agora(2026, 11, 9, 13, 45):
            resposta = self.client.post(
                reverse('login'), {'username': 'mae', 'password': 'senha123', 'next': self.url},
            )
            self.assertRedirects(resposta, self.url, fetch_redirect_response=False)
            # ...e a presença é registrada direto, sem escanear de novo
            resposta = self.client.get(self.url)
        self.assertEqual(resposta.context['tipo'], 'sucesso')
        self.assertEqual(Presenca.objects.count(), 1)

    def test_logada_dentro_da_janela_registra_direto(self):
        with agora(2026, 11, 9, 14, 5):
            resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.context['tipo'], 'sucesso')
        self.assertContains(resposta, 'Presença confirmada')
        presenca = Presenca.objects.get()
        self.assertEqual((presenca.aluna, presenca.turma, presenca.data), (self.aluna, self.turma, SEG_09))
        self.assertEqual(presenca.registrada_por, self.responsavel)
        self.assertEqual(presenca.origem, 'qr')

    def test_janela_30_minutos_antes_ate_o_fim_da_aula(self):
        casos = [
            ((13, 29), 'fora_da_janela'),
            ((13, 30), 'sucesso'),
        ]
        for (h, m), esperado in casos:
            with self.subTest(hora=f'{h}:{m}'), agora(2026, 11, 9, h, m):
                Presenca.objects.all().delete()
                self.assertEqual(self.client.get(self.url).context['tipo'], esperado)
        with agora(2026, 11, 9, 15, 0):
            Presenca.objects.all().delete()
            self.assertEqual(self.client.get(self.url).context['tipo'], 'sucesso')
        with agora(2026, 11, 9, 15, 1):
            Presenca.objects.all().delete()
            self.assertEqual(self.client.get(self.url).context['tipo'], 'fora_da_janela')
            self.assertEqual(Presenca.objects.count(), 0)

    def test_dia_errado_nao_registra(self):
        with agora(2026, 11, 10, 14, 5):  # terça
            resposta = self.client.get(self.url)
        self.assertEqual(resposta.context['tipo'], 'fora_da_janela')
        self.assertEqual(Presenca.objects.count(), 0)
        self.assertIsNotNone(resposta.context['proxima'])

    def test_escanear_duas_vezes_nao_duplica(self):
        with agora(2026, 11, 9, 14, 5):
            self.client.get(self.url)
            resposta = self.client.get(self.url)
        self.assertEqual(resposta.context['tipo'], 'ja_registrada')
        self.assertEqual(Presenca.objects.count(), 1)

    def test_presenca_desmarcada_nao_pode_ser_registrada_de_novo(self):
        with agora(2026, 11, 9, 14, 5):
            self.client.get(self.url)
            Presenca.objects.get().anular(None)
            resposta = self.client.get(self.url)
        self.assertEqual(resposta.context['tipo'], 'desmarcada')
        self.assertTrue(Presenca.objects.get().anulada)

    def test_qr_invalido(self):
        with agora(2026, 11, 9, 14, 5):
            resposta = self.client.get(reverse('presenca:marcar', args=['codigo-errado']))
        self.assertEqual(resposta.context['tipo'], 'qr_invalido')
        self.assertEqual(Presenca.objects.count(), 0)

    def test_qr_antigo_para_de_funcionar_quando_a_escola_gera_outro(self):
        self.config.regenerar_token()
        with agora(2026, 11, 9, 14, 5):
            self.assertEqual(self.client.get(self.url).context['tipo'], 'qr_invalido')
            novo = reverse('presenca:marcar', args=[self.config.token_qr])
            self.assertEqual(self.client.get(novo).context['tipo'], 'sucesso')

    def test_conta_sem_aluna(self):
        self.client.force_login(cria_usuario('estranho'))
        with agora(2026, 11, 9, 14, 5):
            self.assertEqual(self.client.get(self.url).context['tipo'], 'sem_aluna')

    def test_dia_sem_aula_bloqueia_o_registro(self):
        DiaSemAula.objects.create(data=SEG_09, motivo='Feriado')
        with agora(2026, 11, 9, 14, 5):
            self.assertEqual(self.client.get(self.url).context['tipo'], 'fora_da_janela')
        self.assertEqual(Presenca.objects.count(), 0)

    def test_aluna_adulta_com_login_proprio(self):
        adulta_user = cria_usuario('bia')
        cria_aluna('Bia', [self.turma], usuario=adulta_user, tipo_aluna='adulto')
        self.client.force_login(adulta_user)
        with agora(2026, 11, 9, 14, 5):
            resposta = self.client.get(self.url)
        self.assertEqual(resposta.context['tipo'], 'sucesso')
        self.assertEqual(Presenca.objects.get().aluna.nome, 'Bia')

    def test_responsavel_com_varias_filhas_escolhe_a_aluna(self):
        filha2 = cria_aluna('Clara', [self.turma], responsavel=self.responsavel)
        with agora(2026, 11, 9, 14, 5):
            resposta = self.client.get(self.url)
            self.assertTemplateUsed(resposta, 'presenca/escolher_aluna.html')
            self.assertContains(resposta, 'Para qual aluna você quer marcar presença?')
            self.assertEqual(Presenca.objects.count(), 0)

            resposta = self.client.get(self.url, {'aluna': filha2.pk})
        self.assertEqual(resposta.context['tipo'], 'sucesso')
        presenca = Presenca.objects.get()
        self.assertEqual(presenca.aluna, filha2)

    def test_nao_registra_aluna_de_outra_familia(self):
        alheia = cria_aluna('Alheia', [self.turma], responsavel=cria_usuario('outra'))
        cria_aluna('Clara', [self.turma], responsavel=self.responsavel)  # 2 filhas -> seletor
        with agora(2026, 11, 9, 14, 5):
            resposta = self.client.get(self.url, {'aluna': alheia.pk})
        self.assertTemplateUsed(resposta, 'presenca/escolher_aluna.html')
        self.assertEqual(Presenca.objects.count(), 0)

    def test_duas_aulas_abertas_pergunta_qual(self):
        segunda = cria_turma('Ballet B', dia=0, inicio=(15, 0), fim=(16, 0))
        self.aluna.turmas.add(segunda)

        with agora(2026, 11, 9, 14, 45):  # as duas janelas estão abertas
            resposta = self.client.get(self.url)
            self.assertTemplateUsed(resposta, 'presenca/escolher_aulas.html')
            self.assertEqual(Presenca.objects.count(), 0)

            # sem marcar nada: continua na tela, com erro
            resposta = self.client.post(self.url, {'aluna': self.aluna.pk})
            self.assertTemplateUsed(resposta, 'presenca/escolher_aulas.html')
            self.assertEqual(Presenca.objects.count(), 0)

            resposta = self.client.post(self.url, {'aluna': self.aluna.pk, 'aula': [segunda.pk]})
        self.assertEqual(resposta.context['tipo'], 'sucesso')
        self.assertEqual(Presenca.objects.get().turma, segunda)

    def test_duas_aulas_pode_marcar_as_duas(self):
        segunda = cria_turma('Ballet B', dia=0, inicio=(15, 0), fim=(16, 0))
        self.aluna.turmas.add(segunda)
        with agora(2026, 11, 9, 14, 45):
            self.client.post(self.url, {'aluna': self.aluna.pk, 'aula': [self.turma.pk, segunda.pk]})
        self.assertEqual(Presenca.objects.count(), 2)

    def test_so_uma_aula_nao_pergunta(self):
        segunda = cria_turma('Ballet B', dia=0, inicio=(16, 0), fim=(17, 0))
        self.aluna.turmas.add(segunda)
        with agora(2026, 11, 9, 14, 5):  # só a das 14h está aberta
            resposta = self.client.get(self.url)
        self.assertEqual(resposta.context['tipo'], 'sucesso')
        self.assertEqual(Presenca.objects.get().turma, self.turma)


# ---------------------------------------------------------------------------
# Telas do admin personalizado
# ---------------------------------------------------------------------------

@override_settings(STORAGES=STORAGES_TESTE)
class AdminPresencaTests(TestCase):
    def setUp(self):
        define_inicio(SEG_02)
        self.staff = cria_usuario('admin', staff=True)
        self.turma_a = cria_turma('Ballet A', dia=0, inicio=(14, 0), fim=(15, 0))
        self.turma_b = cria_turma('Ballet B', dia=0, inicio=(16, 0), fim=(17, 0))
        self.ana = cria_aluna('Ana', [self.turma_a, self.turma_b])
        self.bia = cria_aluna('Bia', [self.turma_a])
        self.client.force_login(self.staff)

    def test_so_staff_acessa(self):
        self.client.force_login(cria_usuario('mae'))
        rotas = [
            reverse('admin_dashboard:presenca_lista'),
            reverse('admin_dashboard:presenca_resumo'),
            reverse('admin_dashboard:presenca_aluna', args=[self.ana.pk]),
            reverse('admin_dashboard:presenca_dias_sem_aula'),
            reverse('admin_dashboard:presenca_ajustes'),
            reverse('admin_dashboard:presenca_qr_png'),
            reverse('admin_dashboard:presenca_qr_imprimir'),
        ]
        for rota in rotas:
            with self.subTest(rota=rota):
                self.assertEqual(self.client.get(rota).status_code, 302)
        resposta = self.client.post(reverse('admin_dashboard:presenca_marcar_manual'), {})
        self.assertEqual(resposta.status_code, 302)

    def test_menu_lateral_tem_a_aba(self):
        with agora(2026, 11, 9, 18):
            resposta = self.client.get(reverse('admin_dashboard:dashboard'))
        self.assertContains(resposta, 'Lista de presença')

    def test_lista_do_dia_separa_as_aulas(self):
        Presenca.objects.create(aluna=self.ana, turma=self.turma_a, data=SEG_09)
        with agora(2026, 11, 9, 18):
            resposta = self.client.get(reverse('admin_dashboard:presenca_lista'))
        self.assertEqual(resposta.status_code, 200)
        dias = resposta.context['dias']
        self.assertEqual(len(dias), 1)
        self.assertEqual(dias[0]['data'], SEG_09)
        blocos = dias[0]['blocos']
        self.assertEqual([b['turma'].nome for b in blocos], ['Ballet A', 'Ballet B'])  # uma seção por aula
        self.assertEqual((blocos[0]['presentes'], blocos[0]['faltas']), (1, 1))  # Ana presente, Bia falta
        self.assertEqual((blocos[1]['presentes'], blocos[1]['faltas']), (0, 1))  # Ana falta
        self.assertEqual(resposta.context['resumo']['falta'], 2)

    def test_filtros_turma_aluna_status(self):
        Presenca.objects.create(aluna=self.ana, turma=self.turma_a, data=SEG_09)
        url = reverse('admin_dashboard:presenca_lista')
        with agora(2026, 11, 9, 18):
            r = self.client.get(url, {'turma': self.turma_b.pk})
            self.assertEqual([b['turma'].nome for d in r.context['dias'] for b in d['blocos']], ['Ballet B'])

            r = self.client.get(url, {'aluna': self.bia.pk})
            linhas = [l for d in r.context['dias'] for b in d['blocos'] for l in b['linhas']]
            self.assertEqual({l.aluna.nome for l in linhas}, {'Bia'})

            r = self.client.get(url, {'status': 'presente'})
            linhas = [l for d in r.context['dias'] for b in d['blocos'] for l in b['linhas']]
            self.assertEqual([(l.aluna.nome, l.status) for l in linhas], [('Ana', 'presente')])

    def test_filtros_semana_e_mes(self):
        url = reverse('admin_dashboard:presenca_lista')
        with agora(2026, 11, 16, 18):
            semana = self.client.get(url, {'periodo': 'semana'})
            mes = self.client.get(url, {'periodo': 'mes'})
        self.assertEqual([d['data'] for d in semana.context['dias']], [SEG_16])
        self.assertEqual([d['data'] for d in mes.context['dias']], [SEG_16, SEG_09, SEG_02])  # mais recente primeiro

    def test_desmarcar_vira_falta_e_restaurar_desfaz(self):
        presenca = Presenca.objects.create(aluna=self.bia, turma=self.turma_a, data=SEG_09)
        with agora(2026, 11, 9, 18):
            resposta = self.client.post(
                reverse('admin_dashboard:presenca_desmarcar', args=[presenca.pk]),
                {'motivo': 'não foi à aula', 'next': reverse('admin_dashboard:presenca_lista')},
            )
            self.assertRedirects(resposta, reverse('admin_dashboard:presenca_lista'), fetch_redirect_response=False)
            presenca.refresh_from_db()
            self.assertTrue(presenca.anulada)
            self.assertEqual(presenca.anulada_por, self.staff)
            self.assertEqual(presenca.motivo_anulacao, 'não foi à aula')
            self.assertEqual(anexar_faltas_do_mes([self.bia])[0].faltas_mes, 2)  # seg 2 + seg 9

            self.client.post(reverse('admin_dashboard:presenca_restaurar', args=[presenca.pk]))
            presenca.refresh_from_db()
            self.assertFalse(presenca.anulada)
            self.assertEqual(anexar_faltas_do_mes([self.bia])[0].faltas_mes, 1)  # só seg 2

    def test_desmarcar_exige_post(self):
        presenca = Presenca.objects.create(aluna=self.bia, turma=self.turma_a, data=SEG_09)
        resposta = self.client.get(reverse('admin_dashboard:presenca_desmarcar', args=[presenca.pk]))
        self.assertEqual(resposta.status_code, 405)

    def test_next_externo_e_ignorado(self):
        presenca = Presenca.objects.create(aluna=self.bia, turma=self.turma_a, data=SEG_09)
        resposta = self.client.post(
            reverse('admin_dashboard:presenca_desmarcar', args=[presenca.pk]),
            {'next': 'https://site-malicioso.example/'},
        )
        self.assertRedirects(resposta, reverse('admin_dashboard:presenca_lista'), fetch_redirect_response=False)

    def test_marcar_manual(self):
        url = reverse('admin_dashboard:presenca_marcar_manual')
        with agora(2026, 11, 9, 18):
            self.client.post(url, {'aluna': self.bia.pk, 'turma': self.turma_a.pk, 'data': '2026-11-09'})
            presenca = Presenca.objects.get()
            self.assertEqual((presenca.origem, presenca.registrada_por), ('manual', self.staff))

            # data futura, dia sem aula e turma da qual ela não faz parte são recusados
            self.client.post(url, {'aluna': self.bia.pk, 'turma': self.turma_a.pk, 'data': '2026-11-16'})
            self.client.post(url, {'aluna': self.bia.pk, 'turma': self.turma_a.pk, 'data': '2026-11-10'})
            self.client.post(url, {'aluna': self.bia.pk, 'turma': self.turma_b.pk, 'data': '2026-11-09'})
        self.assertEqual(Presenca.objects.count(), 1)

    def test_resumo_ordena_por_faltas(self):
        Presenca.objects.create(aluna=self.bia, turma=self.turma_a, data=SEG_02)
        Presenca.objects.create(aluna=self.bia, turma=self.turma_a, data=SEG_09)
        with agora(2026, 11, 9, 18):
            resposta = self.client.get(reverse('admin_dashboard:presenca_resumo'))
        self.assertEqual(resposta.status_code, 200)
        linhas = resposta.context['linhas']
        self.assertEqual([l['aluna'].nome for l in linhas], ['Ana', 'Bia'])  # Ana: 4 faltas, Bia: 0
        self.assertEqual(linhas[0]['dados']['falta'], 4)
        self.assertEqual(linhas[1]['dados']['falta'], 0)
        self.assertEqual(linhas[1]['dados']['frequencia'], 100)

    def test_detalhe_da_aluna(self):
        Presenca.objects.create(aluna=self.ana, turma=self.turma_a, data=SEG_02)
        with agora(2026, 11, 9, 18):
            resposta = self.client.get(reverse('admin_dashboard:presenca_aluna', args=[self.ana.pk]))
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.context['mes_dados']['falta'], 3)
        self.assertEqual(resposta.context['geral']['presente'], 1)
        self.assertEqual(resposta.context['maior_sequencia'], 3)  # B(2), A(9), B(9)
        self.assertEqual(len(resposta.context['registros']), 4)

    def test_cards_da_lista_de_alunas_mostram_faltas_do_mes(self):
        Presenca.objects.create(aluna=self.bia, turma=self.turma_a, data=SEG_02)
        with agora(2026, 11, 9, 18):
            resposta = self.client.get(reverse('admin_dashboard:alunas_list'))
        self.assertEqual(resposta.status_code, 200)
        faltas = {a.nome: a.faltas_mes for a in resposta.context['alunas']}
        self.assertEqual(faltas, {'Ana': 4, 'Bia': 1})
        self.assertContains(resposta, 'Faltas em novembro/2026')
        html = resposta.content.decode()
        self.assertRegex(html, r'>\s*4 faltas\s*<')
        self.assertRegex(html, r'>\s*1 falta\s*<')  # singular

    def test_dias_sem_aula_crud(self):
        url = reverse('admin_dashboard:presenca_dias_sem_aula')
        self.client.post(url, {'data': '2026-11-09', 'motivo': 'Feriado', 'turma': ''})
        folga = DiaSemAula.objects.get()
        self.assertIsNone(folga.turma)
        with agora(2026, 11, 9, 18):
            resposta = self.client.get(reverse('admin_dashboard:presenca_lista'), {'periodo': 'mes'})
            self.assertEqual(resposta.context['resumo']['falta'], 3)  # só 2/11 (9/11 é feriado)
            self.assertEqual(len(resposta.context['folgas_periodo']), 1)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.post(reverse('admin_dashboard:presenca_dia_sem_aula_excluir', args=[folga.pk]))
        self.assertEqual(DiaSemAula.objects.count(), 0)

    def test_ajustes_e_qr(self):
        url = reverse('admin_dashboard:presenca_ajustes')
        self.assertEqual(self.client.get(url).status_code, 200)

        self.client.post(url, {
            'acao': 'salvar', 'data_inicio_controle': '2026-10-01',
            'minutos_antes': '45', 'minutos_depois': '10',
        })
        config = ConfiguracaoPresenca.obter()
        self.assertEqual((config.minutos_antes, config.minutos_depois), (45, 10))
        self.assertEqual(config.data_inicio_controle, date(2026, 10, 1))

        # valores inválidos não alteram nada
        self.client.post(url, {'acao': 'salvar', 'data_inicio_controle': 'x', 'minutos_antes': '-1', 'minutos_depois': '0'})
        config.refresh_from_db()
        self.assertEqual(config.minutos_antes, 45)

        token_antigo = config.token_qr
        self.client.post(url, {'acao': 'novo_qr'})
        config.refresh_from_db()
        self.assertNotEqual(config.token_qr, token_antigo)

        png = self.client.get(reverse('admin_dashboard:presenca_qr_png'))
        self.assertEqual(png['Content-Type'], 'image/png')
        self.assertTrue(png.content.startswith(b'\x89PNG'))
        self.assertEqual(self.client.get(reverse('admin_dashboard:presenca_qr_imprimir')).status_code, 200)

    def test_confirmar_horarios_automaticos(self):
        HorarioTurma.objects.filter(turma=self.turma_a).update(preenchido_automaticamente=True)
        self.client.post(reverse('admin_dashboard:presenca_ajustes'), {'acao': 'confirmar_horarios'})
        self.assertFalse(HorarioTurma.objects.filter(preenchido_automaticamente=True).exists())

    def test_turmas_sem_horario_aparecem_como_pendentes(self):
        pendente = cria_turma('Pendente', dia=None)
        cria_aluna('Zeca', [pendente])
        with agora(2026, 11, 9, 18):
            resposta = self.client.get(reverse('admin_dashboard:presenca_lista'))
        self.assertEqual([t.nome for t in resposta.context['turmas_pendentes']], ['Pendente'])


# ---------------------------------------------------------------------------
# Formulário de turma (horários)
# ---------------------------------------------------------------------------

@override_settings(STORAGES=STORAGES_TESTE)
class HorariosDaTurmaTests(TestCase):
    def setUp(self):
        self.staff = cria_usuario('admin', staff=True)
        self.client.force_login(self.staff)

    def test_editar_turma_salva_horarios(self):
        turma = cria_turma('Ballet A', dia=None)
        url = reverse('admin_dashboard:turma_editar', args=[turma.pk])
        self.assertContains(self.client.get(url), 'Horários das aulas')

        self.client.post(url, {
            'nome': 'Ballet A', 'capacidade_maxima': '20', 'ativa': 'on',
            'horarios_enviados': '1',
            'horario_dia': ['0', '2', ''], 'horario_inicio': ['14:00', '15:30', ''], 'horario_fim': ['15:00', '16:30', ''],
        })
        horarios = list(turma.horarios_aula.order_by('dia_semana').values_list('dia_semana', 'hora_inicio', 'hora_fim'))
        self.assertEqual(horarios, [(0, time(14), time(15)), (2, time(15, 30), time(16, 30))])
        self.assertFalse(turma.horarios_aula.filter(preenchido_automaticamente=True).exists())

    def test_formulario_antigo_sem_a_secao_nao_apaga_horarios(self):
        turma = cria_turma('Ballet A')
        self.client.post(reverse('admin_dashboard:turma_editar', args=[turma.pk]), {
            'nome': 'Ballet A', 'capacidade_maxima': '20', 'ativa': 'on',
        })
        self.assertEqual(turma.horarios_aula.count(), 1)

    def test_criar_turma_com_horario(self):
        self.client.post(reverse('admin_dashboard:turma_criar'), {
            'nome': 'Nova', 'capacidade_maxima': '10', 'ativa': 'on',
            'horarios_enviados': '1',
            'horario_dia': ['4'], 'horario_inicio': ['09:00'], 'horario_fim': ['10:00'],
        })
        turma = Turma.objects.get(nome='Nova')
        self.assertEqual(turma.horarios_aula.get().dia_semana, 4)

    def test_validacoes(self):
        turma = cria_turma('Ballet A', dia=None)

        class Post(dict):
            def getlist(self, chave):
                valor = self.get(chave, [])
                return valor if isinstance(valor, list) else [valor]

        avisos = salvar_horarios_turma(turma, Post({
            'horarios_enviados': '1',
            'horario_dia': ['0', '0', '1', '2'],
            'horario_inicio': ['14:00', '15:00', '16:00', ''],
            'horario_fim': ['15:00', '16:00', '15:00', '17:00'],
        }))
        # salvo: só segunda 14-15. Repetido (seg), fim<início (ter) e incompleto (qua) geram aviso
        self.assertEqual(len(avisos), 3)
        self.assertEqual(list(turma.horarios_aula.values_list('dia_semana', flat=True)), [0])
