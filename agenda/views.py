from django.shortcuts import render, redirect
from .models import Agendamento
from usuarios.models import Turma  # Mudou: importa Turma em vez de Aula
from datetime import datetime, date
from .google_calendar import criar_evento_google

DIAS_SEMANA = {
    'Segunda': 0,
    'Terça': 1,
    'Quarta': 2,
    'Quinta': 3,
    'Sexta': 4,
    'Sábado': 5,
}


def agendar(request):
    # Busca apenas aulas do tipo 'aula_experimental'
    aulas = Turma.objects.filter(tipo='aula_experimental', ativa=True).order_by('nome')

    if request.method == 'POST':
        aula_id = request.POST.get('aula')
        data_str = request.POST.get('data')

        aula = Turma.objects.filter(id=aula_id, ativa=True).first()  # Mudou: Turma

        if not aula or not data_str:
            return render(
                request,
                'agenda/agendar.html',
                {
                    'aulas': aulas,
                    'erro': 'Preencha todos os campos corretamente.'
                }
            )

        # Converte a data do formulário
        data_escolhida = datetime.strptime(data_str, '%Y-%m-%d').date()

        # Bloqueia datas passadas
        if data_escolhida < date.today():
            return render(
                request,
                'agenda/agendar.html',
                {
                    'aulas': aulas,
                    'erro': 'Não é possível agendar aulas em datas passadas.'
                }
            )

        # Verifica se o dia da semana bate com a aula
        if data_escolhida.weekday() != DIAS_SEMANA[aula.dia_semana]:
            return render(
                request,
                'agenda/agendar.html',
                {
                    'aulas': aulas,
                    'erro': 'A data escolhida não corresponde ao dia da aula.'
                }
            )

        # Cria o agendamento
        agendamento = Agendamento.objects.create(
            nome_responsavel=request.POST.get('nome_responsavel'),
            nome_aluna=request.POST.get('nome_aluna'),
            idade_aluna=request.POST.get('idade_aluna'),
            email=request.POST.get('email'),
            telefone=request.POST.get('telefone'),
            data=data_escolhida,
            horario=aula.horario,
            aula=aula  # Agora aula é uma Turma
        )

        # Cria o evento no Google Agenda
        criar_evento_google(agendamento)

        return redirect('confirmacao', agendamento_id=agendamento.id)

    return render(
        request,
        'agenda/agendar.html',
        {
            'aulas': aulas,
            'hoje': date.today()
        }
    )


def confirmacao(request, agendamento_id):
    agendamento = Agendamento.objects.get(id=agendamento_id)
    return render(
        request,
        'agenda/confirmacao.html',
        {'agendamento': agendamento}
    )





