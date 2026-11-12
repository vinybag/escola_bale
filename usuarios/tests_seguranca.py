import contextlib
import io
import os
from pathlib import Path
from unittest import mock

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

import init_db

SENHA = 'uma-senha-longa-de-teste-123'


class InitDbTests(TestCase):
    def rodar(self, **ambiente):
        base = {k: v for k, v in os.environ.items() if not k.startswith('ADMIN_')}

        with mock.patch.dict(os.environ, {**base, **ambiente}, clear=True):
            saida = io.StringIO()

            with contextlib.redirect_stdout(saida):
                criou = init_db.criar_superusuario_inicial()

        return criou, saida.getvalue()

    def test_sem_a_variavel_nao_cria_conta_nenhuma(self):
        criou, saida = self.rodar()

        self.assertFalse(criou)
        self.assertFalse(User.objects.exists())
        self.assertIn('ADMIN_INITIAL_PASSWORD', saida)

    def test_com_a_variavel_cria_o_superusuario_sem_mostrar_a_senha(self):
        criou, saida = self.rodar(ADMIN_INITIAL_PASSWORD=SENHA, ADMIN_EMAIL='dona@escola.com')
        usuario = User.objects.get(username='admin')

        self.assertTrue(criou)
        self.assertTrue(usuario.is_superuser and usuario.is_staff)
        self.assertTrue(usuario.check_password(SENHA))
        self.assertEqual(usuario.email, 'dona@escola.com')
        self.assertNotIn(SENHA, saida)

    def test_nome_de_usuario_pode_ser_escolhido(self):
        self.rodar(ADMIN_INITIAL_PASSWORD=SENHA, ADMIN_USERNAME='diretora')
        self.assertTrue(User.objects.filter(username='diretora', is_superuser=True).exists())

    def test_senha_curta_e_recusada(self):
        criou, _ = self.rodar(ADMIN_INITIAL_PASSWORD='curta')

        self.assertFalse(criou)
        self.assertFalse(User.objects.exists())

    def test_conta_existente_nunca_tem_a_senha_trocada(self):
        User.objects.create_superuser('admin', 'a@a.com', 'senha-original-123')
        criou, _ = self.rodar(ADMIN_INITIAL_PASSWORD=SENHA)

        self.assertFalse(criou)
        self.assertTrue(User.objects.get(username='admin').check_password('senha-original-123'))

    def test_o_arquivo_nao_tem_senha_escrita(self):
        codigo = Path(init_db.__file__).read_text(encoding='utf-8')

        self.assertNotIn("password='", codigo)
        self.assertNotIn('password="', codigo)


class ProtegerContaAdminTests(TestCase):
    def comando(self, *args):
        saida = io.StringIO()
        call_command('proteger_conta_admin', *args, stdout=saida)

        return saida.getvalue()

    def test_conta_inexistente(self):
        self.assertIn('NÃO existe', self.comando())

    def test_sem_bloquear_so_mostra(self):
        conta = User.objects.create_superuser('admin', 'a@a.com', 'senha-antiga-123')
        saida = self.comando()

        self.assertIn('em uso', saida)
        self.assertIn('nunca fez login', saida)
        self.assertTrue(User.objects.get(pk=conta.pk).has_usable_password())

    def test_nao_bloqueia_se_for_a_unica_conta_de_administracao(self):
        User.objects.create_superuser('admin', 'a@a.com', 'senha-antiga-123')

        with self.assertRaises(CommandError):
            self.comando('--bloquear')

        self.assertTrue(User.objects.get(username='admin').has_usable_password())

    def test_bloqueia_quando_ha_outra_conta_de_administracao(self):
        User.objects.create_superuser('admin', 'a@a.com', 'senha-antiga-123')
        User.objects.create_superuser('dona', 'd@d.com', 'outra-senha-forte-456')
        saida = self.comando('--bloquear')
        conta = User.objects.get(username='admin')

        self.assertIn('bloqueada', saida)
        self.assertFalse(conta.has_usable_password())
        self.assertFalse(conta.check_password('senha-antiga-123'))
        self.assertTrue(User.objects.get(username='dona').has_usable_password())

    def test_forcar_bloqueia_mesmo_sendo_a_unica(self):
        User.objects.create_superuser('admin', 'a@a.com', 'senha-antiga-123')
        self.comando('--bloquear', '--forcar')

        self.assertFalse(User.objects.get(username='admin').has_usable_password())

    def test_bloquear_duas_vezes_nao_da_erro(self):
        User.objects.create_superuser('admin', 'a@a.com', 'senha-antiga-123')
        User.objects.create_superuser('dona', 'd@d.com', 'outra-senha-forte-456')
        self.comando('--bloquear')

        self.assertIn('já está bloqueada', self.comando('--bloquear'))
