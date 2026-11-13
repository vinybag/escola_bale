"""
Testes do app de preços e descontos. Rodar com:  python manage.py test precos

Os casos 1, 2 e 3 são casos REAIS da escola (valor cheio de R$ 110 por turma).
"""

from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from usuarios.models import Aluna, Turma

from . import motor
from .models import (
    Combinacao, CombinacaoItem, CombinacaoPrecoGrupo, Configuracao, GrauParentesco, GrupoDesconto, RegraDesconto,
    formatar_moeda, formatar_percentual,
)
from .motor import Entrada, Familia

# Nos testes não há arquivos estáticos compilados (o projeto usa o armazenamento com manifesto).
ESTATICOS_SIMPLES = override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})

D = Decimal


class BaseRegras(TestCase):
    """Cria as turmas e as regras da escola exatamente como a dona descreveu."""

    def setUp(self):
        self.ballet = Turma.objects.create(nome='Ballet', valor_mensalidade=D('110'))
        self.jazz = Turma.objects.create(nome='Jazz', valor_mensalidade=D('110'))
        self.hiphop = Turma.objects.create(nome='Hip Hop', valor_mensalidade=D('100'))
        self.vocal = Turma.objects.create(nome='Técnica vocal', valor_mensalidade=D('50'), regime_preco='fixo')
        self.experimental = Turma.objects.create(nome='Aula experimental', tipo='aula_experimental')

        self.golden = GrupoDesconto.objects.create(nome='Golden')

        def regra(nome, valor, incide_em, **kw):
            return RegraDesconto.objects.create(nome=nome, valor=D(valor), incide_em=incide_em, **kw)

        self.r_golden = regra('Golden 1ª turma', 10, 'primeira', grupo=self.golden)
        self.r_segunda = regra('2ª modalidade', 15, 'segunda', publico='ja_aluna')
        self.r_segunda_nova = regra('2ª modalidade (aluna nova)', 10, 'segunda', publico='nova')
        self.r_terceira = regra('3ª modalidade', 20, 'terceira_em_diante', publico='ja_aluna')
        self.r_irma = regra('Irmã', 15, 'primeira', familia='irma_mesma_responsavel')
        self.r_irma.grupos_excecao.add(self.golden)  # Golden não recebe desconto de parentes
        self.r_campanha = regra(
            'Campanha novembro e dezembro', 50, 'segunda_em_diante', efeito='preco_fixo', publico='ja_aluna',
            inicio=date(2026, 11, 1), fim=date(2026, 12, 31),
            so_turmas_entradas_no_periodo=True, substitui_outros=True,
        )

    def calcular(self, entradas, **kw):
        kw.setdefault('quando', date(2026, 11, 12))

        return motor.calcular(entradas, **kw)

    def duas_turmas_da_aluna_antiga(self, segunda=None, data=date(2026, 1, 10)):
        """Ballet no primeiro cadastro + outra turma que entrou depois (a aluna já era aluna)."""
        return [Entrada(self.ballet), Entrada(segunda or self.jazz, data=data, apos_cadastro=True)]


class CasosReaisDaEscolaTests(BaseRegras):
    def test_caso_1_golden_com_segunda_turma_paga_192_50(self):
        resultado = self.calcular(self.duas_turmas_da_aluna_antiga(), grupos={self.golden.pk})

        self.assertEqual(resultado.total, D('192.50'))

    def test_caso_2_irma_com_segunda_turma_paga_187(self):
        resultado = self.calcular(self.duas_turmas_da_aluna_antiga(), familia=Familia(irma_anterior=True))

        self.assertEqual(resultado.total, D('187.00'))

    def test_caso_3_segunda_turma_sem_outros_descontos_paga_203_50(self):
        resultado = self.calcular(self.duas_turmas_da_aluna_antiga())

        self.assertEqual(resultado.total, D('203.50'))

    def test_dois_descontos_na_mesma_turma_sao_somados_e_nao_aplicados_em_cascata(self):
        # Irmã também na 2ª turma: 15% + 15% sobre o valor cheio de 110 = R$ 33,00 de desconto.
        # Em cascata (15% e depois 15% do que sobrou) a turma ficaria em 79,475.
        irma_na_segunda = RegraDesconto.objects.create(
            nome='Irmã na 2ª', valor=D('15'), incide_em='segunda', familia='irma_mesma_responsavel',
        )
        resultado = self.calcular(
            self.duas_turmas_da_aluna_antiga(), familia=Familia(irma_anterior=True),
            regras=[self.r_segunda, irma_na_segunda],
        )

        self.assertEqual(resultado.linhas[1].final, D('77.00'))
        self.assertEqual(resultado.total, D('187.00'))

    def test_golden_com_os_dois_descontos_na_mesma_turma_tambem_soma(self):
        # Se o Golden fosse configurado na 2ª turma: 10% + 15% de 110 = 27,50 -> 82,50 (e a 1ª fica cheia).
        golden_na_segunda = RegraDesconto.objects.create(nome='Golden na 2ª', valor=D('10'), incide_em='segunda', grupo=self.golden)
        resultado = self.calcular(
            self.duas_turmas_da_aluna_antiga(), grupos={self.golden.pk}, regras=[self.r_segunda, golden_na_segunda],
        )

        self.assertEqual(resultado.total, D('192.50'))

    def test_golden_nao_recebe_desconto_de_parentes_nem_de_irmas(self):
        resultado = self.calcular(
            self.duas_turmas_da_aluna_antiga(), grupos={self.golden.pk}, familia=Familia(irma_anterior=True),
        )

        self.assertEqual(resultado.total, D('192.50'))  # igual ao caso 1: a regra da irmã não entra

    def test_golden_com_uma_turma_so_recebe_o_desconto_sobre_essa_turma(self):
        resultado = self.calcular([Entrada(self.ballet)], grupos={self.golden.pk})

        self.assertEqual(resultado.total, D('99.00'))

    def test_irma_com_uma_turma_so_recebe_o_desconto_sobre_essa_turma(self):
        resultado = self.calcular([Entrada(self.ballet)], familia=Familia(irma_anterior=True))

        self.assertEqual(resultado.total, D('93.50'))

    def test_mostra_o_passo_a_passo(self):
        resultado = self.calcular(self.duas_turmas_da_aluna_antiga(), grupos={self.golden.pk})
        primeira, segunda = resultado.linhas

        self.assertEqual((primeira.posicao, primeira.final), (1, D('99.00')))
        self.assertEqual([d.nome for d in primeira.descontos], ['Golden 1ª turma'])
        self.assertEqual((segunda.posicao, segunda.final), (2, D('93.50')))
        self.assertEqual([d.nome for d in segunda.descontos], ['2ª modalidade'])


