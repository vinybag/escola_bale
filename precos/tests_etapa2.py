"""Testes da etapa 2: preço calculado na ficha da aluna, irmãs/parentes e geração por mês."""

from datetime import date, timedelta
from decimal import Decimal
from io import StringIO
from unittest import mock

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from pagamentos.models import Mensalidade
from usuarios.models import Aluna, Perfil, Turma

from . import motor, servico
from .models import EntradaTurma, GrauParentesco, GrupoDesconto, LigacaoFamiliar, PrecoAluna, RegraDesconto
from .motor import Entrada, Familia
from .tests import ESTATICOS_SIMPLES, BaseRegras

D = Decimal


class QuemRecebeNoMotorTests(BaseRegras):
    """O desconto de família para irmãs e parentes, nos três modos."""

    def setUp(self):
        super().setUp()
        self.prima = GrauParentesco.objects.create(nome='Prima')
        self.r_prima = RegraDesconto.objects.create(
            nome='Prima', valor=D('10'), incide_em='primeira', familia='parentesco', grau=self.prima,
        )

    def total(self, familia, **kw):
        return self.calcular([Entrada(self.ballet)], familia=familia, regras=kw.get('regras', [self.r_irma, self.r_prima])).total

    def test_irma_automatico_so_a_que_entrou_depois_recebe(self):
        self.assertEqual(self.total(Familia(irma_anterior=True, tem_irma=True)), D('93.50'))
        self.assertEqual(self.total(Familia(irma_anterior=False, tem_irma=True)), D('110.00'))

    def test_irma_as_duas_recebem(self):
        self.r_irma.quem_recebe = 'ambas'
        self.assertEqual(self.total(Familia(irma_anterior=True, tem_irma=True)), D('93.50'))
        self.assertEqual(self.total(Familia(irma_anterior=False, tem_irma=True)), D('93.50'))

    def test_irma_so_a_marcada_recebe(self):
        self.r_irma.quem_recebe = 'marcada'
        self.assertEqual(self.total(Familia(irma_anterior=True, tem_irma=True, marcada=True)), D('93.50'))
        self.assertEqual(self.total(Familia(irma_anterior=True, tem_irma=True, marcada=False)), D('110.00'))
        self.assertEqual(self.total(Familia(irma_anterior=False, tem_irma=True, marcada=True)), D('93.50'))

    def test_sem_irma_ninguem_recebe_nem_marcada(self):
        self.r_irma.quem_recebe = 'marcada'
        self.assertEqual(self.total(Familia(marcada=True)), D('110.00'))

    def test_prima_automatico_cada_uma_recebe(self):
        familia = Familia(graus=frozenset({self.prima.pk}))
        self.assertEqual(self.total(familia), D('99.00'))

    def test_prima_so_a_que_entrou_depois(self):
        self.r_prima.quem_recebe = 'depois'
        self.assertEqual(self.total(Familia(graus=frozenset({self.prima.pk}))), D('110.00'))
        self.assertEqual(
            self.total(Familia(graus=frozenset({self.prima.pk}), graus_antes=frozenset({self.prima.pk}))), D('99.00'),
        )

    def test_prima_so_a_marcada(self):
        self.r_prima.quem_recebe = 'marcada'
        self.assertEqual(self.total(Familia(graus=frozenset({self.prima.pk}))), D('110.00'))
        self.assertEqual(self.total(Familia(graus=frozenset({self.prima.pk}), marcada=True)), D('99.00'))

    def test_golden_continua_sem_desconto_de_irma_em_qualquer_modo(self):
        self.r_irma.quem_recebe = 'ambas'
        resultado = self.calcular(
            [Entrada(self.ballet)], grupos={self.golden.pk}, familia=Familia(tem_irma=True),
            regras=[self.r_irma, self.r_golden],
        )
        self.assertEqual(resultado.total, D('99.00'))  # só o Golden


