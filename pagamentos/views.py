from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from .models import Mensalidade
from .asaas_helper import AsaasAPI
from datetime import datetime
import json


ASAAS_WEBHOOK_TOKEN = settings.ASAAS_WEBHOOK_TOKEN
ASAAS_WEBHOOK_EMAIL = "vinybag@gmail.com"


# ==================== UTILITÁRIOS ====================

def marcar_mensalidade_como_paga(mensalidade, forma_pagamento, comprovante):
    if mensalidade.status != 'pago':
        mensalidade.status = 'pago'
        mensalidade.data_pagamento = datetime.now()
        mensalidade.forma_pagamento = forma_pagamento
        mensalidade.comprovante = comprovante
        mensalidade.save()


def extrair_pix_data(qrcode_data):
    if not qrcode_data:
        return None
    return {
        'payload': qrcode_data.get('payload', ''),
        'encodedImage': qrcode_data.get('encodedImage', ''),
        'expirationDate': qrcode_data.get('expirationDate', ''),
    }


def montar_pix_contexto(mensalidade, payment_id, pix_data, valor):
    return {
        'mensalidade': mensalidade,
        'payment_id': payment_id,
        'pix_data': pix_data,
        'valor': valor,
    }


def localizar_mensalidade_por_payment(payment_id, external_reference, customer_id=None):
    mensalidade = None

    try:
        mensalidade = Mensalidade.objects.get(asaas_payment_id=payment_id)
        print(f"[WEBHOOK] Mensalidade encontrada por asaas_payment_id: {mensalidade.id}")
        return mensalidade
    except Mensalidade.DoesNotExist:
        print(f"[WEBHOOK] Nenhuma mensalidade encontrada por payment_id {payment_id}")

    if external_reference and external_reference.startswith('mensalidade:'):
        try:
            mensalidade_id_ref = external_reference.split(':', 1)[1]
            mensalidade = Mensalidade.objects.get(id=mensalidade_id_ref)
            mensalidade.asaas_payment_id = payment_id
            if customer_id:
                mensalidade.asaas_customer_id = customer_id
                mensalidade.save(update_fields=['asaas_payment_id', 'asaas_customer_id'])
            else:
                mensalidade.save(update_fields=['asaas_payment_id'])

            print(f"[WEBHOOK] Mensalidade localizada por externalReference: {mensalidade.id}")
            return mensalidade
        except Mensalidade.DoesNotExist:
            print(f"[WEBHOOK] Nenhuma mensalidade encontrada para externalReference {external_reference}")
        except Exception as e:
            print(f"[WEBHOOK] Erro ao buscar por externalReference: {e}")

    return None


# ==================== VIEWS ====================

@login_required
def mensalidades(request):
    mensalidades = Mensalidade.objects.filter(responsavel=request.user).order_by('-mes_referencia')
    return render(request, 'pagamentos/mensalidades.html', {'mensalidades': mensalidades})


@login_required
def pagar(request, mensalidade_id):
    mensalidade = get_object_or_404(
        Mensalidade,
        id=mensalidade_id,
        responsavel=request.user
    )

    if mensalidade.status == 'pago':
        return redirect('mensalidades')

    context = {
        'mensalidade': mensalidade,
    }
    return render(request, 'pagamentos/pagar.html', context)


