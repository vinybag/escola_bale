"""
Filmagem do espetáculo: link do Drive liberado só para logins escolhidos.

O que estes testes protegem:
- quem não foi marcado não abre a filmagem (nem sabendo a rota);
- o link do Drive nunca aparece em nenhuma página, só no redirecionamento
  de quem tem acesso;
- cada dia (cada Espetáculo) tem seu próprio link e sua própria lista;
- o admin só aceita link http/https e só é aberto pela equipe.
"""

from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from espetaculo.models import Espetaculo
from usuarios.models import Aluna

STORAGES_TESTE = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'
    },
}

# A home fica em /espetaculo/home/; o namespace 'espetaculo' está duplicado
# nas urls (aviso W005), então ela não é reversível pelo nome.
HOME = '/espetaculo/home/'

LINK_DIA_1 = 'https://drive.google.com/drive/folders/dia-um-secreto'
LINK_DIA_2 = 'https://drive.google.com/drive/folders/dia-dois-secreto'


def _espetaculo(titulo, dias, link=''):
    return Espetaculo.objects.create(
        titulo=titulo, descricao='x', tipo='espetaculo',
        data_apresentacao=timezone.now() + timedelta(days=dias),
        local='Teatro', endereco='Rua A', link_filmagem=link,
    )


@override_settings(STORAGES=STORAGES_TESTE)
class AcessoAFilmagemTests(TestCase):
    def setUp(self):
        self.dia1 = _espetaculo('Espetáculo - Dia 1', -2, LINK_DIA_1)
        self.dia2 = _espetaculo('Espetáculo - Dia 2', -1, LINK_DIA_2)

        self.comprou = User.objects.create_user('comprou', 'c@example.com', 'senha123')
        self.nao_comprou = User.objects.create_user('nao', 'n@example.com', 'senha123')
        self.staff = User.objects.create_user(
            'staff', 's@example.com', 'senha123', is_staff=True
        )

        self.dia1.usuarios_filmagem.add(self.comprou)

        self.rota_dia1 = reverse('espetaculo:filmagem_acessar', args=[self.dia1.pk])
        self.rota_dia2 = reverse('espetaculo:filmagem_acessar', args=[self.dia2.pk])
        self.minhas = reverse('espetaculo:minhas_filmagens')

    # ---------- rota protegida ----------

    def test_quem_foi_liberado_e_redirecionado_para_o_link(self):
        self.client.force_login(self.comprou)

        resposta = self.client.get(self.rota_dia1)

        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(resposta['Location'], LINK_DIA_1)

    def test_quem_nao_foi_liberado_recebe_403_mesmo_sabendo_a_rota(self):
        self.client.force_login(self.nao_comprou)

        resposta = self.client.get(self.rota_dia1)

        self.assertEqual(resposta.status_code, 403)
        self.assertNotIn(LINK_DIA_1, resposta.content.decode())
        self.assertNotIn('Location', resposta)

    def test_anonimo_vai_para_o_login_e_nao_para_o_link(self):
        resposta = self.client.get(self.rota_dia1)

        self.assertEqual(resposta.status_code, 302)
        self.assertNotEqual(resposta['Location'], LINK_DIA_1)
        self.assertIn('login', resposta['Location'])

    def test_liberar_um_dia_nao_libera_o_outro(self):
        self.client.force_login(self.comprou)

        self.assertEqual(self.client.get(self.rota_dia1).status_code, 302)
        self.assertEqual(self.client.get(self.rota_dia2).status_code, 403)

    def test_cada_dia_leva_para_o_seu_proprio_link(self):
        self.dia2.usuarios_filmagem.add(self.comprou)
        self.client.force_login(self.comprou)

        self.assertEqual(self.client.get(self.rota_dia1)['Location'], LINK_DIA_1)
        self.assertEqual(self.client.get(self.rota_dia2)['Location'], LINK_DIA_2)

    def test_a_equipe_sempre_consegue_abrir(self):
        self.client.force_login(self.staff)

        self.assertEqual(self.client.get(self.rota_dia1)['Location'], LINK_DIA_1)
        self.assertEqual(self.client.get(self.rota_dia2)['Location'], LINK_DIA_2)

    def test_liberado_mas_sem_link_cadastrado_da_404(self):
        sem_link = _espetaculo('Sem link', -3, '')
        sem_link.usuarios_filmagem.add(self.comprou)
        self.client.force_login(self.comprou)

        resposta = self.client.get(
            reverse('espetaculo:filmagem_acessar', args=[sem_link.pk])
        )

        self.assertEqual(resposta.status_code, 404)

    def test_a_resposta_do_redirecionamento_nao_fica_em_cache(self):
        self.client.force_login(self.comprou)

        resposta = self.client.get(self.rota_dia1)

        self.assertIn('no-store', resposta['Cache-Control'])

    def test_espetaculo_inativo_continua_acessivel_a_quem_foi_liberado(self):
        self.dia1.ativo = False
        self.dia1.save()
        self.client.force_login(self.comprou)

        self.assertEqual(self.client.get(self.rota_dia1).status_code, 302)

    # ---------- "Minhas filmagens" ----------

    def test_minhas_filmagens_lista_so_as_liberadas(self):
        self.client.force_login(self.comprou)

        resposta = self.client.get(self.minhas)

        self.assertContains(resposta, 'Espetáculo - Dia 1')
        self.assertNotContains(resposta, 'Espetáculo - Dia 2')

    def test_minhas_filmagens_nunca_escreve_o_link_do_drive_na_pagina(self):
        self.dia2.usuarios_filmagem.add(self.comprou)
        self.client.force_login(self.comprou)

        resposta = self.client.get(self.minhas)

        html = resposta.content.decode()
        self.assertNotIn(LINK_DIA_1, html)
        self.assertNotIn(LINK_DIA_2, html)
        self.assertIn(self.rota_dia1, html)
        self.assertIn(self.rota_dia2, html)

    def test_quem_nao_comprou_ve_a_pagina_vazia_sem_nenhuma_filmagem(self):
        self.client.force_login(self.nao_comprou)

        resposta = self.client.get(self.minhas)

        self.assertContains(resposta, 'Nenhuma filmagem liberada')
        self.assertNotContains(resposta, 'Espetáculo - Dia 1')

    def test_minhas_filmagens_exige_login(self):
        resposta = self.client.get(self.minhas)

        self.assertEqual(resposta.status_code, 302)
        self.assertIn('login', resposta['Location'])

    def test_filmagem_sem_link_nao_aparece_na_lista(self):
        sem_link = _espetaculo('Sem link', -3, '')
        sem_link.usuarios_filmagem.add(self.comprou)
        self.client.force_login(self.comprou)

        resposta = self.client.get(self.minhas)

        self.assertNotContains(resposta, 'Sem link')

    # ---------- card na home e botão na listagem ----------

    def test_card_de_filmagens_so_aparece_para_quem_tem_acesso(self):
        self.client.force_login(self.comprou)
        self.assertTrue(self.client.get(HOME).context['tem_filmagens'])
        self.assertContains(
            self.client.get(reverse('espetaculo:lista_publica')), 'Minhas filmagens'
        )

        self.client.force_login(self.nao_comprou)
        self.assertFalse(self.client.get(HOME).context['tem_filmagens'])
        self.assertNotContains(
            self.client.get(reverse('espetaculo:lista_publica')), 'Minhas filmagens'
        )

    def test_visitante_anonimo_nao_ve_card_de_filmagens(self):
        resposta = self.client.get(reverse('espetaculo:lista_publica'))

        self.assertNotContains(resposta, 'Minhas filmagens')


