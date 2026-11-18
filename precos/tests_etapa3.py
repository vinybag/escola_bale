"""Etapa 3: em qual login a mensalidade da aluna é gerada (ficha ou grupo de família)."""

from datetime import date
from decimal import Decimal
from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from pagamentos import cobranca
from pagamentos.models import Mensalidade
from usuarios.models import Aluna, Perfil, Turma

from . import servico
from .models import GrupoDesconto, PrecoAluna
from .tests import ESTATICOS_SIMPLES

D = Decimal


class Base(TestCase):
    def setUp(self):
        def login(nome):
            u = User.objects.create_user(nome, email=f'{nome}@x.com', password='x', first_name=nome.title())
            Perfil.objects.create(user=u, is_responsavel=True, telefone='11999990000')
            return u

        self.filha_user = login('filha')   # representante da família
        self.mae_user = login('mae')       # adulta com login próprio
        self.turma = Turma.objects.create(nome='Ballet', valor_mensalidade=D('110'))
        antiga = date(2025, 1, 10)

        self.filha = Aluna.objects.create(
            nome='Filha', tipo_aluna='adulto', usuario=self.filha_user, valor_mensalidade=D('91.30'),
            gerar_mensalidade_automatica=True, dia_vencimento=10,
        )
        self.mae = Aluna.objects.create(
            nome='Mãe', tipo_aluna='adulto', usuario=self.mae_user, valor_mensalidade=D('91.30'),
            gerar_mensalidade_automatica=True, dia_vencimento=10,
        )
        self.neta = Aluna.objects.create(
            nome='Neta', responsavel=self.filha_user, valor_mensalidade=D('91.40'),
            gerar_mensalidade_automatica=True, dia_vencimento=10,
        )
        Aluna.objects.all().update(data_matricula=antiga)

        self.familia = GrupoDesconto.objects.create(nome='Família Silva', eh_familia=True, representante=self.filha_user)
        self.familia.alunas.add(self.filha, self.mae, self.neta)


class PagadorTests(Base):
    def pagador(self, aluna):
        return servico.pagador_da_aluna(Aluna.objects.get(pk=aluna.pk))

    def test_grupo_de_familia_leva_todas_para_o_login_do_representante(self):
        for aluna in (self.filha, self.mae, self.neta):
            self.assertEqual(self.pagador(aluna), self.filha_user)

    def test_sem_grupo_vale_o_padrao_de_sempre(self):
        self.familia.alunas.clear()

        self.assertEqual(self.pagador(self.mae), self.mae_user)          # adulta: o próprio login
        self.assertEqual(self.pagador(self.neta), self.filha_user)       # infantil: o responsável

    def test_ficha_tem_prioridade_sobre_o_grupo(self):
        outro = User.objects.create_user('outro', email='o@x.com', password='x')
        PrecoAluna.objects.create(aluna=self.mae, pagador=outro)

        self.assertEqual(self.pagador(self.mae), outro)
        self.assertEqual(self.pagador(self.neta), self.filha_user)

    def test_grupo_desligado_ou_sem_representante_nao_vale(self):
        self.familia.ativo = False
        self.familia.save()
        self.assertEqual(self.pagador(self.mae), self.mae_user)

        self.familia.ativo = True
        self.familia.representante = None
        self.familia.save()
        self.assertEqual(self.pagador(self.mae), self.mae_user)

    def test_grupo_de_desconto_comum_nao_muda_o_login(self):
        self.familia.eh_familia = False
        self.familia.save()

        self.assertEqual(self.pagador(self.mae), self.mae_user)


