import io
import re
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from PIL import Image

from core import aparencia
from core.models import ConfiguracaoEscola

ESTATICOS = override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})


def imagem(formato='PNG', tamanho=(900, 400), cor=(200, 30, 30, 255)):
    saida = io.BytesIO()
    Image.new('RGBA' if formato == 'PNG' else 'RGB', tamanho, cor if formato == 'PNG' else cor[:3]).save(saida, format=formato)
    return saida.getvalue()


def arquivo(conteudo, nome='logo.png', tipo='image/png'):
    return SimpleUploadedFile(nome, conteudo, content_type=tipo)


class CoresTests(TestCase):
    def test_normaliza(self):
        self.assertEqual(aparencia.normalizar_cor(' B07A84 '), '#b07a84')
        self.assertEqual(aparencia.normalizar_cor(''), '')

    def test_recusa_formato_invalido(self):
        for ruim in ('red', '#12345', '#gggggg', 'rgb(1,2,3)', '#12345678'):
            with self.assertRaises(ValueError, msg=ruim):
                aparencia.normalizar_cor(ruim)

    def test_recusa_cor_clara_demais(self):
        for clara in ('#ffffff', '#ffeeaa', '#dddddd'):
            with self.assertRaises(ValueError):
                aparencia.validar_cor(clara)

    def test_todas_as_paletas_aguentam_texto_branco(self):
        for nome, cor in aparencia.PALETAS:
            self.assertEqual(aparencia.validar_cor(cor), cor, nome)

    def test_cor_padrao_nao_gera_css(self):
        self.assertEqual(aparencia.css_do_tema(''), '')

    def test_css_do_tema_tem_todas_as_variaveis(self):
        css = aparencia.css_do_tema('#7b4fa0')

        for var in ('--cor-principal:#7b4fa0', '--cor-principal-rgb:123, 79, 160', '--cor-principal-escura',
                    '--cor-principal-clara', '--cor-principal-borda', '--cor-fundo-suave'):
            self.assertIn(var, css)

    def test_tons_ficam_na_ordem_certa(self):
        v = aparencia.variaveis_css('#7b4fa0')

        self.assertLess(aparencia._luminancia(v['--cor-principal-escura']), aparencia._luminancia(v['--cor-principal']))
        self.assertGreater(aparencia._luminancia(v['--cor-principal-clara']), aparencia._luminancia(v['--cor-principal']))
        self.assertGreater(aparencia._luminancia(v['--cor-fundo-suave']), aparencia._luminancia(v['--cor-principal-clara']))


