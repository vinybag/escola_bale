import requests
from django.conf import settings


def enviar_whatsapp_template(numero_destino, nome_template, parametros):
    url = f"https://graph.facebook.com/v20.0/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"

    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
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

    resposta = requests.post(url, headers=headers, json=payload, timeout=15)
    return resposta.status_code, resposta.json()