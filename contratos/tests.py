"""
Testes do app de contratos. Rodar com:  python manage.py test contratos

Os PDFs-modelo usados aqui são gerados na hora (não dependem dos contratos reais).
"""

import io
import re
from datetime import timedelta
from decimal import Decimal
from unittest import mock

import pypdf
from django.contrib.auth.models import User
from django.core import mail
from django.db import DatabaseError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from usuarios.models import Aluna, Perfil

from . import pdf as motor
from . import regras, servicos
from .models import BolsaAluna, CodigoAssinatura, Contrato, ModeloContrato, OpcaoBolsa

# Nos testes não há arquivos estáticos compilados (o projeto usa o armazenamento com manifesto).
ESTATICOS_SIMPLES = override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})

LINHAS_PADRAO = [
    'CONTRATO DE TESTE',
    'Contratante: [[NOME_RESPONSAVEL]]',
    'Aluna: [[NOME_ALUNA]]',
    'Nascimento: [[DATA_NASCIMENTO_ALUNA]]',
    'CPF: [[CPF]]',
    'RG: [[RG]]',
    'Endereco: [[ENDERECO]]',
    'Mensalidade de [[VALOR_MENSALIDADE_1__________]] por mes.',
    'Ano: [[ANO]]',
    'Imagem: [[AUTORIZACAO_IMAGEM]]',
    'Assinatura: [[ASSINATURA]]',
    'Data: [[DATA]]',
]
LINHAS_BOLSA = [
    'Percentual: [[BOLSA_PERCENTUAL]]',
    'Cheia: [[BOLSA_MENSALIDADE_CHEIA]]',
    'A pagar: [[BOLSA_MENSALIDADE_A_PAGAR]]',
]


def gerar_pdf(linhas):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setFont('Helvetica', 12)
    y = 780

    for linha in linhas:
        c.drawString(72, y, linha)
        y -= 24

    c.showPage()
    c.save()

    return buf.getvalue()


def texto_normalizado(conteudo):
    return re.sub(r'\s+', ' ', motor.extrair_texto(conteudo))


DADOS_VALIDOS = {
    'nome': 'Maria da Silva Santos',
    'cpf': '529.982.247-25',
    'rg': '12.345.678-9',
    'endereco': 'Rua das Flores, 123, Centro, Piedade - SP',
    'telefone': '(15) 99999-1234',
    'data_nascimento': '2015-03-20',
}


class RegrasTests(TestCase):
    def test_cpf(self):
        self.assertTrue(regras.validar_cpf('529.982.247-25'))
        self.assertTrue(regras.validar_cpf('52998224725'))
        self.assertFalse(regras.validar_cpf('529.982.247-26'))
        self.assertFalse(regras.validar_cpf('111.111.111-11'))
        self.assertFalse(regras.validar_cpf('123'))
        self.assertEqual(regras.formatar_cpf('52998224725'), '529.982.247-25')

    def test_dinheiro_por_extenso(self):
        casos = {
            '110': 'R$ 110,00 (cento e dez reais)',
            '114': 'R$ 114,00 (cento e catorze reais)',
            '125': 'R$ 125,00 (cento e vinte e cinco reais)',
            '85': 'R$ 85,00 (oitenta e cinco reais)',
            '0': 'R$ 0,00 (zero reais)',
            '1': 'R$ 1,00 (um real)',
            '100': 'R$ 100,00 (cem reais)',
            '1100': 'R$ 1.100,00 (mil e cem reais)',
            '1250': 'R$ 1.250,00 (mil duzentos e cinquenta reais)',
            '2000': 'R$ 2.000,00 (dois mil reais)',
            '82.5': 'R$ 82,50 (oitenta e dois reais e cinquenta centavos)',
            '0.5': 'R$ 0,50 (cinquenta centavos)',
        }

        for entrada, esperado in casos.items():
            self.assertEqual(regras.dinheiro(Decimal(entrada)), esperado)

    def test_parse_dinheiro(self):
        self.assertEqual(regras.parse_dinheiro('110'), Decimal('110.00'))
        self.assertEqual(regras.parse_dinheiro('110,5'), Decimal('110.50'))
        self.assertEqual(regras.parse_dinheiro('R$ 1.250,00'), Decimal('1250.00'))
        self.assertEqual(regras.parse_dinheiro('1.250'), Decimal('1250.00'))
        self.assertEqual(regras.parse_dinheiro('110.50'), Decimal('110.50'))
        self.assertIsNone(regras.parse_dinheiro('abc'))
        self.assertIsNone(regras.parse_dinheiro(''))
        self.assertIsNone(regras.parse_dinheiro('-5'))

    def test_bolsa(self):
        self.assertEqual(regras.formatar_percentual(Decimal('50.00')), '50%')
        self.assertEqual(regras.formatar_percentual(Decimal('33.50')), '33,5%')
        self.assertEqual(regras.calcular_a_pagar(Decimal('110'), Decimal('50')), Decimal('55.00'))
        self.assertEqual(regras.calcular_a_pagar(Decimal('110'), Decimal('100')), Decimal('0.00'))
        self.assertEqual(regras.calcular_a_pagar(Decimal('110'), Decimal('33.5')), Decimal('73.15'))


