import json
import os
import traceback
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib import messages
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from pagamentos.asaas_helper import AsaasAPI
from usuarios.models import Aluna

from .forms import InscricaoAudicaoForm
from .models import (
    Assento,
    Espetaculo,
    IngressoEvento,
    InscricaoAudicao,
    MapaAssentos,
    PedidoIngressoEvento,
)


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
    espetaculo = Espetaculo.objects.filter(ativo=True).first()
    return render(request, 'espetaculo/personagens_publicos.html', {'espetaculo': espetaculo})


def inscricao_audicao(request):
    """Processa a inscrição para audição"""
    if request.method == 'POST':
        form = InscricaoAudicaoForm(request.POST)
        if form.is_valid():
            inscricao = form.save(commit=False)
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
    try:
        idade = int(request.GET.get('idade', 0))
    except (TypeError, ValueError):
        idade = 0

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
        'rosa_branca': idade >= 6,
    }

    personagens_disponiveis = []
    dict_choices = dict(InscricaoAudicao.PERSONAGENS_CHOICES)

    for personagem_id, disponivel in regras.items():
        if disponivel:
            nome = dict_choices.get(personagem_id, personagem_id)
            personagens_disponiveis.append({'id': personagem_id, 'nome': nome})

    return JsonResponse({'personagens': personagens_disponiveis})


def audicao_rosa_branca(request):
    template_name = 'espetaculo/audicao_nova_publica.html'

    espetaculo = Espetaculo.objects.filter(ativo=True, audicao_aberta=True).order_by('-data_apresentacao').first()

    if not espetaculo:
        espetaculo = Espetaculo.objects.filter(ativo=True).order_by('-data_apresentacao').first()

    if request.method == 'POST':
        try:
            nome_completo = request.POST.get('nome_completo', '').strip()
            whatsapp = request.POST.get('whatsapp', '').strip()
            idade = request.POST.get('idade', '').strip()
            turma_atual = request.POST.get('turma_atual', '').strip()
            responsavel = request.POST.get('responsavel', '').strip()
            observacoes = request.POST.get('observacoes', '').strip()
            confirmacao = request.POST.get('confirmacao_requisitos')

            if not all([nome_completo, whatsapp, idade, turma_atual, responsavel, confirmacao]):
                messages.error(request, 'Preencha todos os campos obrigatórios.')
                return render(request, template_name, {'espetaculo': espetaculo})

            try:
                idade_int = int(idade)
            except (TypeError, ValueError):
                messages.error(request, 'Informe uma idade válida.')
                return render(request, template_name, {'espetaculo': espetaculo})

            if idade_int < 6:
                messages.error(request, 'Essa audição é permitida somente para crianças a partir de 6 anos.')
                return render(request, template_name, {'espetaculo': espetaculo})

            inscricao = InscricaoAudicao.objects.create(
                nome_completo=nome_completo,
                whatsapp=whatsapp,
                idade=idade_int,
                personagens='rosa_branca',
                espetaculo=espetaculo,
            )

            print(
                f'INSCRIÇÃO AUDIÇÃO CRIADA: '
                f'id={inscricao.id}, '
                f'nome={inscricao.nome_completo}, '
                f'personagem={inscricao.personagens}, '
                f'turma={turma_atual}, '
                f'responsavel={responsavel}, '
                f'observacoes={observacoes}'
            )

            messages.success(request, 'Inscrição enviada com sucesso!')
            return redirect('espetaculo:audicao_rosa_branca_sucesso')

        except Exception as e:
            print('ERRO AO SALVAR INSCRIÇÃO DA ROSA BRANCA')
            print(str(e))
            traceback.print_exc()
            messages.error(request, f'Erro ao enviar inscrição: {e}')
            return render(request, template_name, {'espetaculo': espetaculo})

    return render(request, template_name, {'espetaculo': espetaculo})


def audicao_rosa_branca_sucesso(request):
    return render(request, 'espetaculo/audicao_rosa_branca_sucesso.html')