class BaseAlunas(TestCase):
    def setUp(self):
        self.ballet = Turma.objects.create(nome='Ballet', valor_mensalidade=D('110'))
        self.jazz = Turma.objects.create(nome='Jazz', valor_mensalidade=D('110'))
        self.mae = User.objects.create_user('mae', email='mae@x.com', password='x')
        Perfil.objects.create(user=self.mae, is_responsavel=True)
        self.r_irma = RegraDesconto.objects.create(
            nome='Irmã', valor=D('15'), incide_em='primeira', familia='irma_mesma_responsavel',
        )
        self.r_segunda = RegraDesconto.objects.create(nome='2ª', valor=D('15'), incide_em='segunda', publico='ja_aluna')

    def nova_aluna(self, nome, turmas=(), matricula=None, **kw):
        aluna = Aluna.objects.create(nome=nome, responsavel=kw.pop('responsavel', self.mae), **kw)

        if matricula:
            Aluna.objects.filter(pk=aluna.pk).update(data_matricula=matricula)
            aluna.refresh_from_db()

        for turma in turmas:
            aluna.turmas.add(turma)

        return aluna


class EntradasTests(BaseAlunas):
    def test_marcar_turma_cria_entrada_e_desmarcar_apaga(self):
        aluna = self.nova_aluna('Ana', [self.ballet])
        self.assertEqual(EntradaTurma.objects.filter(aluna=aluna).count(), 1)
        aluna.turmas.remove(self.ballet)
        self.assertEqual(EntradaTurma.objects.filter(aluna=aluna).count(), 0)

    def test_turma_depois_do_cadastro_conta_como_ja_era_aluna(self):
        aluna = self.nova_aluna('Ana', [self.ballet], matricula=date(2026, 1, 10))
        EntradaTurma.objects.filter(aluna=aluna).update(data_entrada=date(2026, 1, 10))
        aluna.turmas.add(self.jazz)  # entra hoje

        entradas = servico.entradas_da_aluna(aluna)

        self.assertEqual([e.turma.nome for e in entradas], ['Ballet', 'Jazz'])
        self.assertEqual([e.apos_cadastro for e in entradas], [False, True])

    def test_aluna_antiga_sem_entradas_ganha_na_data_da_matricula(self):
        aluna = self.nova_aluna('Ana', matricula=date(2025, 3, 1))
        aluna.turmas.through.objects.create(aluna=aluna, turma=self.ballet)  # sem sinal
        EntradaTurma.objects.all().delete()

        entradas = servico.entradas_da_aluna(aluna)

        self.assertEqual(len(entradas), 1)
        self.assertFalse(entradas[0].apos_cadastro)
        self.assertEqual(EntradaTurma.objects.get().data_entrada, date(2025, 3, 1))


class FamiliaTests(BaseAlunas):
    def test_irmas_mesma_responsavel_so_a_mais_nova_na_escola_recebe(self):
        velha = self.nova_aluna('Velha', [self.ballet], matricula=date(2025, 1, 1))
        nova = self.nova_aluna('Nova', [self.ballet], matricula=date(2026, 2, 1))

        self.assertFalse(servico.montar_familia(aluna=velha).irma_anterior)
        self.assertTrue(servico.montar_familia(aluna=velha).tem_irma)
        self.assertTrue(servico.montar_familia(aluna=nova).irma_anterior)

        self.assertEqual(servico.calcular_para_aluna(velha).total, D('110.00'))
        self.assertEqual(servico.calcular_para_aluna(nova).total, D('93.50'))

    def test_irma_inativa_nao_conta(self):
        velha = self.nova_aluna('Velha', [self.ballet], matricula=date(2025, 1, 1), ativa=False)
        nova = self.nova_aluna('Nova', [self.ballet])

        self.assertFalse(servico.montar_familia(aluna=nova).irma_anterior)

    def test_responsaveis_diferentes_nao_sao_irmas(self):
        outra = User.objects.create_user('outra', email='o@x.com', password='x')
        self.nova_aluna('A', [self.ballet], matricula=date(2025, 1, 1))
        b = self.nova_aluna('B', [self.ballet], responsavel=outra)

        self.assertFalse(servico.montar_familia(aluna=b).tem_irma)

    def test_ligacao_de_prima_vale_nos_dois_sentidos_e_marca_quem_entrou_antes(self):
        prima = GrauParentesco.objects.create(nome='Prima')
        outra_mae = User.objects.create_user('tia', email='t@x.com', password='x')
        a = self.nova_aluna('A', [self.ballet], matricula=date(2025, 1, 1))
        b = self.nova_aluna('B', [self.ballet], matricula=date(2026, 1, 1), responsavel=outra_mae)
        LigacaoFamiliar.objects.create(aluna=b, parente=a, grau=prima)

        fa, fb = servico.montar_familia(aluna=a), servico.montar_familia(aluna=b)

        self.assertEqual((fa.graus, fa.graus_antes), (frozenset({prima.pk}), frozenset()))
        self.assertEqual((fb.graus, fb.graus_antes), (frozenset({prima.pk}), frozenset({prima.pk})))

    def test_marcada_na_ficha_e_lida(self):
        a = self.nova_aluna('A')
        PrecoAluna.objects.create(aluna=a, valor_manual=False, recebe_desconto_familiar=True)

        self.assertTrue(servico.montar_familia(aluna=a, marcada=servico.marcada_para_receber(a)).marcada)