@login_required
def pagar_pix(request, mensalidade_id):
    mensalidade = get_object_or_404(Mensalidade, id=mensalidade_id, responsavel=request.user)

    if mensalidade.status == 'pago':
        return redirect('mensalidades')

    try:
        asaas = AsaasAPI()

        perfil = request.user.perfil
        cpf_cliente = perfil.cpf.replace('.', '').replace('-', '') if perfil.cpf else ''

        if not cpf_cliente or len(cpf_cliente) != 11:
            cpf_cliente = '24971563792'

        customer_data = {
            'name': request.user.get_full_name() or request.user.username,
            'email': request.user.email,
            'cpfCnpj': cpf_cliente,
        }

        descricao = f"Mensalidade {mensalidade.aluna.nome} - {mensalidade.mes_referencia.strftime('%m/%Y')}"
        external_reference = f"mensalidade:{mensalidade.id}"
        payment_id_existente = mensalidade.asaas_payment_id

        if payment_id_existente:
            cobranca_existente = asaas.consultar_cobranca(payment_id_existente)
            print(f"[PIX] Cobrança existente para mensalidade {mensalidade.id}: {cobranca_existente}")

            if cobranca_existente:
                status_existente = cobranca_existente.get('status')

                if status_existente == 'RECEIVED':
                    marcar_mensalidade_como_paga(mensalidade, 'pix', payment_id_existente)
                    return redirect(f'/pagamentos/sucesso/?mensalidade_id={mensalidade.id}')

                if status_existente in ['PENDING', 'OVERDUE']:
                    qrcode_data = asaas.obter_qrcode_pix(payment_id_existente)
                    pix_data = extrair_pix_data(qrcode_data)
                    context = montar_pix_contexto(
                        mensalidade=mensalidade,
                        payment_id=payment_id_existente,
                        pix_data=pix_data,
                        valor=cobranca_existente.get('value', mensalidade.valor),
                    )
                    return render(request, 'pagamentos/pix.html', context)

        resultado = asaas.criar_cobranca_pix(
            valor=mensalidade.valor,
            descricao=descricao,
            customer_data=customer_data,
            external_reference=external_reference,
        )

        print(f"[VIEW] Resultado completo: {resultado}")

        if resultado and 'error' in resultado:
            erro_msg = resultado['error']
            if isinstance(erro_msg, dict):
                mensagem_erro = json.dumps(erro_msg, indent=2, ensure_ascii=False)
            else:
                mensagem_erro = str(erro_msg)

            return render(request, 'pagamentos/pagar.html', {
                'mensalidade': mensalidade,
                'erro': f'Erro Asaas: {mensagem_erro}'
            })

        if resultado and 'id' in resultado:
            mensalidade.asaas_payment_id = resultado['id']
            if 'customer' in resultado:
                mensalidade.asaas_customer_id = resultado['customer']
            mensalidade.save()

            if resultado.get('status') == 'RECEIVED':
                marcar_mensalidade_como_paga(mensalidade, 'pix', resultado['id'])
                return redirect(f'/pagamentos/sucesso/?mensalidade_id={mensalidade.id}')

            qrcode_data = asaas.obter_qrcode_pix(resultado['id'])
            pix_data = extrair_pix_data(qrcode_data)
            context = montar_pix_contexto(
                mensalidade=mensalidade,
                payment_id=resultado['id'],
                pix_data=pix_data,
                valor=resultado.get('value'),
            )
            return render(request, 'pagamentos/pix.html', context)

        return render(request, 'pagamentos/pagar.html', {
            'mensalidade': mensalidade,
            'erro': f'Resposta inesperada do Asaas: {resultado}'
        })

    except Exception as e:
        import traceback
        traceback.print_exc()

        return render(request, 'pagamentos/pagar.html', {
            'mensalidade': mensalidade,
            'erro': f'Erro ao gerar PIX: {str(e)}'
        })


@login_required
def verificar_pagamento_pix(request, payment_id):
    try:
        asaas = AsaasAPI()
        resultado = asaas.consultar_cobranca(payment_id)

        print(f"[Verificação] Payment ID: {payment_id}")
        print(f"[Verificação] Status: {resultado.get('status') if resultado else 'ERRO'}")

        if resultado and resultado.get('status') == 'RECEIVED':
            mensalidade = Mensalidade.objects.get(asaas_payment_id=payment_id)
            marcar_mensalidade_como_paga(mensalidade, 'pix', payment_id)

            return JsonResponse({
                'status': 'paid',
                'redirect': f'/pagamentos/sucesso/?mensalidade_id={mensalidade.id}'
            })

        status = resultado.get('status', 'PENDING') if resultado else 'ERROR'
        return JsonResponse({'status': status.lower()})

    except Exception as e:
        print(f"[Verificação] Erro: {e}")
        return JsonResponse({'error': str(e)}, status=400)


@login_required
def pagamento_sucesso(request):
    mensalidade_id = request.GET.get('mensalidade_id')

    mensalidade = None

    if mensalidade_id:
        try:
            mensalidade = Mensalidade.objects.get(id=mensalidade_id)
        except Exception:
            pass

    if mensalidade:
        return render(request, 'pagamentos/sucesso.html', {'mensalidade': mensalidade})
    else:
        return redirect('mensalidades')


@login_required
def pagamento_cancelado(request):
    return render(request, 'pagamentos/cancelado.html')


# ==================== WEBHOOK DO ASAAS ====================

def localizar_parcela_espetaculo_por_payment_id(payment_id):
    from espetaculo.models import ParcelaCobrancaEspetaculo

    if not payment_id:
        return None

    return (
        ParcelaCobrancaEspetaculo.objects
        .select_related('cobranca', 'cobranca__participacao')
        .filter(asaas_payment_id=payment_id)
        .first()
    )

