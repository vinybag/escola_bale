"""Testes: a família preenche a data de nascimento da aluna pelo painel."""

from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from usuarios.models import Aluna

# Nos testes não há arquivos estáticos compilados (o projeto usa o armazenamento com manifesto).
ESTATICOS_SIMPLES = override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})


def url_salvar(aluna):
    return reverse('aluna_data_nascimento', args=[aluna.pk])


@ESTATICOS_SIMPLES
class DataNascimentoPeloPainelTests(TestCase):
    def setUp(self):
        self.resp = User.objects.create_user('maria', email='m@x.com', password='x', first_name='Maria')
        self.outra = User.objects.create_user('outra', email='o@x.com', password='x')
        self.staff = User.objects.create_user('adm', email='a@x.com', password='x', is_staff=True)

        self.sem = Aluna.objects.create(nome='Ana Sem Data', tipo_aluna='infantil', responsavel=self.resp)
        self.com = Aluna.objects.create(
            nome='Bia Com Data', tipo_aluna='infantil', responsavel=self.resp, data_nascimento=date(2015, 3, 20),
        )

        self.fam = Client()
        self.fam.force_login(self.resp)
        self.fam_outra = Client()
        self.fam_outra.force_login(self.outra)
        self.admin = Client()
        self.admin.force_login(self.staff)

    def salvar(self, aluna, valor, client=None, **kw):
        return (client or self.fam).post(url_salvar(aluna), {'data_nascimento': valor}, **kw)

    # ------------------------------------------------------------------ painel

    def test_formulario_so_aparece_para_quem_nao_tem_data(self):
        html = self.fam.get(reverse('dashboard')).content.decode()

        self.assertIn('data de nascimento não informada', html)
        self.assertIn(url_salvar(self.sem), html)
        self.assertNotIn(url_salvar(self.com), html)
        self.assertIn(f'{self.com.idade} anos', html)

    def test_idade_no_singular_e_menos_de_um_ano(self):
        hoje = timezone.localdate()
        Aluna.objects.create(nome='Um Ano', tipo_aluna='infantil', responsavel=self.resp, data_nascimento=hoje - timedelta(days=400))
        Aluna.objects.create(nome='Bebe', tipo_aluna='infantil', responsavel=self.resp, data_nascimento=hoje - timedelta(days=100))
        html = self.fam.get(reverse('dashboard')).content.decode()

        self.assertRegex(html, r'Um Ano</strong>\s*-\s*1 ano\s')
        self.assertRegex(html, r'Bebe</strong>\s*-\s*menos de 1 ano')

    # ------------------------------------------------------------------ salvar

    def test_salvar_grava_e_aparece_para_o_admin(self):
        r = self.salvar(self.sem, '2016-08-02', follow=True)
        self.sem.refresh_from_db()

        self.assertEqual(self.sem.data_nascimento, date(2016, 8, 2))
        self.assertContains(r, 'Data de nascimento de Ana Sem Data salva: 02/08/2016')
        self.assertNotIn(url_salvar(self.sem), r.content.decode())  # o formulário some

        ficha = self.admin.get(reverse('admin_dashboard:aluna_detalhes', args=[self.sem.pk]))
        self.assertContains(ficha, '02/08/2016')
        self.assertContains(ficha, f'{self.sem.idade} anos')

    def test_aceita_o_formato_brasileiro(self):
        self.salvar(self.sem, '02/08/2016')
        self.sem.refresh_from_db()

        self.assertEqual(self.sem.data_nascimento, date(2016, 8, 2))

    def test_nunca_sobrescreve_uma_data_que_ja_existe(self):
        r = self.salvar(self.com, '2010-01-01', follow=True)
        self.com.refresh_from_db()

        self.assertEqual(self.com.data_nascimento, date(2015, 3, 20))
        self.assertContains(r, 'já tem a data de nascimento cadastrada')

    def test_datas_invalidas_nao_gravam_nada(self):
        amanha = (timezone.localdate() + timedelta(days=1)).isoformat()

        for valor in ('', 'abc', '2016-02-31', '1900-01-01', amanha):
            r = self.salvar(self.sem, valor, follow=True)
            self.sem.refresh_from_db()

            self.assertIsNone(self.sem.data_nascimento, valor)
            self.assertTrue(
                'Informe uma data de nascimento válida' in r.content.decode()
                or 'Confira a data de nascimento' in r.content.decode(),
                valor,
            )

    # -------------------------------------------------------------- permissões

    def test_outra_familia_nao_consegue_preencher(self):
        r = self.salvar(self.sem, '2016-08-02', client=self.fam_outra)
        self.sem.refresh_from_db()

        self.assertEqual(r.status_code, 404)
        self.assertIsNone(self.sem.data_nascimento)

    def test_exige_login_e_metodo_post(self):
        self.assertEqual(self.salvar(self.sem, '2016-08-02', client=Client()).status_code, 302)
        self.assertEqual(self.fam.get(url_salvar(self.sem)).status_code, 405)
        self.sem.refresh_from_db()
        self.assertIsNone(self.sem.data_nascimento)

    def test_aluna_inativa_nao_pode_ser_alterada_por_aqui(self):
        Aluna.objects.filter(pk=self.sem.pk).update(ativa=False)

        self.assertEqual(self.salvar(self.sem, '2016-08-02').status_code, 404)

    def test_aluna_adulta_ve_e_preenche_a_propria_data(self):
        adulta_user = User.objects.create_user('joana', email='j@x.com', password='x')
        adulta = Aluna.objects.create(nome='Joana Adulta', tipo_aluna='adulto', usuario=adulta_user)
        cliente = Client()
        cliente.force_login(adulta_user)

        self.assertIn('Joana Adulta', cliente.get(reverse('dashboard')).content.decode())

        self.salvar(adulta, '1990-05-17', client=cliente)
        adulta.refresh_from_db()

        self.assertEqual(adulta.data_nascimento, date(1990, 5, 17))

    def test_responsavel_que_tambem_e_aluna_ve_as_duas_coisas(self):
        propria = Aluna.objects.create(nome='Maria Aluna', tipo_aluna='adulto', usuario=self.resp)
        html = self.fam.get(reverse('dashboard')).content.decode()

        self.assertIn('Maria Aluna', html)
        self.assertIn('Ana Sem Data', html)
        self.assertEqual(html.count(url_salvar(propria)), 1)

    # ----------------------------------------------------------- admin (lista)

    def test_admin_ve_a_contagem_e_filtra_quem_falta(self):
        Aluna.objects.create(nome='Inativa Sem Data', tipo_aluna='infantil', responsavel=self.resp, ativa=False)

        html = self.admin.get(reverse('admin_dashboard:alunas_list')).content.decode()
        self.assertIn('1 aluna ativa sem data de nascimento', html)  # a inativa não conta
        self.assertIn('sem data de nascimento</span>', html)

        filtrada = self.admin.get(reverse('admin_dashboard:alunas_list') + '?status=ativas&nascimento=sem')
        self.assertContains(filtrada, 'Ana Sem Data')
        self.assertNotContains(filtrada, 'Bia Com Data')
        self.assertContains(filtrada, 'Mostrando só alunas sem data de nascimento')

    def test_o_aviso_some_quando_todas_tem_data(self):
        Aluna.objects.filter(pk=self.sem.pk).update(data_nascimento=date(2016, 8, 2))

        html = self.admin.get(reverse('admin_dashboard:alunas_list')).content.decode()
        self.assertNotIn('ativa sem data de nascimento', html)
        self.assertNotIn('ativas sem data de nascimento', html)
