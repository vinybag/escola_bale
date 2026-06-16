from django.shortcuts import render, get_object_or_404, redirect
from .models import Espetaculo, InscricaoAudicao
from .forms import InscricaoAudicaoForm
from django.contrib import messages
from django.http import JsonResponse
import traceback
from decimal import Decimal
from django.utils import timezone
from .models import Espetaculo, PedidoIngressoEvento, IngressoEvento
from pagamentos.asaas_helper import AsaasAPI

def espetaculo_home(request):
    """Página inicial do espetáculo"""
    try:
        if request.user.is_authenticated:
            espetaculo = Espetaculo.objects.filter(ativo=True).order_by('-data_apresentacao').first()
        else:
            espetaculo = Espetaculo.objects.filter(ativo=True, publico=True).order_by('-data_apresentacao').first()
    except Exception:
        espetaculo = None

    context = {
        'espetaculo': espetaculo,
    }

    return render(request, 'espetaculo/home.html', context)


def espetaculos_lista_publica(request):
    """Página pública com lista de espetáculos/eventos ativos"""
    if request.user.is_authenticated:
        espetaculos = Espetaculo.objects.filter(ativo=True).order_by('-data_apresentacao')
    else:
        espetaculos = Espetaculo.objects.filter(ativo=True, publico=True).order_by('-data_apresentacao')

    return render(request, 'espetaculo/public_list.html', {'espetaculos': espetaculos})


def espetaculo_detalhes_publico(request, pk):
    """Página pública com detalhes de um espetáculo/evento específico"""

    if request.user.is_authenticated:
        queryset = Espetaculo.objects.filter(ativo=True)
    else:
        queryset = Espetaculo.objects.filter(ativo=True, publico=True)

    espetaculo = get_object_or_404(queryset, pk=pk)

    return render(request, 'espetaculo/public_detalhes.html', {'espetaculo': espetaculo})

def personagens_publicos(request):
    """Página pública com os personagens clicáveis"""
    from .models import Espetaculo
    espetaculo = Espetaculo.objects.filter(ativo=True).first()
    return render(request, 'espetaculo/personagens_publicos.html', {'espetaculo': espetaculo})

def inscricao_audicao(request):
    """Processa a inscrição para audição"""
    if request.method == 'POST':
        form = InscricaoAudicaoForm(request.POST)
        if form.is_valid():
            inscricao = form.save(commit=False)
            # Pega o espetáculo ativo
            from .models import Espetaculo
            espetaculo = Espetaculo.objects.filter(ativo=True).first()
            inscricao.espetaculo = espetaculo
            inscricao.save()
            messages.success(request, 'Inscrição realizada com sucesso! Entraremos em contato em breve.')
            return redirect('/espetaculos/inscricao-sucesso/')
        else:
            messages.error(request, 'Erro ao realizar inscrição. Verifique os dados.')
    
    return redirect('/espetaculos/personagens/')

def inscricao_sucesso(request):
    """Página de confirmação de inscrição"""
    return render(request, 'espetaculo/inscricao_sucesso.html')

def get_personagens_por_idade(request):
    """Retorna os personagens disponíveis para a idade informada"""
    idade = int(request.GET.get('idade', 0))
    
    # Regras de idade por personagem
    regras = {
        'thessalia': idade >= 15,
        'zyara': idade >= 8,
        'zyar': idade >= 8,
        'astela_nur': idade >= 16,
        'kai_ignus': idade >= 10,
        'eldrick_felicius': idade >= 10,
        'florine': 8 <= idade <= 20,
        'odessa': idade >= 10,
        'aurelia': idade >= 10,
        'cora_del_amour': idade >= 8,
        '3_marias': 6 <= idade <= 12,
    }
    
    personagens_disponiveis = []
    for personagem_id, disponivel in regras.items():
        if disponivel:
            # Pega o nome do dicionário PERSONAGENS_CHOICES do modelo
            dict_choices = dict(InscricaoAudicao.PERSONAGENS_CHOICES)
            nome = dict_choices.get(personagem_id, personagem_id)
            personagens_disponiveis.append({'id': personagem_id, 'nome': nome})
    
    return JsonResponse({'personagens': personagens_disponiveis})


