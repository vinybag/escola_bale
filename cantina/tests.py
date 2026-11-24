from decimal import Decimal

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from . import servico
from .models import MovimentoEstoque, Produto

D = Decimal


def estaticos():
    return override_settings(STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    })


class ServicoTests(TestCase):
    def setUp(self):
        self.p = Produto.objects.create(nome='Suco', preco=D('5'), quantidade=10)

    def test_entrada_soma_e_registra(self):
        mov = servico.movimentar(self.p, 'entrada', 5, motivo='compra')

        self.assertEqual(self.p.quantidade, 15)
        self.assertEqual(Produto.objects.get(pk=self.p.pk).quantidade, 15)
        self.assertEqual((mov.variacao, mov.saldo_depois, mov.motivo), (5, 15, 'compra'))

    def test_saida_perda_e_venda_tiram(self):
        for tipo in ('saida', 'perda', 'venda'):
            servico.movimentar(self.p, tipo, 2)

        self.assertEqual(Produto.objects.get(pk=self.p.pk).quantidade, 4)

    def test_nao_deixa_ficar_negativo(self):
        with self.assertRaises(ValueError):
            servico.movimentar(self.p, 'saida', 11)

        self.assertEqual(Produto.objects.get(pk=self.p.pk).quantidade, 10)
        self.assertEqual(MovimentoEstoque.objects.count(), 0)

    def test_contagem_define_a_quantidade(self):
        mov = servico.movimentar(self.p, 'ajuste', 7)

        self.assertEqual((mov.variacao, mov.saldo_depois), (-3, 7))

    def test_contagem_igual_nao_cria_movimento(self):
        self.assertIsNone(servico.movimentar(self.p, 'ajuste', 10))
        self.assertEqual(MovimentoEstoque.objects.count(), 0)

    def test_quantidade_invalida(self):
        for q in (0, -1, 'a', 2_000_000):
            with self.assertRaises(ValueError):
                servico.movimentar(self.p, 'entrada', q)

    def test_situacao_do_estoque(self):
        self.p.estoque_minimo = 3
        self.p.quantidade = 3
        self.assertEqual(self.p.situacao_estoque, 'baixo')
        self.p.quantidade = 0
        self.assertEqual(self.p.situacao_estoque, 'zerado')
        self.p.quantidade = 8
        self.assertEqual(self.p.situacao_estoque, 'ok')

    def test_codigo_vazio_vira_nulo_e_nao_conflita(self):
        Produto.objects.create(nome='A', preco=D('1'), codigo_barras='  ')
        Produto.objects.create(nome='B', preco=D('1'), codigo_barras='')

        self.assertEqual(Produto.objects.filter(codigo_barras__isnull=True).count(), 3)