class GeracaoTests(Base):
    def gerar_auto(self):
        call_command('gera_mensalidades_auto', stdout=StringIO())

    def test_cron_gera_uma_mensalidade_por_aluna_todas_no_login_do_representante(self):
        self.gerar_auto()

        itens = Mensalidade.objects.all()
        self.assertEqual(itens.count(), 3)
        self.assertEqual({m.responsavel_id for m in itens}, {self.filha_user.pk})
        self.assertEqual(
            {m.aluna.nome: m.valor for m in itens.select_related('aluna')},
            {'Filha': D('91.30'), 'Mãe': D('91.30'), 'Neta': D('91.40')},
        )

    def test_familia_ve_um_card_so_com_o_total(self):
        self.gerar_auto()

        cards = cobranca.agrupar(Mensalidade.objects.filter(responsavel=self.filha_user))

        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0].valor, D('274.00'))
        self.assertEqual(cards[0].nomes_alunas, 'Filha, Mãe e Neta')

    def test_login_da_mae_nao_recebe_mais_a_mensalidade_dela(self):
        self.gerar_auto()

        self.assertFalse(Mensalidade.objects.filter(responsavel=self.mae_user).exists())

    def test_mensalidades_que_ja_existiam_nao_mudam_de_login(self):
        existente = Mensalidade.objects.create(
            aluna=self.mae, responsavel=self.mae_user, mes_referencia=date(2020, 1, 1), valor=D('50'),
            data_vencimento=date(2020, 1, 10),
        )
        self.gerar_auto()

        existente.refresh_from_db()
        self.assertEqual(existente.responsavel_id, self.mae_user.pk)

    def test_comando_manual_tambem_usa_o_representante(self):
        call_command('gerar_mensalidades', ano=2026, mes=12, stdout=StringIO())

        self.assertEqual(
            {(m.aluna.nome, m.responsavel_id) for m in Mensalidade.objects.select_related('aluna')},
            {('Filha', self.filha_user.pk), ('Mãe', self.filha_user.pk), ('Neta', self.filha_user.pk)},
        )

    def test_comando_manual_continua_ignorando_adulta_sem_pagador_definido(self):
        self.familia.alunas.remove(self.mae)
        call_command('gerar_mensalidades', ano=2026, mes=12, stdout=StringIO())

        self.assertFalse(Mensalidade.objects.filter(aluna=self.mae).exists())


@ESTATICOS_SIMPLES
class TelasTests(Base):
    def setUp(self):
        super().setUp()
        self.c = Client()
        self.c.force_login(User.objects.create_user('adm', email='a@x.com', password='x', is_staff=True))

    def test_ficha_mostra_o_campo_e_o_grupo_de_familia(self):
        pagina = self.c.get(reverse('admin_dashboard:aluna_editar', args=[self.mae.pk]))

        self.assertContains(pagina, 'Gerar a mensalidade no login de')
        self.assertContains(pagina, 'grupo de família "Família Silva"')

    def test_salvar_a_ficha_guarda_o_login_escolhido(self):
        outro = User.objects.create_user('outro', email='o@x.com', password='x')
        self.c.post(reverse('admin_dashboard:aluna_editar', args=[self.mae.pk]), {
            'nome': 'Mãe', 'tipo_aluna': 'adulto', 'usuario': self.mae_user.pk, 'ativa': 'on',
            'dia_vencimento': 10, 'valor_mensalidade': '91.30', 'valor_manual': 'on', 'pagador': outro.pk,
        })

        self.assertEqual(PrecoAluna.objects.get(aluna=self.mae).pagador_id, outro.pk)

    def test_voltar_para_automatico_limpa_a_escolha(self):
        PrecoAluna.objects.create(aluna=self.mae, pagador=self.filha_user)
        self.c.post(reverse('admin_dashboard:aluna_editar', args=[self.mae.pk]), {
            'nome': 'Mãe', 'tipo_aluna': 'adulto', 'usuario': self.mae_user.pk, 'ativa': 'on',
            'dia_vencimento': 10, 'valor_mensalidade': '91.30', 'valor_manual': 'on', 'pagador': '',
        })

        self.assertIsNone(PrecoAluna.objects.get(aluna=self.mae).pagador_id)

    def test_criar_grupo_de_familia_pela_tela(self):
        grupo = GrupoDesconto.objects.create(nome='Família Souza')
        self.c.post(reverse('precos_admin:grupo_detalhe', args=[grupo.pk]), {
            'acao': 'salvar', 'nome': 'Família Souza', 'ativo': 'on', 'eh_familia': 'on', 'representante': self.filha_user.pk,
        })

        grupo.refresh_from_db()
        self.assertTrue(grupo.eh_familia)
        self.assertEqual(grupo.representante, self.filha_user)

    def test_grupo_de_familia_sem_representante_e_recusado(self):
        grupo = GrupoDesconto.objects.create(nome='Família Souza')
        self.c.post(reverse('precos_admin:grupo_detalhe', args=[grupo.pk]), {
            'acao': 'salvar', 'nome': 'Família Souza', 'ativo': 'on', 'eh_familia': 'on', 'representante': '',
        })

        grupo.refresh_from_db()
        self.assertFalse(grupo.eh_familia)

    def test_desmarcar_familia_limpa_o_representante(self):
        self.c.post(reverse('precos_admin:grupo_detalhe', args=[self.familia.pk]), {
            'acao': 'salvar', 'nome': 'Família Silva', 'ativo': 'on', 'representante': self.filha_user.pk,
        })

        self.familia.refresh_from_db()
        self.assertFalse(self.familia.eh_familia)
        self.assertIsNone(self.familia.representante)
