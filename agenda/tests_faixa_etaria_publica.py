"""
Telas públicas de agendamento de aula experimental (onde as famílias escolhem
a turma): mostram a faixa etária de cada turma, vinda do cadastro da turma.
"""

from html.parser import HTMLParser

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from agenda.models import ConfiguracaoAgendamento
from usuarios.models import Turma

STORAGES_TESTE = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'
    },
}


class _Extrator(HTMLParser):
    """Lê o HTML como o navegador: opções do menu e textos das <option>."""

    def __init__(self):
        super().__init__()
        self.opcoes_do_menu = []     # [{'value':..., 'text': data-text, 'corpo': texto}]
        self.options = []            # texto de cada <option> do <select>
        self._pilha = []
        self._atual = None
        self._dentro_option = False

    def handle_starttag(self, tag, attrs):
        atributos = dict(attrs)
        if tag == 'div' and 'select-option' in (atributos.get('class') or '').split():
            self._atual = {
                'value': atributos.get('data-value'),
                'text': atributos.get('data-text'),
                'corpo': '',
            }
            self.opcoes_do_menu.append(self._atual)
            self._pilha = [tag]
        elif self._atual is not None and tag == 'div':
            self._pilha.append(tag)
        if tag == 'option':
            self._dentro_option = True
            self.options.append('')

    def handle_endtag(self, tag):
        if self._atual is not None and tag == 'div':
            self._pilha.pop()
            if not self._pilha:
                self._atual = None
        if tag == 'option':
            self._dentro_option = False

    def handle_data(self, data):
        if self._atual is not None:
            self._atual['corpo'] += data
        if self._dentro_option:
            self.options[-1] += data


def _ler(resposta):
    extrator = _Extrator()
    extrator.feed(resposta.content.decode())
    return extrator


def _corpo(opcao):
    return ' '.join(opcao['corpo'].split())


