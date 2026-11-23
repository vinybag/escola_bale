"""Etapa 4: desconto de família sobre o TOTAL das mensalidades do grupo de família."""

from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from usuarios.models import Aluna, Turma

from . import motor, servico
from .models import GrupoDesconto, PrecoAluna, RegraDesconto
from .tests import ESTATICOS_SIMPLES

D = Decimal
HOJE = timezone.localdate()


class Base(TestCase):
    def setUp(self):
        self.rep = User.objects.create_user('rep', email='r@x.com', password='x')
        self.balé = Turma.objects.create(nome='Ballet', valor_mensalidade=D('110'))
        self.vocal = Turma.objects.create(nome='Técnica vocal', valor_mensalidade=D('50'), regime_preco='fixo')
        self.golden = GrupoDesconto.objects.create(nome='Golden')
        RegraDesconto.objects.create(nome='Golden 10%', efeito='percentual', valor=D('10'), incide_em='todas')
        regra = RegraDesconto.objects.get(nome='Golden 10%')
        regra.grupo = self.golden
        regra.save()
        self.regra = RegraDesconto.objects.create(
            nome='Desconto família', efeito='percentual', valor=D('7.5'), incide_em='todas',
            familia='total_grupo_familia', minimo_integrantes=2, arredondar_total_para=D('1'),
        )
        self.familia = GrupoDesconto.objects.create(nome='Família', eh_familia=True, representante=self.rep)
        self.alunas = [self.nova(n) for n in ('A', 'B', 'C')]

    def nova(self, nome, turmas=None, manual=False, entrar=True):
        aluna = Aluna.objects.create(nome=nome, valor_mensalidade=D('1'), data_matricula=date(2025, 1, 1))
        aluna.turmas.set(turmas or [self.balé])
        PrecoAluna.objects.create(aluna=aluna, valor_manual=manual)
        self.golden.alunas.add(aluna)

        if entrar:
            self.familia.alunas.add(aluna)

        return aluna

    def valor(self, aluna):
        return servico.valor_para_mes(Aluna.objects.get(pk=aluna.pk), HOJE)


class RateioPuroTests(TestCase):
    def test_297_menos_7_5_arredonda_para_274_e_divide_em_centavos(self):
        total, partes = motor.ratear_familia([(D('99'), D('0'))] * 3, D('7.5'), D('1'))

        self.assertEqual(total, D('274'))
        self.assertEqual(partes, [D('91.33'), D('91.33'), D('91.34')])
        self.assertEqual(sum(partes), total)

    def test_parte_fixa_nao_recebe_desconto(self):
        total, partes = motor.ratear_familia([(D('99'), D('50')), (D('99'), D('0'))], D('10'), D('0.10'))

        self.assertEqual(total, D('228.20'))   # 50 + 198 × 0,90
        self.assertEqual(sum(partes), total)

    def test_soma_sempre_fecha_com_valores_desiguais(self):
        partes_in = [(D('99'), D('0')), (D('180.50'), D('50')), (D('33.33'), D('0')), (D('77'), D('0'))]
        total, partes = motor.ratear_familia(partes_in, D('7.5'), D('1'))

        self.assertEqual(sum(partes), total)
        self.assertTrue(all(p >= 0 for p in partes))


