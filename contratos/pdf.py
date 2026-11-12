"""
Motor de PDF dos contratos.

O PDF-modelo traz marcadores no texto, como [[CPF]]. Para preencher:
  1. achamos cada marcador (posição exata na página);
  2. apagamos do arquivo as letras do marcador (para o texto do PDF ficar limpo,
     pesquisável e copiável) e conferimos que nada mais mudou de lugar;
  3. escrevemos o valor ali, na mesma linha, diminuindo a letra se não couber.

Se a remoção das letras não puder ser feita com segurança em algum PDF, o marcador
só é coberto por um retângulo branco (o visual é o mesmo; o texto do marcador
fica "por baixo" no arquivo).

Este módulo importa bibliotecas de PDF. Ele é carregado só quando um contrato é
analisado ou gerado, para que um problema nelas não derrube o resto do site.
"""

import hashlib
import io
import logging
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path
from xml.sax.saxutils import escape

import pdfplumber
import pypdf
from pdfminer.converter import PDFLayoutAnalyzer
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfparser import PDFParser
from pypdf.generic import ArrayObject, ByteStringObject, ContentStream, FloatObject
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from . import regras

logger = logging.getLogger(__name__)

FONTES = Path(__file__).resolve().parent / 'fontes'
FONTE = 'ContratoSerif'
FONTE_NEGRITO = 'ContratoSerif-Bold'
TAMANHO_MINIMO = 7.5
MARGEM_DIREITA = 72  # 1 polegada, como nos contratos

PADRAO_MARCADOR = re.compile(r'\[\[([A-Z0-9_]*[A-Z0-9])_*\]\]')


def _registrar_fontes():
    if FONTE not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(FONTE, str(FONTES / 'Caladea-Regular.ttf')))
        pdfmetrics.registerFont(TTFont(FONTE_NEGRITO, str(FONTES / 'Caladea-Bold.ttf')))
        pdfmetrics.registerFontFamily(
            FONTE, normal=FONTE, bold=FONTE_NEGRITO, italic=FONTE, boldItalic=FONTE_NEGRITO,
        )


def largura_texto(texto, tamanho, negrito=False):
    _registrar_fontes()
    return pdfmetrics.stringWidth(texto, FONTE_NEGRITO if negrito else FONTE, tamanho)


def hash_pdf(conteudo):
    return hashlib.sha256(conteudo).hexdigest()


# --------------------------------------------------------------- análise do PDF

def localizar_marcadores(pdf_bytes):
    """
    Lê o PDF e devolve (marcadores, invalidos).

    marcadores: lista de dicts com nome, página, posição e o espaço livre na linha.
    invalidos: textos que começam com [[ mas não são um marcador válido.
    """
    marcadores = []
    invalidos = []

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for n, pagina in enumerate(pdf.pages):
            altura = float(pagina.height)
            limite_direito = float(pagina.width) - MARGEM_DIREITA
            palavras = pagina.extract_words()
            caracteres = pagina.chars

            for w in palavras:
                if '[[' not in w['text']:
                    continue

                cs = sorted(
                    (
                        c for c in caracteres
                        if c['x0'] >= w['x0'] - 0.5
                        and c['x1'] <= w['x1'] + 0.5
                        and abs(c['top'] - w['top']) < 2
                    ),
                    key=lambda c: c['x0'],
                )
                texto = ''.join(c['text'] for c in cs)
                m = PADRAO_MARCADOR.search(texto)

                if not m:
                    invalidos.append({'texto': texto, 'pagina': n + 1})
                    continue

                sufixo = texto[m.end():]
                na_linha = [o for o in palavras if abs(o['top'] - w['top']) < 3]
                seguintes = [o for o in na_linha if o['x0'] > w['x1'] + 0.5]
                limite = (min(o['x0'] for o in seguintes) - 3) if seguintes else limite_direito
                x0 = cs[m.start()]['x0']

                marcadores.append({
                    'nome': m.group(1),
                    'pagina': n,
                    'x0': x0,
                    'x1': cs[m.end() - 1]['x1'],
                    'x1_total': cs[-1]['x1'] if sufixo else cs[m.end() - 1]['x1'],
                    'sufixo': sufixo,
                    'top': w['top'],
                    'bottom': w['bottom'],
                    'altura_pagina': altura,
                    'tamanho': float(cs[m.start()]['size']),
                    'negrito': 'bold' in cs[m.start()]['fontname'].lower(),
                    'limite': limite,
                    'contexto': ' '.join(
                        o['text'] for o in sorted(na_linha, key=lambda o: o['x0'])
                    )[:220],
                })

    return marcadores, invalidos