def audicao_nova_publica(request):
    espetaculo = Espetaculo.objects.filter(ativo=True).order_by('-data_apresentacao').first()
    return render(request, 'espetaculo/audicao_nova_publica.html', {'espetaculo': espetaculo})


def gerar_ingressos_do_pedido(pedido, assentos_ids=None):
    """
    Gera os IngressoEvento do pedido. Se assentos_ids for informado
    (fluxo com mapa de assentos numerados), cada ingresso criado é
    vinculado a um assento e o assento é marcado como vendido.
    """
    ingressos_existentes = pedido.ingressos.count()

    if ingressos_existentes >= pedido.quantidade:
        for ingresso in pedido.ingressos.all():
            ingresso.garantir_arquivos()
        return

    faltantes = pedido.quantidade - ingressos_existentes

    assentos_disponiveis = []
    if assentos_ids:
        assentos_disponiveis = list(
            Assento.objects.filter(id__in=assentos_ids, mapa__evento=pedido.evento)
        )

    for indice in range(faltantes):
        codigo = IngressoEvento.gerar_codigo()

        while IngressoEvento.objects.filter(codigo_unico=codigo).exists():
            codigo = IngressoEvento.gerar_codigo()

        assento_vinculado = None
        if indice < len(assentos_disponiveis):
            assento_vinculado = assentos_disponiveis[indice]

        ingresso = IngressoEvento.objects.create(
            pedido=pedido,
            evento=pedido.evento,
            codigo_unico=codigo,
            nome_participante=pedido.nome_completo,
            assento=assento_vinculado,
        )
        ingresso.garantir_arquivos()

        if assento_vinculado:
            assento_vinculado.marcar_como_vendido()


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
    evento = get_object_or_404(Espetaculo, pk=pk, ativo=True)

    if not evento.publico and not request.user.is_authenticated:
        return redirect('espetaculo:lista_publica')

    if evento.tipo != 'evento':
        return redirect('espetaculo:detalhes_publico', pk=pk)

    return render(request, 'espetaculo/evento_detalhe.html', {'evento': evento})