class MotorPdfTests(TestCase):
    def test_localiza_marcadores_e_espaco(self):
        achados, invalidos = motor.localizar_marcadores(gerar_pdf(LINHAS_PADRAO + ['Errado: [[cpf]]']))
        nomes = {a['nome'] for a in achados}

        self.assertEqual(nomes, {
            'NOME_RESPONSAVEL', 'NOME_ALUNA', 'DATA_NASCIMENTO_ALUNA', 'CPF', 'RG', 'ENDERECO',
            'VALOR_MENSALIDADE_1', 'ANO', 'AUTORIZACAO_IMAGEM', 'ASSINATURA', 'DATA',
        })
        self.assertEqual(len(invalidos), 1)
        self.assertIn('[[cpf]]', invalidos[0]['texto'])

    def test_preenche_e_remove_o_texto_do_marcador(self):
        original = gerar_pdf(LINHAS_PADRAO)
        valores = {
            'NOME_RESPONSAVEL': 'Maria da Silva Santos', 'NOME_ALUNA': 'Ana Silva', 'DATA_NASCIMENTO_ALUNA': '20/03/2015',
            'CPF': '529.982.247-25', 'RG': '12.345.678-9', 'ENDERECO': 'Rua das Flores, 123',
            'VALOR_MENSALIDADE_1': 'R$ 110,00 (cento e dez reais)', 'ANO': '2026',
            'AUTORIZACAO_IMAGEM': 'AUTORIZA o uso da imagem da aluna.',
            'ASSINATURA': 'Assinado eletronicamente por Maria', 'DATA': '11/11/2026',
        }
        preenchido, avisos = motor.preencher(original, valores)
        texto = texto_normalizado(preenchido)

        self.assertEqual(avisos, [])
        self.assertNotIn('[[', texto)

        for valor in valores.values():
            self.assertIn(valor, texto)

        self.assertIn('CONTRATO DE TESTE', texto)
        self.assertIn('por mes.', texto)

    def test_remocao_nao_move_nenhuma_outra_letra(self):
        original = gerar_pdf(LINHAS_PADRAO)
        limpo, removidas = motor.remover_marcadores(original)

        self.assertGreater(removidas, 100)

        antes = motor._coletar(original)[0]['registros']
        depois = motor._coletar(limpo)[0]['registros']
        marcadas = motor._indices_a_remover(antes, motor.PADRAO_MARCADOR)
        mantidas = [r for i, r in enumerate(antes) if i not in marcadas]

        self.assertEqual(len(mantidas), len(depois))

        for a, d in zip(mantidas, depois):
            self.assertEqual(a['texto'], d['texto'])
            self.assertAlmostEqual(a['x0'], d['x0'], delta=0.3)
            self.assertAlmostEqual(a['y0'], d['y0'], delta=0.3)

    def test_falta_de_valor_e_erro(self):
        with self.assertRaises(ValueError):
            motor.preencher(gerar_pdf(LINHAS_PADRAO), {'CPF': '1'})

    def test_valor_comprido_diminui_a_letra_mas_cabe(self):
        original = gerar_pdf(['Nome: [[NOME_RESPONSAVEL]]'])
        _, avisos = motor.preencher(original, {'NOME_RESPONSAVEL': 'Nome Muito Comprido ' * 6})

        self.assertEqual(len(avisos), 1)  # não cabe nem com letra pequena: avisa

        _, avisos = motor.preencher(original, {'NOME_RESPONSAVEL': 'Maria Aparecida de Albuquerque Santos Oliveira'})
        self.assertEqual(avisos, [])

    def test_pdf_so_de_imagem_e_recusado(self):
        from PIL import Image

        buf = io.BytesIO()
        Image.new('RGB', (600, 800), 'white').save(buf, 'PDF')

        self.assertIn('texto selecionável', motor.analisar_modelo(buf.getvalue())['erro'])
        self.assertIn('PDF', motor.analisar_modelo(b'isto nao e um pdf')['erro'])