def audicao_rosa_branca(request):
    espetaculo = Espetaculo.objects.filter(ativo=True).first()

    if request.method == 'POST':
        try:
            nome_completo = request.POST.get('nome_completo', '').strip()
            whatsapp = request.POST.get('whatsapp', '').strip()
            idade = request.POST.get('idade', '').strip()
            turma_atual = request.POST.get('turma_atual', '').strip()
            responsavel = request.POST.get('responsavel', '').strip()
            confirmacao = request.POST.get('confirmacao_requisitos')

            if not all([nome_completo, whatsapp, idade, turma_atual, responsavel, confirmacao]):
                messages.error(request, 'Preencha todos os campos obrigatórios.')
                return render(request, 'espetaculo/audicao_rosa_branca.html', {'espetaculo': espetaculo})

            idade_int = int(idade)

            if idade_int < 6:
                messages.error(request, 'Essa audição é permitida somente para crianças a partir de 6 anos.')
                return render(request, 'espetaculo/audicao_rosa_branca.html', {'espetaculo': espetaculo})

            inscricao = InscricaoAudicao.objects.create(
                nome_completo=nome_completo,
                whatsapp=whatsapp,
                idade=idade_int,
                personagens='rosa_branca',
                espetaculo=espetaculo,
            )

            print(f'INSCRIÇÃO AUDIÇÃO CRIADA: id={inscricao.id}, nome={inscricao.nome_completo}, personagem={inscricao.personagens}')

            messages.success(request, 'Inscrição enviada com sucesso!')
            return redirect('espetaculo:audicao_rosa_branca_sucesso')

        except Exception as e:
            print('ERRO AO SALVAR INSCRIÇÃO DA ROSA BRANCA')
            print(str(e))
            traceback.print_exc()
            messages.error(request, f'Erro ao enviar inscrição: {e}')
            return render(request, 'espetaculo/audicao_rosa_branca.html', {'espetaculo': espetaculo})

    return render(request, 'espetaculo/audicao_rosa_branca.html', {'espetaculo': espetaculo})


def audicao_rosa_branca_sucesso(request):
    return render(request, 'espetaculo/audicao_rosa_branca_sucesso.html')

def audicao_nova_publica(request):
    espetaculo = Espetaculo.objects.filter(ativo=True).first()
    return render(request, 'espetaculo/audicao_nova_publica.html', {'espetaculo': espetaculo})

def audicao_rosa_branca_sucesso(request):
    return render(request, 'espetaculo/audicao_rosa_branca_sucesso.html')




def gerar_ingressos_do_pedido(pedido):
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


def extrair_pix_data_evento(qrcode_data):
    if not qrcode_data:
        return None
    return {
        'payload': qrcode_data.get('payload', ''),
        'encodedImage': qrcode_data.get('encodedImage', ''),
        'expirationDate': qrcode_data.get('expirationDate', ''),
    }


def localizar_pedido_ingresso_por_payment(payment_id, external_reference=None, customer_id=None):
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


def evento_detalhe_publico(request, pk):
    """Página pública de detalhe de um evento específico"""

    # Busca o evento ativo
    evento = get_object_or_404(Espetaculo, pk=pk, ativo=True)

    # Se for privado e o usuário não estiver logado, nega o acesso
    if not evento.publico and not request.user.is_authenticated:
        return redirect('espetaculo:lista_publica')

    # Só abre essa página para itens do tipo 'evento'
    if evento.tipo != 'evento':
        return redirect('espetaculo:detalhes_publico', pk=pk)

    return render(request, 'espetaculo/evento_detalhe.html', {'evento': evento})


def comprar_ingresso(request, pk):
    evento = get_object_or_404(Espetaculo, pk=pk, ativo=True)

    # Proteção de acesso para evento privado
    if not evento.publico and not request.user.is_authenticated:
        return redirect('espetaculo:lista_publica')

    # Só eventos entram no fluxo de ingresso
    if evento.tipo != 'evento':
        return redirect('espetaculo:detalhes_publico', pk=evento.pk)

    if not evento.venda_aberta:
        return redirect('espetaculo:evento_detalhe_publico', pk=evento.pk)

    if request.method == 'POST':
        nome_completo = request.POST.get('nome_completo', '').strip()
        email = request.POST.get('email', '').strip()
        whatsapp = request.POST.get('whatsapp', '').strip()
        cpf = request.POST.get('cpf', '').strip()
        quantidade = request.POST.get('quantidade', '1').strip()

        try:
            quantidade = int(quantidade)
        except Exception:
            quantidade = 1

        if quantidade < 1:
            quantidade = 1

        if not nome_completo or not whatsapp:
            return render(request, 'espetaculo/comprar_ingresso.html', {
                'evento': evento,
                'erro': 'Preencha os campos obrigatórios.',
            })

        valor_unitario = evento.preco_ingresso or Decimal('0.00')
        valor_total = valor_unitario * quantidade

        pedido = PedidoIngressoEvento.objects.create(
            evento=evento,
            nome_completo=nome_completo,
            email=email,
            whatsapp=whatsapp,
            cpf=cpf,
            quantidade=quantidade,
            valor_unitario=valor_unitario,
            valor_total=valor_total,
            status='pendente',
        )
        pedido.external_reference = f'ingresso_evento:{pedido.id}'
        pedido.save(update_fields=['external_reference'])

        return redirect('espetaculo:pagar_ingresso_pix', pedido_id=pedido.id)

    return render(request, 'espetaculo/comprar_ingresso.html', {
        'evento': evento,
    })