class CampanhaTests(BaseRegras):
    def test_durante_a_campanha_a_turma_extra_custa_50(self):
        entradas = self.duas_turmas_da_aluna_antiga(data=date(2026, 11, 10))
        resultado = self.calcular(entradas, quando=date(2026, 11, 12))

        self.assertEqual(resultado.total, D('160.00'))  # 110 + 50
        self.assertEqual(resultado.linhas[1].final, D('50'))

    def test_a_campanha_nao_soma_golden_nem_irma_na_turma_da_campanha(self):
        entradas = self.duas_turmas_da_aluna_antiga(data=date(2026, 11, 10))
        resultado = self.calcular(entradas, grupos={self.golden.pk})

        self.assertEqual(resultado.linhas[0].final, D('99.00'))   # a 1ª turma segue com o Golden
        self.assertEqual(resultado.linhas[1].final, D('50'))      # a da campanha: R$ 50 e pronto

    def test_depois_da_campanha_volta_ao_valor_normal_com_desconto_de_segunda_turma(self):
        entradas = self.duas_turmas_da_aluna_antiga(data=date(2026, 11, 10))

        self.assertEqual(self.calcular(entradas, quando=date(2026, 12, 31)).total, D('160.00'))
        self.assertEqual(self.calcular(entradas, quando=date(2027, 1, 1)).total, D('203.50'))

    def test_cada_turma_extra_da_campanha_custa_50(self):
        entradas = self.duas_turmas_da_aluna_antiga(data=date(2026, 11, 10))
        entradas.append(Entrada(self.hiphop, data=date(2026, 11, 20), apos_cadastro=True))

        self.assertEqual(self.calcular(entradas).total, D('210.00'))  # 110 + 50 + 50

    def test_turma_em_que_entrou_antes_da_campanha_nao_ganha_o_preco_da_campanha(self):
        entradas = self.duas_turmas_da_aluna_antiga(data=date(2026, 9, 1))

        self.assertEqual(self.calcular(entradas).total, D('203.50'))

    def test_campanha_so_para_quem_ja_e_aluna(self):
        # As duas turmas foram escolhidas no primeiro cadastro: aluna nova, vale o desconto menor.
        entradas = [Entrada(self.ballet), Entrada(self.jazz, data=date(2026, 11, 10))]

        self.assertEqual(self.calcular(entradas).total, D('209.00'))  # 110 + 99 (10% de 110)

    def test_regra_desligada_nao_vale(self):
        RegraDesconto.objects.filter(pk=self.r_campanha.pk).update(ativa=False)
        entradas = self.duas_turmas_da_aluna_antiga(data=date(2026, 11, 10))

        self.assertEqual(self.calcular(entradas).total, D('203.50'))


class TurmasEspeciaisTests(BaseRegras):
    def test_turma_de_preco_fixo_nao_recebe_nenhum_desconto(self):
        resultado = self.calcular(
            [Entrada(self.ballet), Entrada(self.vocal, apos_cadastro=True)],
            grupos={self.golden.pk}, familia=Familia(irma_anterior=True),
        )
        vocal = resultado.linhas[1]

        self.assertEqual(vocal.final, D('50'))
        self.assertEqual(vocal.descontos, [])
        self.assertIsNone(vocal.posicao)

    def test_turma_de_preco_fixo_nao_conta_como_modalidade(self):
        # Ballet + Técnica vocal + Jazz: o Jazz é a 2ª modalidade (a vocal não conta).
        resultado = self.calcular([
            Entrada(self.ballet), Entrada(self.vocal, apos_cadastro=True),
            Entrada(self.jazz, data=date(2026, 3, 1), apos_cadastro=True),
        ])

        self.assertEqual([linha.posicao for linha in resultado.linhas], [1, None, 2])
        self.assertEqual(resultado.total, D('253.50'))  # 110 + 50 + 93,50

    def test_preco_fixo_que_conta_como_modalidade(self):
        Turma.objects.filter(pk=self.vocal.pk).update(regime_preco='fixo_conta')
        self.vocal.refresh_from_db()
        resultado = self.calcular([
            Entrada(self.ballet), Entrada(self.vocal, apos_cadastro=True),
            Entrada(self.jazz, data=date(2026, 3, 1), apos_cadastro=True),
        ])

        self.assertEqual([linha.posicao for linha in resultado.linhas], [1, 2, 3])
        self.assertEqual(resultado.linhas[1].final, D('50'))   # a vocal continua sem desconto
        self.assertEqual(resultado.linhas[2].final, D('88.00'))  # Jazz é a 3ª: 20% de 110

    def test_turma_sem_valor_cadastrado_avisa_e_nao_fecha_o_calculo(self):
        resultado = self.calcular([Entrada(self.experimental)])

        self.assertFalse(resultado.ok)
        self.assertIn('não tem valor', resultado.avisos[0])

    def test_sem_turmas_nao_fecha_o_calculo(self):
        self.assertFalse(self.calcular([]).ok)