@ESTATICOS_SIMPLES
class BaseContratoTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user('adm', email='adm@x.com', password='x', is_staff=True)
        self.resp = User.objects.create_user('maria', email='maria@x.com', password='x', first_name='Maria', last_name='Silva')
        Perfil.objects.create(user=self.resp, telefone='', is_responsavel=True)
        self.outra = User.objects.create_user('outra', email='outra@x.com', password='x')
        Perfil.objects.create(user=self.outra, telefone='', is_responsavel=True)

        self.admin = Client()
        self.admin.force_login(self.staff)
        self.fam = Client()
        self.fam.force_login(self.resp)
        self.fam_outra = Client()
        self.fam_outra.force_login(self.outra)

    def enviar_modelo(self, tipo, linhas, ano=2026, valores=None, ativar=True):
        modelo, erro, _ = servicos.criar_modelo(
            SimpleUploadedFile('m.pdf', gerar_pdf(linhas)), tipo, f'Modelo {tipo}', ano, self.staff,
        )
        self.assertIsNone(erro)
        modelo.valores = valores or {}
        modelo.save()

        if ativar:
            self.assertEqual(servicos.problemas_para_ativar(modelo), [])
            servicos.ativar_modelo(modelo)

        return modelo

    def modelo_padrao(self, **kw):
        return self.enviar_modelo('padrao', LINHAS_PADRAO, valores={'ANO': '2026', 'VALOR_MENSALIDADE_1': '110'}, **kw)

    def modelo_bolsista(self, **kw):
        return self.enviar_modelo('bolsista', LINHAS_PADRAO + LINHAS_BOLSA, valores={'ANO': '2026', 'VALOR_MENSALIDADE_1': '110'}, **kw)

    def nova_aluna(self, nome='Ana Silva', **kw):
        kw.setdefault('responsavel', self.resp)
        kw.setdefault('valor_mensalidade', Decimal('110'))

        return Aluna.objects.create(nome=nome, tipo_aluna='infantil', **kw)

    def preencher_dados(self, contrato, client=None):
        r = (client or self.fam).post(reverse('contratos:dados', args=[contrato.pk]), DADOS_VALIDOS)
        self.assertEqual(r.status_code, 302)
        contrato.refresh_from_db()

    def pedir_codigo(self, contrato, client=None):
        mail.outbox.clear()
        (client or self.fam).post(reverse('contratos:enviar_codigo', args=[contrato.pk]))

        return re.search(r'é: (\d{6})', mail.outbox[-1].body).group(1)


class ModelosETiposTests(BaseContratoTests):
    def test_ativacao_exige_os_valores_do_ano(self):
        modelo, _, _ = servicos.criar_modelo(SimpleUploadedFile('m.pdf', gerar_pdf(LINHAS_PADRAO)), 'padrao', 'M', 2026, self.staff)
        problemas = servicos.problemas_para_ativar(modelo)

        self.assertTrue(any('ANO' in p for p in problemas))
        self.assertTrue(any('VALOR_MENSALIDADE_1' in p for p in problemas))

        self.admin.post(reverse('contratos_admin:modelo_detalhe', args=[modelo.pk]), {'acao': 'ativar'})
        modelo.refresh_from_db()
        self.assertFalse(modelo.ativo)

        self.admin.post(
            reverse('contratos_admin:modelo_detalhe', args=[modelo.pk]),
            {'acao': 'salvar_valores', 'valor_ANO': '2026', 'valor_VALOR_MENSALIDADE_1': 'R$ 110'},
        )
        modelo.refresh_from_db()
        self.assertEqual(modelo.valores['VALOR_MENSALIDADE_1'], '110.00')

        self.admin.post(reverse('contratos_admin:modelo_detalhe', args=[modelo.pk]), {'acao': 'ativar'})
        modelo.refresh_from_db()
        self.assertTrue(modelo.ativo)
        self.assertEqual(regras.ano_ativo(), 2026)

    def test_marcadores_de_bolsa_so_valem_no_contrato_de_bolsista(self):
        modelo, _, _ = servicos.criar_modelo(
            SimpleUploadedFile('m.pdf', gerar_pdf(LINHAS_PADRAO + LINHAS_BOLSA)), 'padrao', 'M', 2026, self.staff,
        )
        modelo.valores = {'ANO': '2026', 'VALOR_MENSALIDADE_1': '110'}
        modelo.save()

        self.assertTrue(any('bolsa' in p.lower() for p in servicos.problemas_para_ativar(modelo)))

    def test_so_um_modelo_ativo_por_tipo(self):
        antigo = self.modelo_padrao()
        novo = self.modelo_padrao(ano=2027)
        antigo.refresh_from_db()

        self.assertFalse(antigo.ativo)
        self.assertTrue(novo.ativo)

    def test_upload_invalido_nao_cria_nada(self):
        for nome, conteudo in (('a.pdf', b'texto'), ('a.png', b'\x89PNG\r\n\x1a\n' + b'0' * 20)):
            self.admin.post(reverse('contratos_admin:modelos'), {'tipo': 'padrao', 'ano': '2026', 'arquivo': SimpleUploadedFile(nome, conteudo)})

        self.assertEqual(ModeloContrato.objects.count(), 0)

    def test_so_admin_acessa_as_telas_de_admin(self):
        for nome in ('lista', 'modelos', 'bolsas'):
            self.assertEqual(self.admin.get(reverse(f'contratos_admin:{nome}')).status_code, 200)
            self.assertEqual(self.fam.get(reverse(f'contratos_admin:{nome}')).status_code, 302)
            self.assertEqual(Client().get(reverse(f'contratos_admin:{nome}')).status_code, 302)


