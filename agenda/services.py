from .google_calendar import criar_evento_google


def criar_evento_se_necessario(agendamento):
    """Cria o evento no Google Agenda apenas se ainda não tiver sido criado."""
    if agendamento.evento_calendario_criado:
        return True

    sucesso = criar_evento_google(agendamento)
    if sucesso:
        agendamento.evento_calendario_criado = True
        agendamento.save(update_fields=['evento_calendario_criado'])
    return sucesso


def confirmar_pagamento_agendamento(agendamento, payment_id=None):
    """Marca o agendamento como pago e garante que o evento seja criado."""
    if agendamento.status_pagamento != 'pago':
        agendamento.status_pagamento = 'pago'
        campos = ['status_pagamento']

        if payment_id:
            agendamento.asaas_payment_id = payment_id
            campos.append('asaas_payment_id')

        agendamento.save(update_fields=campos)

    criar_evento_se_necessario(agendamento)


def liberar_gratuita(agendamento):
    """Usado pelo botão do admin: libera a aula sem cobrar nada."""
    agendamento.status_pagamento = 'gratuito'
    agendamento.valor = 0
    agendamento.save(update_fields=['status_pagamento', 'valor'])
    criar_evento_se_necessario(agendamento)