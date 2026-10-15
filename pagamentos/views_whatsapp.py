"""
Webhook do WhatsApp (Meta): recebe as mensagens que as pessoas enviam para o
número de avisos e dispara a resposta automática com o número de atendimento.

Configuração na Meta (developers.facebook.com > seu app > WhatsApp >
Configuração > Webhook):
  * URL de retorno de chamada:  https://SEU-DOMINIO/pagamentos/webhook/whatsapp/
    (com a barra no final; a Meta não segue redirecionamentos)
  * Token de verificação:       o mesmo valor de WHATSAPP_VERIFY_TOKEN
  * Campo assinado:             messages
"""

import hashlib
import hmac
import json
import logging

from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .whatsapp_autoresposta import processar_payload

logger = logging.getLogger(__name__)


def _iguais(a, b):
    """Comparação em tempo constante."""
    return hmac.compare_digest(
        (a or '').encode('utf-8'), (b or '').encode('utf-8')
    )


def assinatura_valida(corpo, cabecalho, segredo):
    """
    Confere o cabeçalho X-Hub-Signature-256 ("sha256=<hmac>") calculado pela
    Meta com a chave secreta do app. Sem segredo configurado, nada é aceito.
    """
    if not segredo or not cabecalho:
        return False

    esperado = 'sha256=' + hmac.new(
        segredo.encode('utf-8'), corpo, hashlib.sha256
    ).hexdigest()

    return _iguais(cabecalho.strip(), esperado)


def _verificar_webhook(request):
    """GET de verificação feito pela Meta ao cadastrar o webhook."""
    token_esperado = getattr(settings, 'WHATSAPP_VERIFY_TOKEN', None)

    modo = request.GET.get('hub.mode')
    token = request.GET.get('hub.verify_token')
    desafio = request.GET.get('hub.challenge', '')

    if not token_esperado:
        logger.error('WhatsApp webhook: WHATSAPP_VERIFY_TOKEN não configurado')
        return HttpResponse(status=403)

    if modo == 'subscribe' and _iguais(token, token_esperado):
        return HttpResponse(desafio, content_type='text/plain')

    return HttpResponse(status=403)


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def webhook_whatsapp(request):
    if request.method == 'GET':
        return _verificar_webhook(request)

    segredo = getattr(settings, 'WHATSAPP_APP_SECRET', None)

    if not segredo:
        logger.error('WhatsApp webhook: WHATSAPP_APP_SECRET não configurado')
        return HttpResponse(status=403)

    if not assinatura_valida(
        request.body, request.headers.get('X-Hub-Signature-256'), segredo
    ):
        logger.warning('WhatsApp webhook: assinatura inválida')
        return HttpResponse(status=403)

    try:
        payload = json.loads(request.body)
    except ValueError:
        return HttpResponse(status=400)

    # Depois de validar a assinatura, sempre responde 200: um erro nosso não
    # deve fazer a Meta reenviar o mesmo aviso repetidamente.
    try:
        processar_payload(payload)
    except Exception:
        logger.exception('WhatsApp webhook: erro ao processar o payload')

    return HttpResponse(status=200)