class ContratoPendenteTests(BaseContratoTests):
    def test_sem_modelo_ativo_nao_cria_contrato(self):
        self.nova_aluna()
        self.assertEqual(Contrato.objects.count(), 0)

    def test_aluna_nova_ganha_contrato_pendente(self):
        self.modelo_padrao()
        aluna = self.nova_aluna()
        contrato = Contrato.objects.get(aluna=aluna)

        self.assertEqual((contrato.status, contrato.ano, contrato.contratante), ('pendente', 2026, self.resp))

    def test_aluna_inativa_nao_ganha_contrato(self):
        self.modelo_padrao()
        self.nova_aluna(ativa=False)
        self.assertEqual(Contrato.objects.count(), 0)

    def test_gerar_pendentes_so_para_quem_falta(self):
        aluna = self.nova_aluna()
        sem_contato = Aluna.objects.create(nome='Sem Contato', tipo_aluna='infantil')
        self.modelo_padrao()

        criados, ano, sem = servicos.gerar_pendentes()
        self.assertEqual((criados, ano, [a.pk for a in sem]), (1, 2026, [sem_contato.pk]))
        self.assertEqual(servicos.gerar_pendentes()[0], 0)
        self.assertTrue(Contrato.objects.filter(aluna=aluna).exists())

    def test_nao_ha_dois_contratos_abertos_para_a_mesma_aluna(self):
        self.modelo_padrao()
        aluna = self.nova_aluna()

        self.assertIsNone(servicos.criar_contrato_pendente(aluna))

        contrato = Contrato.objects.get(aluna=aluna)
        servicos.anular(contrato, 'teste')
        self.assertIsNotNone(servicos.criar_contrato_pendente(aluna))
        self.assertEqual(Contrato.objects.filter(aluna=aluna).count(), 2)

    def test_aluna_adulta_e_a_propria_contratante(self):
        self.modelo_padrao()
        adulta = User.objects.create_user('adulta', email='adulta@x.com', password='x')
        aluna = Aluna.objects.create(nome='Joana', tipo_aluna='adulto', usuario=adulta)

        self.assertEqual(Contrato.objects.get(aluna=aluna).contratante, adulta)


