from datetime import date, datetime
from decimal import Decimal
import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from agenda.models import Agendamento, ConfiguracaoAgendamento
from agenda.services import (
    confirmar_pagamento_agendamento,
    criar_evento_se_necessario,
)
from pagamentos.asaas_helper import AsaasAPI
from usuarios.models import Aluna, Turma


DIAS_SEMANA = {
    "Segunda": 0,
    "Terça": 1,
    "Quarta": 2,
    "Quinta": 3,
    "Sexta": 4,
    "Sábado": 5,
}


def buscar_alunas_do_usuario(user):
    """Busca alunas vinculadas ao usuário logado."""

    if not user.is_authenticated:
        return Aluna.objects.none()

    aluna_propria = Aluna.objects.filter(
        usuario=user,
        ativa=True,
    )

    alunas_dependentes = Aluna.objects.filter(
        responsavel=user,
        ativa=True,
    )

    return (aluna_propria | alunas_dependentes).distinct()


def usuario_pode_agendar_como_responsavel(user):
    """
    Permite que o responsável agende para si mesmo
    quando ele ainda não possui um registro próprio de aluna.
    """

    if not user.is_authenticated:
        return False

    if Aluna.objects.filter(
        usuario=user,
        ativa=True,
    ).exists():
        return False

    return True


def calcular_idade(data_nascimento):
    if not data_nascimento:
        return 0

    hoje = date.today()

    idade = hoje.year - data_nascimento.year

    if (hoje.month, hoje.day) < (
        data_nascimento.month,
        data_nascimento.day,
    ):
        idade -= 1

    return idade


def obter_aulas_com_status(configuracao):
    aulas = list(
        Turma.objects.filter(
            ativa=True,
            disponivel_experimental=True,
        ).order_by("nome")
    )

    return [
        {
            "turma": aula,
            "gratuita": configuracao.turma_e_gratuita(aula),
        }
        for aula in aulas
    ]


def contexto_agendamento_publico(
    aulas_com_status,
    configuracao,
    erro=None,
):
    contexto = {
        "aulas_com_status": aulas_com_status,
        "configuracao": configuracao,
        "hoje": date.today(),
    }

    if erro:
        contexto["erro"] = erro

    return contexto


def validar_data_da_aula(data_str, aula):
    if not data_str:
        return None, "Informe a data da aula."

    try:
        data_escolhida = datetime.strptime(
            data_str,
            "%Y-%m-%d",
        ).date()
    except ValueError:
        return None, "A data escolhida é inválida."

    if data_escolhida < date.today():
        return None, (
            "Não é possível agendar aulas em datas passadas."
        )

    dia_semana_aula = DIAS_SEMANA.get(aula.dia_semana)

    if dia_semana_aula is None:
        return None, "A turma não possui um dia da semana válido."

    if data_escolhida.weekday() != dia_semana_aula:
        return None, (
            "A data escolhida não corresponde ao dia da aula."
        )

    return data_escolhida, None


def agendar(request):
    """
    Fluxo público de agendamento.

    Pessoas sem login:
    - pagam quando a turma não está gratuita;
    - não pagam quando a turma participa da campanha.
    """

    if request.user.is_authenticated:
        tem_dependentes = buscar_alunas_do_usuario(
            request.user
        ).exists()

        pode_como_responsavel = (
            usuario_pode_agendar_como_responsavel(
                request.user
            )
        )

        if tem_dependentes or pode_como_responsavel:
            return redirect("agendar_aluna")

    configuracao = ConfiguracaoAgendamento.obter()
    aulas_com_status = obter_aulas_com_status(configuracao)

    if request.method == "POST":
        aula_id = request.POST.get("aula")
        data_str = request.POST.get("data")

        aula = Turma.objects.filter(
            id=aula_id,
            ativa=True,
            disponivel_experimental=True,
        ).first()

        if not aula:
            return render(
                request,
                "agenda/agendar.html",
                contexto_agendamento_publico(
                    aulas_com_status,
                    configuracao,
                    "Selecione uma aula válida.",
                ),
            )

        data_escolhida, erro_data = validar_data_da_aula(
            data_str,
            aula,
        )

        if erro_data:
            return render(
                request,
                "agenda/agendar.html",
                contexto_agendamento_publico(
                    aulas_com_status,
                    configuracao,
                    erro_data,
                ),
            )

        dados_comuns = {
            "nome_responsavel": request.POST.get(
                "nome_responsavel",
                "",
            ).strip(),

            "nome_aluna": request.POST.get(
                "nome_aluna",
                "",
            ).strip(),

            "idade_aluna": request.POST.get(
                "idade_aluna",
                0,
            ),

            "email": request.POST.get(
                "email",
                "",
            ).strip(),

            "telefone": request.POST.get(
                "telefone",
                "",
            ).strip(),

            "data": data_escolhida,
            "horario": aula.horario,
            "aula": aula,
        }

        if configuracao.turma_e_gratuita(aula):
            agendamento = Agendamento.objects.create(
                **dados_comuns,
                status_pagamento="gratuito",
                valor=Decimal("0.00"),
                evento_calendario_criado=False,
            )

            criar_evento_se_necessario(agendamento)

            return redirect(
                "confirmacao",
                agendamento_id=agendamento.id,
            )

        agendamento = Agendamento.objects.create(
            **dados_comuns,
            status_pagamento="pendente",
            valor=configuracao.valor_aula_experimental,
            evento_calendario_criado=False,
        )

        return redirect(
            "agendamento_pagamento",
            agendamento_id=agendamento.id,
        )

    return render(
        request,
        "agenda/agendar.html",
        contexto_agendamento_publico(
            aulas_com_status,
            configuracao,
        ),
    )