def comprar_ingresso(request, pk):
    evento = get_object_or_404(
        Espetaculo,
        pk=pk,
        ativo=True
    )

    if not evento.publico and not request.user.is_authenticated:
        return redirect('espetaculo:lista_publica')

    if evento.tipo != 'evento':
        return redirect(
            'espetaculo:detalhes_publico',
            pk=evento.pk
        )

    if not evento.venda_aberta:
        return redirect(
            'espetaculo:evento_detalhe_publico',
            pk=evento.pk
        )

    if evento.exige_login_para_compra and not request.user.is_authenticated:
        messages.error(
            request,
            'Você precisa estar logado para comprar ingresso para este evento.'
        )
        return redirect(
            'espetaculo:evento_detalhe_publico',
            pk=evento.pk
        )

    aluna = None

    if request.user.is_authenticated:
        aluna = Aluna.objects.filter(
            usuario=request.user
        ).first()

    if evento.permite_ingresso_gratuito_aluna and aluna:
        pedido_existente = PedidoIngressoEvento.objects.filter(
            evento=evento,
            email=request.user.email,
            status='pago',
            external_reference__startswith='ingresso_gratuito_aluna:',
        ).first()

        if pedido_existente:
            return redirect(
                'espetaculo:ingresso_sucesso',
                pedido_id=pedido_existente.id
            )

        pedido = PedidoIngressoEvento.objects.create(
            evento=evento,
            nome_completo=aluna.nome,
            email=request.user.email or '',
            whatsapp=getattr(aluna, 'whatsapp', '') or '-',
            cpf=getattr(aluna, 'cpf', '') or '',
            quantidade=1,
            valor_unitario=Decimal('0.00'),
            valor_total=Decimal('0.00'),
            status='pago',
        )

        pedido.data_pagamento = timezone.now()
        pedido.external_reference = (
            f'ingresso_gratuito_aluna:{pedido.id}'
        )
        pedido.save(
            update_fields=[
                'data_pagamento',
                'external_reference',
            ]
        )

        gerar_ingressos_do_pedido(pedido)

        return redirect(
            'espetaculo:ingresso_sucesso',
            pedido_id=pedido.id
        )

    if request.method == 'POST':
        nome_completo = request.POST.get(
            'nome_completo',
            ''
        ).strip()

        email = request.POST.get(
            'email',
            ''
        ).strip()

        whatsapp = request.POST.get(
            'whatsapp',
            ''
        ).strip()

        cpf = request.POST.get(
            'cpf',
            ''
        ).strip()

        if not nome_completo or not whatsapp:
            if evento.venda_com_assentos_numerados:
                return render(
                    request,
                    'espetaculo/comprar_ingresso_assentos.html',
                    {
                        'evento': evento,
                        'erro': (
                            'Preencha nome completo e WhatsApp.'
                        ),
                    }
                )

            return render(
                request,
                'espetaculo/comprar_ingresso.html',
                {
                    'evento': evento,
                    'erro': (
                        'Preencha os campos obrigatórios.'
                    ),
                }
            )

        valor_unitario = evento.preco_ingresso or Decimal('0.00')

        if evento.venda_com_assentos_numerados:
            if not evento.tem_mapa_assentos:
                return render(
                    request,
                    'espetaculo/comprar_ingresso_assentos.html',
                    {
                        'evento': evento,
                        'erro': (
                            'Este evento ainda não possui mapa '
                            'de assentos configurado. '
                            'Fale com a organização.'
                        ),
                    }
                )

            request.session[
                f'compra_evento_{pk}_nome_completo'
            ] = nome_completo

            request.session[
                f'compra_evento_{pk}_email'
            ] = email

            request.session[
                f'compra_evento_{pk}_whatsapp'
            ] = whatsapp

            request.session[
                f'compra_evento_{pk}_cpf'
            ] = cpf

            request.session[
                f'compra_evento_{pk}_valor_unitario'
            ] = str(valor_unitario)

            request.session[
                f'compra_evento_{pk}_assentos_ids'
            ] = []

            request.session.modified = True

            return redirect(
                'espetaculo:mapa_assentos_publico',
                pk=pk
            )

        quantidade = request.POST.get(
            'quantidade',
            '1'
        ).strip()

        try:
            quantidade = int(quantidade)
        except (TypeError, ValueError):
            quantidade = 1

        if quantidade < 1:
            quantidade = 1

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

        pedido.external_reference = (
            f'ingresso_evento:{pedido.id}'
        )
        pedido.save(
            update_fields=[
                'external_reference',
            ]
        )

        return redirect(
            'espetaculo:pagar_ingresso_pix',
            pedido_id=pedido.id
        )

    if evento.venda_com_assentos_numerados:
        return render(
            request,
            'espetaculo/comprar_ingresso_assentos.html',
            {
                'evento': evento,
            }
        )

    return render(
        request,
        'espetaculo/comprar_ingresso.html',
        {
            'evento': evento,
        }
    )


def pagar_ingresso_pix(request, pedido_id):
    pedido = get_object_or_404(PedidoIngressoEvento, id=pedido_id)
    evento = pedido.evento

    if not evento.publico and not request.user.is_authenticated:
        return redirect('espetaculo:lista_publica')

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
                    gerar_ingressos_do_pedido(pedido, assentos_ids=_obter_assentos_confirmados_pedido(pedido))
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
                gerar_ingressos_do_pedido(pedido, assentos_ids=_obter_assentos_confirmados_pedido(pedido))
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


def _obter_assentos_confirmados_pedido(pedido):
    """
    Recupera os IDs de assentos já vinculados aos ingressos deste pedido
    (usado ao reconsultar um pagamento já processado, sem sessão ativa).
    """
    return list(
        IngressoEvento.objects.filter(pedido=pedido, assento__isnull=False).values_list('assento_id', flat=True)
    )


