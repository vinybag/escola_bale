"""Logo e cores da escola nas telas das famílias e no site público (a administração não muda)."""

import io
import re

PALETAS = [
    # (nome, cor principal). A primeira é a padrão do sistema: guarda "vazio" e deixa tudo como sempre foi.
    ('Rosa (padrão)', ''),
    ('Roxo', '#7b4fa0'),
    ('Azul', '#3f6fb0'),
    ('Verde', '#4f8a6b'),
    ('Vinho', '#8a2c3b'),
    ('Dourado', '#a8803a'),
    ('Coral', '#cc5f55'),
    ('Grafite', '#4a4a55'),
]

CONTRASTE_MINIMO = 3.0   # a cor precisa aguentar texto branco por cima
TAMANHO_MAXIMO_LOGO = 2 * 1024 * 1024
LADO_MAXIMO_LOGO = (600, 300)
FORMATOS_ACEITOS = {'PNG', 'JPEG', 'WEBP'}

_HEX = re.compile(r'^#[0-9a-fA-F]{6}$')


def normalizar_cor(texto):
    """'#B07A84' / 'b07a84' -> '#b07a84'. Vazio -> ''. Inválido -> ValueError."""
    texto = (texto or '').strip()

    if not texto:
        return ''

    if not texto.startswith('#'):
        texto = '#' + texto

    if not _HEX.match(texto):
        raise ValueError('Cor inválida. Use o formato #RRGGBB (ex.: #7b4fa0).')

    return texto.lower()


def _rgb(cor):
    return tuple(int(cor[i:i + 2], 16) for i in (1, 3, 5))


def _hex(rgb):
    return '#%02x%02x%02x' % tuple(max(0, min(255, round(c))) for c in rgb)


def _misturar(cor, outra, quanto):
    """Mistura `cor` com `outra` (quanto = 0..1 da outra)."""
    return _hex(tuple(a + (b - a) * quanto for a, b in zip(_rgb(cor), outra)))


def _luminancia(cor):
    def canal(c):
        c = c / 255

        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (canal(c) for c in _rgb(cor))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contraste_com_branco(cor):
    return 1.05 / (_luminancia(cor) + 0.05)


def validar_cor(cor):
    """Levanta ValueError se a cor é clara demais para texto branco por cima."""
    cor = normalizar_cor(cor)

    if cor and contraste_com_branco(cor) < CONTRASTE_MINIMO:
        raise ValueError('Essa cor é clara demais: o texto branco não ficaria legível. Escolha uma mais escura.')

    return cor


def variaveis_css(cor):
    """Variáveis CSS derivadas da cor principal. Vazio quando a escola usa a cor padrão."""
    if not cor:
        return {}

    r, g, b = _rgb(cor)
    return {
        '--cor-principal': cor,
        '--cor-principal-rgb': f'{r}, {g}, {b}',
        '--cor-principal-escura': _misturar(cor, (0, 0, 0), 0.11),
        '--cor-principal-clara': _misturar(cor, (255, 255, 255), 0.55),
        '--cor-principal-borda': _misturar(cor, (255, 255, 255), 0.45),
        '--cor-fundo-suave': _misturar(cor, (255, 255, 255), 0.95),
    }


def css_do_tema(cor):
    variaveis = variaveis_css(cor)

    if not variaveis:
        return ''

    return ':root{' + ';'.join(f'{nome}:{valor}' for nome, valor in variaveis.items()) + '}'


def processar_logo(arquivo):
    """
    Valida e normaliza a imagem enviada: só PNG, JPG ou WebP, até 2 MB. A imagem é lida e
    gravada de novo (PNG, no máximo 600x300), o que descarta qualquer conteúdo escondido.
    Devolve (bytes, tipo). Levanta ValueError com mensagem em português.
    """
    from PIL import Image, ImageOps, UnidentifiedImageError

    if arquivo.size > TAMANHO_MAXIMO_LOGO:
        raise ValueError('A imagem é grande demais. O limite é 2 MB.')

    try:
        imagem = Image.open(arquivo)
        formato = imagem.format
        imagem.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, ValueError):
        raise ValueError('Não consegui ler essa imagem. Envie um arquivo PNG, JPG ou WebP.')

    if formato not in FORMATOS_ACEITOS:
        raise ValueError('Formato não aceito. Envie PNG, JPG ou WebP.')

    imagem = ImageOps.exif_transpose(imagem)
    imagem = imagem.convert('RGBA')
    imagem.thumbnail(LADO_MAXIMO_LOGO)
    saida = io.BytesIO()
    imagem.save(saida, format='PNG', optimize=True)
    return saida.getvalue(), 'image/png'