class ValorPorMesTests(BaseAlunas):
    def setUp(self):
        super().setUp()
        self.r_campanha = RegraDesconto.objects.create(
            nome='Campanha', valor=D('50'), incide_em='segunda_em_diante', efeito='preco_fixo', publico='ja_aluna',
            inicio=date(2026, 11, 1), fim=date(2026, 12, 31), so_turmas_entradas_no_periodo=True, substitui_outros=True,
        )
        self.aluna = self.nova_aluna('Ana', [self.ballet], matricula=date(2026, 1, 10))
        EntradaTurma.objects.filter(aluna=self.aluna).update(data_entrada=date(2026, 1, 10))
        self.aluna.turmas.add(self.jazz)
        EntradaTurma.objects.filter(aluna=self.aluna, turma=self.jazz).update(data_entrada=date(2026, 11, 20))
        self.aluna.valor_mensalidade = D('777.00')
        self.aluna.save()

    def test_aluna_sem_registro_e_manual_e_nada_muda(self):
        self.assertTrue(servico.valor_e_manual(self.aluna))
        self.assertEqual(servico.valor_para_mes(self.aluna, date(2026, 12, 1)), D('777.00'))
        self.assertEqual(servico.valor_para_mes(self.aluna, date(2027, 1, 1)), D('777.00'))

    def test_calculada_acompanha_o_mes_campanha_ate_dezembro_e_normal_em_janeiro(self):
        PrecoAluna.objects.create(aluna=self.aluna, valor_manual=False)

        self.assertEqual(servico.valor_para_mes(self.aluna, date(2026, 12, 1)), D('160.00'))   # 110 + 50
        self.assertEqual(servico.valor_para_mes(self.aluna, date(2027, 1, 1)), D('203.50'))    # 110 + 93,50

    def test_calculada_sem_poder_calcular_cai_no_valor_da_ficha(self):
        self.jazz.valor_mensalidade = None
        self.jazz.save()
        PrecoAluna.objects.create(aluna=self.aluna, valor_manual=False)

        self.assertEqual(servico.valor_para_mes(self.aluna, date(2026, 12, 1)), D('777.00'))

    def test_comando_automatico_cobra_o_valor_do_mes(self):
        PrecoAluna.objects.create(aluna=self.aluna, valor_manual=False)
        manual = self.nova_aluna('Manual', matricula=date(2026, 1, 1), valor_mensalidade=D('120.00'))
        manual.turmas.add(self.ballet)

        hoje = timezone.localdate()
        mes_seguinte = date(hoje.year + (hoje.month == 12), hoje.month % 12 + 1, 1)
        call_command('gera_mensalidades_auto', stdout=StringIO())

        valor_calculado = Mensalidade.objects.get(aluna=self.aluna, mes_referencia=mes_seguinte).valor
        self.assertEqual(valor_calculado, servico.valor_para_mes(self.aluna, mes_seguinte))
        self.assertEqual(Mensalidade.objects.get(aluna=manual, mes_referencia=mes_seguinte).valor, D('120.00'))
        self.aluna.refresh_from_db()
        self.assertEqual(self.aluna.valor_mensalidade, valor_calculado)  # a ficha acompanha o que foi cobrado

    def test_comando_manual_cobra_o_mes_pedido(self):
        PrecoAluna.objects.create(aluna=self.aluna, valor_manual=False)
        call_command('gerar_mensalidades', ano=2026, mes=12, stdout=StringIO())

        self.assertEqual(Mensalidade.objects.get(aluna=self.aluna, mes_referencia=date(2026, 12, 1)).valor, D('160.00'))


