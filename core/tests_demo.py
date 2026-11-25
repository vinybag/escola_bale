from decimal import Decimal
from unittest import mock

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, TestCase, override_settings

from cantina.models import Produto
from core import demo
from pagamentos.asaas_helper import AsaasAPI
from pagamentos.models import Mensalidade
from usuarios.models import Aluna

ESTATICOS = override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})


class ComandoTests(TestCase):
    def test_recusa_sem_demo_mode(self):
        User.objects.create_user('real', password='x')

        with override_settings(DEMO_MODE=False):
            with self.assertRaises(CommandError):
                call_command('popular_demo', '--apagar-tudo')

        self.assertTrue(User.objects.filter(username='real').exists())

    def test_exige_confirmacao(self):
        with override_settings(DEMO_MODE=True):
            with self.assertRaises(CommandError):
                call_command('popular_demo')

    def test_cria_a_escola_e_recria_do_zero(self):
        User.objects.create_user('lixo', password='x')

        with override_settings(DEMO_MODE=True):
            call_command('popular_demo', '--apagar-tudo', verbosity=0)
            primeiro = Mensalidade.objects.count()
            call_command('popular_demo', '--apagar-tudo', verbosity=0)

        self.assertFalse(User.objects.filter(username='lixo').exists())
        self.assertEqual(Mensalidade.objects.count(), primeiro)
        self.assertEqual(Aluna.objects.count(), 4)
        self.assertEqual(Produto.objects.count(), 5)
        self.assertEqual(Mensalidade.objects.count(), 16)

    def test_contas_da_demo_nao_tem_senha_e_admin_nao_e_superusuario(self):
        with override_settings(DEMO_MODE=True):
            call_command('popular_demo', '--apagar-tudo', verbosity=0)

        adm = User.objects.get(username=demo.ADMIN)
        self.assertTrue(adm.is_staff)
        self.assertFalse(adm.is_superuser)
        self.assertFalse(User.objects.filter(is_superuser=True).exists())
        self.assertFalse(any(u.has_usable_password() for u in User.objects.all()))

    def test_desconto_da_familia_aparece_nas_mensalidades(self):
        with override_settings(DEMO_MODE=True):
            call_command('popular_demo', '--apagar-tudo', verbosity=0)

        mariana = User.objects.get(username=demo.RESPONSAVEL)
        mes_atual = Mensalidade.objects.filter(responsavel=mariana).order_by('-mes_referencia')[:2]
        self.assertEqual(len(mes_atual), 2)  # as duas irmãs na mesma responsável
        self.assertTrue(all(m.valor > 0 for m in mes_atual))


@ESTATICOS
class EntradaETelasTests(TestCase):
    def setUp(self):
        with override_settings(DEMO_MODE=True):
            call_command('popular_demo', '--apagar-tudo', verbosity=0)

    def test_fora_da_demo_nao_existe(self):
        with override_settings(DEMO_MODE=False):
            self.assertEqual(Client().post('/demo/entrar/administradora/').status_code, 404)

    def test_so_aceita_post(self):
        with override_settings(DEMO_MODE=True):
            self.assertEqual(Client().get('/demo/entrar/administradora/').status_code, 404)

    def test_entra_como_administradora_e_como_responsavel(self):
        with override_settings(DEMO_MODE=True):
            c = Client()
            r = c.post('/demo/entrar/administradora/')
            self.assertEqual(r.url, '/admin-dashboard/')
            self.assertEqual(c.get('/admin-dashboard/').status_code, 200)

            c2 = Client()
            self.assertEqual(c2.post('/demo/entrar/responsavel/').url, '/conta/dashboard/')
            self.assertEqual(c2.get('/pagamentos/mensalidades/').status_code, 200)

    def test_quem_inexistente(self):
        with override_settings(DEMO_MODE=True):
            self.assertEqual(Client().post('/demo/entrar/ninguem/').status_code, 302)

    def test_faixa_so_na_demo(self):
        with override_settings(DEMO_MODE=True):
            self.assertContains(Client().get('/'), 'Ambiente de demonstração')

        with override_settings(DEMO_MODE=False):
            self.assertNotContains(Client().get('/'), 'Ambiente de demonstração')

    def test_bloqueios_na_demo(self):
        from django.conf import settings

        with override_settings(DEMO_MODE=True, MIDDLEWARE=settings.MIDDLEWARE + ['core.demo.DemoMiddleware']):
            for caminho in ('/admin/', '/conta/alterar-senha/', '/conta/esqueci-senha/', '/conta/cadastro/'):
                r = Client().get(caminho)
                self.assertEqual((r.status_code, r.url), (302, '/'), caminho)

            self.assertEqual(Client().get('/').headers['X-Robots-Tag'], 'noindex, nofollow')

    def test_fora_da_demo_o_admin_do_django_continua(self):
        from django.conf import settings

        with override_settings(DEMO_MODE=False, MIDDLEWARE=settings.MIDDLEWARE + ['core.demo.DemoMiddleware']):
            self.assertEqual(Client().get('/admin/').status_code, 302)  # vai para o login do admin
            self.assertIn('login', Client().get('/admin/').url)

    def test_buscadores_nao_indexam(self):
        from django.http import HttpResponse
        from django.test import RequestFactory

        with override_settings(DEMO_MODE=True):
            r = demo.DemoMiddleware(lambda req: HttpResponse('ok'))(RequestFactory().get('/'))

        self.assertEqual(r['X-Robots-Tag'], 'noindex, nofollow')