class FamiliaTests(Base):
    def test_tres_integrantes_golden_274_no_total(self):
        valores = [self.valor(a) for a in self.alunas]

        self.assertEqual(sum(valores), D('274'))
        self.assertEqual(valores, [D('91.33'), D('91.33'), D('91.34')])

    def test_cada_uma_continua_com_o_golden_sem_a_familia_no_cálculo_individual(self):
        resultado = servico.calcular_para_aluna(self.alunas[0])

        self.assertEqual(resultado.total, D('99'))

    def test_tecnica_vocal_fica_fora_do_desconto(self):
        self.alunas[0].turmas.add(self.vocal)

        valores = [self.valor(a) for a in self.alunas]

        # 3 × 99 = 297 com 7,5% = 274,72 ; + 50 da técnica vocal = 324,72 → 324
        self.assertEqual(sum(valores), D('324'))

    def test_so_a_partir_de_dois_integrantes(self):
        self.familia.alunas.remove(self.alunas[1], self.alunas[2])

        self.assertEqual(self.valor(self.alunas[0]), D('99'))

        self.familia.alunas.add(self.alunas[1])
        valores = [self.valor(a) for a in self.alunas[:2]]
        self.assertEqual(sum(valores), D('183'))   # 198 − 7,5% = 183,15

    def test_minimo_de_tres(self):
        self.regra.minimo_integrantes = 3
        self.regra.save()
        self.familia.alunas.remove(self.alunas[2])

        self.assertEqual([self.valor(a) for a in self.alunas[:2]], [D('99'), D('99')])

    def test_manual_fica_de_fora_e_mantem_o_valor_digitado(self):
        manual = self.nova('M', manual=True)
        manual.valor_mensalidade = D('120')
        manual.save()

        self.assertEqual(self.valor(manual), D('120'))
        self.assertEqual(sum(self.valor(a) for a in self.alunas), D('274'))

    def test_aluna_inativa_nao_entra_na_conta(self):
        Aluna.objects.filter(pk=self.alunas[2].pk).update(ativa=False)

        self.assertEqual(sum(self.valor(a) for a in self.alunas[:2]), D('183'))

    def test_grupo_sem_ser_de_familia_nao_recebe(self):
        self.familia.eh_familia = False
        self.familia.save()

        self.assertEqual(self.valor(self.alunas[0]), D('99'))

    def test_regra_desligada_ou_fora_do_periodo(self):
        self.regra.ativa = False
        self.regra.save()
        self.assertEqual(self.valor(self.alunas[0]), D('99'))

        self.regra.ativa = True
        self.regra.fim = date(2020, 1, 1)
        self.regra.save()
        self.assertEqual(self.valor(self.alunas[0]), D('99'))

    def test_regra_presa_a_outro_grupo_de_familia_nao_vale(self):
        outro = GrupoDesconto.objects.create(nome='Outra', eh_familia=True, representante=self.rep)
        self.regra.familias_desconto.set([outro])

        self.assertEqual(self.valor(self.alunas[0]), D('99'))

    def test_regra_marcada_para_esta_familia_vale(self):
        self.regra.familias_desconto.set([self.familia])

        self.assertEqual(sum(self.valor(a) for a in self.alunas), D('274'))

    def test_arredondamento_configuravel(self):
        self.regra.arredondar_total_para = D('0.10')
        self.regra.save()

        self.assertEqual(sum(self.valor(a) for a in self.alunas), D('274.70'))

    def test_atualizar_valores_grava_na_ficha(self):
        servico.atualizar_valores_da_familia(self.alunas[0])

        gravados = [Aluna.objects.get(pk=a.pk).valor_mensalidade for a in self.alunas]
        self.assertEqual(sum(gravados), D('274'))

    def test_valor_para_cobrar_atualiza_a_ficha(self):
        valor = servico.valor_para_cobrar(Aluna.objects.get(pk=self.alunas[2].pk), HOJE)

        self.assertEqual(Aluna.objects.get(pk=self.alunas[2].pk).valor_mensalidade, valor)

    def test_regra_de_total_nao_vira_desconto_individual(self):
        # sem grupo de família a regra não mexe em ninguém, mesmo marcada para todas
        self.familia.delete()

        self.assertEqual(self.valor(self.alunas[0]), D('99'))


@ESTATICOS_SIMPLES
class FormularioDaRegraTests(Base):
    def setUp(self):
        super().setUp()
        from django.test import Client
        from django.urls import reverse
        staff = User.objects.create_user('adm', password='x', is_staff=True)
        self.c = Client()
        self.c.force_login(staff)
        self.url = reverse('precos_admin:regra_nova')

    def dados(self, **extra):
        d = {'nome': 'Família nova', 'ativa': 'on', 'efeito': 'percentual', 'valor': '7,5', 'incide_em': 'todas',
             'publico': 'todas', 'familia': 'total_grupo_familia', 'quem_recebe': 'automatico',
             'minimo_integrantes': '2', 'arredondar_total_para': '1'}
        d.update(extra)
        return d

    def test_exige_marcar_a_familia(self):
        self.c.post(self.url, self.dados())

        self.assertFalse(RegraDesconto.objects.filter(nome='Família nova').exists())

    def test_salva_com_a_familia_marcada(self):
        self.c.post(self.url, self.dados(familias_desconto=[str(self.familia.pk)]))
        regra = RegraDesconto.objects.get(nome='Família nova')

        self.assertEqual(list(regra.familias_desconto.all()), [self.familia])
        self.assertIn('Família', regra.resumo())