@login_required
def agendar_aluna(request):
    """
    Fluxo para usuários logados.
    Continua sempre gratuito, independentemente da campanha.
    """

    alunas_vinculadas = buscar_alunas_do_usuario(
        request.user
    )

    pode_como_responsavel = (
        usuario_pode_agendar_como_responsavel(
            request.user
        )
    )

    if not alunas_vinculadas.exists() and not pode_como_responsavel:
        return redirect("agendar")

    opcoes = [
        {
            "value": str(aluna.id),
            "label": aluna.nome,
        }
        for aluna in alunas_vinculadas
    ]

    nome_responsavel_logado = (
        request.user.get_full_name()
        or request.user.username
    )

    if pode_como_responsavel:
        opcoes.append(
            {
                "value": "responsavel",
                "label": f"{nome_responsavel_logado} (você)",
            }
        )

    aulas = Turma.objects.filter(
        ativa=True,
        disponivel_experimental=True,
    ).order_by("nome")

    perfil = getattr(request.user, "perfil", None)

    if request.method == "POST":
        opcao_escolhida = request.POST.get("aluna_id")
        aula_id = request.POST.get("aula")
        data_str = request.POST.get("data")

        aula = Turma.objects.filter(
            id=aula_id,
            ativa=True,
            disponivel_experimental=True,
        ).first()

        valores_validos = {
            opcao["value"]
            for opcao in opcoes
        }

        if (
            opcao_escolhida not in valores_validos
            or not aula
            or not data_str
        ):
            return render(
                request,
                "agenda/agendar_aluna.html",
                {
                    "aulas": aulas,
                    "opcoes": opcoes,
                    "hoje": date.today(),
                    "erro": (
                        "Preencha todos os campos corretamente."
                    ),
                },
            )

        data_escolhida, erro_data = validar_data_da_aula(
            data_str,
            aula,
        )

        if erro_data:
            return render(
                request,
                "agenda/agendar_aluna.html",
                {
                    "aulas": aulas,
                    "opcoes": opcoes,
                    "hoje": date.today(),
                    "erro": erro_data,
                },
            )

        if opcao_escolhida == "responsavel":
            nome_aluna = nome_responsavel_logado
            idade_aluna = calcular_idade(
                perfil.data_nascimento
                if perfil
                else None
            )
            aluna_vinculada = None
        else:
            aluna = alunas_vinculadas.filter(
                id=opcao_escolhida,
            ).first()

            if not aluna:
                return render(
                    request,
                    "agenda/agendar_aluna.html",
                    {
                        "aulas": aulas,
                        "opcoes": opcoes,
                        "hoje": date.today(),
                        "erro": "Aluna inválida.",
                    },
                )

            nome_aluna = aluna.nome
            idade_aluna = aluna.idade or 0
            aluna_vinculada = aluna

        agendamento = Agendamento.objects.create(
            nome_responsavel=nome_responsavel_logado,
            nome_aluna=nome_aluna,
            idade_aluna=idade_aluna,
            email=request.user.email,
            telefone=(
                perfil.telefone
                if perfil and perfil.telefone
                else ""
            ),
            data=data_escolhida,
            horario=aula.horario,
            aula=aula,
            aluna_vinculada=aluna_vinculada,
            status_pagamento="gratuito",
            valor=Decimal("0.00"),
            evento_calendario_criado=False,
        )

        criar_evento_se_necessario(agendamento)

        return redirect(
            "confirmacao",
            agendamento_id=agendamento.id,
        )

    return render(
        request,
        "agenda/agendar_aluna.html",
        {
            "aulas": aulas,
            "opcoes": opcoes,
            "hoje": date.today(),
        },
    )


