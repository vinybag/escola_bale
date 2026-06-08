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
    """Centraliza a atualização da mensalidade para evitar lógica duplicada."""
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


def obter_forma_pagamento_asaas(payment):
    billing_type = (payment or {}).get('billingType')

    if billing_type == 'PIX':
        return 'pix'
    if billing_type in ['CREDIT_CARD', 'DEBIT_CARD']:
        return 'cartao'

    return 'asaas'


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
def pagar_cartao(request, mensalidade_id):
    mensalidade = get_object_or_404(
        Mensalidade,
        id=mensalidade_id,
        responsavel=request.user
    )

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
        success_url = request.build_absolute_uri(f'/pagamentos/sucesso/?mensalidade_id={mensalidade.id}')

        customer_id = mensalidade.asaas_customer_id or None

        resultado = asaas.criar_cobranca_cartao_redirect(
            valor=mensalidade.valor,
            descricao=descricao,
            due_date=mensalidade.vencimento.strftime("%Y-%m-%d"),
            success_url=success_url,
            customer_id=customer_id,
            customer_data=None if customer_id else customer_data,
            external_reference=external_reference,
        )

        print(f"[CARTAO] Resultado completo: {resultado}")

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
                mensalidade.save(update_fields=['asaas_payment_id', 'asaas_customer_id'])
            else:
                mensalidade.save(update_fields=['asaas_payment_id'])

            invoice_url = resultado.get('invoiceUrl')
            if not invoice_url:
                return render(request, 'pagamentos/pagar.html', {
                    'mensalidade': mensalidade,
                    'erro': 'O Asaas não retornou a invoiceUrl para o pagamento com cartão.'
                })

            return redirect(invoice_url)

        return render(request, 'pagamentos/pagar.html', {
            'mensalidade': mensalidade,
            'erro': f'Resposta inesperada do Asaas: {resultado}'
        })

    except Exception as e:
        import traceback
        traceback.print_exc()

        return render(request, 'pagamentos/pagar.html', {
            'mensalidade': mensalidade,
            'erro': f'Erro ao processar pagamento com cartão: {str(e)}'
        })


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

        # 1) Reaproveita cobrança existente se ainda estiver válida
        if payment_id_existente:
            cobranca_existente = asaas.consultar_cobranca(payment_id_existente)
            print(f"[PIX] Cobrança existente para mensalidade {mensalidade.id}: {cobranca_existente}")

            if cobranca_existente:
                status_existente = cobranca_existente.get('status')
                billing_type_existente = cobranca_existente.get('billingType')

                # Só reaproveita se a cobrança existente for realmente PIX
                if billing_type_existente == 'PIX':
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

        # 2) Nenhuma cobrança válida — cria uma nova
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
    """Verifica se o pagamento PIX foi confirmado no Asaas"""
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
            payment = dados.get('payment', {})
            payment_id = payment.get('id')
            external_reference = payment.get('externalReference')
            customer_id = payment.get('customer')
            billing_type = payment.get('billingType')

            print(f"[WEBHOOK] Evento: {evento}, Payment ID: {payment_id}")
            print(f"[WEBHOOK] Billing Type: {billing_type}")
            print(f"[WEBHOOK] External Reference: {external_reference}")
            print(f"[WEBHOOK] Dados completos: {json.dumps(dados, indent=2, ensure_ascii=False)}")

            eventos_que_baixam = ['PAYMENT_RECEIVED', 'PAYMENT_CONFIRMED']

            if evento in eventos_que_baixam and payment_id:
                mensalidade = localizar_mensalidade_por_payment(
                    payment_id=payment_id,
                    external_reference=external_reference,
                    customer_id=customer_id,
                )

                if mensalidade:
                    forma_pagamento = obter_forma_pagamento_asaas(payment)
                    marcar_mensalidade_como_paga(mensalidade, forma_pagamento, payment_id)
                    print(f"[WEBHOOK] Mensalidade {mensalidade.id} atualizada para PAGO via {forma_pagamento}")
                else:
                    print(f"[WEBHOOK] Nenhuma mensalidade localizada para payment_id {payment_id}")

                return HttpResponse(status=200)

            print(f"[WEBHOOK] Evento ignorado: {evento}")
            return HttpResponse(status=200)

        except Exception as e:
            print(f"[WEBHOOK] Erro: {e}")
            import traceback
            traceback.print_exc()
            return HttpResponse(status=500)

    return HttpResponse(status=405)