class CombinacaoComFamiliaTests(Base):
    """Dança + ginástica = 100 cada; Golden paga 99 na dança; só a dança recebe o desconto de família."""

    def setUp(self):
        super().setUp()
        from .models import Combinacao, CombinacaoItem, CombinacaoPrecoGrupo
        self.ginastica = Turma.objects.create(nome='Ginástica', valor_mensalidade=D('120'))
        comb = Combinacao.objects.create(nome='Dança + ginástica')
        self.item_danca = CombinacaoItem.objects.create(combinacao=comb, nome='Dança', preco=D('100'), ordem=0)
        self.item_danca.turmas.set([self.balé])
        item_gin = CombinacaoItem.objects.create(combinacao=comb, nome='Ginástica', preco=D('100'), ordem=1)
        item_gin.turmas.set([self.ginastica])
        CombinacaoPrecoGrupo.objects.create(item=self.item_danca, grupo=self.golden, preco=D('99'))
        for a in self.alunas[:2]:
            Aluna.objects.filter(pk=a.pk).update()
        self.alunas[0].turmas.add(self.ginastica)

    def test_sem_marcar_ninguem_a_combinacao_fica_fora_do_desconto(self):
        # a aluna da combinação (99 + 100) não entra na base; as outras duas (2 × 99) sim:
        # 199 + 198 × 0,925 = 382,15 → 382
        self.assertEqual(sum(self.valor(a) for a in self.alunas), D('382'))

    def test_so_a_danca_recebe_o_desconto_da_familia(self):
        self.item_danca.aceita_desconto_familia = True
        self.item_danca.save()

        a0 = self.valor(self.alunas[0])
        total = sum(self.valor(a) for a in self.alunas)

        # base descontável: 3 × 99 = 297 → 274,72 ; + 100 da ginástica = 374,72 → 374
        self.assertEqual(total, D('374'))
        self.assertGreater(a0, D('100'))
        self.assertLess(a0, D('199'))


class EmSequenciaTests(Base):
    def setUp(self):
        super().setUp()
        self.regra.delete()  # sem desconto sobre o total: aqui o desconto é por aluna
        self.individual = RegraDesconto.objects.create(
            nome='Desconto família', efeito='percentual', valor=D('7.5'), incide_em='todas', grupo=self.familia,
        )

    def test_somando_o_valor_fica_em_90_70(self):
        self.assertEqual(servico.calcular_para_aluna(self.alunas[0]).total, D('90.70'))   # 110 − 11 − 8,25

    def test_em_sequencia_fica_em_91_50(self):
        self.individual.em_sequencia = True
        self.individual.save()
        resultado = servico.calcular_para_aluna(self.alunas[0])

        self.assertEqual(resultado.total, D('91.50'))    # 99 − 7,5% = 91,575
        self.assertTrue(resultado.linhas[0].descontos[-1].em_sequencia)

    def test_tecnica_vocal_continua_sem_desconto(self):
        self.individual.em_sequencia = True
        self.individual.save()
        self.alunas[0].turmas.add(self.vocal)

        self.assertEqual(servico.calcular_para_aluna(self.alunas[0]).total, D('141.50'))

    def test_duas_em_sequencia_e_uma_somada(self):
        outra = RegraDesconto.objects.create(
            nome='Extra', efeito='percentual', valor=D('10'), incide_em='todas', grupo=self.familia, em_sequencia=True,
        )
        self.individual.em_sequencia = True
        self.individual.save()
        self.assertEqual(outra.pk is not None, True)

        # 110 − 11 (Golden) = 99 ; −7,5% = 91,575 ; −10% = 82,4175
        self.assertEqual(servico.calcular_para_aluna(self.alunas[0]).total, D('82.40'))