def verificar_pagamento_ingresso_pix(request, payment_id):
    try:
        asaas = AsaasAPI()
        resultado = asaas.consultar_cobranca(payment_id)

        if resultado and resultado.get('status') == 'RECEIVED':
            pedido = PedidoIngressoEvento.objects.get(asaas_payment_id=payment_id)
            pedido.marcar_como_pago()
            gerar_ingressos_do_pedido(pedido, assentos_ids=_obter_assentos_confirmados_pedido(pedido))

            return JsonResponse({
                'status': 'paid',
                'redirect': f"/espetaculos/ingresso/sucesso/{pedido.id}/"
            })

        status = resultado.get('status', 'PENDING') if resultado else 'ERROR'
        return JsonResponse({'status': status.lower()})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


def evento_ingressos(request, evento_id):
    evento = get_object_or_404(
        Espetaculo,
        pk=evento_id,
        ativo=True,
        publico=True,
        venda_aberta=True
    )

    context = {
        'evento': evento,
    }
    return render(request, 'espetaculo/evento_ingressos.html', context)


def checkout_ingresso(request, evento_id):
    evento = get_object_or_404(
        Espetaculo,
        pk=evento_id,
        ativo=True,
        publico=True,
        venda_aberta=True
    )

    if request.method == 'POST':
        nome_completo = request.POST.get('nome_completo', '').strip()
        email = request.POST.get('email', '').strip()
        whatsapp = request.POST.get('whatsapp', '').strip()
        cpf = request.POST.get('cpf', '').strip()
        quantidade = request.POST.get('quantidade', '1')

        if not nome_completo or not whatsapp:
            messages.error(request, 'Preencha nome completo e WhatsApp.')
            return render(request, 'espetaculo/checkout_ingresso.html', {'evento': evento})

        try:
            quantidade = int(quantidade)
            if quantidade < 1:
                raise ValueError
        except (TypeError, ValueError):
            messages.error(request, 'Informe uma quantidade válida.')
            return render(request, 'espetaculo/checkout_ingresso.html', {'evento': evento})

        try:
            valor_unitario = Decimal(evento.preco_ingresso)
            valor_total = valor_unitario * quantidade
        except (InvalidOperation, TypeError):
            messages.error(request, 'Não foi possível calcular o valor do ingresso.')
            return render(request, 'espetaculo/checkout_ingresso.html', {'evento': evento})

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

        return redirect('espetaculo:pagamento_pix_ingresso', pedido_id=pedido.pk)

    context = {
        'evento': evento,
    }
    return render(request, 'espetaculo/checkout_ingresso.html', context)


def pagamento_pix_ingresso(request, pedido_id):
    pedido = get_object_or_404(
        PedidoIngressoEvento.objects.select_related('evento'),
        pk=pedido_id
    )

    if pedido.status == 'pago':
        return redirect('espetaculo:ingresso_sucesso', pedido_id=pedido.pk)

    context = {
        'pedido': pedido,
        'evento': pedido.evento,
    }
    return render(request, 'espetaculo/pagamento_pix_ingresso.html', context)


def retorno_pagamento_ingresso(request, pedido_id):
    pedido = get_object_or_404(
        PedidoIngressoEvento.objects.select_related('evento'),
        pk=pedido_id
    )

    # Aqui depois você pode consultar o Asaas
    # e atualizar pedido.status / pedido.asaas_status

    if pedido.status == 'pago':
        return redirect('espetaculo:ingresso_sucesso', pedido_id=pedido.pk)

    messages.info(request, 'O pagamento ainda está pendente.')
    return redirect('espetaculo:pagamento_pix_ingresso', pedido_id=pedido.pk)


def ingresso_sucesso(request, pedido_id):
    pedido = get_object_or_404(
        PedidoIngressoEvento.objects.select_related('evento'),
        pk=pedido_id,
        status='pago'
    )

    ingressos = pedido.ingressos.all().order_by('criado_em')

    context = {
        'pedido': pedido,
        'evento': pedido.evento,
        'ingressos': ingressos,
    }
    return render(request, 'espetaculo/ingresso_sucesso.html', context)