class BolsaTests(BaseContratoTests):
    def setUp(self):
        super().setUp()
        self.op50 = OpcaoBolsa.objects.create(nome='Bolsa 50%', percentual=Decimal('50'))
        self.dados_aluna = {
            'nome': 'Bia', 'genero': 'F', 'ativa': 'on', 'tipo_aluna': 'infantil', 'responsavel': self.resp.pk,
            'valor_mensalidade': '110', 'dia_vencimento': '10',
        }

    def test_criar_aluna_bolsista_pelo_admin(self):
        self.modelo_padrao()
        r = self.admin.post(
            reverse('admin_dashboard:aluna_criar'), {**self.dados_aluna, 'e_bolsista': 'on', 'opcao_bolsa': self.op50.pk},
        )
        self.assertEqual(r.status_code, 302)

        aluna = Aluna.objects.get(nome='Bia')
        self.assertEqual(aluna.bolsa.opcao, self.op50)
        self.assertTrue(Contrato.objects.filter(aluna=aluna).exists())

    def test_bolsista_sem_escolha_ou_sem_valor_nao_cria_a_aluna(self):
        for extra in ({'e_bolsista': 'on'}, {'e_bolsista': 'on', 'opcao_bolsa': self.op50.pk, 'valor_mensalidade': ''}):
            self.admin.post(reverse('admin_dashboard:aluna_criar'), {**self.dados_aluna, **extra})

        self.assertFalse(Aluna.objects.filter(nome='Bia').exists())

    def test_editar_aluna_liga_e_desliga_a_bolsa(self):
        aluna = self.nova_aluna('Bia')
        url = reverse('admin_dashboard:aluna_editar', args=[aluna.pk])
        base = {'nome': 'Bia', 'ativa': 'on', 'valor_mensalidade': '110', 'dia_vencimento': '10', 'responsavel': self.resp.pk, 'cpf': ''}

        self.admin.post(url, {**base, 'e_bolsista': 'on', 'opcao_bolsa': self.op50.pk})
        self.assertTrue(BolsaAluna.objects.filter(aluna=aluna).exists())

        self.admin.post(url, base)
        self.assertFalse(BolsaAluna.objects.filter(aluna=aluna).exists())

    def test_contrato_de_bolsista_usa_o_modelo_de_bolsista_e_calcula_os_valores(self):
        self.modelo_padrao()
        self.modelo_bolsista()
        aluna = self.nova_aluna('Bia')
        BolsaAluna.objects.create(aluna=aluna, opcao=self.op50)
        contrato = Contrato.objects.get(aluna=aluna)

        self.preencher_dados(contrato)
        self.assertEqual(contrato.tipo, 'bolsista')

        texto = texto_normalizado(self.fam.get(reverse('contratos:pdf', args=[contrato.pk, 'previa'])).content)
        self.assertIn('Percentual: 50%', texto)
        self.assertIn('Cheia: R$ 110,00 (cento e dez reais)', texto)
        self.assertIn('A pagar: R$ 55,00 (cinquenta e cinco reais)', texto)

    def test_trocar_a_bolsa_depois_de_imprimir_invalida_a_versao_impressa(self):
        self.modelo_padrao()
        self.modelo_bolsista()
        aluna = self.nova_aluna('Bia')
        contrato = Contrato.objects.get(aluna=aluna)

        self.preencher_dados(contrato)
        self.fam.get(reverse('contratos:pdf', args=[contrato.pk, 'imprimir']))
        contrato.refresh_from_db()
        self.assertEqual(contrato.status, 'aguardando_papel')

        servicos.salvar_bolsa_da_aluna(aluna, {'e_bolsista': 'on', 'opcao_bolsa': str(self.op50.pk)})
        contrato.refresh_from_db()
        self.assertEqual(contrato.status, 'dados_preenchidos')