def agendamento_pagamento(request, agendamento_id):
    """Tela intermediária de pagamento PIX."""

    agendamento = get_object_or_404(
        Agendamento,
        id=agendamento_id,
    )

    if agendamento.status_pagamento in (
        "pago",
        "gratuito",
    ):
        return redirect(
            "confirmacao",
            agendamento_id=agendamento.id,
        )

    try:
        asaas = AsaasAPI()

        cpf_cliente = "24971563792"

        customer_data = {
            "name": agendamento.nome_responsavel,
            "email": agendamento.email,
            "cpfCnpj": cpf_cliente,
        }

        descricao = (
            f"Aula experimental - "
            f"{agendamento.nome_aluna} "
            f"({agendamento.aula.nome})"
        )

        external_reference = (
            f"agendamento_experimental:{agendamento.id}"
        )

        if agendamento.asaas_payment_id:
            cobranca_existente = asaas.consultar_cobranca(
                agendamento.asaas_payment_id
            )

            if cobranca_existente:
                status_existente = (
                    cobranca_existente.get("status")
                )

                if status_existente == "RECEIVED":
                    confirmar_pagamento_agendamento(
                        agendamento,
                        agendamento.asaas_payment_id,
                    )

                    return redirect(
                        "confirmacao",
                        agendamento_id=agendamento.id,
                    )

                if status_existente in (
                    "PENDING",
                    "OVERDUE",
                ):
                    qrcode_data = asaas.obter_qrcode_pix(
                        agendamento.asaas_payment_id
                    )

                    pix_data = (
                        {
                            "payload": qrcode_data.get(
                                "payload",
                                "",
                            ),
                            "encodedImage": qrcode_data.get(
                                "encodedImage",
                                "",
                            ),
                            "expirationDate": qrcode_data.get(
                                "expirationDate",
                                "",
                            ),
                        }
                        if qrcode_data
                        else None
                    )

                    return render(
                        request,
                        "agenda/pagamento_pix.html",
                        {
                            "agendamento": agendamento,
                            "payment_id": (
                                agendamento.asaas_payment_id
                            ),
                            "pix_data": pix_data,
                            "valor": agendamento.valor,
                        },
                    )

        resultado = asaas.criar_cobranca_pix(
            valor=agendamento.valor,
            descricao=descricao,
            customer_data=customer_data,
            external_reference=external_reference,
        )

        if resultado and "error" in resultado:
            erro_msg = resultado["error"]

            mensagem_erro = (
                json.dumps(
                    erro_msg,
                    ensure_ascii=False,
                )
                if isinstance(erro_msg, dict)
                else str(erro_msg)
            )

            return render(
                request,
                "agenda/pagamento_pix.html",
                {
                    "agendamento": agendamento,
                    "erro": f"Erro Asaas: {mensagem_erro}",
                },
            )

        if resultado and "id" in resultado:
            agendamento.asaas_payment_id = resultado["id"]

            campos = ["asaas_payment_id"]

            if "customer" in resultado:
                agendamento.asaas_customer_id = (
                    resultado["customer"]
                )
                campos.append("asaas_customer_id")

            agendamento.save(update_fields=campos)

            if resultado.get("status") == "RECEIVED":
                confirmar_pagamento_agendamento(
                    agendamento,
                    resultado["id"],
                )

                return redirect(
                    "confirmacao",
                    agendamento_id=agendamento.id,
                )

            qrcode_data = asaas.obter_qrcode_pix(
                resultado["id"]
            )

            pix_data = (
                {
                    "payload": qrcode_data.get(
                        "payload",
                        "",
                    ),
                    "encodedImage": qrcode_data.get(
                        "encodedImage",
                        "",
                    ),
                    "expirationDate": qrcode_data.get(
                        "expirationDate",
                        "",
                    ),
                }
                if qrcode_data
                else None
            )

            return render(
                request,
                "agenda/pagamento_pix.html",
                {
                    "agendamento": agendamento,
                    "payment_id": resultado["id"],
                    "pix_data": pix_data,
                    "valor": resultado.get(
                        "value",
                        agendamento.valor,
                    ),
                },
            )

        return render(
            request,
            "agenda/pagamento_pix.html",
            {
                "agendamento": agendamento,
                "erro": (
                    f"Resposta inesperada do Asaas: {resultado}"
                ),
            },
        )

    except Exception as erro:
        import traceback

        traceback.print_exc()

        return render(
            request,
            "agenda/pagamento_pix.html",
            {
                "agendamento": agendamento,
                "erro": f"Erro ao gerar PIX: {erro}",
            },
        )


def verificar_pagamento_agendamento(request, payment_id):
    try:
        asaas = AsaasAPI()
        resultado = asaas.consultar_cobranca(payment_id)

        if (
            resultado
            and resultado.get("status") == "RECEIVED"
        ):
            agendamento = Agendamento.objects.get(
                asaas_payment_id=payment_id,
            )

            confirmar_pagamento_agendamento(
                agendamento,
                payment_id,
            )

            return JsonResponse(
                {
                    "status": "paid",
                    "redirect": reverse(
                        "confirmacao",
                        args=[agendamento.id],
                    ),
                }
            )

        status = (
            resultado.get("status", "PENDING")
            if resultado
            else "ERROR"
        )

        return JsonResponse(
            {
                "status": status.lower(),
            }
        )

    except Exception as erro:
        return JsonResponse(
            {
                "error": str(erro),
            },
            status=400,
        )


def confirmacao(request, agendamento_id):
    agendamento = get_object_or_404(
        Agendamento,
        id=agendamento_id,
    )

    return render(
        request,
        "agenda/confirmacao.html",
        {
            "agendamento": agendamento,
        },
    )