def ver_imagem_ingresso(request, ingresso_id):
    ingresso = get_object_or_404(IngressoEvento, id=ingresso_id)

    ingresso.garantir_arquivos()

    if not ingresso.imagem_ingresso:
        raise Http404("Imagem do ingresso não encontrada.")

    storage = ingresso.imagem_ingresso.storage
    nome = ingresso.imagem_ingresso.name

    if not nome or not storage.exists(nome):
        ingresso.garantir_arquivos(force=True)
        ingresso.refresh_from_db()
        nome = ingresso.imagem_ingresso.name
        storage = ingresso.imagem_ingresso.storage

    if not nome or not storage.exists(nome):
        raise Http404("Arquivo da imagem do ingresso não existe no disco.")

    return FileResponse(storage.open(nome, "rb"), content_type="image/png")


def baixar_ingresso(request, ingresso_id):
    ingresso = get_object_or_404(IngressoEvento, id=ingresso_id)

    ingresso.garantir_arquivos()

    if not ingresso.imagem_ingresso:
        raise Http404("Arquivo do ingresso não encontrado.")

    storage = ingresso.imagem_ingresso.storage
    nome = ingresso.imagem_ingresso.name

    if not nome or not storage.exists(nome):
        ingresso.garantir_arquivos(force=True)
        ingresso.refresh_from_db()
        nome = ingresso.imagem_ingresso.name
        storage = ingresso.imagem_ingresso.storage

    if not nome or not storage.exists(nome):
        raise Http404("Arquivo do ingresso não existe no disco.")

    return FileResponse(
        storage.open(nome, "rb"),
        as_attachment=True,
        filename=os.path.basename(nome),
    )


def baixar_qrcode_ingresso(request, ingresso_id):
    ingresso = get_object_or_404(IngressoEvento, id=ingresso_id)

    ingresso.garantir_arquivos()

    if not ingresso.qrcode_image:
        raise Http404("QR code não encontrado.")

    storage = ingresso.qrcode_image.storage
    nome = ingresso.qrcode_image.name

    if not nome or not storage.exists(nome):
        ingresso.garantir_arquivos(force=True)
        ingresso.refresh_from_db()
        nome = ingresso.qrcode_image.name
        storage = ingresso.qrcode_image.storage

    if not nome or not storage.exists(nome):
        raise Http404("Arquivo do QR code não existe no disco.")

    return FileResponse(
        storage.open(nome, "rb"),
        as_attachment=True,
        filename=os.path.basename(nome),
    )


def mapa_assentos_publico(request, pk):
    """
    Página pública onde o comprador escolhe os assentos.

    Para eventos com assentos numerados, a quantidade de ingressos
    é definida diretamente pela quantidade de assentos selecionados
    no mapa.
    """
    evento = get_object_or_404(
        Espetaculo,
        pk=pk,
        ativo=True,
    )

    if not evento.venda_aberta:
        messages.error(
            request,
            'As vendas para este evento não estão abertas.',
        )
        return redirect(
            'espetaculo:evento_detalhe_publico',
            pk=pk,
        )

    if (
        not evento.venda_com_assentos_numerados
        or not evento.tem_mapa_assentos
    ):
        messages.error(
            request,
            'Este evento não possui venda com assentos numerados.',
        )
        return redirect(
            'espetaculo:evento_detalhe_publico',
            pk=pk,
        )

    nome_completo = request.session.get(
        f'compra_evento_{pk}_nome_completo',
        '',
    )

    whatsapp = request.session.get(
        f'compra_evento_{pk}_whatsapp',
        '',
    )

    if not nome_completo or not whatsapp:
        messages.error(
            request,
            'Preencha seus dados antes de escolher os assentos.',
        )
        return redirect(
            'espetaculo:comprar_ingresso',
            pk=pk,
        )

    mapa = get_object_or_404(
        MapaAssentos.objects.prefetch_related('assentos'),
        evento=evento,
    )

    liberar_assentos_expirados(mapa)

    if not request.session.session_key:
        request.session.create()

    identificador_sessao = request.session.session_key

    assentos = mapa.assentos.all().order_by(
        'fileira',
        'numero',
    )

    ja_selecionados = request.session.get(
        f'compra_evento_{pk}_assentos_ids',
        [],
    )

    context = {
        'espetaculo': evento,
        'evento': evento,
        'mapa': mapa,
        'assentos': assentos,
        'identificador_sessao': identificador_sessao,
        'ja_selecionados': ja_selecionados,
        'total_selecionados': len(ja_selecionados),
    }

    return render(
        request,
        'espetaculo/mapa_assentos_publico.html',
        context,
    )


