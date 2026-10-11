"""
Contatos de compradores de ingressos (pagos e não finalizados).

Alimenta a tela "Contatos" dentro de "Ingressos vendidos". A ideia é dar à
equipe uma lista única de pessoas, com o WhatsApp à mão, para:

  * falar com quem escolheu os assentos, gerou o PIX e NÃO pagou
    (entender o motivo e tentar recuperar a venda);
  * ver também quem comprou.

Nada aqui é gravado no banco: o status de cada pessoa é CALCULADO a cada
abertura da tela a partir dos pedidos (PedidoIngressoEvento) que já
existem. Por isso:

  * casos antigos aparecem automaticamente (não depende de "daqui pra
    frente"); e
  * se quem não comprou voltar e pagar depois (mesmo WhatsApp), o status
    vira "Comprou" sozinho.
"""

import re
from collections import defaultdict
from datetime import timedelta
from urllib.parse import quote

from django.db.models import Prefetch
from django.utils import timezone

from espetaculo.models import Assento, IngressoEvento, PedidoIngressoEvento


# Status calculados (ordem de prioridade: o primeiro que a pessoa tiver vence).
COMPROU = 'comprou'
VERIFICAR = 'verificar'
EM_ANDAMENTO = 'em_andamento'
NAO_FINALIZOU = 'nao_finalizou'

PRIORIDADE = [COMPROU, VERIFICAR, EM_ANDAMENTO, NAO_FINALIZOU]

ROTULOS = {
    COMPROU: 'Comprou',
    VERIFICAR: 'Verificar no Asaas',
    EM_ANDAMENTO: 'Pagando agora',
    NAO_FINALIZOU: 'Não finalizou',
}

# Pedido "pendente" criado há menos que isso ainda pode estar sendo pago
# (a reserva do assento dura 15 min), então não é tratado como desistência.
MINUTOS_EM_ANDAMENTO = 20

# Status do Asaas que indicam dinheiro recebido.
ASAAS_STATUS_PAGO = {'RECEIVED', 'CONFIRMED', 'RECEIVED_IN_CASH'}


def normalizar_whatsapp(valor):
    """
    Devolve só os dígitos com DDI 55 (ex.: '5511912345678'), ou None se o
    texto não parecer um telefone brasileiro válido.

    O campo é texto livre: aceita "(11) 91234-5678", "11 91234 5678",
    "+55 11 91234-5678" etc. e rejeita "-", vazio e lixo.
    """
    digitos = re.sub(r'\D', '', valor or '')

    if digitos.startswith('00'):
        digitos = digitos[2:]

    if len(digitos) in (12, 13) and digitos.startswith('55'):
        nacional = digitos[2:]
    elif len(digitos) in (10, 11):
        nacional = digitos
    else:
        return None

    ddd = int(nacional[:2])
    if not 11 <= ddd <= 99:
        return None

    return '55' + nacional


def _eh_cortesia(pedido):
    return (
        pedido.valor_total is None
        or pedido.valor_total <= 0
        or (pedido.external_reference or '').startswith(
            'ingresso_gratuito_aluna:'
        )
    )


def _gerou_pix(pedido):
    return bool(
        (pedido.codigo_pix or '').strip()
        or (pedido.asaas_payment_id or '').strip()
    )


def classificar_pedido(pedido, agora):
    """
    Classifica UM pedido. Devolve COMPROU, VERIFICAR, EM_ANDAMENTO,
    NAO_FINALIZOU, ou None quando o pedido não interessa à lista
    (cortesia/gratuito, ou a pessoa nem chegou a gerar o PIX).
    """
    if _eh_cortesia(pedido):
        return None

    if pedido.status == 'pago':
        return COMPROU

    if not _gerou_pix(pedido):
        return None

    # O Asaas diz que recebeu, mas o sistema não marcou como pago
    # (ex.: webhook que não chegou). Não abordar como "não comprou".
    if (pedido.asaas_status or '').upper() in ASAAS_STATUS_PAGO:
        return VERIFICAR

    limite = agora - timedelta(minutes=MINUTOS_EM_ANDAMENTO)
    if pedido.status == 'pendente' and pedido.criado_em > limite:
        return EM_ANDAMENTO

    # pendente antigo, expirado ou cancelado
    return NAO_FINALIZOU


def _ids_assentos(pedido):
    ids = []
    for valor in pedido.assentos_ids or []:
        try:
            ids.append(int(valor))
        except (TypeError, ValueError):
            continue
    return ids


def _assentos_do_pedido(pedido, rotulos_por_id):
    rotulos = [
        rotulos_por_id[i]
        for i in _ids_assentos(pedido)
        if i in rotulos_por_id
    ]

    if not rotulos:
        # Pedidos antigos podem não ter os IDs salvos: usa os assentos
        # dos ingressos já emitidos (carregados via prefetch).
        rotulos = [
            ing.assento.rotulo
            for ing in pedido.ingressos.all()
            if ing.assento_id and ing.status != 'cancelado'
        ]

    return rotulos