class RegrasDeAplicacaoTests(BaseRegras):
    def test_terceira_turma_usa_o_desconto_de_quem_ja_e_aluna_e_a_segunda_continua_como_nova(self):
        # Ballet e Jazz no primeiro cadastro (2ª = aluna nova, 10%); depois entrou no Hip Hop (3ª, 20%).
        entradas = [
            Entrada(self.ballet), Entrada(self.jazz),
            Entrada(self.hiphop, data=date(2026, 3, 1), apos_cadastro=True),
        ]
        resultado = self.calcular(entradas)

        self.assertEqual([linha.final for linha in resultado.linhas], [D('110'), D('99.00'), D('80.00')])
        self.assertEqual(resultado.total, D('289.00'))

    def test_regra_de_grupo_so_vale_para_quem_esta_no_grupo(self):
        self.assertEqual(self.calcular([Entrada(self.ballet)]).total, D('110.00'))
        self.assertEqual(self.calcular([Entrada(self.ballet)], grupos={self.golden.pk}).total, D('99.00'))

    def test_regra_restrita_a_turmas_so_vale_nelas(self):
        regra = RegraDesconto.objects.create(nome='Só no Jazz', valor=D('50'), incide_em='todas')
        regra.turmas.add(self.jazz)
        entradas = [Entrada(self.ballet), Entrada(self.jazz)]
        resultado = self.calcular(entradas, regras=[regra])

        self.assertEqual([linha.final for linha in resultado.linhas], [D('110'), D('55.00')])

    def test_regra_fora_do_periodo_nao_vale(self):
        regra = RegraDesconto.objects.create(
            nome='Janeiro', valor=D('10'), incide_em='todas', inicio=date(2027, 1, 1), fim=date(2027, 1, 31),
        )

        self.assertEqual(self.calcular([Entrada(self.ballet)], regras=[regra], quando=date(2026, 12, 31)).total, D('110.00'))
        self.assertEqual(self.calcular([Entrada(self.ballet)], regras=[regra], quando=date(2027, 1, 15)).total, D('99.00'))

    def test_parentesco_marcado_na_ficha(self):
        prima = GrauParentesco.objects.create(nome='Prima')
        regra = RegraDesconto.objects.create(nome='Prima', valor=D('10'), incide_em='primeira', familia='parentesco', grau=prima)

        com = self.calcular([Entrada(self.ballet)], regras=[regra], familia=Familia(graus=frozenset({prima.pk})))
        sem = self.calcular([Entrada(self.ballet)], regras=[regra])

        self.assertEqual((com.total, sem.total), (D('99.00'), D('110.00')))

    def test_responsavel_que_tambem_e_aluna_so_ela_recebe(self):
        regra = RegraDesconto.objects.create(nome='Mãe aluna', valor=D('10'), incide_em='primeira', familia='responsavel_aluna')

        self.assertEqual(self.calcular([Entrada(self.ballet)], regras=[regra], familia=Familia(responsavel_aluna=True)).total, D('99.00'))
        self.assertEqual(self.calcular([Entrada(self.ballet)], regras=[regra]).total, D('110.00'))

    def test_arredondamento_e_para_baixo_de_10_em_10_centavos(self):
        regra = RegraDesconto.objects.create(nome='33,33%', valor=D('33.33'), incide_em='segunda')
        resultado = self.calcular(self.duas_turmas_da_aluna_antiga(), regras=[regra])

        self.assertEqual(resultado.total_exato, D('183.3370'))
        self.assertEqual(resultado.total, D('183.30'))
        self.assertEqual(resultado.ajuste_arredondamento, D('0.0370'))

    def test_passo_de_arredondamento_e_configuravel(self):
        resultado = self.calcular([Entrada(self.ballet)], regras=[], passo=D('5'))
        self.assertEqual(resultado.total, D('110'))

        regra = RegraDesconto.objects.create(nome='7%', valor=D('7'), incide_em='primeira')
        self.assertEqual(self.calcular([Entrada(self.ballet)], regras=[regra], passo=D('5')).total, D('100'))
        self.assertEqual(self.calcular([Entrada(self.ballet)], regras=[regra], passo=D('0.01')).total, D('102.30'))

    def test_desconto_nunca_deixa_a_turma_negativa(self):
        regras = [
            RegraDesconto.objects.create(nome='80%', valor=D('80'), incide_em='primeira'),
            RegraDesconto.objects.create(nome='50%', valor=D('50'), incide_em='primeira'),
        ]

        self.assertEqual(self.calcular([Entrada(self.ballet)], regras=regras).total, D('0.00'))

    def test_formatacao(self):
        self.assertEqual(formatar_moeda(D('1250')), 'R$ 1.250,00')
        self.assertEqual(formatar_moeda(D('93.5')), 'R$ 93,50')
        self.assertEqual(formatar_percentual(D('15.00')), '15%')
        self.assertEqual(formatar_percentual(D('33.50')), '33,5%')

    def test_resumo_da_regra_em_portugues(self):
        self.assertEqual(
            self.r_campanha.resumo(),
            'Turma custa R$ 50,00 · da 2ª turma em diante · só se já era aluna · de 01/11/2026 a 31/12/2026 · sem outros descontos',
        )
        self.assertEqual(self.r_golden.resumo(), '10% de desconto · na 1ª turma · grupo Golden')