def liberar_assentos_expirados(mapa):
    """Libera assentos cuja reserva temporária já passou do tempo limite."""
    for assento in mapa.assentos.filter(status='reservado_temporario'):
        if assento.esta_reservado_expirado:
            assento.liberar()


@require_POST
def assento_selecionar_api(request, pk):
    """
    API chamada pelo JavaScript quando o comprador clica em um assento.

    A quantidade de ingressos não é definida antecipadamente.
    Ela corresponde ao número de assentos selecionados no mapa.
    """
    evento = get_object_or_404(
        Espetaculo,
        pk=pk,
        ativo=True,
    )

    if not evento.venda_aberta:
        return JsonResponse(
            {
                'ok': False,
                'erro': 'As vendas para este evento não estão abertas.',
            },
            status=403,
        )

    if not evento.venda_com_assentos_numerados:
        return JsonResponse(
            {
                'ok': False,
                'erro': (
                    'Este evento não utiliza seleção de assentos.'
                ),
            },
            status=400,
        )

    mapa = get_object_or_404(
        MapaAssentos,
        evento=evento,
    )

    if not request.session.session_key:
        request.session.create()

    identificador_sessao = request.session.session_key

    try:
        dados = json.loads(request.body)

        assento_id = int(
            dados.get('assento_id')
        )

        acao = dados.get('acao')

    except (
        ValueError,
        TypeError,
        json.JSONDecodeError,
    ):
        return JsonResponse(
            {
                'ok': False,
                'erro': 'Requisição inválida.',
            },
            status=400,
        )

    if acao not in ('selecionar', 'desmarcar'):
        return JsonResponse(
            {
                'ok': False,
                'erro': 'Ação inválida.',
            },
            status=400,
        )

    assento = get_object_or_404(
        Assento,
        pk=assento_id,
        mapa=mapa,
    )

    selecionados = request.session.get(
        f'compra_evento_{pk}_assentos_ids',
        [],
    )

    selecionados = list(selecionados)

    if acao == 'selecionar':
        if assento.id in selecionados:
            return JsonResponse(
                {
                    'ok': True,
                    'status': 'selecionado',
                    'total_selecionados': len(selecionados),
                }
            )

        if assento.esta_reservado_expirado:
            assento.liberar()

        if assento.status != 'disponivel':
            return JsonResponse(
                {
                    'ok': False,
                    'erro': (
                        'Este assento não está mais disponível.'
                    ),
                },
                status=409,
            )

        try:
            assento.reservar_temporariamente(
                identificador_sessao
            )
        except Exception:
            assento.refresh_from_db()

            if assento.esta_reservado_expirado:
                assento.liberar()
                assento.reservar_temporariamente(
                    identificador_sessao
                )
            else:
                return JsonResponse(
                    {
                        'ok': False,
                        'erro': (
                            'Não foi possível reservar este assento. '
                            'Tente novamente.'
                        ),
                    },
                    status=409,
                )

        if assento.id not in selecionados:
            selecionados.append(assento.id)

        request.session[
            f'compra_evento_{pk}_assentos_ids'
        ] = selecionados

        request.session.modified = True

        return JsonResponse(
            {
                'ok': True,
                'status': 'selecionado',
                'total_selecionados': len(selecionados),
            }
        )

    if assento.status != 'reservado_temporario':
        return JsonResponse(
            {
                'ok': False,
                'erro': (
                    'Este assento não está reservado para esta sessão.'
                ),
            },
            status=403,
        )

    if assento.reservado_por_sessao != identificador_sessao:
        return JsonResponse(
            {
                'ok': False,
                'erro': (
                    'Você só pode desmarcar assentos '
                    'selecionados por você.'
                ),
            },
            status=403,
        )

    assento.liberar()

    if assento.id in selecionados:
        selecionados.remove(assento.id)

    request.session[
        f'compra_evento_{pk}_assentos_ids'
    ] = selecionados

    request.session.modified = True

    return JsonResponse(
        {
            'ok': True,
            'status': 'disponivel',
            'total_selecionados': len(selecionados),
        }
    )


