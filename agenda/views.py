from decimal import Decimal
from datetime import datetime, date
import json

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.urls import reverse

from .models import Agendamento
from .services import criar_evento_se_necessario, confirmar_pagamento_agendamento
from usuarios.models import Turma, Aluna
from pagamentos.asaas_helper import AsaasAPI


DIAS_SEMANA = {
    'Segunda': 0,
    'Terça': 1,
    'Quarta': 2,
    'Quinta': 3,
    'Sexta': 4,
    'Sábado': 5,
}

VALOR_AULA_EXPERIMENTAL = Decimal('25.00')


def buscar_alunas_do_usuario(user):
    """Alunas vinculadas ao usuário logado (como aluna própria ou como responsável)."""
    if not user.is_authenticated:
        return Aluna.objects.none()

    aluna_propria = Aluna.objects.filter(usuario=user, ativa=True)
    alunas_dependentes = Aluna.objects.filter(responsavel=user, ativa=True)

    return (aluna_propria | alunas_dependentes).distinct()


def agendar(request):
    # Se está logado e já é aluna/responsável Bailah, vai para o fluxo gratuito
    if request.user.is_authenticated:
        if buscar_alunas_do_usuario(request.user).exists():
            return redirect('agendar_aluna')

    from .models import ConfiguracaoAgendamento
    configuracao = ConfiguracaoAgendamento.obter()

    aulas = Turma.objects.filter(
        ativa=True,
        disponivel_experimental=True
    ).order_by('nome')

    if request.method == 'POST':
        aula_id = request.POST.get('aula')
        data_str = request.POST.get('data')

        aula = Turma.objects.filter(
            id=aula_id,
            ativa=True,
            disponivel_experimental=True
        ).first()

        if not aula or not data_str:
            return render(
                request,
                'agenda/agendar.html',
                {
                    'aulas': aulas,
                    'erro': 'Preencha todos os campos corretamente.'
                }
            )

        data_escolhida = datetime.strptime(data_str, '%Y-%m-%d').date()

        if data_escolhida < date.today():
            return render(
                request,
                'agenda/agendar.html',
                {
                    'aulas': aulas,
                    'erro': 'Não é possível agendar aulas em datas passadas.'
                }
            )

        if data_escolhida.weekday() != DIAS_SEMANA[aula.dia_semana]:
            return render(
                request,
                'agenda/agendar.html',
                {
                    'aulas': aulas,
                    'erro': 'A data escolhida não corresponde ao dia da aula.'
                }
            )

        dados_comuns = dict(
            nome_responsavel=request.POST.get('nome_responsavel'),
            nome_aluna=request.POST.get('nome_aluna'),
            idade_aluna=request.POST.get('idade_aluna'),
            email=request.POST.get('email'),
            telefone=request.POST.get('telefone'),
            data=data_escolhida,
            horario=aula.horario,
            aula=aula,
        )

        if configuracao.campanha_gratuita_ativa:
            # Campanha ativa: agenda direto como gratuita, sem cobrança
            agendamento = Agendamento.objects.create(
                **dados_comuns,
                status_pagamento='gratuito',
                valor=Decimal('0.00'),
                evento_calendario_criado=False,
            )
            criar_evento_se_necessario(agendamento)
            return redirect('confirmacao', agendamento_id=agendamento.id)

        # Campanha inativa: fluxo normal, com pagamento via PIX
        agendamento = Agendamento.objects.create(
            **dados_comuns,
            status_pagamento='pendente',
            valor=VALOR_AULA_EXPERIMENTAL,
            evento_calendario_criado=False,
        )

        return redirect('agendamento_pagamento', agendamento_id=agendamento.id)

    return render(
        request,
        'agenda/agendar.html',
        {
            'aulas': aulas,
            'hoje': date.today()
        }
    )


@login_required
def agendar_aluna(request):
    """Fluxo exclusivo para quem já tem login — sempre gratuito, sem digitar nome livre."""
    alunas_vinculadas = buscar_alunas_do_usuario(request.user)

    if not alunas_vinculadas.exists():
        return redirect('agendar')

    aulas = Turma.objects.filter(
        ativa=True,
        disponivel_experimental=True
    ).order_by('nome')

    perfil = getattr(request.user, 'perfil', None)

    if request.method == 'POST':
        aluna_id = request.POST.get('aluna_id')
        aula_id = request.POST.get('aula')
        data_str = request.POST.get('data')

        aluna = alunas_vinculadas.filter(id=aluna_id).first()

        aula = Turma.objects.filter(
            id=aula_id,
            ativa=True,
            disponivel_experimental=True
        ).first()

        if not aluna or not aula or not data_str:
            return render(
                request,
                'agenda/agendar_aluna.html',
                {
                    'aulas': aulas,
                    'alunas_vinculadas': alunas_vinculadas,
                    'erro': 'Preencha todos os campos corretamente.'
                }
            )

        data_escolhida = datetime.strptime(data_str, '%Y-%m-%d').date()

        if data_escolhida < date.today():
            return render(
                request,
                'agenda/agendar_aluna.html',
                {
                    'aulas': aulas,
                    'alunas_vinculadas': alunas_vinculadas,
                    'erro': 'Não é possível agendar aulas em datas passadas.'
                }
            )

        if data_escolhida.weekday() != DIAS_SEMANA[aula.dia_semana]:
            return render(
                request,
                'agenda/agendar_aluna.html',
                {
                    'aulas': aulas,
                    'alunas_vinculadas': alunas_vinculadas,
                    'erro': 'A data escolhida não corresponde ao dia da aula.'
                }
            )

        nome_responsavel = request.user.get_full_name() or request.user.username

        agendamento = Agendamento.objects.create(
            nome_responsavel=nome_responsavel,
            nome_aluna=aluna.nome,
            idade_aluna=aluna.idade or 0,
            email=request.user.email,
            telefone=perfil.telefone if perfil and perfil.telefone else '',
            data=data_escolhida,
            horario=aula.horario,
            aula=aula,
            aluna_vinculada=aluna,
            status_pagamento='gratuito',
            valor=Decimal('0.00'),
            evento_calendario_criado=False,
        )

        criar_evento_se_necessario(agendamento)

        return redirect('confirmacao', agendamento_id=agendamento.id)

    return render(
        request,
        'agenda/agendar_aluna.html',
        {
            'aulas': aulas,
            'alunas_vinculadas': alunas_vinculadas,
            'hoje': date.today(),
        }
    )