class CombinacaoTests(BaseRegras):
    """Balé + ginástica: cada turma custa R$ 100 (R$ 200 no total); a Golden paga R$ 99 no balé (R$ 199)."""

    def setUp(self):
        super().setUp()
        self.ginastica = Turma.objects.create(nome='Ginástica Artística', valor_mensalidade=D('120'))
        self.ballet2 = Turma.objects.create(nome='Ballet Juvenil', valor_mensalidade=D('110'))

        self.combo = Combinacao.objects.create(nome='Balé + Ginástica')
        self.item_bale = CombinacaoItem.objects.create(combinacao=self.combo, nome='Balé', preco=D('100'), ordem=0)
        self.item_bale.turmas.add(self.ballet, self.ballet2)
        self.item_gin = CombinacaoItem.objects.create(combinacao=self.combo, nome='Ginástica', preco=D('100'), ordem=1)
        self.item_gin.turmas.add(self.ginastica)
        CombinacaoPrecoGrupo.objects.create(item=self.item_bale, grupo=self.golden, preco=D('99'))

    def bale_e_ginastica(self, bale=None):
        return [Entrada(bale or self.ballet), Entrada(self.ginastica, data=date(2026, 3, 1), apos_cadastro=True)]

    def ginastica_e_bale(self, bale=None):
        return [Entrada(self.ginastica), Entrada(bale or self.ballet, data=date(2026, 3, 1), apos_cadastro=True)]

    def test_sem_golden_as_duas_juntas_pagam_200(self):
        self.assertEqual(self.calcular(self.bale_e_ginastica()).total, D('200.00'))

    def test_a_ordem_de_entrada_nao_muda_o_valor(self):
        self.assertEqual(self.calcular(self.ginastica_e_bale()).total, D('200.00'))

    def test_golden_paga_199_em_qualquer_ordem(self):
        for entradas in (self.bale_e_ginastica(), self.ginastica_e_bale()):
            resultado = self.calcular(entradas, grupos={self.golden.pk})
            finais = {linha.nome: linha.final for linha in resultado.linhas}

            self.assertEqual(resultado.total, D('199.00'))
            self.assertEqual(finais, {'Ballet': D('99'), 'Ginástica Artística': D('100')})

    def test_vale_para_qualquer_turma_de_bale(self):
        self.assertEqual(self.calcular(self.bale_e_ginastica(self.ballet2)).total, D('200.00'))
        self.assertEqual(self.calcular(self.bale_e_ginastica(self.ballet2), grupos={self.golden.pk}).total, D('199.00'))

    def test_so_uma_turma_do_par_nao_ganha_a_combinacao(self):
        self.assertEqual(self.calcular([Entrada(self.ballet)]).total, D('110.00'))
        self.assertEqual(self.calcular([Entrada(self.ginastica)]).total, D('120.00'))
        # ginástica + jazz não é a combinação: segue o desconto normal de 2ª modalidade
        resultado = self.calcular([Entrada(self.ginastica), Entrada(self.jazz, data=date(2026, 3, 1), apos_cadastro=True)])
        self.assertEqual(resultado.total, D('213.50'))

    def test_o_par_conta_como_uma_modalidade_e_a_terceira_turma_vira_a_segunda(self):
        entradas = self.bale_e_ginastica() + [Entrada(self.jazz, data=date(2026, 3, 2), apos_cadastro=True)]
        resultado = self.calcular(entradas)

        self.assertEqual([linha.posicao for linha in resultado.linhas], [1, 1, 2])
        self.assertEqual(resultado.linhas[2].final, D('93.50'))  # desconto de 2ª modalidade (15%)
        self.assertEqual(resultado.total, D('293.50'))
        self.assertEqual(self.calcular(entradas, grupos={self.golden.pk}).total, D('292.50'))

    def test_turmas_da_combinacao_nao_recebem_outros_descontos(self):
        resultado = self.calcular(self.bale_e_ginastica(), familia=Familia(irma_anterior=True))

        self.assertEqual(resultado.total, D('200.00'))  # a regra da irmã não mexe nas turmas do par
        self.assertTrue(all(linha.combinacao == 'Balé + Ginástica' for linha in resultado.linhas))

    def test_campanha_nao_vale_para_turma_da_combinacao(self):
        entradas = [Entrada(self.ballet), Entrada(self.ginastica, data=date(2026, 11, 10), apos_cadastro=True)]

        self.assertEqual(self.calcular(entradas, quando=date(2026, 11, 12)).total, D('200.00'))

    def test_duas_turmas_de_bale_com_ginastica_usa_a_primeira_no_par(self):
        entradas = [
            Entrada(self.ballet), Entrada(self.ginastica, data=date(2026, 3, 1), apos_cadastro=True),
            Entrada(self.ballet2, data=date(2026, 3, 2), apos_cadastro=True),
        ]
        resultado = self.calcular(entradas)

        self.assertEqual([linha.final for linha in resultado.linhas], [D('100'), D('100'), D('93.50')])
        self.assertEqual(resultado.total, D('293.50'))

    def test_combinacao_desligada_ou_fora_do_periodo_nao_vale(self):
        Combinacao.objects.filter(pk=self.combo.pk).update(ativa=False)
        self.assertEqual(self.calcular(self.bale_e_ginastica()).total, D('212.00'))  # 110 + 15% de desconto na 120

        Combinacao.objects.filter(pk=self.combo.pk).update(ativa=True, inicio=date(2027, 1, 1))
        self.assertEqual(self.calcular(self.bale_e_ginastica()).total, D('212.00'))
        self.assertEqual(self.calcular(self.bale_e_ginastica(), quando=date(2027, 2, 1)).total, D('200.00'))

    def test_turma_de_preco_fixo_nunca_entra_em_combinacao(self):
        item_vocal = CombinacaoItem.objects.create(combinacao=self.combo, nome='Vocal', preco=D('10'), ordem=2)
        item_vocal.turmas.add(self.vocal)

        # Com 3 itens a combinação exige as 3 turmas; a vocal (preço fixo) nunca conta, então não fecha:
        self.assertEqual(self.calcular(self.bale_e_ginastica()).total, D('212.00'))  # preço normal: 110 + 120 com 15%
        self.assertEqual(self.calcular(self.bale_e_ginastica() + [Entrada(self.vocal)]).total, D('212.00') + D('50'))

    def test_resumo_da_combinacao(self):
        self.assertEqual(self.combo.resumo(), 'Balé R$ 100,00 + Ginástica R$ 100,00 · Golden: Balé R$ 99,00')