@ESTATICOS_SIMPLES
class FichaDaAlunaTests(BaseAlunas):
    def setUp(self):
        super().setUp()
        self.staff = User.objects.create_user('adm', email='a@x.com', password='x', is_staff=True)
        self.c = Client()
        self.c.force_login(self.staff)

    def dados_criar(self, **extra):
        dados = {
            'nome': 'Bia', 'tipo_aluna': 'infantil', 'responsavel': self.mae.pk, 'ativa': 'on',
            'turmas': [self.ballet.pk, self.jazz.pk], 'dia_vencimento': 10, 'valor_mensalidade': '',
        }
        dados.update(extra)
        return dados

    def test_criar_aluna_calcula_o_valor_sozinho(self):
        # nova aluna, 2 turmas no mesmo dia: nenhuma conta como "já era aluna" (110 + 110)
        resposta = self.c.post(reverse('admin_dashboard:aluna_criar'), self.dados_criar())

        self.assertEqual(resposta.status_code, 302)
        aluna = Aluna.objects.get(nome='Bia')
        self.assertEqual(aluna.valor_mensalidade, D('220.00'))
        self.assertFalse(PrecoAluna.objects.get(aluna=aluna).valor_manual)
        self.assertEqual(EntradaTurma.objects.filter(aluna=aluna).count(), 2)

    def test_criar_aluna_com_valor_manual_guarda_o_digitado(self):
        self.c.post(reverse('admin_dashboard:aluna_criar'), self.dados_criar(valor_manual='on', valor_mensalidade='150.00'))

        aluna = Aluna.objects.get(nome='Bia')
        self.assertEqual(aluna.valor_mensalidade, D('150.00'))
        self.assertTrue(PrecoAluna.objects.get(aluna=aluna).valor_manual)

    def test_criar_aluna_ordem_define_qual_turma_e_a_primeira(self):
        self.c.post(reverse('admin_dashboard:aluna_criar'), self.dados_criar(
            **{f'entrada_ordem_{self.jazz.pk}': 1, f'entrada_ordem_{self.ballet.pk}': 2},
        ))

        aluna = Aluna.objects.get(nome='Bia')
        self.assertEqual([e.turma.nome for e in aluna.entradas_turma.all()], ['Jazz', 'Ballet'])

    def test_criar_com_turma_sem_valor_mostra_erro_e_nao_cria(self):
        sem_valor = Turma.objects.create(nome='Nova turma')
        resposta = self.c.post(
            reverse('admin_dashboard:aluna_criar'), self.dados_criar(turmas=[sem_valor.pk]), follow=True,
        )

        self.assertFalse(Aluna.objects.filter(nome='Bia').exists())
        self.assertContains(resposta, 'Não foi possível calcular')

    def test_aluna_antiga_aparece_com_valor_manual_e_salvar_nao_muda_o_valor(self):
        aluna = self.nova_aluna('Antiga', [self.ballet], matricula=date(2025, 5, 5), valor_mensalidade=D('123.45'))
        pagina = self.c.get(reverse('admin_dashboard:aluna_editar', args=[aluna.pk]))

        self.assertContains(pagina, 'Cálculo da mensalidade')
        self.assertContains(pagina, 'name="valor_manual" id="calc-manual" checked')

        self.c.post(reverse('admin_dashboard:aluna_editar', args=[aluna.pk]), {
            'nome': 'Antiga', 'tipo_aluna': 'infantil', 'responsavel': self.mae.pk, 'ativa': 'on',
            'turmas': [self.ballet.pk], 'dia_vencimento': 10, 'valor_mensalidade': '123.45', 'valor_manual': 'on',
            f'entrada_data_{self.ballet.pk}': '2025-05-05',
        })

        aluna.refresh_from_db()
        self.assertEqual(aluna.valor_mensalidade, D('123.45'))
        self.assertTrue(PrecoAluna.objects.get(aluna=aluna).valor_manual)

    def test_editar_sem_mexer_no_valor_manual_nao_recalcula_mesmo_com_turma_nova(self):
        aluna = self.nova_aluna('Antiga', [self.ballet], matricula=date(2025, 5, 5), valor_mensalidade=D('123.45'))
        self.c.post(reverse('admin_dashboard:aluna_editar', args=[aluna.pk]), {
            'nome': 'Antiga', 'tipo_aluna': 'infantil', 'responsavel': self.mae.pk, 'ativa': 'on',
            'turmas': [self.ballet.pk, self.jazz.pk], 'dia_vencimento': 10, 'valor_mensalidade': '123.45',
            'valor_manual': 'on',
        })

        aluna.refresh_from_db()
        self.assertEqual(aluna.valor_mensalidade, D('123.45'))
        jazz = aluna.entradas_turma.get(turma=self.jazz)
        self.assertEqual(jazz.data_entrada, timezone.localdate())  # entrou hoje, depois do cadastro

    def test_desmarcar_manual_na_edicao_passa_a_calcular(self):
        aluna = self.nova_aluna('Antiga', [self.ballet], matricula=date(2025, 5, 5), valor_mensalidade=D('123.45'))
        self.c.post(reverse('admin_dashboard:aluna_editar', args=[aluna.pk]), {
            'nome': 'Antiga', 'tipo_aluna': 'infantil', 'responsavel': self.mae.pk, 'ativa': 'on',
            'turmas': [self.ballet.pk], 'dia_vencimento': 10, 'valor_mensalidade': '123.45',
        })

        aluna.refresh_from_db()
        self.assertEqual(aluna.valor_mensalidade, D('110.00'))  # única aluna da responsável, 1 turma
        self.assertFalse(PrecoAluna.objects.get(aluna=aluna).valor_manual)

    def test_marcar_parente_e_marcada_ficam_gravados(self):
        prima = GrauParentesco.objects.create(nome='Prima')
        outra = self.nova_aluna('Prima Lia', [self.ballet], responsavel=User.objects.create_user('t', email='t@x.com', password='x'))
        self.c.post(reverse('admin_dashboard:aluna_criar'), self.dados_criar(
            turmas=[self.ballet.pk], lig_parente=[outra.pk], lig_grau=[prima.pk], recebe_desconto_familiar='on',
        ))

        aluna = Aluna.objects.get(nome='Bia')
        self.assertTrue(LigacaoFamiliar.objects.filter(aluna=aluna, parente=outra, grau=prima).exists())
        self.assertTrue(PrecoAluna.objects.get(aluna=aluna).recebe_desconto_familiar)

    def test_endpoint_de_calculo_ao_vivo(self):
        resposta = self.c.post(reverse('precos_admin:calcular_aluna'), {
            'turmas': [self.ballet.pk], 'tipo_aluna': 'infantil', 'responsavel': self.mae.pk,
        })

        corpo = resposta.json()
        self.assertTrue(corpo['ok'])
        self.assertEqual(corpo['total'], '110.00')
        self.assertIn('Ballet', corpo['html'])

    def test_endpoint_so_para_staff(self):
        leigo = Client()
        leigo.force_login(User.objects.create_user('leigo', email='l@x.com', password='x'))

        self.assertEqual(leigo.post(reverse('precos_admin:calcular_aluna'), {}).status_code, 302)