def agendamento_pagamento(request, agendamento_id):
    """Tela intermediária de PIX — entre o formulário e a confirmação."""
    agendamento = get_object_or_404(Agendamento, id=agendamento_id)

    if agendamento.status_pagamento in ('pago', 'gratuito'):
        return redirect('confirmacao', agendamento_id=agendamento.id)

    try:
        asaas = AsaasAPI()

        # Fluxo público não tem CPF — usa o mesmo fallback já usado na mensalidade
        cpf_cliente = '24971563792'

        customer_data = {
            'name': agendamento.nome_responsavel,
            'email': agendamento.email,
            'cpfCnpj': cpf_cliente,
        }

        descricao = f"Aula experimental - {agendamento.nome_aluna} ({agendamento.aula.nome})"
        external_reference = f"agendamento_experimental:{agendamento.id}"

        if agendamento.asaas_payment_id:
            cobranca_existente = asaas.consultar_cobranca(agendamento.asaas_payment_id)

            if cobranca_existente:
                status_existente = cobranca_existente.get('status')

                if status_existente == 'RECEIVED':
                    confirmar_pagamento_agendamento(agendamento, agendamento.asaas_payment_id)
                    return redirect('confirmacao', agendamento_id=agendamento.id)

                if status_existente in ['PENDING', 'OVERDUE']:
                    qrcode_data = asaas.obter_qrcode_pix(agendamento.asaas_payment_id)
                    pix_data = {
                        'payload': qrcode_data.get('payload', ''),
                        'encodedImage': qrcode_data.get('encodedImage', ''),
                        'expirationDate': qrcode_data.get('expirationDate', ''),
                    } if qrcode_data else None

                    return render(request, 'agenda/pagamento_pix.html', {
                        'agendamento': agendamento,
                        'payment_id': agendamento.asaas_payment_id,
                        'pix_data': pix_data,
                        'valor': agendamento.valor,
                    })

        resultado = asaas.criar_cobranca_pix(
            valor=agendamento.valor,
            descricao=descricao,
            customer_data=customer_data,
            external_reference=external_reference,
        )

        if resultado and 'error' in resultado:
            erro_msg = resultado['error']
            mensagem_erro = json.dumps(erro_msg, ensure_ascii=False) if isinstance(erro_msg, dict) else str(erro_msg)
            return render(request, 'agenda/pagamento_pix.html', {
                'agendamento': agendamento,
                'erro': f'Erro Asaas: {mensagem_erro}',
            })

        if resultado and 'id' in resultado:
            agendamento.asaas_payment_id = resultado['id']
            campos = ['asaas_payment_id']
            if 'customer' in resultado:
                agendamento.asaas_customer_id = resultado['customer']
                campos.append('asaas_customer_id')
            agendamento.save(update_fields=campos)

            if resultado.get('status') == 'RECEIVED':
                confirmar_pagamento_agendamento(agendamento, resultado['id'])
                return redirect('confirmacao', agendamento_id=agendamento.id)

            qrcode_data = asaas.obter_qrcode_pix(resultado['id'])
            pix_data = {
                'payload': qrcode_data.get('payload', ''),
                'encodedImage': qrcode_data.get('encodedImage', ''),
                'expirationDate': qrcode_data.get('expirationDate', ''),
            } if qrcode_data else None

            return render(request, 'agenda/pagamento_pix.html', {
                'agendamento': agendamento,
                'payment_id': resultado['id'],
                'pix_data': pix_data,
                'valor': resultado.get('value', agendamento.valor),
            })

        return render(request, 'agenda/pagamento_pix.html', {
            'agendamento': agendamento,
            'erro': f'Resposta inesperada do Asaas: {resultado}',
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return render(request, 'agenda/pagamento_pix.html', {
            'agendamento': agendamento,
            'erro': f'Erro ao gerar PIX: {str(e)}',
        })


def verificar_pagamento_agendamento(request, payment_id):
    try:
        asaas = AsaasAPI()
        resultado = asaas.consultar_cobranca(payment_id)

        if resultado and resultado.get('status') == 'RECEIVED':
            agendamento = Agendamento.objects.get(asaas_payment_id=payment_id)
            confirmar_pagamento_agendamento(agendamento, payment_id)

            return JsonResponse({
                'status': 'paid',
                'redirect': reverse('confirmacao', args=[agendamento.id])
            })

        status = resultado.get('status', 'PENDING') if resultado else 'ERROR'
        return JsonResponse({'status': status.lower()})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


def confirmacao(request, agendamento_id):
    agendamento = Agendamento.objects.get(id=agendamento_id)
    return render(
        request,
        'agenda/confirmacao.html',
        {'agendamento': agendamento}
    )