def analisar_modelo(pdf_bytes):
    """
    Analisa um PDF-modelo enviado pelo admin.

    Devolve dict com: marcadores (para guardar no banco), invalidos, paginas, erro.
    """
    try:
        leitor = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        paginas = len(leitor.pages)
    except Exception:
        return {'erro': 'Não foi possível ler este arquivo como PDF.'}

    try:
        marcadores, invalidos = localizar_marcadores(pdf_bytes)

        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            tem_texto = any(p.extract_text() for p in pdf.pages)
    except Exception:
        return {'erro': 'Não foi possível analisar o texto deste PDF.'}

    if not tem_texto:
        return {
            'erro': (
                'Este PDF não tem texto selecionável (parece uma foto ou um '
                'documento escaneado). Exporte o contrato como PDF direto do '
                'Google Docs ou do Word.'
            ),
        }

    resumo = [
        {
            'nome': m['nome'],
            'pagina': m['pagina'] + 1,
            'contexto': m['contexto'],
            'largura_livre': round(m['limite'] - m['x0'], 1),
            'tamanho': round(m['tamanho'], 1),
            'negrito': m['negrito'],
        }
        for m in marcadores
    ]

    return {'marcadores': resumo, 'invalidos': invalidos, 'paginas': paginas, 'erro': None}


def avisos_de_espaco(marcadores):
    """Avisos para marcadores cujo valor, mesmo com letra pequena, não cabe no espaço."""
    avisos = []

    for m in marcadores:
        amostra = regras.amostra_marcador(m['nome'])
        necessario = largura_texto(amostra, TAMANHO_MINIMO, m.get('negrito', False))

        if m['largura_livre'] < necessario:
            avisos.append(
                f'[[{m["nome"]}]] (página {m["pagina"]}): o espaço até a próxima '
                f'palavra da linha é curto para um valor como "{amostra}". '
                'Deixe mais espaço depois do marcador (ou ponha-o no fim da linha).'
            )

    return avisos



# --------------------------------------------------- remoção do texto dos marcadores

class _Falha(Exception):
    """Algo no PDF impede a remoção segura do texto (usamos o plano B: só cobrir)."""


class _Coletor(PDFLayoutAnalyzer):
    """Anota cada caractere na ordem em que o arquivo o desenha, e de qual comando ele veio."""

    def __init__(self, rsrcmgr):
        super().__init__(rsrcmgr, pageno=1, laparams=None)
        self.operacoes = 0
        self.registros = []
        self._k = 0

    def nova_operacao(self):
        self.operacoes += 1
        self._k = 0

    def render_char(self, matrix, font, fontsize, scaling, rise, cid, ncs, graphicstate):
        avanco = super().render_char(matrix, font, fontsize, scaling, rise, cid, ncs, graphicstate)
        item = self.cur_item._objs[-1]
        self.registros.append({
            'op': self.operacoes - 1,
            'k': self._k,
            'texto': item.get_text(),
            'largura': font.char_width(cid),
            'x0': item.x0,
            'y0': item.y0,
        })
        self._k += 1

        return avanco


class _Interprete(PDFPageInterpreter):
    def do_TJ(self, seq):  # todo comando de mostrar texto (Tj, TJ, ' e ") passa por aqui
        self.device.nova_operacao()
        super().do_TJ(seq)