def confirmar_selecao_assentos(request, pk):
    """
    Confirma os assentos selecionados no mapa, calcula a quantidade
    pelo número de assentos escolhidos, cria o pedido e encaminha
    para o pagamento PIX.
    """
    evento = get_object_or_404(
        Espetaculo,
        pk=pk,
        ativo=True,
    )

    if not evento.venda_aberta:
        messages.error(
            request,
            'As vendas para este evento não estão abertas.',
        )
        return redirect(
            'espetaculo:evento_detalhe_publico',
            pk=pk,
        )

    if not evento.venda_com_assentos_numerados:
        messages.error(
            request,
            'Este evento não utiliza assentos numerados.',
        )
        return redirect(
            'espetaculo:evento_detalhe_publico',
            pk=pk,
        )

    selecionados_ids = request.session.get(
        f'compra_evento_{pk}_assentos_ids',
        [],
    )

    selecionados_ids = list(
        dict.fromkeys(selecionados_ids)
    )

    quantidade = len(selecionados_ids)

    if quantidade < 1:
        messages.error(
            request,
            'Selecione pelo menos um assento antes de continuar.',
        )
        return redirect(
            'espetaculo:mapa_assentos_publico',
            pk=pk,
        )

    if not request.session.session_key:
        request.session.create()

    identificador_sessao = request.session.session_key

    assentos = Assento.objects.filter(
        id__in=selecionados_ids,
        mapa__evento=evento,
        status='reservado_temporario',
        reservado_por_sessao=identificador_sessao,
    )

    if assentos.count() != quantidade:
        messages.error(
            request,
            (
                'Algum assento selecionado expirou ou foi escolhido '
                'por outra pessoa. Selecione novamente.'
            ),
        )

        request.session[
            f'compra_evento_{pk}_assentos_ids'
        ] = []

        request.session.modified = True

        return redirect(
            'espetaculo:mapa_assentos_publico',
            pk=pk,
        )

    nome_completo = request.session.get(
        f'compra_evento_{pk}_nome_completo',
        '',
    )

    email = request.session.get(
        f'compra_evento_{pk}_email',
        '',
    )

    whatsapp = request.session.get(
        f'compra_evento_{pk}_whatsapp',
        '',
    )

    cpf = request.session.get(
        f'compra_evento_{pk}_cpf',
        '',
    )

    if not nome_completo or not whatsapp:
        messages.error(
            request,
            'Os dados do comprador estão incompletos.',
        )
        return redirect(
            'espetaculo:comprar_ingresso',
            pk=pk,
        )

    try:
        valor_unitario = Decimal(
            request.session.get(
                f'compra_evento_{pk}_valor_unitario',
                '0',
            )
        )
    except (InvalidOperation, TypeError, ValueError):
        messages.error(
            request,
            'Não foi possível calcular o valor dos ingressos.',
        )
        return redirect(
            'espetaculo:comprar_ingresso',
            pk=pk,
        )

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

    pedido.external_reference = (
        f'ingresso_evento:{pedido.id}'
    )

    pedido.save(
        update_fields=[
            'external_reference',
        ]
    )

    assentos_ids_confirmados = list(
        assentos.values_list(
            'id',
            flat=True,
        )
    )

    for assento in assentos:
        assento.reservado_por_sessao = (
            f'pedido:{pedido.id}'
        )

        assento.save(
            update_fields=[
                'reservado_por_sessao',
                'atualizado_em',
            ]
        )

    for chave in (
        'nome_completo',
        'email',
        'whatsapp',
        'cpf',
        'valor_unitario',
        'assentos_ids',
    ):
        request.session.pop(
            f'compra_evento_{pk}_{chave}',
            None,
        )

    request.session[
        f'pedido_{pedido.id}_assentos_ids'
    ] = assentos_ids_confirmados

    request.session.modified = True

    return redirect(
        'espetaculo:pagar_ingresso_pix',
        pedido_id=pedido.id,
    )