@ESTATICOS_SIMPLES
class ConferirAlunasTests(BaseAlunas):
    def setUp(self):
        super().setUp()
        self.staff = User.objects.create_user('adm', email='a@x.com', password='x', is_staff=True)
        self.c = Client()
        self.c.force_login(self.staff)
        self.aluna = self.nova_aluna('Ana', [self.ballet], matricula=date(2025, 1, 1), valor_mensalidade=D('100.00'))

    def test_lista_mostra_a_diferenca_e_nao_muda_nada(self):
        pagina = self.c.get(reverse('precos_admin:conferir'))

        self.assertContains(pagina, 'Ana')
        self.assertContains(pagina, 'valor manual')
        self.aluna.refresh_from_db()
        self.assertEqual(self.aluna.valor_mensalidade, D('100.00'))
        self.assertFalse(PrecoAluna.objects.exists())

    def test_so_muda_quem_foi_marcada(self):
        outra = self.nova_aluna('Bia', [self.ballet], responsavel=User.objects.create_user('o', email='o@x.com', password='x'), valor_mensalidade=D('100.00'))
        self.c.post(reverse('precos_admin:conferir_aplicar'), {'alunas': [self.aluna.pk]})

        self.aluna.refresh_from_db()
        outra.refresh_from_db()
        self.assertEqual(self.aluna.valor_mensalidade, D('110.00'))
        self.assertFalse(servico.valor_e_manual(self.aluna))
        self.assertEqual(outra.valor_mensalidade, D('100.00'))
        self.assertTrue(servico.valor_e_manual(outra))

    def test_nao_aplica_quando_nao_da_para_calcular(self):
        self.ballet.valor_mensalidade = None
        self.ballet.save()
        self.c.post(reverse('precos_admin:conferir_aplicar'), {'alunas': [self.aluna.pk]})

        self.aluna.refresh_from_db()
        self.assertEqual(self.aluna.valor_mensalidade, D('100.00'))
        self.assertTrue(servico.valor_e_manual(self.aluna))

    def test_so_staff_aplica(self):
        leigo = Client()
        leigo.force_login(User.objects.create_user('leigo', email='l@x.com', password='x'))
        leigo.post(reverse('precos_admin:conferir_aplicar'), {'alunas': [self.aluna.pk]})

        self.aluna.refresh_from_db()
        self.assertEqual(self.aluna.valor_mensalidade, D('100.00'))