@csrf_exempt
def webhook_asaas(request):
    """Recebe notificações do Asaas quando um pagamento é atualizado"""

    if request.method == 'POST':
        token_recebido = (
            request.headers.get('asaas-access-token')
            or request.headers.get('access_token')
            or ''
        ).strip()

        token_esperado = (ASAAS_WEBHOOK_TOKEN or '').strip()

        print(f"[WEBHOOK] Token recebido: {token_recebido!r}")

        if not token_recebido or token_recebido != token_esperado:
            print("[WEBHOOK] Token inválido! Acesso negado.")
            return HttpResponse(status=401)

        try:
            dados = json.loads(request.body)
            evento = dados.get('event')
            payment = dados.get('payment', {}) or {}
            payment_id = payment.get('id')
            external_reference = payment.get('externalReference')
            customer_id = payment.get('customer')
            payment_status = payment.get('status')

            print(f"[WEBHOOK] Evento: {evento}, Payment ID: {payment_id}")
            print(f"[WEBHOOK] External Reference: {external_reference}")
            print(f"[WEBHOOK] Payment status: {payment_status}")
            print(f"[WEBHOOK] Dados completos: {json.dumps(dados, indent=2, ensure_ascii=False)}")

            if evento == 'PAYMENT_RECEIVED' and payment_id:

                # 1. Tenta localizar mensalidade
                mensalidade = localizar_mensalidade_por_payment(
                    payment_id=payment_id,
                    external_reference=external_reference,
                    customer_id=customer_id,
                )

                if mensalidade:
                    marcar_mensalidade_como_paga(mensalidade, 'pix', payment_id)
                    print(f"[WEBHOOK] Mensalidade {mensalidade.id} atualizada para PAGO")
                    return HttpResponse(status=200)

                # 2. Tenta localizar parcela de espetáculo
                parcela = localizar_parcela_espetaculo_por_payment_id(payment_id)

                if parcela:
                    parcela.atualizar_status_asaas(payment_status)
                    print(f"[WEBHOOK] Parcela de espetáculo {parcela.id} atualizada com status {payment_status}")
                    return HttpResponse(status=200)

                # 3. Tenta localizar pedido de ingresso de evento
                pedido = localizar_pedido_ingresso_evento_por_payment(
                    payment_id=payment_id,
                    external_reference=external_reference,
                    customer_id=customer_id,
                )

                if pedido:
                    pedido.marcar_como_pago()
                    gerar_ingressos_do_pedido_webhook(pedido)
                    print(f"[WEBHOOK] Pedido de ingresso {pedido.id} atualizado para PAGO")
                    return HttpResponse(status=200)

                print(f"[WEBHOOK] Nenhuma mensalidade, parcela ou pedido localizada para payment_id {payment_id}")
                return HttpResponse(status=200)

            print(f"[WEBHOOK] Evento ignorado: {evento}")
            return HttpResponse(status=200)

        except Exception as e:
            print(f"[WEBHOOK] Erro: {e}")
            import traceback
            traceback.print_exc()
            return HttpResponse(status=500)

    return HttpResponse(status=405)

def localizar_pedido_ingresso_evento_por_payment(payment_id, external_reference=None, customer_id=None):
    from espetaculo.models import PedidoIngressoEvento

    pedido = PedidoIngressoEvento.objects.filter(asaas_payment_id=payment_id).first()
    if pedido:
        return pedido

    if external_reference and external_reference.startswith('ingresso_evento:'):
        try:
            pedido_id = external_reference.split(':', 1)[1]
            pedido = PedidoIngressoEvento.objects.get(id=pedido_id)
            pedido.asaas_payment_id = payment_id
            if customer_id:
                pedido.asaas_customer_id = customer_id
                pedido.save(update_fields=['asaas_payment_id', 'asaas_customer_id'])
            else:
                pedido.save(update_fields=['asaas_payment_id'])
            return pedido
        except PedidoIngressoEvento.DoesNotExist:
            return None

    return None


def gerar_ingressos_do_pedido_webhook(pedido):
    from espetaculo.models import IngressoEvento

    if pedido.ingressos.exists():
        return

    for _ in range(pedido.quantidade):
        codigo = IngressoEvento.gerar_codigo()
        while IngressoEvento.objects.filter(codigo_unico=codigo).exists():
            codigo = IngressoEvento.gerar_codigo()

        IngressoEvento.objects.create(
            pedido=pedido,
            evento=pedido.evento,
            codigo_unico=codigo,
            nome_participante=pedido.nome_completo,
        )