def _coletar(pdf_bytes):
    """Por página: {'registros': [...], 'operacoes': N}, na ordem de desenho."""
    paginas = []
    documento = PDFDocument(PDFParser(io.BytesIO(pdf_bytes)))
    recursos = PDFResourceManager()

    for pagina in PDFPage.create_pages(documento):
        coletor = _Coletor(recursos)
        _Interprete(recursos, coletor).process_page(pagina)
        paginas.append({'registros': coletor.registros, 'operacoes': coletor.operacoes})

    return paginas


def _indices_a_remover(registros, padrao):
    """Índices (em `registros`) das letras que formam marcadores."""
    texto = []
    mapa = []

    for i, r in enumerate(registros):
        for letra in r['texto']:
            texto.append(letra)
            mapa.append(i)

    remover = set()

    for m in padrao.finditer(''.join(texto)):
        remover.update(mapa[p] for p in range(m.start(), m.end()))

    return remover


def _bytes_da_string(objeto):
    if isinstance(objeto, ByteStringObject):
        return bytes(objeto)

    return objeto.original_bytes


def _e_string(objeto):
    return hasattr(objeto, 'original_bytes') or isinstance(objeto, ByteStringObject)


def _reescrever_operacao(operandos, operador, remover, codigos_na_operacao):
    """
    Devolve os operandos novos de um comando TJ sem as letras de `remover`
    ({k: largura em milésimos}). No lugar de cada trecho apagado entra um deslocamento,
    para o texto que vem depois continuar exatamente onde estava.
    """
    if operador not in (b'Tj', b'TJ'):
        raise _Falha('comando de texto não suportado')

    itens = list(operandos[0]) if operador == b'TJ' else [operandos[0]]
    total = sum(len(_bytes_da_string(i)) for i in itens if _e_string(i))

    if not codigos_na_operacao or total % codigos_na_operacao:
        raise _Falha('não foi possível separar as letras do comando')

    bpc = total // codigos_na_operacao

    novos = []
    atual = bytearray()
    pendente = 0.0
    k = 0

    def fechar():
        if atual:
            novos.append(ByteStringObject(bytes(atual)))
            atual.clear()

    def deslocar():
        nonlocal pendente
        if pendente:
            fechar()
            novos.append(FloatObject(round(-pendente, 4)))
            pendente = 0.0

    for item in itens:
        if not _e_string(item):
            deslocar()
            fechar()
            novos.append(item)
            continue

        dados = _bytes_da_string(item)

        for j in range(0, len(dados), bpc):
            if k in remover:
                pendente += remover[k]
            else:
                deslocar()
                atual += dados[j:j + bpc]

            k += 1

    deslocar()
    fechar()

    return [ArrayObject(novos)]