@estaticos()
class TelasTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user('adm', password='x', is_staff=True)
        self.comum = User.objects.create_user('comum', password='x')
        self.c = Client()
        self.c.force_login(self.staff)

    def dados(self, **extra):
        d = {'nome': 'Água', 'categoria': 'Bebidas', 'preco': '3,50', 'custo': '1,80', 'quantidade': '24',
             'estoque_minimo': '6', 'codigo_barras': '789 123', 'ativo': 'on'}
        d.update(extra)
        return d

    def test_so_equipe_acessa(self):
        outro = Client()
        outro.force_login(self.comum)

        self.assertEqual(outro.get(reverse('cantina_admin:lista')).status_code, 302)
        self.assertEqual(Client().get(reverse('cantina_admin:lista')).status_code, 302)

    def test_telas_abrem(self):
        p = Produto.objects.create(nome='X', preco=D('2'), quantidade=3)

        for nome, args in [('lista', []), ('novo', []), ('editar', [p.pk]), ('movimentacoes', [])]:
            self.assertEqual(self.c.get(reverse(f'cantina_admin:{nome}', args=args)).status_code, 200, nome)

    def test_cadastra_com_estoque_inicial_e_codigo_sem_espacos(self):
        self.c.post(reverse('cantina_admin:novo'), self.dados())
        p = Produto.objects.get(nome='Água')

        self.assertEqual((p.preco, p.custo, p.quantidade, p.codigo_barras), (D('3.50'), D('1.80'), 24, '789123'))
        self.assertEqual(p.movimentos.get().motivo, 'Estoque inicial')

    def test_preco_obrigatorio_e_invalido(self):
        for preco in ('', 'abc', '-1'):
            self.c.post(reverse('cantina_admin:novo'), self.dados(preco=preco))

        self.assertEqual(Produto.objects.count(), 0)

    def test_codigo_repetido_e_recusado(self):
        Produto.objects.create(nome='Outro', preco=D('1'), codigo_barras='789123')
        self.c.post(reverse('cantina_admin:novo'), self.dados())

        self.assertEqual(Produto.objects.count(), 1)

    def test_editar_nao_mexe_no_estoque(self):
        self.c.post(reverse('cantina_admin:novo'), self.dados())
        p = Produto.objects.get(nome='Água')
        self.c.post(reverse('cantina_admin:editar', args=[p.pk]), self.dados(preco='4', quantidade='999'))
        p.refresh_from_db()

        self.assertEqual((p.preco, p.quantidade), (D('4'), 24))

    def test_ajustar_estoque_pela_tela(self):
        p = Produto.objects.create(nome='X', preco=D('2'), quantidade=3)
        self.c.post(reverse('cantina_admin:ajustar', args=[p.pk]), {'tipo': 'entrada', 'quantidade': '10', 'motivo': 'x'})
        self.c.post(reverse('cantina_admin:ajustar', args=[p.pk]), {'tipo': 'saida', 'quantidade': '100'})
        p.refresh_from_db()

        self.assertEqual(p.quantidade, 13)

    def test_leitor_abre_produto_ou_comeca_cadastro(self):
        p = Produto.objects.create(nome='X', preco=D('2'), codigo_barras='555')

        achou = self.c.get(reverse('cantina_admin:buscar_codigo'), {'codigo': '555'})
        self.assertRedirects(achou, reverse('cantina_admin:editar', args=[p.pk]))

        novo = self.c.get(reverse('cantina_admin:buscar_codigo'), {'codigo': '999'})
        self.assertEqual(novo.url, reverse('cantina_admin:novo') + '?codigo=999')
        self.assertContains(self.c.get(novo.url), 'value="999"')

    def test_desativar_filtrar_e_excluir(self):
        p = Produto.objects.create(nome='Bala', preco=D('1'), quantidade=5)
        self.c.post(reverse('cantina_admin:alternar', args=[p.pk]))

        self.assertNotContains(self.c.get(reverse('cantina_admin:lista')), '<strong>Bala</strong>')
        self.assertContains(self.c.get(reverse('cantina_admin:lista'), {'filtro': 'inativos'}), '<strong>Bala</strong>')

        self.c.post(reverse('cantina_admin:excluir', args=[p.pk]))
        self.assertFalse(Produto.objects.exists())

    def test_busca_por_nome_e_filtro_de_estoque_baixo(self):
        Produto.objects.create(nome='Suco', preco=D('5'), quantidade=1, estoque_minimo=2)
        Produto.objects.create(nome='Bolo', preco=D('5'), quantidade=50, estoque_minimo=2)

        self.assertNotContains(self.c.get(reverse('cantina_admin:lista'), {'q': 'suc'}), 'Bolo')
        baixo = self.c.get(reverse('cantina_admin:lista'), {'filtro': 'baixo'})
        self.assertContains(baixo, 'Suco')
        self.assertNotContains(baixo, 'Bolo')

    def test_excluir_e_ajustar_exigem_post(self):
        p = Produto.objects.create(nome='X', preco=D('2'))

        self.assertEqual(self.c.get(reverse('cantina_admin:excluir', args=[p.pk])).status_code, 405)
        self.assertEqual(self.c.get(reverse('cantina_admin:ajustar', args=[p.pk])).status_code, 405)