class FluxoDaFamiliaTests(BaseContratoTests):
    def setUp(self):
        super().setUp()
        self.modelo = self.modelo_padrao()
        self.aluna = self.nova_aluna()
        self.contrato = Contrato.objects.get(aluna=self.aluna)

    def assinar(self, codigo):
        return self.fam.post(reverse('contratos:assinar', args=[self.contrato.pk]), {'codigo': codigo, 'concordo': 'on'})

    def test_outra_familia_nao_acessa(self):
        for nome in ('dados', 'revisar', 'assinar'):
            self.assertEqual(self.fam_outra.get(reverse(f'contratos:{nome}', args=[self.contrato.pk])).status_code, 404)

        self.assertEqual(self.fam_outra.post(reverse('contratos:enviar_codigo', args=[self.contrato.pk])).status_code, 404)
        self.assertEqual(Client().get(reverse('contratos:lista')).status_code, 302)

    def test_validacao_do_formulario(self):
        r = self.fam.post(reverse('contratos:dados', args=[self.contrato.pk]), {**DADOS_VALIDOS, 'cpf': '111.111.111-11'})
        self.assertContains(r, 'CPF inválido')

        self.contrato.refresh_from_db()
        self.assertEqual(self.contrato.status, 'pendente')

    def test_dados_ficam_salvos_no_perfil(self):
        self.preencher_dados(self.contrato)
        perfil = Perfil.objects.get(user=self.resp)

        self.assertEqual((perfil.cpf, perfil.rg), ('529.982.247-25', '12.345.678-9'))
        self.assertEqual(self.contrato.status, 'dados_preenchidos')

    def test_fluxo_completo_de_assinatura(self):
        self.preencher_dados(self.contrato)
        self.fam.get(reverse('contratos:revisar', args=[self.contrato.pk]))
        codigo = self.pedir_codigo(self.contrato)

        self.assertEqual(mail.outbox[-1].to, ['maria@x.com'])
        self.assertNotEqual(CodigoAssinatura.objects.get(contrato=self.contrato).codigo_hash, codigo)

        r = self.assinar(codigo)
        self.assertEqual(r.status_code, 302)

        c = Contrato.objects.get(pk=self.contrato.pk)
        self.assertEqual(c.status, 'assinado_digital')
        self.assertEqual(len(pypdf.PdfReader(io.BytesIO(c.pdf_assinado_bytes)).pages), 2)  # contrato + termo

        texto = texto_normalizado(c.pdf_assinado_bytes)
        self.assertIn('Assinado eletronicamente por Maria da Silva Santos', texto)
        self.assertIn('TERMO DE ASSINATURA ELETRÔNICA', texto)
        self.assertIn(c.hash_conteudo, texto.replace(' ', ''))
        self.assertNotIn('[[', texto)

        # cópia por e-mail com o PDF anexado
        self.assertEqual(mail.outbox[-1].attachments[0][1], c.pdf_assinado_bytes)

        # só quem é da família baixa; e não dá para assinar de novo
        self.assertEqual(self.fam.get(reverse('contratos:pdf', args=[c.pk, 'assinado'])).status_code, 200)
        self.assertEqual(self.fam_outra.get(reverse('contratos:pdf', args=[c.pk, 'assinado'])).status_code, 404)
        self.assertEqual(self.assinar(codigo).status_code, 302)
        self.assertEqual(Contrato.objects.get(pk=c.pk).pdf_assinado_bytes, c.pdf_assinado_bytes)

    def test_codigo_errado_conta_tentativas_e_bloqueia(self):
        """Regressão: a contagem de tentativas já foi desfeita por um erro dentro da transação."""
        self.preencher_dados(self.contrato)
        self.fam.get(reverse('contratos:revisar', args=[self.contrato.pk]))
        codigo = self.pedir_codigo(self.contrato)
        errado = '000000' if codigo != '000000' else '111111'

        for i in range(1, 6):
            self.assinar(errado)
            self.assertEqual(CodigoAssinatura.objects.get(contrato=self.contrato, usado=False).tentativas, i)

        # mesmo o código certo não vale mais; a pessoa volta para a conferência com a mensagem
        r = self.fam.post(
            reverse('contratos:assinar', args=[self.contrato.pk]), {'codigo': codigo, 'concordo': 'on'}, follow=True,
        )
        self.assertContains(r, 'Muitas tentativas')
        self.assertNotEqual(Contrato.objects.get(pk=self.contrato.pk).status, 'assinado_digital')

    def test_codigo_vencido(self):
        self.preencher_dados(self.contrato)
        self.fam.get(reverse('contratos:revisar', args=[self.contrato.pk]))
        codigo = self.pedir_codigo(self.contrato)
        CodigoAssinatura.objects.filter(contrato=self.contrato).update(expira_em=timezone.now() - timedelta(minutes=1))

        self.assertContains(self.assinar(codigo), 'expirou')

    def test_novo_codigo_so_depois_de_um_minuto(self):
        self.preencher_dados(self.contrato)
        self.pedir_codigo(self.contrato)
        r = self.fam.post(reverse('contratos:enviar_codigo', args=[self.contrato.pk]), follow=True)

        self.assertContains(r, 'Aguarde')
        self.assertEqual(len(mail.outbox), 1)

    def test_falha_no_envio_do_email_nao_deixa_codigo_valendo(self):
        self.preencher_dados(self.contrato)

        with mock.patch('contratos.servicos.EmailMessage.send', side_effect=Exception('smtp')):
            r = self.fam.post(reverse('contratos:enviar_codigo', args=[self.contrato.pk]), follow=True)

        self.assertContains(r, 'Não foi possível enviar o e-mail')
        self.assertFalse(CodigoAssinatura.objects.filter(contrato=self.contrato, usado=False).exists())

    def test_contrato_alterado_depois_da_conferencia_nao_pode_ser_assinado(self):
        self.preencher_dados(self.contrato)
        self.fam.get(reverse('contratos:revisar', args=[self.contrato.pk]))
        codigo = self.pedir_codigo(self.contrato)

        self.modelo.valores['VALOR_MENSALIDADE_1'] = '130.00'
        self.modelo.save()

        r = self.assinar(codigo)
        self.assertEqual(r.headers['Location'], reverse('contratos:revisar', args=[self.contrato.pk]))
        self.assertEqual(Contrato.objects.get(pk=self.contrato.pk).status, 'dados_preenchidos')

        # conferindo de novo (o contrato já mostra o valor novo), assina normalmente
        texto = texto_normalizado(self.fam.get(reverse('contratos:pdf', args=[self.contrato.pk, 'previa'])).content)
        self.assertIn('R$ 130,00 (cento e trinta reais)', texto)

        CodigoAssinatura.objects.filter(contrato=self.contrato).update(criado_em=timezone.now() - timedelta(seconds=120))
        self.assinar(self.pedir_codigo(self.contrato))

        c = Contrato.objects.get(pk=self.contrato.pk)
        self.assertEqual(c.status, 'assinado_digital')
        self.assertIn('R$ 130,00', c.dados['campos_ano']['VALOR_MENSALIDADE_1'])  # valor congelado no contrato

    def test_imprimir_marca_aguardando_papel_e_deixa_assinatura_em_branco(self):
        self.preencher_dados(self.contrato)
        r = self.fam.get(reverse('contratos:pdf', args=[self.contrato.pk, 'imprimir']))
        self.contrato.refresh_from_db()

        self.assertEqual(self.contrato.status, 'aguardando_papel')
        self.assertIn('____ / ____ / ________', texto_normalizado(r.content))
        self.assertIn('no-store', r['Cache-Control'])