def montar_mensagem_whatsapp(nome, titulo_evento):
    primeiro_nome = (nome or '').strip().split(' ')[0].title()
    saudacao = f'Olá, {primeiro_nome}!' if primeiro_nome else 'Olá!'

    return (
        f'{saudacao} Tudo bem? Aqui é da escola de balé. '
        f'Vi que você começou a comprar ingressos para "{titulo_evento}" '
        f'mas não chegou a finalizar o pagamento. '
        f'Aconteceu algum problema? Posso te ajudar?'
    )


def montar_link_whatsapp(numero, mensagem=None):
    link = f'https://wa.me/{numero}'
    if mensagem:
        link += f'?text={quote(mensagem)}'
    return link


def montar_contatos(espetaculo, agora=None):
    """
    Devolve (contatos, sem_whatsapp).

    contatos: lista de dicts, uma por pessoa (agrupadas pelo WhatsApp),
        da atividade mais recente para a mais antiga.
    sem_whatsapp: quantos pedidos relevantes ficaram de fora por não terem
        um WhatsApp válido (ex.: contas logadas sem telefone no perfil).
    """
    agora = agora or timezone.now()

    pedidos = list(
        PedidoIngressoEvento.objects
        .filter(evento=espetaculo)
        .prefetch_related(
            Prefetch(
                'ingressos',
                queryset=IngressoEvento.objects.select_related('assento'),
            )
        )
        .order_by('criado_em')
    )

    # Uma única consulta para os rótulos de todos os assentos citados.
    todos_ids = {i for p in pedidos for i in _ids_assentos(p)}
    rotulos_por_id = {
        a.id: a.rotulo for a in Assento.objects.filter(id__in=todos_ids)
    } if todos_ids else {}

    grupos = defaultdict(list)  # whatsapp normalizado -> [(pedido, status)]
    sem_whatsapp = 0

    for pedido in pedidos:
        status = classificar_pedido(pedido, agora)
        if status is None:
            continue

        numero = normalizar_whatsapp(pedido.whatsapp)
        if numero is None:
            sem_whatsapp += 1
            continue

        grupos[numero].append((pedido, status))

    contatos = []

    for numero, itens in grupos.items():
        status_pessoa = next(
            s for s in PRIORIDADE if any(st == s for _, st in itens)
        )

        do_status = [p for p, st in itens if st == status_pessoa]
        referencia = do_status[-1]  # o mais recente (lista ordenada)

        if status_pessoa == COMPROU:
            # Somando todos os pedidos pagos da pessoa.
            quantidade = sum(p.quantidade for p in do_status)
            valor = sum(p.valor_total for p in do_status)
            assentos = []
            for p in do_status:
                assentos.extend(_assentos_do_pedido(p, rotulos_por_id))
            quando = referencia.data_pagamento or referencia.criado_em
        else:
            quantidade = referencia.quantidade
            valor = referencia.valor_total
            assentos = _assentos_do_pedido(referencia, rotulos_por_id)
            quando = referencia.criado_em

        tentativas_sem_pagar = sum(
            1 for _, st in itens if st in (NAO_FINALIZOU, EM_ANDAMENTO)
        )

        email = next(
            (p.email for p, _ in reversed(itens) if p.email), ''
        )

        mensagem = (
            montar_mensagem_whatsapp(referencia.nome_completo, espetaculo.titulo)
            if status_pessoa == NAO_FINALIZOU
            else None
        )

        contatos.append({
            'nome': referencia.nome_completo,
            'whatsapp': referencia.whatsapp,
            'whatsapp_numero': numero,
            'whatsapp_link': montar_link_whatsapp(numero, mensagem),
            'email': email,
            'status': status_pessoa,
            'status_rotulo': ROTULOS[status_pessoa],
            'quantidade': quantidade,
            'valor': valor,
            'assentos': assentos,
            'quando': quando,
            'pedido_ids': [p.id for p, _ in itens],
            'tentativas_sem_pagar': tentativas_sem_pagar,
            # Comprou, mas antes tinha tentado sem sucesso.
            'tentou_antes': (
                status_pessoa == COMPROU and tentativas_sem_pagar > 0
            ),
        })

    contatos.sort(key=lambda c: c['quando'], reverse=True)

    return contatos, sem_whatsapp


def contar_por_status(contatos):
    contagem = {s: 0 for s in PRIORIDADE}
    for c in contatos:
        contagem[c['status']] += 1
    return contagem


def filtrar_contatos(contatos, status=None, busca=''):
    if status in PRIORIDADE:
        contatos = [c for c in contatos if c['status'] == status]

    busca = (busca or '').strip().lower()
    if busca:
        so_digitos = re.sub(r'\D', '', busca)

        def casa(c):
            if busca in (c['nome'] or '').lower():
                return True
            if busca in (c['email'] or '').lower():
                return True
            return bool(so_digitos) and so_digitos in c['whatsapp_numero']

        contatos = [c for c in contatos if casa(c)]

    return contatos
