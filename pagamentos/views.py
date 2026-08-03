from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from .models import Mensalidade
from .asaas_helper import AsaasAPI
from datetime import datetime
import json
from espetaculo.services.ingressos import confirmar_pagamento_pedido


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

    if mensalidade.status_atual == 'pago':
        return redirect('mensalidades')

    context = {
        'mensalidade': mensalidade,
    }
    return render(request, 'pagamentos/pagar.html', context)


@login_required
def pagar_pix(request, mensalidade_id):
    from decimal import Decimal

    mensalidade = get_object_or_404(Mensalidade, id=mensalidade_id, responsavel=request.user)

    if mensalidade.status_atual == 'pago':
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

        valor_cobranca = mensalidade.valor_atualizado
        descricao = f"Mensalidade {mensalidade.aluna.nome} - {mensalidade.mes_referencia.strftime('%m/%Y')}"
        external_reference = f"mensalidade:{mensalidade.id}"
        payment_id_existente = mensalidade.asaas_payment_id

        if payment_id_existente:
            cobranca_existente = asaas.consultar_cobranca(payment_id_existente)
            print(f"[PIX] Cobrança existente para mensalidade {mensalidade.id}: {cobranca_existente}")

            if cobranca_existente:
                status_existente = cobranca_existente.get('status')
                valor_existente = Decimal(str(cobranca_existente.get('value', '0.00'))).quantize(Decimal('0.01'))
                valor_atual = Decimal(str(valor_cobranca)).quantize(Decimal('0.01'))

                if status_existente == 'RECEIVED':
                    marcar_mensalidade_como_paga(mensalidade, 'pix', payment_id_existente)
                    return redirect(f'/pagamentos/sucesso/?mensalidade_id={mensalidade.id}')

                if status_existente in ['PENDING', 'OVERDUE']:
                    if valor_existente == valor_atual:
                        qrcode_data = asaas.obter_qrcode_pix(payment_id_existente)
                        pix_data = extrair_pix_data(qrcode_data)
                        context = montar_pix_contexto(
                            mensalidade=mensalidade,
                            payment_id=payment_id_existente,
                            pix_data=pix_data,
                            valor=valor_existente,
                        )
                        return render(request, 'pagamentos/pix.html', context)

                    print(
                        f"[PIX] Valor desatualizado na cobrança existente. "
                        f"Asaas={valor_existente} | Sistema={valor_atual}. "
                        f"Nova cobrança será criada."
                    )

        resultado = asaas.criar_cobranca_pix(
            valor=valor_cobranca,
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
            mensalidade.save(update_fields=['asaas_payment_id', 'asaas_customer_id'] if 'customer' in resultado else ['asaas_payment_id'])

            if resultado.get('status') == 'RECEIVED':
                marcar_mensalidade_como_paga(mensalidade, 'pix', resultado['id'])
                return redirect(f'/pagamentos/sucesso/?mensalidade_id={mensalidade.id}')

            qrcode_data = asaas.obter_qrcode_pix(resultado['id'])
            pix_data = extrair_pix_data(qrcode_data)
            context = montar_pix_contexto(
                mensalidade=mensalidade,
                payment_id=resultado['id'],
                pix_data=pix_data,
                valor=resultado.get('value', valor_cobranca),
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


def localizar_agendamento_por_payment(payment_id, external_reference=None, customer_id=None):
    from agenda.models import Agendamento

    agendamento = Agendamento.objects.filter(asaas_payment_id=payment_id).first()
    if agendamento:
        print(f"[WEBHOOK] Agendamento encontrado por asaas_payment_id: {agendamento.id}")
        return agendamento

    if external_reference and external_reference.startswith('agendamento_experimental:'):
        try:
            agendamento_id = external_reference.split(':', 1)[1]
            agendamento = Agendamento.objects.get(id=agendamento_id)
            agendamento.asaas_payment_id = payment_id

            update_fields = ['asaas_payment_id']
            if customer_id:
                agendamento.asaas_customer_id = customer_id
                update_fields.append('asaas_customer_id')

            agendamento.save(update_fields=update_fields)
            print(f"[WEBHOOK] Agendamento localizado por externalReference: {agendamento.id}")
            return agendamento

        except Agendamento.DoesNotExist:
            print(f"[WEBHOOK] Nenhum agendamento encontrado para externalReference {external_reference}")
            return None

    return None


def localizar_parcela_espetaculo_por_payment(payment_id, external_reference=None, customer_id=None, installment_id=None):
    from espetaculo.models import CobrancaEspetaculo, ParcelaCobrancaEspetaculo

    if payment_id:
        parcela = (
            ParcelaCobrancaEspetaculo.objects
            .select_related('cobranca', 'cobranca__participacao')
            .filter(asaas_payment_id=payment_id)
            .first()
        )
        if parcela:
            print(f"[WEBHOOK] Parcela encontrada por payment_id: {parcela.id}")
            return parcela

    if installment_id:
        parcela = (
            ParcelaCobrancaEspetaculo.objects
            .select_related('cobranca', 'cobranca__participacao')
            .filter(asaas_installment_id=installment_id)
            .order_by('numero_parcela', 'id')
            .first()
        )
        if parcela:
            if payment_id and parcela.asaas_payment_id != payment_id:
                parcela.asaas_payment_id = payment_id
                parcela.save(update_fields=['asaas_payment_id'])
            print(f"[WEBHOOK] Parcela encontrada por installment_id: {parcela.id}")
            return parcela

    if external_reference and external_reference.startswith('cobranca_espetaculo:'):
        try:
            cobranca_id = external_reference.split(':', 1)[1]
            cobranca = (
                CobrancaEspetaculo.objects
                .select_related('participacao')
                .prefetch_related('parcelas')
                .get(id=cobranca_id)
            )

            if customer_id and cobranca.asaas_customer_id != customer_id:
                cobranca.asaas_customer_id = customer_id
                cobranca.save(update_fields=['asaas_customer_id'])

            parcela = cobranca.parcelas.filter(asaas_payment_id=payment_id).first()
            if parcela:
                print(f"[WEBHOOK] Parcela encontrada via cobrança + payment_id: {parcela.id}")
                return parcela

            if installment_id:
                parcela = cobranca.parcelas.filter(asaas_installment_id=installment_id).order_by('numero_parcela', 'id').first()
                if parcela:
                    if payment_id and parcela.asaas_payment_id != payment_id:
                        parcela.asaas_payment_id = payment_id
                        parcela.save(update_fields=['asaas_payment_id'])
                    print(f"[WEBHOOK] Parcela encontrada via cobrança + installment_id: {parcela.id}")
                    return parcela

            if cobranca.parcelas.count() == 1:
                parcela = cobranca.parcelas.first()
                if parcela and payment_id and parcela.asaas_payment_id != payment_id:
                    parcela.asaas_payment_id = payment_id
                    parcela.save(update_fields=['asaas_payment_id'])
                print(f"[WEBHOOK] Parcela única localizada via externalReference: {parcela.id}")
                return parcela

            print(
                f"[WEBHOOK] Cobrança {cobranca.id} localizada, "
                f"mas nenhuma parcela foi associada ao payment_id={payment_id}, installment_id={installment_id}"
            )

        except CobrancaEspetaculo.DoesNotExist:
            print(f"[WEBHOOK] Cobrança não encontrada para externalReference {external_reference}")
        except Exception as e:
            print(f"[WEBHOOK] Erro ao localizar parcela de espetáculo: {e}")

    return None


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

            eventos_confirmacao = {'PAYMENT_RECEIVED', 'PAYMENT_CONFIRMED', 'PAYMENT_UPDATED'}
            status_confirmados = {'RECEIVED', 'CONFIRMED', 'RECEIVED_IN_CASH'}

            if evento in eventos_confirmacao and payment_id and payment_status in status_confirmados:

                mensalidade = localizar_mensalidade_por_payment(
                    payment_id=payment_id,
                    external_reference=external_reference,
                    customer_id=customer_id,
                )

                if mensalidade:
                    marcar_mensalidade_como_paga(mensalidade, 'pix', payment_id)
                    print(f"[WEBHOOK] Mensalidade {mensalidade.id} atualizada para PAGO")
                    return HttpResponse(status=200)

                agendamento = localizar_agendamento_por_payment(
                    payment_id=payment_id,
                    external_reference=external_reference,
                    customer_id=customer_id,
                )

                if agendamento:
                    from agenda.services import confirmar_pagamento_agendamento
                    confirmar_pagamento_agendamento(agendamento, payment_id)
                    print(f"[WEBHOOK] Agendamento {agendamento.id} atualizado para PAGO")
                    return HttpResponse(status=200)

                installment_id = payment.get('installment')

                parcela = localizar_parcela_espetaculo_por_payment(
                    payment_id=payment_id,
                    external_reference=external_reference,
                    customer_id=customer_id,
                    installment_id=installment_id,
                )

                if parcela:
                    parcela.atualizar_status_asaas(payment_status)
                    print(f"[WEBHOOK] Parcela de espetáculo {parcela.id} atualizada com status {payment_status}")
                    return HttpResponse(status=200)

                pedido = localizar_pedido_ingresso_evento_por_payment(
                    payment_id=payment_id,
                    external_reference=external_reference,
                    customer_id=customer_id,
                )

                if pedido:
                    confirmar_pagamento_pedido(pedido)
                    print(f"[WEBHOOK] Pedido de ingresso {pedido.id} atualizado para PAGO")
                    return HttpResponse(status=200)

                print(f"[WEBHOOK] Nenhuma mensalidade, agendamento, parcela ou pedido localizado para payment_id {payment_id}")
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

            update_fields = ['asaas_payment_id']

            if customer_id:
                pedido.asaas_customer_id = customer_id
                update_fields.append('asaas_customer_id')

            pedido.save(update_fields=update_fields)
            return pedido

        except PedidoIngressoEvento.DoesNotExist:
            return None

    return None