class ScanEAnulacaoTests(BaseContratoTests):
    def setUp(self):
        super().setUp()
        self.modelo_padrao()
        self.contrato = Contrato.objects.get(aluna=self.nova_aluna())

    def enviar(self, nome, conteudo, **extra):
        return self.admin.post(
            reverse('contratos_admin:acao', args=[self.contrato.pk]),
            {'acao': 'scan', **extra, 'arquivo': SimpleUploadedFile(nome, conteudo)},
        )

    def test_arquivos_invalidos_sao_recusados(self):
        grande = b'%PDF-1.4' + b'0' * (servicos.TAMANHO_MAXIMO_SCAN + 1)

        for nome, conteudo in (('a.txt', b'texto'), ('vazio.pdf', b''), ('grande.pdf', grande), ('falso.pdf', b'MZ programa')):
            self.enviar(nome, conteudo)
            self.contrato.refresh_from_db()
            self.assertFalse(self.contrato.tem_scan, nome)
            self.assertEqual(self.contrato.status, 'pendente')

    def test_pdf_jpg_e_png_sao_aceitos_conferindo_o_conteudo(self):
        from PIL import Image

        for formato, tipo in (('PNG', 'image/png'), ('JPEG', 'image/jpeg')):
            buf = io.BytesIO()
            Image.new('RGB', (40, 40), 'white').save(buf, formato)
            self.enviar('qualquer-nome.pdf', buf.getvalue())
            self.contrato.refresh_from_db()
            self.assertEqual(self.contrato.scan_tipo, tipo)

        self.enviar('c.pdf', gerar_pdf(LINHAS_PADRAO))
        self.contrato.refresh_from_db()
        self.assertEqual((self.contrato.status, self.contrato.scan_tipo, self.contrato.scan_enviado_por), ('assinado_papel', 'application/pdf', self.staff))

        r = self.admin.get(reverse('contratos_admin:download', args=[self.contrato.pk, 'scan']))
        self.assertEqual((r.status_code, r['Content-Type']), (200, 'application/pdf'))

    def test_upload_pela_pagina_da_aluna_volta_para_a_pagina_da_aluna(self):
        r = self.enviar('c.pdf', gerar_pdf(LINHAS_PADRAO), voltar='aluna')
        self.assertEqual(r.headers['Location'], reverse('admin_dashboard:aluna_detalhes', args=[self.contrato.aluna_id]))

    def test_contrato_assinado_digitalmente_nao_aceita_scan(self):
        Contrato.objects.filter(pk=self.contrato.pk).update(status='assinado_digital')
        self.enviar('c.pdf', gerar_pdf(LINHAS_PADRAO))

        self.assertFalse(Contrato.objects.get(pk=self.contrato.pk).tem_scan)

    def test_anular_exige_motivo(self):
        url = reverse('contratos_admin:acao', args=[self.contrato.pk])

        self.admin.post(url, {'acao': 'anular', 'motivo': ''})
        self.assertEqual(Contrato.objects.get(pk=self.contrato.pk).status, 'pendente')

        self.admin.post(url, {'acao': 'anular', 'motivo': 'Dados errados'})
        self.assertEqual(Contrato.objects.get(pk=self.contrato.pk).status, 'anulado')
        self.assertNotContains(self.fam.get(reverse('contratos:lista')), 'Ana Silva')

    def test_familia_nao_usa_as_rotas_de_download_do_admin(self):
        self.assertEqual(self.fam.get(reverse('contratos_admin:download', args=[self.contrato.pk, 'scan'])).status_code, 302)


class TelasDeAlunaTests(BaseContratoTests):
    def test_formularios_e_ficha_da_aluna_mostram_bolsa_e_contrato(self):
        OpcaoBolsa.objects.create(nome='Bolsa 50%', percentual=Decimal('50'))
        self.modelo_padrao()
        aluna = self.nova_aluna()

        self.assertContains(self.admin.get(reverse('admin_dashboard:aluna_criar')), 'É bolsista?')
        self.assertContains(self.admin.get(reverse('admin_dashboard:aluna_editar', args=[aluna.pk])), 'É bolsista?')

        ficha = self.admin.get(reverse('admin_dashboard:aluna_detalhes', args=[aluna.pk]))
        self.assertContains(ficha, 'Contrato 2026')
        self.assertContains(ficha, 'Pendente')

    def test_painel_da_familia_mostra_o_contrato_logo_depois_das_mensalidades(self):
        self.modelo_padrao()
        self.nova_aluna()
        html = self.fam.get(reverse('dashboard')).content.decode()

        self.assertIn('1 pendente', html)
        self.assertLess(html.index('Ver Mensalidades'), html.index('📄 Contrato'))


