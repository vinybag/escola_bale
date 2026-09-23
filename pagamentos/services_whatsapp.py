import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def enviar_whatsapp_template(numero_destino, nome_template, parametros):
    """
    Envia uma mensagem de template pela WhatsApp Cloud API (Meta).

    Retorna uma tupla (status_code, resposta_json). Em caso de erro,
    a resposta_json contém o motivo retornado pela Meta (chave "error"),
    que é registrado no log para facilitar o diagnóstico.
    """
    phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
    access_token = settings.WHATSAPP_ACCESS_TOKEN

    if not phone_number_id or not access_token:
        erro = {
            "error": {
                "message": (
                    "WHATSAPP_PHONE_NUMBER_ID ou WHATSAPP_ACCESS_TOKEN "
                    "não configurados neste serviço (settings retornou "
                    "valor vazio/None)."
                )
            }
        }
        logger.error("Config ausente ao enviar WhatsApp: %s", erro)
        return 0, erro

    url = f"https://graph.facebook.com/v20.0/{phone_number_id}/messages"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": numero_destino,
        "type": "template",
        "template": {
            "name": nome_template,
            "language": {"code": "pt_BR"},
            "components": [
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": str(p)} for p in parametros]
                }
            ]
        }
    }

    try:
        resposta = requests.post(url, headers=headers, json=payload, timeout=15)
    except requests.RequestException as exc:
        erro = {"error": {"message": f"Falha de conexão com a Meta: {exc}"}}
        logger.error("Erro de rede ao enviar WhatsApp para %s: %s", numero_destino, exc)
        return 0, erro

    resposta_json = {}
    try:
        resposta_json = resposta.json()
    except ValueError:
        resposta_json = {"error": {"message": f"Resposta não-JSON: {resposta.text[:300]}"}}

    if resposta.status_code != 200:
        logger.error(
            "Falha ao enviar WhatsApp para %s (template=%s): status=%s resposta=%s",
            numero_destino, nome_template, resposta.status_code, resposta_json,
        )

    return resposta.status_code, resposta_json