@override_settings(STORAGES=STORAGES_TESTE)
class TelaGeralTests(TestCase):
    """/agenda/experimental/ : visitante, sem login."""

    def setUp(self):
        self.url = reverse('agendar')
        self.baby = self._turma('Baby Class', '3 a 5 anos')
        self.adulto = self._turma('Ballet Adulto', '16 anos em diante')
        self.sem_faixa = self._turma('Turma Sem Faixa', '')

    def _turma(self, nome, faixa, **extra):
        return Turma.objects.create(
            nome=nome, faixa_etaria=faixa, horario='14h',
            ativa=extra.pop('ativa', True),
            disponivel_experimental=extra.pop('disponivel', True),
        )

    def _opcoes(self, **params):
        resposta = self.client.get(self.url, params)
        self.assertEqual(resposta.status_code, 200)
        return {o['text'].split(' — ')[0]: o for o in _ler(resposta).opcoes_do_menu}

    # ---------- na lista de turmas ----------

    def test_cada_turma_mostra_a_sua_faixa_etaria(self):
        opcoes = self._opcoes()

        self.assertIn('Faixa etária: 3 a 5 anos', _corpo(opcoes['Baby Class']))
        self.assertIn(
            'Faixa etária: 16 anos em diante', _corpo(opcoes['Ballet Adulto'])
        )

    def test_a_faixa_de_uma_turma_nao_aparece_na_outra(self):
        opcoes = self._opcoes()
        self.assertNotIn('16 anos', _corpo(opcoes['Baby Class']))
        self.assertNotIn('3 a 5', _corpo(opcoes['Ballet Adulto']))

    def test_turma_sem_faixa_nao_mostra_a_linha(self):
        opcoes = self._opcoes()
        self.assertNotIn('Faixa etária', _corpo(opcoes['Turma Sem Faixa']))

    def test_a_faixa_vem_do_cadastro_da_turma(self):
        Turma.objects.filter(pk=self.baby.pk).update(faixa_etaria='4 a 6 anos')

        opcoes = self._opcoes()

        self.assertIn('Faixa etária: 4 a 6 anos', _corpo(opcoes['Baby Class']))
        self.assertNotIn('3 a 5 anos', _corpo(opcoes['Baby Class']))

    # ---------- no texto que fica no campo depois de escolher ----------

    def test_o_texto_escolhido_inclui_a_faixa_etaria(self):
        opcoes = self._opcoes()
        self.assertEqual(
            opcoes['Baby Class']['text'], 'Baby Class — 14h — 3 a 5 anos (R$ 25,00)'
        )

    def test_o_texto_escolhido_sem_faixa_fica_como_antes(self):
        opcoes = self._opcoes()
        self.assertEqual(
            opcoes['Turma Sem Faixa']['text'], 'Turma Sem Faixa — 14h (R$ 25,00)'
        )

    def test_turma_gratuita_mantem_o_aviso_depois_da_faixa(self):
        configuracao = ConfiguracaoAgendamento.obter()
        configuracao.campanha_gratuita_ativa = True
        configuracao.save()

        opcoes = self._opcoes()

        self.assertEqual(
            opcoes['Baby Class']['text'],
            'Baby Class — 14h — 3 a 5 anos (Gratuita)',
        )

    # ---------- cuidados ----------

    def test_aspas_e_simbolos_na_faixa_nao_quebram_a_pagina(self):
        Turma.objects.filter(pk=self.baby.pk).update(
            faixa_etaria='Até 5 "anos" <b>& cia'
        )

        resposta = self.client.get(self.url)
        extrator = _ler(resposta)
        opcao = next(o for o in extrator.opcoes_do_menu if o['value'] == str(self.baby.pk))

        # o atributo continua inteiro e legível para o navegador...
        self.assertEqual(
            opcao['text'], 'Baby Class — 14h — Até 5 "anos" <b>& cia (R$ 25,00)'
        )
        # ...e nenhum HTML vindo do cadastro é interpretado
        self.assertNotContains(resposta, '<b>& cia')

    def test_turma_inativa_ou_indisponivel_continua_fora_da_lista(self):
        self._turma('Inativa', '1 a 2 anos', ativa=False)
        self._turma('Fechada', '7 a 9 anos', disponivel=False)

        resposta = self.client.get(self.url)

        self.assertNotContains(resposta, 'Inativa')
        self.assertNotContains(resposta, 'Fechada')
        self.assertNotContains(resposta, '1 a 2 anos')
        self.assertNotContains(resposta, '7 a 9 anos')

    def test_a_faixa_continua_aparecendo_quando_o_formulario_volta_com_erro(self):
        resposta = self.client.post(self.url, {'aula': '', 'data': ''})

        self.assertEqual(resposta.status_code, 200)
        opcoes = {o['text'].split(' — ')[0]: o for o in _ler(resposta).opcoes_do_menu}
        self.assertIn('Faixa etária: 3 a 5 anos', _corpo(opcoes['Baby Class']))

    # ---------- esquecer de escolher a turma não pode dar erro 500 ----------

    def test_enviar_sem_escolher_a_turma_pede_para_escolher(self):
        # O campo da turma é um menu personalizado (campo escondido): o
        # navegador não o valida, então isto acontece de verdade.
        resposta = self.client.post(self.url, {'aula': '', 'data': '2030-01-07'})

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'Selecione uma aula válida.')

    def test_turma_com_valor_invalido_tambem_pede_para_escolher(self):
        for valor in ('abc', '1.5', ' ', '999999', '-1'):
            with self.subTest(valor=valor):
                resposta = self.client.post(
                    self.url, {'aula': valor, 'data': '2030-01-07'}
                )
                self.assertEqual(resposta.status_code, 200)
                self.assertContains(resposta, 'Selecione uma aula válida.')

    def test_enviar_sem_o_campo_da_turma_tambem_nao_da_erro(self):
        resposta = self.client.post(self.url, {'data': '2030-01-07'})
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'Selecione uma aula válida.')

    def test_turma_valida_segue_o_fluxo_de_sempre(self):
        # Turma escolhida e data inválida: continua caindo na validação da
        # data (e não na da turma).
        resposta = self.client.post(
            self.url, {'aula': str(self.baby.pk), 'data': 'lixo'}
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertNotContains(resposta, 'Selecione uma aula válida.')

    def test_sem_nenhuma_turma_a_mensagem_de_sempre(self):
        Turma.objects.all().delete()
        resposta = self.client.get(self.url)
        self.assertContains(resposta, 'Nenhuma aula disponível para agendamento.')


@override_settings(STORAGES=STORAGES_TESTE)
class TelaDaFamiliaLogadaTests(TestCase):
    """Família com login: a tela mostra a faixa etária em cada opção."""

    def setUp(self):
        self.usuario = User.objects.create_user('resp', 'r@example.com', 'senha123')
        self.client.force_login(self.usuario)
        self.url = reverse('agendar_aluna')

        self.baby = Turma.objects.create(
            nome='Baby Class', faixa_etaria='3 a 5 anos', horario='14h',
            ativa=True, disponivel_experimental=True,
        )
        self.sem_faixa = Turma.objects.create(
            nome='Turma Sem Faixa', faixa_etaria='', horario='15h',
            ativa=True, disponivel_experimental=True,
        )

    def _options(self):
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 200)
        return [' '.join(t.split()) for t in _ler(resposta).options]

    def test_a_tela_publica_geral_leva_a_familia_para_esta_tela(self):
        resposta = self.client.get(reverse('agendar'))
        self.assertRedirects(resposta, self.url, fetch_redirect_response=False)

    def test_cada_opcao_mostra_a_faixa_etaria(self):
        self.assertIn('Baby Class às 14h – 3 a 5 anos', self._options())

    def test_turma_sem_faixa_fica_como_antes(self):
        self.assertIn('Turma Sem Faixa às 15h', self._options())

    def test_a_faixa_acompanha_o_cadastro(self):
        Turma.objects.filter(pk=self.baby.pk).update(faixa_etaria='4 a 6 anos')
        self.assertIn('Baby Class às 14h – 4 a 6 anos', self._options())

    def test_turma_fora_da_lista_continua_fora(self):
        Turma.objects.create(
            nome='Fechada', faixa_etaria='7 a 9 anos', horario='9h',
            ativa=True, disponivel_experimental=False,
        )
        self.assertFalse(any('Fechada' in o for o in self._options()))

    def test_visitante_na_tela_da_familia_e_mandado_para_o_login(self):
        self.client.logout()
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 302)
        self.assertIn('login', resposta['Location'])

    def test_enviar_sem_escolher_a_turma_nao_da_erro(self):
        resposta = self.client.post(self.url, {
            'aluna_id': 'responsavel', 'aula': '', 'data': '2030-01-07',
        })
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'Escolha a aula')  # a tela volta a abrir

    def test_a_faixa_continua_na_tela_depois_do_erro(self):
        resposta = self.client.post(self.url, {
            'aluna_id': 'responsavel', 'aula': 'abc', 'data': '',
        })
        self.assertEqual(resposta.status_code, 200)
        options = [' '.join(t.split()) for t in _ler(resposta).options]
        self.assertIn('Baby Class às 14h – 3 a 5 anos', options)
