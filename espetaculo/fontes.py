"""
Fonte usada na geração das imagens de ingresso (QR code + dados do
participante).

Antes, o código tentava carregar "arial.ttf" direto do sistema
operacional. Isso funciona no Windows, mas NÃO existe nos servidores
Linux (Railway) onde o projeto roda em produção — o carregamento sempre
falhava e caía silenciosamente no `ImageFont.load_default()`, uma fonte
bitmap minúscula, pensada só para debug, nunca para o ingresso final que
o participante imprime.

Por isso, a fonte (DejaVu Sans, de uso livre) agora vem junto do próprio
projeto, em `espetaculo/fonts/`, e é carregada a partir daqui — assim o
resultado fica igual em qualquer servidor, independente do que estiver
(ou não) instalado no sistema operacional.
"""

import os

from PIL import ImageFont

_PASTA_FONTES = os.path.join(
    os.path.dirname(__file__),
    'fonts',
)

_CAMINHO_REGULAR = os.path.join(_PASTA_FONTES, 'DejaVuSans.ttf')
_CAMINHO_NEGRITO = os.path.join(_PASTA_FONTES, 'DejaVuSans-Bold.ttf')


def carregar_fonte(tamanho, negrito=False):
    """
    Carrega a fonte do ingresso no tamanho pedido.

    Se, por algum motivo, o arquivo da fonte não puder ser lido (ex.:
    arquivo corrompido ou ausente), cai de volta para a fonte padrão do
    Pillow em vez de quebrar a geração do ingresso — pior o visual,
    nunca pior o funcionamento.
    """
    caminho = _CAMINHO_NEGRITO if negrito else _CAMINHO_REGULAR

    try:
        return ImageFont.truetype(caminho, tamanho)
    except Exception:
        return ImageFont.load_default()
