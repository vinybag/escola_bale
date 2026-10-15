"""
Resposta automática para quem escreve no número de WhatsApp de avisos.

O número da API da Meta serve apenas para DISPARAR avisos (mensalidades,
ensaios). Muita gente responde a ele achando que a escola vai ler. Este
módulo recebe o aviso da Meta (webhook) e responde, uma única vez, dizendo
qual é o número de atendimento correto.

Regras:
  * No máximo uma resposta por pessoa a cada 24 horas (evita spam, custo
    e laços de resposta).
  * Nunca responde à própria escola (evita loop se o número de atendimento
    escrever para o número de avisos).
  * Ignora reações (👍 numa mensagem) e mensagens de sistema.
  * Ignora mensagens muito antigas (por exemplo, reenviadas pela Meta
    depois de o servidor ter ficado fora do ar).
  * Só responde mensagens destinadas ao número configurado.
  * O texto da mensagem recebida NÃO é guardado.
"""

import logging
import re
from datetime import datetime, timedelta, timezone as dt_timezone

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from .models import WhatsAppMensagemRecebida
from .services_whatsapp import enviar_whatsapp_texto

logger = logging.getLogger(__name__)

# A pessoa recebe no máximo uma resposta automática nesse intervalo.
JANELA_ENTRE_RESPOSTAS = timedelta(hours=24)

# Mensagens recebidas há mais tempo que isso não recebem resposta.
IDADE_MAXIMA_MENSAGEM = timedelta(hours=6)

# Dois avisos quase simultâneos da mesma pessoa: o de menor id é quem
# responde. Um registro "processando" só bloqueia por este tempo, para que
# uma falha no meio do caminho não silencie a pessoa por 24 horas.
TEMPO_MAXIMO_PROCESSANDO = timedelta(minutes=1)

# Tipos de mensagem que não merecem resposta.
TIPOS_IGNORADOS = {'reaction', 'system', 'unsupported', 'request_welcome'}


def somente_digitos(valor):
    return re.sub(r'\D', '', str(valor or ''))


def normalizar_numero_br(valor):
    """
    Devolve só os dígitos com DDI 55 (ex.: '5511912345678'), ou None se não
    parecer um telefone brasileiro. Aceita "(11) 91234-5678",
    "+55 11 91234-5678", "11912345678" etc.
    """
    digitos = somente_digitos(valor)

    if digitos.startswith('00'):
        digitos = digitos[2:]

    if len(digitos) in (12, 13) and digitos.startswith('55'):
        nacional = digitos[2:]
    elif len(digitos) in (10, 11):
        nacional = digitos
    else:
        return None

    if not 11 <= int(nacional[:2]) <= 99:
        return None

    return '55' + nacional


def formatar_numero_br(numero_com_ddi):
    """'5511912345678' -> '(11) 91234-5678' (e '551112345678' -> '(11) 1234-5678')."""
    nacional = numero_com_ddi[2:]
    ddd, resto = nacional[:2], nacional[2:]
    return f'({ddd}) {resto[:-4]}-{resto[-4:]}'


def _chave_numero(valor):
    """
    Chave para comparar dois telefones ignorando o 9º dígito, que a Meta às
    vezes entrega sem ele para números brasileiros antigos: (DDD, 8 últimos
    dígitos). Devolve None se não parecer um número brasileiro.
    """
    numero = normalizar_numero_br(valor)
    if numero is None:
        return None
    return numero[2:4], numero[-8:]


def numero_atendimento():
    """
    Número em que a escola atende, com DDI, ou None se não configurado.

    Lê WHATSAPP_NUMERO_ATENDIMENTO, de propósito uma variável própria: a
    WHATSAPP_NUMERO_ESCOLA, mais antiga, guarda o número de DISPAROS e não
    deve ser usada aqui.
    """
    return normalizar_numero_br(
        getattr(settings, 'WHATSAPP_NUMERO_ATENDIMENTO', None)
    )


def montar_texto_autoresposta(numero_atendimento_com_ddi):
    numero = formatar_numero_br(numero_atendimento_com_ddi)
    link = f'https://wa.me/{numero_atendimento_com_ddi}'

    return (
        'Olá! 👋 Este número é usado apenas para o envio de avisos '
        'automáticos (mensalidades, ensaios e comunicados) e não recebe '
        'nem responde mensagens.\n\n'
        'Para falar com a escola, chame no WhatsApp:\n'
        f'📱 {numero}\n'
        f'{link}\n\n'
        'Obrigado!'
    )