@override_settings(STORAGES=STORAGES_TESTE)
class AdminFilmagensTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            'staff', 's@example.com', 'senha123', is_staff=True
        )
        self.dia1 = _espetaculo('Dia 1', -2)
        self.dia2 = _espetaculo('Dia 2', -1)
        self.url = reverse('admin_dashboard:espetaculo_filmagens', args=[self.dia1.pk])

        # Família com uma criança (responsável) e uma aluna adulta com login.
        self.mae = User.objects.create_user(
            'mae', 'mae@example.com', 'senha123',
            first_name='Maria', last_name='Souza',
        )
        Aluna.objects.create(nome='Ana Souza', responsavel=self.mae)
        self.adulta = User.objects.create_user(
            'adulta', 'adulta@example.com', 'senha123', first_name='Bruna',
        )
        Aluna.objects.create(
            nome='Bruna Lima', usuario=self.adulta, tipo_aluna='adulto'
        )
        self.sem_aluna = User.objects.create_user(
            'curioso', 'curioso@example.com', 'senha123'
        )

    def test_so_a_equipe_abre_a_pagina(self):
        comum = User.objects.create_user('comum', 'x@example.com', 'senha123')

        self.client.force_login(comum)
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 302)

        self.client.logout()
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 302)

    def test_a_pagina_lista_responsaveis_e_alunas_adultas_mas_nao_quem_nao_tem_aluna(self):
        self.client.force_login(self.staff)

        resposta = self.client.get(self.url)

        ids = [u['id'] for u in resposta.context['usuarios']]
        self.assertIn(self.mae.pk, ids)
        self.assertIn(self.adulta.pk, ids)
        self.assertNotIn(self.sem_aluna.pk, ids)
        self.assertContains(resposta, 'Ana Souza')   # a filha aparece junto da mãe
        self.assertContains(resposta, 'Aluna adulta')
        self.assertContains(resposta, 'Responsável')

    def test_salvar_grava_o_link_e_os_logins_marcados(self):
        self.client.force_login(self.staff)

        resposta = self.client.post(self.url, {
            'link_filmagem': '  https://drive.google.com/drive/folders/abc  ',
            'usuarios': [str(self.mae.pk), str(self.adulta.pk)],
        })

        self.assertRedirects(resposta, self.url)
        self.dia1.refresh_from_db()
        self.assertEqual(
            self.dia1.link_filmagem, 'https://drive.google.com/drive/folders/abc'
        )
        self.assertEqual(
            set(self.dia1.usuarios_filmagem.values_list('pk', flat=True)),
            {self.mae.pk, self.adulta.pk},
        )

    def test_salvar_um_dia_nao_mexe_no_outro(self):
        self.dia2.link_filmagem = 'https://drive.google.com/outro'
        self.dia2.save()
        self.dia2.usuarios_filmagem.add(self.mae)
        self.client.force_login(self.staff)

        self.client.post(self.url, {
            'link_filmagem': 'https://drive.google.com/drive/folders/abc',
            'usuarios': [str(self.adulta.pk)],
        })

        self.dia2.refresh_from_db()
        self.assertEqual(self.dia2.link_filmagem, 'https://drive.google.com/outro')
        self.assertEqual(
            list(self.dia2.usuarios_filmagem.values_list('pk', flat=True)),
            [self.mae.pk],
        )

    def test_desmarcar_remove_o_acesso(self):
        self.dia1.link_filmagem = 'https://drive.google.com/drive/folders/abc'
        self.dia1.save()
        self.dia1.usuarios_filmagem.add(self.mae, self.adulta)
        self.client.force_login(self.staff)

        self.client.post(self.url, {
            'link_filmagem': self.dia1.link_filmagem,
            'usuarios': [str(self.mae.pk)],
        })

        self.assertEqual(
            list(self.dia1.usuarios_filmagem.values_list('pk', flat=True)),
            [self.mae.pk],
        )

    def test_link_com_esquema_perigoso_e_recusado_e_nada_e_salvo(self):
        self.client.force_login(self.staff)

        for ruim in ['javascript:alert(1)', 'ftp://exemplo.com/a', 'drive.google.com/x', 'não é link']:
            resposta = self.client.post(self.url, {
                'link_filmagem': ruim,
                'usuarios': [str(self.mae.pk)],
            })

            self.assertEqual(resposta.status_code, 200, ruim)
            self.assertContains(resposta, 'não é válido')
            self.dia1.refresh_from_db()
            self.assertEqual(self.dia1.link_filmagem, '', ruim)
            self.assertEqual(self.dia1.usuarios_filmagem.count(), 0, ruim)

    def test_erro_no_link_nao_perde_o_que_foi_marcado(self):
        self.client.force_login(self.staff)

        resposta = self.client.post(self.url, {
            'link_filmagem': 'javascript:alert(1)',
            'usuarios': [str(self.mae.pk)],
        })

        marcados = [u['id'] for u in resposta.context['usuarios'] if u['marcado']]
        self.assertEqual(marcados, [self.mae.pk])
        self.assertEqual(resposta.context['link_filmagem'], 'javascript:alert(1)')

    def test_ids_invalidos_no_post_sao_ignorados(self):
        self.client.force_login(self.staff)

        resposta = self.client.post(self.url, {
            'link_filmagem': 'https://drive.google.com/drive/folders/abc',
            'usuarios': ['abc', '', '999999', str(self.mae.pk)],
        })

        self.assertRedirects(resposta, self.url)
        self.assertEqual(
            list(self.dia1.usuarios_filmagem.values_list('pk', flat=True)),
            [self.mae.pk],
        )

    def test_quem_ja_estava_marcado_continua_na_lista_para_poder_desmarcar(self):
        self.dia1.usuarios_filmagem.add(self.sem_aluna)
        self.client.force_login(self.staff)

        resposta = self.client.get(self.url)

        marcados = [u['id'] for u in resposta.context['usuarios'] if u['marcado']]
        self.assertEqual(marcados, [self.sem_aluna.pk])

    def test_a_tela_de_edicao_do_espetaculo_tem_o_botao_para_a_pagina(self):
        self.client.force_login(self.staff)

        resposta = self.client.get(
            reverse('admin_dashboard:espetaculo_editar', args=[self.dia1.pk])
        )

        self.assertContains(resposta, self.url)
