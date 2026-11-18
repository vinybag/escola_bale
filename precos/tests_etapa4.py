"""Etapa 4: desconto de família sobre o TOTAL das mensalidades do grupo de família."""

from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from usuarios.models import Aluna, Turma

from . import motor, servico
from .models import GrupoDesconto, PrecoAluna, RegraDesconto

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
        self.regra.grupo = outro
        self.regra.save()

        self.assertEqual(self.valor(self.alunas[0]), D('99'))

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