def remover_marcadores(pdf_bytes, padrao=PADRAO_MARCADOR):
    """
    Apaga do PDF as letras dos marcadores. Devolve (pdf, quantidade_de_letras_removidas).

    Se algo der errado, ou se qualquer outra letra mudar de lugar, devolve o PDF
    original sem alterações (quantidade 0): o preenchimento continua funcionando
    só cobrindo o marcador.
    """
    try:
        antes = _coletar(pdf_bytes)
        por_pagina = [_indices_a_remover(p['registros'], padrao) for p in antes]

        if not any(por_pagina):
            return pdf_bytes, 0

        leitor = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        escritor = pypdf.PdfWriter()

        for n, pagina in enumerate(leitor.pages):
            nova = escritor.add_page(pagina)

            if not por_pagina[n]:
                continue

            conteudo = ContentStream(nova.get_contents(), escritor)
            operacoes = list(conteudo.operations)
            posicoes = [i for i, (_, op) in enumerate(operacoes) if op in (b'Tj', b'TJ', b"'", b'"')]

            if len(posicoes) != antes[n]['operacoes']:
                raise _Falha('o número de comandos de texto não confere')

            registros = antes[n]['registros']
            codigos = Counter(r['op'] for r in registros)
            por_operacao = {}

            for i in por_pagina[n]:
                r = registros[i]
                por_operacao.setdefault(r['op'], {})[r['k']] = r['largura'] * 1000.0

            for op, remover in por_operacao.items():
                pos = posicoes[op]
                operandos, operador = operacoes[pos]
                novos = _reescrever_operacao(operandos, operador, remover, codigos[op])
                operacoes[pos] = (novos, b'TJ')

            conteudo.operations = operacoes
            nova.replace_contents(conteudo)

        saida = io.BytesIO()
        escritor.write(saida)
        resultado = saida.getvalue()

        # Conferência de segurança: as letras que ficaram não podem ter se movido.
        depois = _coletar(resultado)

        for n in range(len(antes)):
            mantidos = [r for i, r in enumerate(antes[n]['registros']) if i not in por_pagina[n]]
            atuais = depois[n]['registros']

            if len(mantidos) != len(atuais):
                raise _Falha('o texto restante não confere')

            for a, d in zip(mantidos, atuais):
                if a['texto'] != d['texto'] or abs(a['x0'] - d['x0']) > 0.3 or abs(a['y0'] - d['y0']) > 0.3:
                    raise _Falha('alguma letra mudou de lugar')

        return resultado, sum(len(p) for p in por_pagina)
    except Exception as erro:
        logger.warning('Remoção do texto dos marcadores não aplicada (%s); usando só a cobertura.', erro)
        return pdf_bytes, 0


@lru_cache(maxsize=8)
def _modelo_pronto(pdf_bytes):
    """Marcadores e PDF já sem o texto deles. Guardado em memória (o modelo quase nunca muda)."""
    achados, _ = localizar_marcadores(pdf_bytes)
    limpo, _ = remover_marcadores(pdf_bytes)

    return tuple(achados), limpo


# ------------------------------------------------------------------ preenchimento

def preencher(pdf_bytes, valores):
    """
    Preenche os marcadores do PDF com `valores` (dict nome -> texto).

    Devolve (pdf_preenchido_em_bytes, avisos). Levanta ValueError se algum
    marcador do PDF não tiver valor.
    """
    _registrar_fontes()

    achados, pdf_bytes = _modelo_pronto(pdf_bytes)

    faltando = sorted({a['nome'] for a in achados if a['nome'] not in valores})

    if faltando:
        raise ValueError('Faltam valores para: ' + ', '.join(f'[[{n}]]' for n in faltando))

    leitor = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    escritor = pypdf.PdfWriter()
    avisos = []

    for n, pagina in enumerate(leitor.pages):
        da_pagina = [a for a in achados if a['pagina'] == n]

        if da_pagina:
            largura = float(pagina.mediabox.width)
            altura = float(pagina.mediabox.height)
            buf = io.BytesIO()
            c = canvas.Canvas(buf, pagesize=(largura, altura))

            for a in da_pagina:
                texto = valores[a['nome']] + a['sufixo']
                fonte = FONTE_NEGRITO if a['negrito'] else FONTE
                tam = a['tamanho']
                disponivel = a['limite'] - a['x0']

                while tam > TAMANHO_MINIMO and pdfmetrics.stringWidth(texto, fonte, tam) > disponivel:
                    tam -= 0.25

                if pdfmetrics.stringWidth(texto, fonte, tam) > disponivel + 0.5:
                    avisos.append(f'[[{a["nome"]}]] não coube no espaço da linha.')

                H = a['altura_pagina']

                c.setFillColorRGB(1, 1, 1)
                c.rect(
                    a['x0'] - 1,
                    H - a['bottom'] - 1,
                    (a['x1_total'] - a['x0']) + 2,
                    (a['bottom'] - a['top']) + 2.5,
                    stroke=0,
                    fill=1,
                )
                c.setFillColorRGB(0, 0, 0)
                c.setFont(fonte, tam)
                c.drawString(a['x0'], H - a['bottom'] + 0.22 * a['tamanho'], texto)

            c.showPage()
            c.save()
            buf.seek(0)
            pagina.merge_page(pypdf.PdfReader(buf).pages[0])

        escritor.add_page(pagina)

    saida = io.BytesIO()
    escritor.write(saida)

    return saida.getvalue(), avisos