class PagamentoSimuladoTests(TestCase):
    @override_settings(DEMO_MODE=True)
    def test_pix_de_mentira_fica_pago_depois_de_alguns_segundos(self):
        api = AsaasAPI()
        cobranca = api.criar_cobranca_pix(Decimal('91.50'), 'x')

        self.assertTrue(cobranca['id'].startswith('pay_demo_'))
        self.assertEqual(api.consultar_cobranca(cobranca['id'])['status'], 'PENDING')
        self.assertEqual(api.consultar_cobranca(cobranca['id'])['value'], 91.5)
        self.assertIn('DEMONSTRACAO', api.obter_qrcode_pix(cobranca['id'])['payload'])

        with mock.patch('django.utils.timezone.now') as agora:
            from datetime import datetime, timedelta, timezone
            agora.return_value = datetime.now(timezone.utc) + timedelta(seconds=demo.SEGUNDOS_PARA_PAGAR + 1)
            self.assertEqual(api.consultar_cobranca(cobranca['id'])['status'], 'RECEIVED')

    @override_settings(DEMO_MODE=True)
    def test_whatsapp_nao_envia(self):
        from pagamentos.services_whatsapp import enviar_whatsapp_template, enviar_whatsapp_texto

        with mock.patch('requests.post') as post:
            self.assertEqual(enviar_whatsapp_template('5511900000000', 'x', []), (200, {'demo': True}))
            self.assertEqual(enviar_whatsapp_texto('5511900000000', 'oi'), (200, {'demo': True}))
            post.assert_not_called()

    @override_settings(DEMO_MODE=True)
    def test_id_estranho_nao_quebra(self):
        self.assertIsNone(AsaasAPI().consultar_cobranca('pay_123'))


@ESTATICOS
class FluxoDoPixNaDemoTests(TestCase):
    def test_responsavel_gera_o_pix_de_mentira_e_ele_vira_pago(self):
        from datetime import datetime, timedelta, timezone as tz

        with override_settings(DEMO_MODE=True):
            call_command('popular_demo', '--apagar-tudo', verbosity=0)
            c = Client()
            c.post('/demo/entrar/responsavel/')
            aberta = Mensalidade.objects.filter(status__in=['pendente', 'atrasado']).first()

            tela = c.get(f'/pagamentos/pagar/pix/{aberta.pk}/')
            self.assertEqual(tela.status_code, 200)
            self.assertContains(tela, 'DEMONSTRACAO-pay_demo_')

            aberta.refresh_from_db()
            self.assertTrue(aberta.asaas_payment_id.startswith('pay_demo_'))
            self.assertEqual(c.get(f'/pagamentos/verificar-pix/{aberta.asaas_payment_id}/').json()['status'], 'pending')

            with mock.patch('django.utils.timezone.now') as agora:
                agora.return_value = datetime.now(tz.utc) + timedelta(seconds=demo.SEGUNDOS_PARA_PAGAR + 2)
                self.assertEqual(c.get(f'/pagamentos/verificar-pix/{aberta.asaas_payment_id}/').json()['status'], 'paid')

            aberta.refresh_from_db()
            self.assertEqual(aberta.status, 'pago')
