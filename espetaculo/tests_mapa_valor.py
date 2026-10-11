from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from espetaculo.models import (
    Assento,
    Espetaculo,
    MapaAssentos,
    ParticipacaoEspetaculo,
)
from usuarios.models import Aluna


# O storage de estáticos de produção (manifesto) exige `collectstatic`
# antes de renderizar templates com {% static %}; nos testes usamos o
# storage simples só para a página poder ser renderizada.
@override_settings(
    STORAGES={
        'default': {
            'BACKEND': 'django.core.files.storage.FileSystemStorage',
        },
        'staticfiles': {
            'BACKEND': (
                'django.contrib.staticfiles.storage.StaticFilesStorage'
            ),
        },
    }
)
class MapaPublicoValorTests(TestCase):
    def setUp(self):
        self.evento = Espetaculo.objects.create(
            titulo='Quebra-Nozes',
            descricao='x',
            tipo='evento',
            data_apresentacao=timezone.now() + timedelta(days=10),
            local='Teatro',
            endereco='Rua A',
            preco_ingresso=Decimal('50.00'),
            venda_aberta=True,
            venda_com_assentos_numerados=True,
        )
        mapa = MapaAssentos.objects.create(evento=self.evento)
        for numero in (1, 2, 3):
            Assento.objects.create(
                mapa=mapa,
                identificador=f'A{numero}',
                fileira='A',
                numero=numero,
                x_pct=Decimal(numero),
                y_pct=Decimal('1'),
            )

        self.url = reverse(
            'espetaculo:mapa_assentos_publico', args=[self.evento.pk]
        )

    def _preparar_sessao(self, valor_unitario='50.00'):
        sessao = self.client.session
        pk = self.evento.pk
        sessao[f'compra_evento_{pk}_nome_completo'] = 'Maria Silva'
        sessao[f'compra_evento_{pk}_whatsapp'] = '11912345678'
        if valor_unitario is not None:
            sessao[f'compra_evento_{pk}_valor_unitario'] = valor_unitario
        sessao.save()

    def test_mostra_valor_por_assento(self):
        self._preparar_sessao()

        resposta = self.client.get(self.url)

        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(resposta.context['mostrar_valor'])
        self.assertContains(resposta, 'R$ 50,00 por assento')
        # valor chega ao JavaScript com ponto decimal
        self.assertContains(resposta, 'data-valor-unitario="50.00"')
        self.assertContains(resposta, 'id="totalValor"')

    def test_valor_vem_da_sessao_que_e_o_que_sera_cobrado(self):
        self._preparar_sessao(valor_unitario='35.50')
        # preço do evento mudou depois: a cobrança usa o da sessão.
        Espetaculo.objects.filter(pk=self.evento.pk).update(
            preco_ingresso=Decimal('90.00')
        )

        resposta = self.client.get(self.url)

        self.assertContains(resposta, 'data-valor-unitario="35.50"')
        self.assertContains(resposta, 'R$ 35,50 por assento')

    def test_sem_valor_na_sessao_usa_preco_do_evento(self):
        self._preparar_sessao(valor_unitario=None)

        resposta = self.client.get(self.url)

        self.assertContains(resposta, 'data-valor-unitario="50.00"')

    def test_valor_invalido_na_sessao_usa_preco_do_evento(self):
        self._preparar_sessao(valor_unitario='lixo')

        resposta = self.client.get(self.url)

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'data-valor-unitario="50.00"')

    def test_evento_gratuito_nao_mostra_valor(self):
        Espetaculo.objects.filter(pk=self.evento.pk).update(
            preco_ingresso=Decimal('0.00')
        )
        self._preparar_sessao(valor_unitario='0.00')

        resposta = self.client.get(self.url)

        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(resposta.context['mostrar_valor'])
        self.assertNotContains(resposta, 'por assento')
        self.assertContains(resposta, 'data-valor-unitario="0"')

    def test_visitante_sem_login_nao_tem_gratuidade(self):
        self._preparar_sessao()

        resposta = self.client.get(self.url)

        self.assertEqual(resposta.context['gratuitas_disponiveis'], 0)
        self.assertNotContains(
            resposta, 'class="legenda-pill legenda-pill-gratis"'
        )

    def test_responsavel_com_aluna_participante_ve_gratuidades(self):
        User = get_user_model()
        responsavel = User.objects.create_user(
            'resp', 'resp@example.com', 'senha123'
        )
        for nome in ('Ana', 'Bia'):
            aluna = Aluna.objects.create(nome=nome, responsavel=responsavel)
            ParticipacaoEspetaculo.objects.create(
                espetaculo=self.evento, aluna=aluna, vai_dancar=True,
            )
        # Terceira aluna não vai dançar: não conta.
        outra = Aluna.objects.create(nome='Carla', responsavel=responsavel)
        ParticipacaoEspetaculo.objects.create(
            espetaculo=self.evento, aluna=outra, vai_dancar=False,
        )

        self.client.force_login(responsavel)
        self._preparar_sessao()

        resposta = self.client.get(self.url)

        self.assertEqual(resposta.context['gratuitas_disponiveis'], 2)
        self.assertContains(resposta, 'data-gratuitas="2"')
        self.assertContains(
            resposta, 'class="legenda-pill legenda-pill-gratis"'
        )
        self.assertContains(resposta, '2 gratuitos de aluna')

    def test_mesma_regra_de_cobranca_do_servidor(self):
        """
        O desconto exibido deve bater com quantidade_gratuita_disponivel,
        a mesma função que confirmar_selecao_assentos usa para cobrar.
        """
        from espetaculo.views import quantidade_gratuita_disponivel

        User = get_user_model()
        responsavel = User.objects.create_user(
            'resp2', 'resp2@example.com', 'senha123'
        )
        aluna = Aluna.objects.create(nome='Ana', responsavel=responsavel)
        ParticipacaoEspetaculo.objects.create(
            espetaculo=self.evento, aluna=aluna, vai_dancar=True,
        )

        self.client.force_login(responsavel)
        self._preparar_sessao()

        resposta = self.client.get(self.url)

        request = resposta.wsgi_request
        self.assertEqual(
            resposta.context['gratuitas_disponiveis'],
            quantidade_gratuita_disponivel(request, self.evento),
        )