# ---------------------------------------------------------- termo de assinatura

def termo_assinatura(info):
    """Página final com os dados da assinatura eletrônica (PDF em bytes)."""
    _registrar_fontes()

    corpo = ParagraphStyle('corpo', fontName=FONTE, fontSize=11, leading=15, spaceAfter=8)
    titulo = ParagraphStyle(
        'titulo', fontName=FONTE_NEGRITO, fontSize=16, leading=20, spaceAfter=14,
    )
    pequeno = ParagraphStyle(
        'pequeno', fontName=FONTE, fontSize=9, leading=12, textColor=colors.HexColor('#555555'),
    )
    celula = ParagraphStyle('celula', fontName=FONTE, fontSize=10.5, leading=13)
    rotulo = ParagraphStyle('rotulo', fontName=FONTE_NEGRITO, fontSize=10.5, leading=13)

    linhas = [
        ('Contrato', info['contrato']),
        ('Aluna', info['aluna']),
        ('Assinante', info['nome']),
        ('CPF', info['cpf']),
        ('E-mail', info['email']),
        ('Assinado em', info['assinado_em']),
        ('Endereço de acesso (IP)', info['ip']),
        ('Navegador', info['navegador']),
        ('Forma de autenticação', info['metodo']),
        ('Código de verificação', info['codigo']),
        ('Impressão digital (SHA-256)', info['hash']),
    ]

    codigo = ParagraphStyle('codigo', fontName='Courier', fontSize=9.5, leading=13)

    def valor_da_linha(r, v):
        if r.startswith('Impressão digital'):
            # 64 caracteres em duas linhas de 32, em fonte de código: fácil de ler e de copiar.
            return Paragraph(f'{escape(v[:32])}<br/>{escape(v[32:])}', codigo)

        return Paragraph(escape(str(v)), celula)

    tabela = Table(
        [[Paragraph(escape(r), rotulo), valor_da_linha(r, v)] for r, v in linhas],
        colWidths=[5.6 * cm, 10.4 * cm],
    )
    tabela.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#BBBBBB')),
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#F3F0F6')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))

    texto_termo = (
        'Este termo registra a assinatura eletrônica do contrato que o antecede. '
        'A pessoa identificada abaixo acessou o sistema com o seu login e senha, '
        'conferiu o contrato preenchido, declarou ter lido e concordado com todas as '
        'cláusulas e confirmou a assinatura com um código enviado ao seu e-mail.'
    )
    texto_hash = (
        'A impressão digital (SHA-256) identifica o conteúdo do contrato nas páginas '
        'anteriores a este termo. Qualquer alteração posterior no arquivo muda esse '
        'valor e permite perceber que o documento foi modificado.'
    )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=2.5 * cm, rightMargin=2.5 * cm,
        topMargin=2.5 * cm, bottomMargin=2.5 * cm, title='Termo de assinatura eletrônica',
    )
    doc.build([
        Paragraph('TERMO DE ASSINATURA ELETRÔNICA', titulo),
        Paragraph(escape(texto_termo), corpo),
        Spacer(1, 6),
        tabela,
        Spacer(1, 12),
        Paragraph(escape(texto_hash), pequeno),
    ])

    return buf.getvalue()


def juntar(*pdfs):
    """Junta vários PDFs (bytes) em um só, na ordem dada."""
    escritor = pypdf.PdfWriter()

    for conteudo in pdfs:
        for pagina in pypdf.PdfReader(io.BytesIO(conteudo)).pages:
            escritor.add_page(pagina)

    saida = io.BytesIO()
    escritor.write(saida)

    return saida.getvalue()


def extrair_texto(pdf_bytes):
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        return '\n'.join((p.extract_text() or '') for p in pdf.pages)