class LogoTests(TestCase):
    def test_png_e_normalizado(self):
        dados, tipo = aparencia.processar_logo(arquivo(imagem(tamanho=(1800, 800))))
        saida = Image.open(io.BytesIO(dados))

        self.assertEqual(tipo, 'image/png')
        self.assertLessEqual(saida.size[0], 600)
        self.assertLessEqual(saida.size[1], 300)

    def test_jpeg_e_webp_sao_aceitos(self):
        for formato in ('JPEG', 'WEBP'):
            self.assertEqual(aparencia.processar_logo(arquivo(imagem(formato)))[1], 'image/png')

    def test_recusas(self):
        casos = [
            arquivo(b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>', 'x.svg', 'image/svg+xml'),
            arquivo(b'isto nao e imagem', 'x.png'),
            arquivo(imagem('GIF'), 'x.gif', 'image/gif'),
            arquivo(b'\x00' * (aparencia.TAMANHO_MAXIMO_LOGO + 1)),
        ]

        for caso in casos:
            with self.assertRaises(ValueError):
                aparencia.processar_logo(caso)


@ESTATICOS
class TelasTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user('adm', password='x', is_staff=True)
        self.comum = User.objects.create_user('comum', password='x')
        self.c = Client()
        self.c.force_login(self.staff)
        self.url = reverse('admin_dashboard:configuracoes_aparencia')

    def config(self):
        return ConfiguracaoEscola.obter()

    def test_so_a_equipe_altera(self):
        outro = Client()
        outro.force_login(self.comum)
        outro.post(self.url, {'acao': 'cor', 'paleta': '#7b4fa0'})
        Client().post(self.url, {'acao': 'cor', 'paleta': '#7b4fa0'})

        self.assertEqual(self.config().cor_principal, '')

    def test_escolhe_paleta_e_volta_ao_padrao(self):
        self.c.post(self.url, {'acao': 'cor', 'paleta': '#3f6fb0'})
        self.assertEqual(self.config().cor_principal, '#3f6fb0')

        self.c.post(self.url, {'acao': 'cor', 'paleta': ''})
        self.assertEqual(self.config().cor_principal, '')

    def test_cor_propria_e_validada(self):
        self.c.post(self.url, {'acao': 'cor', 'paleta': 'propria', 'cor_propria': '#112233'})
        self.assertEqual(self.config().cor_principal, '#112233')

        self.c.post(self.url, {'acao': 'cor', 'paleta': 'propria', 'cor_propria': '#fefefe'})
        self.assertEqual(self.config().cor_principal, '#112233')   # a clara foi recusada

    def test_envia_serve_e_remove_a_logo(self):
        self.c.post(self.url, {'acao': 'logo', 'logo': arquivo(imagem())})
        cfg = self.config()
        self.assertEqual((cfg.logo_tipo, cfg.logo_versao), ('image/png', 1))

        r = Client().get('/escola/logo/')
        self.assertEqual((r.status_code, r['Content-Type']), (200, 'image/png'))
        self.assertTrue(r.content.startswith(b'\x89PNG'))
        self.assertEqual(r['X-Content-Type-Options'], 'nosniff')

        self.c.post(self.url, {'acao': 'remover_logo'})
        self.assertEqual(Client().get('/escola/logo/').status_code, 404)
        self.assertEqual(self.config().logo_versao, 2)

    def test_arquivo_ruim_nao_grava(self):
        self.c.post(self.url, {'acao': 'logo', 'logo': arquivo(b'<svg/>', 'x.svg', 'image/svg+xml')})

        self.assertEqual(self.config().logo_tipo, '')

    def test_tela_de_configuracao_mostra_a_aparencia(self):
        r = self.c.get(reverse('admin_dashboard:configuracoes_site'))

        self.assertContains(r, 'Aparência: logo e cor')
        self.assertContains(r, 'Rosa (padrão)')


@ESTATICOS
class RenderizacaoTests(TestCase):
    def test_padrao_nao_muda_nada(self):
        r = Client().get('/')

        self.assertNotContains(r, '--cor-principal:')
        self.assertContains(r, 'img/logo')          # a logo de sempre
        self.assertNotContains(r, 'Sua logo aqui')

    def test_cor_da_escola_chega_nas_telas(self):
        cfg = ConfiguracaoEscola.obter()
        cfg.cor_principal = '#7b4fa0'
        cfg.save()
        r = Client().get('/')

        self.assertContains(r, '--cor-principal:#7b4fa0')

    def test_logo_da_escola_substitui_a_padrao(self):
        cfg = ConfiguracaoEscola.obter()
        cfg.logo_dados, cfg.logo_tipo, cfg.logo_versao = imagem(), 'image/png', 3
        cfg.save()

        self.assertContains(Client().get('/'), '/escola/logo/?v=3')

    def test_demo_sem_logo_mostra_o_aviso(self):
        with override_settings(DEMO_MODE=True):
            self.assertContains(Client().get('/'), 'Sua logo aqui')

    def test_demo_com_logo_nao_mostra_o_aviso(self):
        cfg = ConfiguracaoEscola.obter()
        cfg.logo_dados, cfg.logo_tipo = imagem(), 'image/png'
        cfg.save()

        with override_settings(DEMO_MODE=True):
            self.assertNotContains(Client().get('/'), 'Sua logo aqui')

    def test_a_administracao_continua_igual(self):
        cfg = ConfiguracaoEscola.obter()
        cfg.cor_principal = '#7b4fa0'
        cfg.logo_dados, cfg.logo_tipo = imagem(), 'image/png'
        cfg.save()
        staff = User.objects.create_user('adm', password='x', is_staff=True)
        c = Client()
        c.force_login(staff)
        r = c.get('/admin-dashboard/')

        self.assertNotContains(r, '--cor-principal:')
        self.assertNotContains(r, '/escola/logo/')

    def test_falha_ao_ler_a_aparencia_nao_derruba_a_pagina(self):
        from unittest import mock

        cfg = ConfiguracaoEscola.obter()
        cfg.cor_principal = '#7b4fa0'
        cfg.save()

        with mock.patch('core.aparencia.css_do_tema', side_effect=Exception('falha')):
            r = Client().get('/')

        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, '--cor-principal:')


class CssTests(TestCase):
    def test_toda_variavel_tem_a_cor_atual_como_padrao(self):
        """Sem escolha da escola, o CSS fica como sempre foi: toda var(--cor-*) tem o hexadecimal de reserva."""
        base = Path(settings.BASE_DIR)
        arquivos = [base / 'static/css/style.css'] + list((base / 'templates').rglob('*.html'))

        for arq in arquivos:
            texto = arq.read_text(encoding='utf-8')

            for m in re.finditer(r'var\(--cor-[a-z-]+(?P<resto>[^)]*)\)', texto):
                self.assertIn(',', m.group('resto'), f'{arq.name}: {m.group(0)} sem valor de reserva')

    def test_administracao_nao_usa_as_variaveis(self):
        base = Path(settings.BASE_DIR) / 'admin_dashboard/templates/admin_dashboard'

        for arq in base.rglob('*.html'):
            if 'configuracoes' in str(arq):
                continue

            self.assertNotIn('var(--cor-principal', arq.read_text(encoding='utf-8'), arq.name)