class DataNascimentoDaAlunaTests(BaseContratoTests):
    def setUp(self):
        super().setUp()
        self.modelo = self.modelo_padrao()
        self.aluna = self.nova_aluna()
        self.contrato = Contrato.objects.get(aluna=self.aluna)
        self.url = reverse('contratos:dados', args=[self.contrato.pk])

    def test_e_obrigatoria_e_validada(self):
        casos = {
            '': 'Informe a data de nascimento',
            'abc': 'Informe a data de nascimento',
            '1900-01-01': 'Confira a data de nascimento',
            (timezone.localdate() + timedelta(days=1)).isoformat(): 'Confira a data de nascimento',
        }

        for valor, mensagem in casos.items():
            r = self.fam.post(self.url, {**DADOS_VALIDOS, 'data_nascimento': valor})
            self.assertContains(r, mensagem)

        self.contrato.refresh_from_db()
        self.assertEqual(self.contrato.status, 'pendente')

    def test_aceita_data_no_formato_brasileiro(self):
        self.fam.post(self.url, {**DADOS_VALIDOS, 'data_nascimento': '20/03/2015'})
        self.contrato.refresh_from_db()

        self.assertEqual(self.contrato.dados['aluna']['data_nascimento'], '2015-03-20')

    def test_vem_preenchida_com_a_data_do_cadastro_da_aluna(self):
        self.aluna.data_nascimento = '2014-05-10'
        self.aluna.save()

        self.assertContains(self.fam.get(self.url), 'value="2014-05-10"')

    def test_aparece_no_contrato(self):
        self.preencher_dados(self.contrato)
        texto = texto_normalizado(self.fam.get(reverse('contratos:pdf', args=[self.contrato.pk, 'previa'])).content)

        self.assertIn('Nascimento: 20/03/2015', texto)
        self.assertContains(self.fam.get(reverse('contratos:revisar', args=[self.contrato.pk])), '20/03/2015')

    def test_fica_salva_no_cadastro_quando_estava_vazia(self):
        self.assertIsNone(self.aluna.data_nascimento)
        self.preencher_dados(self.contrato)
        self.aluna.refresh_from_db()

        self.assertEqual(str(self.aluna.data_nascimento), '2015-03-20')

    def test_nao_sobrescreve_o_cadastro_e_avisa_o_admin_quando_for_diferente(self):
        self.aluna.data_nascimento = '2014-05-10'
        self.aluna.save()
        self.preencher_dados(self.contrato)
        self.aluna.refresh_from_db()

        self.assertEqual(str(self.aluna.data_nascimento), '2014-05-10')  # cadastro intacto
        self.assertEqual(self.contrato.dados['aluna']['data_nascimento'], '2015-03-20')  # contrato usa a informada

        pagina = self.admin.get(reverse('contratos_admin:detalhe', args=[self.contrato.pk]))
        self.assertContains(pagina, 'diferente da que está no cadastro')

    def test_modelo_sem_o_marcador_nao_pode_ser_ativado(self):
        linhas = [l for l in LINHAS_PADRAO if 'DATA_NASCIMENTO_ALUNA' not in l]
        modelo, _, _ = servicos.criar_modelo(SimpleUploadedFile('m.pdf', gerar_pdf(linhas)), 'padrao', 'M', 2027, self.staff)
        modelo.valores = {'ANO': '2027', 'VALOR_MENSALIDADE_1': '110'}
        modelo.save()

        self.assertTrue(any('DATA_NASCIMENTO_ALUNA' in p for p in servicos.problemas_para_ativar(modelo)))


class TabelasAindaNaoCriadasTests(BaseContratoTests):
    """Se a migração não rodou, as telas que já existiam não podem quebrar (erro 500)."""

    def test_telas_antigas_continuam_abrindo(self):
        self.modelo_padrao()
        aluna = self.nova_aluna()
        sem_tabela = DatabaseError('relation "contratos_contrato" does not exist')

        with mock.patch('contratos.templatetags.contratos_tags.Contrato') as contrato, \
                mock.patch('contratos.templatetags.contratos_tags.OpcaoBolsa') as opcao:
            contrato.objects.filter.side_effect = sem_tabela
            opcao.objects.filter.side_effect = sem_tabela

            self.assertEqual(self.fam.get(reverse('dashboard')).status_code, 200)

            for nome, args in (('aluna_criar', []), ('aluna_editar', [aluna.pk]), ('aluna_detalhes', [aluna.pk])):
                r = self.admin.get(reverse(f'admin_dashboard:{nome}', args=args))
                self.assertEqual(r.status_code, 200, nome)
                self.assertContains(r, 'não foram aplicadas')