def pagar_ingresso_pix(request, pedido_id):
    pedido = get_object_or_404(PedidoIngressoEvento, id=pedido_id)
    evento = pedido.evento

    # Proteção de acesso para evento privado
    if not evento.publico and not request.user.is_authenticated:
        return redirect('espetaculo:lista_publica')

    # Garante consistência do fluxo
    if evento.tipo != 'evento':
        return redirect('espetaculo:detalhes_publico', pk=evento.pk)

    if not evento.venda_aberta and pedido.status != 'pago':
        return redirect('espetaculo:evento_detalhe_publico', pk=evento.pk)

    if pedido.status == 'pago':
        return redirect('espetaculo:ingresso_sucesso', pedido_id=pedido.id)

    try:
        asaas = AsaasAPI()

        cpf_cliente = (pedido.cpf or '').replace('.', '').replace('-', '').replace('/', '')
        if not cpf_cliente or len(cpf_cliente) != 11:
            cpf_cliente = '24971563792'

        customer_data = {
            'name': pedido.nome_completo,
            'email': pedido.email or 'sem-email@evento.local',
            'cpfCnpj': cpf_cliente,
        }

        descricao = f"Ingresso - {pedido.evento.titulo}"
        payment_id_existente = pedido.asaas_payment_id

        if payment_id_existente:
            cobranca_existente = asaas.consultar_cobranca(payment_id_existente)

            if cobranca_existente:
                status_existente = cobranca_existente.get('status')

                if status_existente == 'RECEIVED':
                    pedido.marcar_como_pago()
                    gerar_ingressos_do_pedido(pedido)
                    return redirect('espetaculo:ingresso_sucesso', pedido_id=pedido.id)

                if status_existente in ['PENDING', 'OVERDUE']:
                    qrcode_data = asaas.obter_qrcode_pix(payment_id_existente)
                    pix_data = extrair_pix_data_evento(qrcode_data)
                    return render(request, 'espetaculo/pix_ingresso.html', {
                        'pedido': pedido,
                        'evento': evento,
                        'payment_id': payment_id_existente,
                        'pix_data': pix_data,
                        'valor': cobranca_existente.get('value', pedido.valor_total),
                    })

        resultado = asaas.criar_cobranca_pix(
            valor=pedido.valor_total,
            descricao=descricao,
            customer_data=customer_data,
            external_reference=pedido.external_reference,
        )

        if resultado and 'error' in resultado:
            return render(request, 'espetaculo/comprar_ingresso.html', {
                'evento': evento,
                'erro': f"Erro Asaas: {resultado['error']}",
            })

        if resultado and 'id' in resultado:
            pedido.asaas_payment_id = resultado['id']
            if 'customer' in resultado:
                pedido.asaas_customer_id = resultado['customer']
            pedido.save(update_fields=['asaas_payment_id', 'asaas_customer_id'])

            if resultado.get('status') == 'RECEIVED':
                pedido.marcar_como_pago()
                gerar_ingressos_do_pedido(pedido)
                return redirect('espetaculo:ingresso_sucesso', pedido_id=pedido.id)

            qrcode_data = asaas.obter_qrcode_pix(resultado['id'])
            pix_data = extrair_pix_data_evento(qrcode_data)

            if pix_data and pix_data.get('payload'):
                pedido.codigo_pix = pix_data['payload']
                pedido.save(update_fields=['codigo_pix'])

            return render(request, 'espetaculo/pix_ingresso.html', {
                'pedido': pedido,
                'evento': evento,
                'payment_id': resultado['id'],
                'pix_data': pix_data,
                'valor': resultado.get('value', pedido.valor_total),
            })

        return render(request, 'espetaculo/comprar_ingresso.html', {
            'evento': evento,
            'erro': f'Resposta inesperada do Asaas: {resultado}',
        })

    except Exception as e:
        traceback.print_exc()
        return render(request, 'espetaculo/comprar_ingresso.html', {
            'evento': evento,
            'erro': f'Erro ao gerar PIX: {str(e)}',
        })


def verificar_pagamento_ingresso_pix(request, payment_id):
    try:
        asaas = AsaasAPI()
        resultado = asaas.consultar_cobranca(payment_id)

        if resultado and resultado.get('status') == 'RECEIVED':
            pedido = PedidoIngressoEvento.objects.get(asaas_payment_id=payment_id)
            pedido.marcar_como_pago()
            gerar_ingressos_do_pedido(pedido)

            return JsonResponse({
                'status': 'paid',
                'redirect': f"/espetaculos/ingresso/sucesso/{pedido.id}/"
            })

        status = resultado.get('status', 'PENDING') if resultado else 'ERROR'
        return JsonResponse({'status': status.lower()})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


def ingresso_sucesso(request, pedido_id):
    pedido = get_object_or_404(PedidoIngressoEvento, id=pedido_id)
    evento = pedido.evento

    # Proteção de acesso para evento privado
    if not evento.publico and not request.user.is_authenticated:
        return redirect('espetaculo:lista_publica')

    if evento.tipo != 'evento':
        return redirect('espetaculo:detalhes_publico', pk=evento.pk)

    if pedido.status != 'pago':
        return redirect('espetaculo:pagar_ingresso_pix', pedido_id=pedido.id)

    ingressos = pedido.ingressos.all()

    return render(request, 'espetaculo/ingresso_sucesso.html', {
        'pedido': pedido,
        'evento': evento,
        'ingressos': ingressos,
    })