@ESTATICOS_SIMPLES
class TelasBase(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user('adm', email='a@x.com', password='x', is_staff=True)
        self.leigo = User.objects.create_user('leigo', email='l@x.com', password='x')
        self.admin = Client()
        self.admin.force_login(self.staff)
        self.familia = Client()
        self.familia.force_login(self.leigo)

        self.ballet = Turma.objects.create(nome='Ballet', valor_mensalidade=D('110'))
        self.jazz = Turma.objects.create(nome='Jazz', valor_mensalidade=D('110'))

    def dados_regra(self, **extra):
        dados = {
            'nome': '2ª modalidade', 'efeito': 'percentual', 'valor': '15', 'incide_em': 'segunda',
            'publico': 'ja_aluna', 'familia': 'nenhuma', 'ativa': 'on',
        }
        dados.update(extra)

        return dados


class AcessoTests(TelasBase):
    def test_so_admin_acessa(self):
        for nome in ('regras', 'regra_nova', 'grupos', 'graus', 'simulador', 'configuracao'):
            self.assertEqual(self.admin.get(reverse(f'precos_admin:{nome}')).status_code, 200, nome)
            self.assertEqual(self.familia.get(reverse(f'precos_admin:{nome}')).status_code, 302, nome)
            self.assertEqual(Client().get(reverse(f'precos_admin:{nome}')).status_code, 302, nome)

    def test_menu_do_admin_tem_o_item(self):
        html = self.admin.get(reverse('admin_dashboard:dashboard')).content.decode()

        self.assertIn('Preços e descontos', html)
        self.assertIn(reverse('precos_admin:regras'), html)


class RegrasTelaTests(TelasBase):
    def test_criar_regra_de_porcentagem(self):
        r = self.admin.post(reverse('precos_admin:regra_nova'), self.dados_regra())
        regra = RegraDesconto.objects.get()

        self.assertEqual(r.status_code, 302)
        self.assertEqual((regra.nome, regra.valor, regra.incide_em, regra.publico), ('2ª modalidade', D('15'), 'segunda', 'ja_aluna'))

    def test_criar_campanha_de_preco_fixo_com_periodo(self):
        self.admin.post(reverse('precos_admin:regra_nova'), self.dados_regra(
            nome='Campanha', efeito='preco_fixo', valor='50', incide_em='segunda_em_diante', inicio='2026-11-01', fim='2026-12-31',
            so_turmas_entradas_no_periodo='on', substitui_outros='on',
        ))
        regra = RegraDesconto.objects.get()

        self.assertEqual((regra.efeito, regra.valor, regra.inicio, regra.fim), ('preco_fixo', D('50'), date(2026, 11, 1), date(2026, 12, 31)))
        self.assertTrue(regra.so_turmas_entradas_no_periodo and regra.substitui_outros)

    def test_regra_com_grupo_excecao_e_turmas(self):
        golden = GrupoDesconto.objects.create(nome='Golden')
        self.admin.post(reverse('precos_admin:regra_nova'), self.dados_regra(
            nome='Irmã', incide_em='primeira', familia='irma_mesma_responsavel', grupos_excecao=[golden.pk], turmas=[self.jazz.pk],
        ))
        regra = RegraDesconto.objects.get()

        self.assertEqual([g.pk for g in regra.grupos_excecao.all()], [golden.pk])
        self.assertEqual([t.pk for t in regra.turmas.all()], [self.jazz.pk])

    def test_valores_invalidos_nao_criam_a_regra(self):
        invalidos = [
            {'nome': ''}, {'valor': ''}, {'valor': '0'}, {'valor': 'abc'}, {'valor': '150'},
            {'inicio': '2026-12-31', 'fim': '2026-11-01'}, {'so_turmas_entradas_no_periodo': 'on'},
            {'familia': 'parentesco'}, {'efeito': 'xyz'},
        ]

        for extra in invalidos:
            self.admin.post(reverse('precos_admin:regra_nova'), self.dados_regra(**extra))

        self.assertEqual(RegraDesconto.objects.count(), 0)

    def test_valor_em_reais_pode_passar_de_100(self):
        self.admin.post(reverse('precos_admin:regra_nova'), self.dados_regra(efeito='preco_fixo', valor='150'))

        self.assertEqual(RegraDesconto.objects.get().valor, D('150'))

    def test_valor_com_virgula(self):
        self.admin.post(reverse('precos_admin:regra_nova'), self.dados_regra(valor='12,5'))

        self.assertEqual(RegraDesconto.objects.get().valor, D('12.5'))

    def test_editar_regra(self):
        regra = RegraDesconto.objects.create(nome='Antiga', valor=D('10'), incide_em='primeira')
        r = self.admin.get(reverse('precos_admin:regra_editar', args=[regra.pk]))

        self.assertContains(r, 'value="Antiga"')

        self.admin.post(reverse('precos_admin:regra_editar', args=[regra.pk]), self.dados_regra(nome='Nova', valor='20'))
        regra.refresh_from_db()

        self.assertEqual((regra.nome, regra.valor), ('Nova', D('20')))

    def test_ligar_desligar_e_excluir(self):
        regra = RegraDesconto.objects.create(nome='Teste', valor=D('10'), incide_em='primeira')

        self.admin.post(reverse('precos_admin:regra_alternar', args=[regra.pk]))
        regra.refresh_from_db()
        self.assertFalse(regra.ativa)

        self.admin.post(reverse('precos_admin:regra_alternar', args=[regra.pk]))
        regra.refresh_from_db()
        self.assertTrue(regra.ativa)

        self.admin.post(reverse('precos_admin:regra_excluir', args=[regra.pk]))
        self.assertFalse(RegraDesconto.objects.exists())

    def test_alterar_e_excluir_exigem_post(self):
        regra = RegraDesconto.objects.create(nome='Teste', valor=D('10'), incide_em='primeira')

        self.assertEqual(self.admin.get(reverse('precos_admin:regra_excluir', args=[regra.pk])).status_code, 405)
        self.assertEqual(self.admin.get(reverse('precos_admin:regra_alternar', args=[regra.pk])).status_code, 405)
        self.assertTrue(RegraDesconto.objects.exists())

    def test_lista_mostra_resumo_e_situacao(self):
        RegraDesconto.objects.create(nome='Campanha antiga', valor=D('50'), incide_em='segunda', efeito='preco_fixo', fim=date(2020, 1, 1))
        RegraDesconto.objects.create(nome='Desligada', valor=D('10'), incide_em='primeira', ativa=False)
        html = self.admin.get(reverse('precos_admin:regras')).content.decode()

        self.assertIn('Encerrada', html)
        self.assertIn('Desligada', html)
        self.assertIn('Turma custa R$ 50,00', html)

    def test_aviso_de_turma_sem_valor(self):
        Turma.objects.create(nome='Sem valor')

        self.assertContains(self.admin.get(reverse('precos_admin:regras')), '1 turma sem valor')


class GruposEParentescosTests(TelasBase):
    def test_criar_grupo_e_gerenciar_membros(self):
        a1 = Aluna.objects.create(nome='Ana', tipo_aluna='infantil')
        a2 = Aluna.objects.create(nome='Bia', tipo_aluna='infantil')

        r = self.admin.post(reverse('precos_admin:grupos'), {'nome': 'Golden', 'descricao': 'Desde 2024'})
        grupo = GrupoDesconto.objects.get()
        self.assertEqual(r.status_code, 302)

        self.admin.post(reverse('precos_admin:grupo_detalhe', args=[grupo.pk]), {'acao': 'adicionar', 'alunas': [a1.pk, a2.pk]})
        self.assertEqual(set(grupo.alunas.all()), {a1, a2})

        self.admin.post(reverse('precos_admin:grupo_detalhe', args=[grupo.pk]), {'acao': 'remover', 'aluna': a1.pk})
        self.assertEqual(list(grupo.alunas.all()), [a2])

    def test_grupo_com_nome_repetido_e_vazio_nao_e_criado(self):
        GrupoDesconto.objects.create(nome='Golden')
        self.admin.post(reverse('precos_admin:grupos'), {'nome': 'golden'})
        self.admin.post(reverse('precos_admin:grupos'), {'nome': ''})

        self.assertEqual(GrupoDesconto.objects.count(), 1)

    def test_excluir_grupo_exclui_as_regras_dele(self):
        grupo = GrupoDesconto.objects.create(nome='Golden')
        RegraDesconto.objects.create(nome='Golden 10%', valor=D('10'), incide_em='primeira', grupo=grupo)
        html = self.admin.get(reverse('precos_admin:grupo_detalhe', args=[grupo.pk])).content.decode()

        self.assertIn('Golden 10%', html)  # a tela avisa quais regras vão junto

        self.admin.post(reverse('precos_admin:grupo_detalhe', args=[grupo.pk]), {'acao': 'excluir'})
        self.assertFalse(GrupoDesconto.objects.exists())
        self.assertFalse(RegraDesconto.objects.exists())

    def test_desligar_o_grupo(self):
        grupo = GrupoDesconto.objects.create(nome='Golden')
        self.admin.post(reverse('precos_admin:grupo_detalhe', args=[grupo.pk]), {'acao': 'salvar', 'nome': 'Golden'})
        grupo.refresh_from_db()

        self.assertFalse(grupo.ativo)  # sem a caixa "ativo" marcada

    def test_graus_de_parentesco(self):
        self.admin.post(reverse('precos_admin:graus'), {'acao': 'criar', 'nome': 'Prima'})
        self.admin.post(reverse('precos_admin:graus'), {'acao': 'criar', 'nome': 'prima'})
        self.assertEqual(GrauParentesco.objects.count(), 1)

        grau = GrauParentesco.objects.get()
        self.admin.post(reverse('precos_admin:graus'), {'acao': 'excluir', 'id': grau.pk})
        self.assertFalse(GrauParentesco.objects.exists())


class ConfiguracaoESimuladorTests(TelasBase):
    def test_configurar_arredondamento(self):
        self.admin.post(reverse('precos_admin:configuracao'), {'passo_arredondamento': '0,50'})
        self.assertEqual(Configuracao.atual().passo_arredondamento, D('0.50'))

        for invalido in ('0', '-1', 'abc', '', '500'):
            self.admin.post(reverse('precos_admin:configuracao'), {'passo_arredondamento': invalido})

        self.assertEqual(Configuracao.atual().passo_arredondamento, D('0.50'))

    def test_arredondamento_padrao_e_10_centavos(self):
        self.assertEqual(Configuracao.atual().passo_arredondamento, D('0.10'))

    def test_simulador_calcula_o_caso_do_golden(self):
        golden = GrupoDesconto.objects.create(nome='Golden')
        RegraDesconto.objects.create(nome='Golden', valor=D('10'), incide_em='primeira', grupo=golden)
        RegraDesconto.objects.create(nome='2ª', valor=D('15'), incide_em='segunda', publico='ja_aluna')

        r = self.admin.post(reverse('precos_admin:simulador'), {
            'turma_1': self.ballet.pk, 'apos_1': '0', 'turma_2': self.jazz.pk, 'apos_2': '1', 'data_2': '2026-03-01',
            'grupos': [golden.pk], 'quando': '2026-11-12',
        })

        self.assertContains(r, 'R$ 192,50')
        self.assertContains(r, 'Golden (10%)')

    def test_simulador_nao_grava_nada(self):
        self.admin.post(reverse('precos_admin:simulador'), {'turma_1': self.ballet.pk, 'quando': '2026-11-12'})

        self.assertEqual(Aluna.objects.count(), 0)

    def test_simulador_sem_turmas_avisa(self):
        self.assertContains(self.admin.post(reverse('precos_admin:simulador'), {'quando': '2026-11-12'}), 'Nenhuma turma informada')


class PrecoNaTurmaTests(TelasBase):
    def dados_turma(self, **extra):
        dados = {'nome': 'Nova Turma', 'capacidade_maxima': '20', 'ativa': 'on', 'valor_mensalidade': '110,50', 'regime_preco': 'normal'}
        dados.update(extra)

        return dados

    def test_formularios_mostram_os_campos(self):
        turma = Turma.objects.create(nome='Vocal', valor_mensalidade=D('50'), regime_preco='fixo')

        self.assertContains(self.admin.get(reverse('admin_dashboard:turma_criar')), 'name="valor_mensalidade"')
        editar = self.admin.get(reverse('admin_dashboard:turma_editar', args=[turma.pk]))
        self.assertContains(editar, 'value="50,00"')
        self.assertContains(editar, 'Preço fixo (não recebe descontos e não conta como modalidade)')

    def test_criar_turma_com_preco(self):
        self.admin.post(reverse('admin_dashboard:turma_criar'), self.dados_turma())
        turma = Turma.objects.get(nome='Nova Turma')

        self.assertEqual((turma.valor_mensalidade, turma.regime_preco), (D('110.50'), 'normal'))

    def test_criar_turma_de_preco_fixo(self):
        self.admin.post(reverse('admin_dashboard:turma_criar'), self.dados_turma(nome='Vocal', valor_mensalidade='50', regime_preco='fixo'))

        self.assertEqual(Turma.objects.get(nome='Vocal').regime_preco, 'fixo')

    def test_editar_preco_da_turma(self):
        self.admin.post(reverse('admin_dashboard:turma_editar', args=[self.ballet.pk]), self.dados_turma(nome='Ballet', valor_mensalidade='125'))
        self.ballet.refresh_from_db()

        self.assertEqual(self.ballet.valor_mensalidade, D('125'))

    def test_valor_invalido_nao_grava(self):
        n = Turma.objects.count()
        self.admin.post(reverse('admin_dashboard:turma_criar'), self.dados_turma(valor_mensalidade='abc'))
        self.admin.post(reverse('admin_dashboard:turma_editar', args=[self.ballet.pk]), self.dados_turma(nome='Ballet', valor_mensalidade='-5'))
        self.ballet.refresh_from_db()

        self.assertEqual(Turma.objects.count(), n)
        self.assertEqual(self.ballet.valor_mensalidade, D('110'))

    def test_valor_em_branco_deixa_a_turma_sem_preco(self):
        self.admin.post(reverse('admin_dashboard:turma_editar', args=[self.ballet.pk]), self.dados_turma(nome='Ballet', valor_mensalidade=''))
        self.ballet.refresh_from_db()

        self.assertIsNone(self.ballet.valor_mensalidade)


class CombinacaoTelaTests(TelasBase):
    def setUp(self):
        super().setUp()
        self.ballet2 = Turma.objects.create(nome='Ballet Juvenil', valor_mensalidade=D('110'))
        self.ginastica = Turma.objects.create(nome='Ginástica Artística', valor_mensalidade=D('120'))
        self.golden = GrupoDesconto.objects.create(nome='Golden')

    def dados_combinacao(self, **extra):
        dados = {
            'nome': 'Balé + Ginástica', 'ativa': 'on',
            'item_1_nome': 'Balé', 'item_1_preco': '100', 'item_1_turmas': [self.ballet.pk, self.ballet2.pk],
            'item_2_nome': 'Ginástica', 'item_2_preco': '100', 'item_2_turmas': [self.ginastica.pk],
            f'grupo_{self.golden.pk}_item_1': '99',
        }
        dados.update(extra)

        return dados

    def test_criar_a_combinacao_da_escola(self):
        r = self.admin.post(reverse('precos_admin:combinacao_nova'), self.dados_combinacao())
        combinacao = Combinacao.objects.get()
        bale, gin = combinacao.itens.all()

        self.assertEqual(r.status_code, 302)
        self.assertEqual((bale.nome, bale.preco, {t.pk for t in bale.turmas.all()}), ('Balé', D('100'), {self.ballet.pk, self.ballet2.pk}))
        self.assertEqual((gin.nome, gin.preco), ('Ginástica', D('100')))
        self.assertEqual([(p.grupo, p.preco) for p in bale.precos_grupo.all()], [(self.golden, D('99'))])
        self.assertEqual(list(gin.precos_grupo.all()), [])

    def test_combinacao_criada_pela_tela_calcula_200_e_199(self):
        self.admin.post(reverse('precos_admin:combinacao_nova'), self.dados_combinacao())
        entradas = [Entrada(self.ballet), Entrada(self.ginastica, data=date(2026, 3, 1), apos_cadastro=True)]

        self.assertEqual(motor.calcular(entradas, quando=date(2026, 11, 12)).total, D('200.00'))
        self.assertEqual(motor.calcular(entradas, grupos={self.golden.pk}, quando=date(2026, 11, 12)).total, D('199.00'))

    def test_validacoes(self):
        invalidos = [
            {'nome': ''},
            {'item_2_nome': '', 'item_2_preco': '', 'item_2_turmas': []},                       # só 1 item
            {'item_2_turmas': [self.ballet.pk]},                                                  # turma repetida em dois itens
            {'item_1_preco': 'abc'}, {'item_1_preco': ''}, {'item_2_turmas': []},
            {'inicio': '2026-12-31', 'fim': '2026-11-01'},
            {f'grupo_{self.golden.pk}_item_1': 'xx'},
        ]

        for extra in invalidos:
            self.admin.post(reverse('precos_admin:combinacao_nova'), self.dados_combinacao(**extra))

        self.assertEqual(Combinacao.objects.count(), 0)

    def test_editar_troca_os_itens_e_os_precos(self):
        self.admin.post(reverse('precos_admin:combinacao_nova'), self.dados_combinacao())
        combinacao = Combinacao.objects.get()

        self.assertContains(self.admin.get(reverse('precos_admin:combinacao_editar', args=[combinacao.pk])), 'value="Balé"')

        self.admin.post(reverse('precos_admin:combinacao_editar', args=[combinacao.pk]), self.dados_combinacao(
            item_1_preco='105', **{f'grupo_{self.golden.pk}_item_1': ''},
        ))
        bale = Combinacao.objects.get().itens.first()

        self.assertEqual(bale.preco, D('105'))
        self.assertEqual(bale.precos_grupo.count(), 0)
        self.assertEqual(Combinacao.objects.count(), 1)
        self.assertEqual(CombinacaoItem.objects.count(), 2)

    def test_ligar_desligar_e_excluir(self):
        self.admin.post(reverse('precos_admin:combinacao_nova'), self.dados_combinacao())
        combinacao = Combinacao.objects.get()

        self.admin.post(reverse('precos_admin:combinacao_alternar', args=[combinacao.pk]))
        combinacao.refresh_from_db()
        self.assertFalse(combinacao.ativa)

        self.admin.post(reverse('precos_admin:combinacao_excluir', args=[combinacao.pk]))
        self.assertEqual((Combinacao.objects.count(), CombinacaoItem.objects.count(), CombinacaoPrecoGrupo.objects.count()), (0, 0, 0))

    def test_lista_mostra_o_resumo(self):
        self.admin.post(reverse('precos_admin:combinacao_nova'), self.dados_combinacao())
        html = self.admin.get(reverse('precos_admin:combinacoes')).content.decode()

        self.assertIn('Balé R$ 100,00 + Ginástica R$ 100,00 · Golden: Balé R$ 99,00', html)

    def test_simulador_mostra_a_combinacao(self):
        self.admin.post(reverse('precos_admin:combinacao_nova'), self.dados_combinacao())
        r = self.admin.post(reverse('precos_admin:simulador'), {
            'turma_1': self.ginastica.pk, 'apos_1': '0', 'turma_2': self.ballet.pk, 'apos_2': '1', 'data_2': '2026-03-01',
            'grupos': [self.golden.pk], 'quando': '2026-11-12',
        })

        self.assertContains(r, 'R$ 199,00')
        self.assertContains(r, 'Combinação: Balé + Ginástica')

    def test_acesso_so_para_admin(self):
        for nome in ('combinacoes', 'combinacao_nova'):
            self.assertEqual(self.admin.get(reverse(f'precos_admin:{nome}')).status_code, 200)
            self.assertEqual(self.familia.get(reverse(f'precos_admin:{nome}')).status_code, 302)

    def test_excluir_grupo_avisa_dos_precos_de_combinacao(self):
        self.admin.post(reverse('precos_admin:combinacao_nova'), self.dados_combinacao())
        html = self.admin.get(reverse('precos_admin:grupo_detalhe', args=[self.golden.pk])).content.decode()

        self.assertIn('1 preço(s) especial(is) do grupo em combinações', html)