def _motivo_para_ignorar(registro, mensagem, atendimento, agora, numero_de_avisos=None):
    """Devolve o motivo (texto) se a mensagem NÃO deve ser respondida."""
    if registro.tipo in TIPOS_IGNORADOS:
        return f'tipo_ignorado:{registro.tipo}'

    if not getattr(settings, 'WHATSAPP_AUTORESPOSTA_ATIVA', True):
        return 'autoresposta_desativada'

    if atendimento is None:
        return 'numero_de_atendimento_nao_configurado'

    # Proteção contra configuração errada: se o "número de atendimento" for o
    # próprio número que recebeu a mensagem (o de disparos), a resposta
    # mandaria a pessoa de volta para um número que não responde.
    if (
        numero_de_avisos
        and _chave_numero(numero_de_avisos) is not None
        and _chave_numero(numero_de_avisos) == _chave_numero(atendimento)
    ):
        logger.error(
            'WHATSAPP_NUMERO_ATENDIMENTO é igual ao número de avisos; '
            'resposta automática não enviada. Informe o número em que a '
            'escola realmente atende.'
        )
        return 'numero_de_atendimento_igual_ao_numero_de_avisos'

    chave_remetente = _chave_numero(registro.telefone)
    if chave_remetente is not None and chave_remetente == _chave_numero(atendimento):
        return 'remetente_e_a_propria_escola'

    try:
        enviada_em = datetime.fromtimestamp(
            int(mensagem.get('timestamp')), tz=dt_timezone.utc
        )
    except (TypeError, ValueError):
        enviada_em = None

    if enviada_em is not None and agora - enviada_em > IDADE_MAXIMA_MENSAGEM:
        return 'mensagem_antiga'

    ja_respondida = (
        WhatsAppMensagemRecebida.objects
        .filter(telefone=registro.telefone)
        .exclude(pk=registro.pk)
        .filter(
            Q(
                status=WhatsAppMensagemRecebida.STATUS_RESPONDIDA,
                criado_em__gte=agora - JANELA_ENTRE_RESPOSTAS,
            )
            | Q(
                status=WhatsAppMensagemRecebida.STATUS_PROCESSANDO,
                criado_em__gte=agora - TEMPO_MAXIMO_PROCESSANDO,
                pk__lt=registro.pk,
            )
        )
        .exists()
    )
    if ja_respondida:
        return 'ja_respondida_nas_ultimas_24h'

    return ''


def _processar_mensagem(mensagem, agora, numero_de_avisos=None):
    """Processa UMA mensagem recebida. Devolve True se enviou resposta."""
    wamid = (mensagem.get('id') or '').strip()
    remetente = somente_digitos(mensagem.get('from'))

    if not wamid or not remetente:
        return False

    registro, criado = WhatsAppMensagemRecebida.objects.get_or_create(
        wamid=wamid,
        defaults={
            'telefone': remetente,
            'tipo': str(mensagem.get('type') or '')[:30],
        },
    )

    if not criado:
        # A Meta reenviou um aviso que já foi tratado.
        return False

    atendimento = numero_atendimento()

    motivo = _motivo_para_ignorar(
        registro, mensagem, atendimento, agora, numero_de_avisos
    )
    if motivo:
        registro.status = WhatsAppMensagemRecebida.STATUS_IGNORADA
        registro.motivo = motivo
        registro.save(update_fields=['status', 'motivo'])
        return False

    try:
        status_http, resposta = enviar_whatsapp_texto(
            remetente, montar_texto_autoresposta(atendimento)
        )
    except Exception as exc:  # nunca derrubar o webhook por falha ao responder
        logger.exception('Erro inesperado ao enviar resposta automática')
        status_http, resposta = 0, {'error': {'message': str(exc)}}

    if status_http == 200:
        registro.status = WhatsAppMensagemRecebida.STATUS_RESPONDIDA
        registro.save(update_fields=['status'])
        return True

    detalhe = ''
    if isinstance(resposta, dict):
        detalhe = str((resposta.get('error') or {}).get('message') or '')
    registro.status = WhatsAppMensagemRecebida.STATUS_ERRO
    registro.motivo = f'http {status_http}: {detalhe}'[:255]
    registro.save(update_fields=['status', 'motivo'])
    return False


def processar_payload(payload, agora=None):
    """
    Processa o JSON enviado pela Meta ao webhook. Devolve quantas respostas
    automáticas foram enviadas.

    O mesmo endereço também recebe avisos de status ("entregue", "lido")
    das mensagens que NÓS enviamos; esses são ignorados.
    """
    agora = agora or timezone.now()
    enviadas = 0

    phone_number_id = str(getattr(settings, 'WHATSAPP_PHONE_NUMBER_ID', '') or '')

    for entrada in (payload or {}).get('entry') or []:
        for mudanca in entrada.get('changes') or []:
            if mudanca.get('field') != 'messages':
                continue

            valor = mudanca.get('value') or {}
            destino = str((valor.get('metadata') or {}).get('phone_number_id') or '')

            # Mensagem para outro número da mesma conta: não é com a gente.
            if phone_number_id and destino and destino != phone_number_id:
                logger.info(
                    'WhatsApp webhook: mensagem para outro número (%s) ignorada',
                    destino,
                )
                continue

            # Número que RECEBEU a mensagem (o de disparos), como a Meta informa.
            numero_de_avisos = (valor.get('metadata') or {}).get(
                'display_phone_number'
            )

            for mensagem in valor.get('messages') or []:
                if _processar_mensagem(mensagem, agora, numero_de_avisos):
                    enviadas += 1

    return enviadas