@ESTATICOS_SIMPLES
class RegraQuemRecebeTelaTests(BaseAlunas):
    def test_salvar_regra_de_irma_com_quem_recebe(self):
        c = Client()
        c.force_login(User.objects.create_user('adm', email='a@x.com', password='x', is_staff=True))
        c.post(reverse('precos_admin:regra_nova'), {
            'nome': 'Irmãs', 'ativa': 'on', 'efeito': 'percentual', 'valor': '15', 'incide_em': 'primeira',
            'publico': 'todas', 'familia': 'irma_mesma_responsavel', 'quem_recebe': 'marcada',
        })

        regra = RegraDesconto.objects.get(nome='Irmãs')
        self.assertEqual(regra.quem_recebe, 'marcada')
        self.assertIn('recebe', regra.resumo())

    def test_quem_recebe_e_ignorado_em_regras_sem_familia(self):
        c = Client()
        c.force_login(User.objects.create_user('adm', email='a@x.com', password='x', is_staff=True))
        c.post(reverse('precos_admin:regra_nova'), {
            'nome': 'Geral', 'ativa': 'on', 'efeito': 'percentual', 'valor': '5', 'incide_em': 'todas',
            'publico': 'todas', 'familia': 'nenhuma', 'quem_recebe': 'marcada',
        })

        self.assertEqual(RegraDesconto.objects.get(nome='Geral').quem_recebe, 'automatico')


@ESTATICOS_SIMPLES
class ConferirRobustezTests(BaseAlunas):
    def setUp(self):
        super().setUp()
        self.c = Client()
        self.c.force_login(User.objects.create_user('adm', email='a@x.com', password='x', is_staff=True))

    def test_abrir_a_conferencia_nao_grava_nada(self):
        aluna = self.nova_aluna('Ana', [self.ballet], valor_mensalidade=D('100'))
        EntradaTurma.objects.all().delete()

        resposta = self.c.get(reverse('precos_admin:conferir') + '?ver=todas')

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'Ana')
        self.assertEqual(EntradaTurma.objects.count(), 0)
        self.assertFalse(PrecoAluna.objects.exists())

    def test_aluna_com_dado_estranho_nao_derruba_a_tela(self):
        self.nova_aluna('Ana', [self.ballet], valor_mensalidade=D('100'))
        bia = self.nova_aluna('Bia', [self.ballet], valor_mensalidade=D('100'))
        original = servico.calcular_para_aluna

        def quebra_na_bia(aluna, *args, **kwargs):
            if aluna.pk == bia.pk:
                raise ValueError('dado estranho')

            return original(aluna, *args, **kwargs)

        with mock.patch('precos.admin_views.servico.calcular_para_aluna', side_effect=quebra_na_bia):
            resposta = self.c.get(reverse('precos_admin:conferir') + '?ver=todas')

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'Ana')
        self.assertContains(resposta, 'erro ao calcular')
        self.assertContains(resposta, 'dado estranho')

    def test_numero_de_consultas_nao_explode_com_muitas_alunas(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        for i in range(30):
            self.nova_aluna(f'Aluna {i}', [self.ballet, self.jazz], valor_mensalidade=D('100'))

        with CaptureQueriesContext(connection) as consultas:
            self.c.get(reverse('precos_admin:conferir') + '?ver=todas')

        self.assertLess(len(consultas), 30 * 12)  # antes eram ~16 por aluna


    def test_mesma_conta_com_leitura_e_com_gravacao(self):
        velha = self.nova_aluna('Velha', [self.ballet], matricula=date(2025, 1, 1))
        nova = self.nova_aluna('Nova', [self.ballet, self.jazz], matricula=date(2026, 2, 1))

        for aluna in (velha, nova):
            lida = servico.calcular_para_aluna(
                Aluna.objects.prefetch_related('turmas', 'entradas_turma', 'grupos_desconto').get(pk=aluna.pk),
                escrever=False,
            )
            self.assertEqual(lida.total, servico.calcular_para_aluna(aluna).total)
