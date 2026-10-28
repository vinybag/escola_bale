"""
Agenda de maquiagem/cabelo: lógica usada pelo painel (grade por horário,
criação de horários em lote, agendar e remover) e pela área das alunas.

Regras importantes:
  * cada aluna tem no máximo UM agendamento por espetáculo;
  * os horários pertencem a uma agenda (turma + maquiadora); uma turma pode ter
    várias maquiadoras, e a grade mostra uma coluna por maquiadora;
  * agendar e remover são atômicos e travam as linhas envolvidas, para duas
    pessoas da secretaria não ocuparem o mesmo horário nem agendarem a mesma
    aluna duas vezes ao mesmo tempo.
"""

from datetime import datetime, timedelta

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.utils import timezone

from usuarios.models import Aluna

from .models import (
    AgendaMaquiagemTurma,
    AgendamentoMaquiagem,
    HorarioMaquiagem,
)

# Trava de segurança: evita criar milhares de horários por engano.
MAX_HORARIOS_POR_MAQUIADORA = 100


class ErroAgendamento(Exception):
    """Mensagem pronta para mostrar à secretaria."""


def formatar_horario(valor):
    """'14/11 às 09:30', no fuso local."""
    return f'{timezone.localtime(valor):%d/%m às %H:%M}'


# ---------------------------------------------------------------------------
# Quem é quem
# ---------------------------------------------------------------------------

def alunas_do_usuario(user):
    """
    Alunas ligadas a quem está logado: a própria aluna adulta e os dependentes
    ativos de quem é responsável. Nunca devolve aluna de outra família.
    """
    if not getattr(user, 'is_authenticated', False):
        return []

    alunas = []
    adulta = Aluna.objects.filter(usuario=user).first()
    if adulta:
        alunas.append(adulta)

    for dependente in Aluna.objects.filter(
        responsavel=user, ativa=True
    ).order_by('nome'):
        if adulta and dependente.pk == adulta.pk:
            continue
        alunas.append(dependente)

    return alunas


def horarios_da_familia(user, espetaculo):
    """
    O que a aluna (ou a família) enxerga na área de maquiagem: SOMENTE os
    horários agendados para as alunas dela.

    Devolve uma lista de dicts {'aluna', 'agendamento'}. Alunas sem horário só
    entram se a turma delas tem maquiagem neste espetáculo (para a tela poder
    dizer "ainda sem horário"); as demais não aparecem.
    """
    alunas = alunas_do_usuario(user)
    if not alunas:
        return []

    por_aluna = {
        ag.aluna_id: ag
        for ag in AgendamentoMaquiagem.objects.filter(
            aluna__in=alunas,
            horario__agenda__espetaculo=espetaculo,
        ).select_related('horario', 'horario__agenda', 'aluna')
    }

    itens = []
    for aluna in alunas:
        agendamento = por_aluna.get(aluna.pk)
        if agendamento is None:
            tem_agenda = AgendaMaquiagemTurma.objects.filter(
                espetaculo=espetaculo, turma__in=aluna.turmas.all()
            ).exists()
            if not tem_agenda:
                continue
        itens.append({'aluna': aluna, 'agendamento': agendamento})

    return itens


# ---------------------------------------------------------------------------
# Consultas do painel
# ---------------------------------------------------------------------------

def agendamento_da_aluna(aluna, espetaculo):
    return AgendamentoMaquiagem.objects.filter(
        aluna=aluna, horario__agenda__espetaculo=espetaculo
    ).select_related('horario', 'horario__agenda').first()


def alunas_sem_horario(espetaculo, turma):
    """Alunas ativas da turma que ainda não têm horário neste espetáculo."""
    return Aluna.objects.filter(
        turmas=turma, ativa=True
    ).exclude(
        agendamentos_maquiagem__horario__agenda__espetaculo=espetaculo
    ).distinct().order_by('nome')


def _agendamento_de(horario):
    try:
        return horario.agendamento
    except ObjectDoesNotExist:
        return None


def montar_grade(espetaculo, turma, dia=None):
    """
    Dados da grade "agenda por horário" de uma turma: uma coluna por maquiadora
    (agenda), uma linha por horário do dia escolhido.

    Cada célula traz um estado: livre, ocupado, reservado, bloqueado ou
    ausente (essa maquiadora não tem horário nesse momento).
    """
    agendas = list(
        AgendaMaquiagemTurma.objects.filter(
            espetaculo=espetaculo, turma=turma
        ).order_by('maquiadora', 'id')
    )
    for agenda in agendas:
        HorarioMaquiagem.liberar_expirados(agenda=agenda)

    horarios = list(
        HorarioMaquiagem.objects.filter(agenda__in=agendas)
        .select_related('agenda', 'agendamento', 'agendamento__aluna')
        .order_by('horario', 'agenda__maquiadora', 'id')
    )

    resumo_dias = {}
    for horario in horarios:
        data = timezone.localtime(horario.horario).date()
        info = resumo_dias.setdefault(data, {'total': 0, 'livres': 0})
        info['total'] += 1
        if horario.status == 'disponivel':
            info['livres'] += 1

    dias = [
        {'data': data, 'total': info['total'], 'livres': info['livres']}
        for data, info in sorted(resumo_dias.items())
    ]

    datas = [d['data'] for d in dias]
    if dia not in datas:
        com_livres = [d['data'] for d in dias if d['livres']]
        dia = (com_livres or datas or [None])[0]

    linhas = []
    if dia is not None:
        do_dia = {}
        for horario in horarios:
            local = timezone.localtime(horario.horario)
            if local.date() == dia:
                do_dia[(local.time(), horario.agenda_id)] = horario

        for hora in sorted({chave[0] for chave in do_dia}):
            celulas = []
            for agenda in agendas:
                horario = do_dia.get((hora, agenda.pk))
                agendamento = _agendamento_de(horario) if horario else None

                if horario is None:
                    estado = 'ausente'
                elif horario.status == 'disponivel':
                    estado = 'livre'
                elif horario.status == 'agendado':
                    estado = 'ocupado'
                elif horario.status == 'reservado_temporario':
                    estado = 'reservado'
                else:
                    estado = 'bloqueado'

                celulas.append({
                    'agenda': agenda,
                    'horario': horario,
                    'agendamento': agendamento,
                    'estado': estado,
                })
            linhas.append({'hora': hora, 'celulas': celulas})

    return {
        'turma': turma,
        'agendas': agendas,
        'dias': dias,
        'dia': dia,
        'linhas': linhas,
        'livres_total': sum(d['livres'] for d in dias),
    }


# ---------------------------------------------------------------------------
# Criar horários em lote
# ---------------------------------------------------------------------------

def gerar_horarios(agendas, dia, inicio, fim, duracao, intervalo=0, hoje=None):
    """
    Cria todos os horários de um dia, para cada agenda (maquiadora) escolhida:
    do início ao fim, de `duracao` em `duracao` minutos (mais um `intervalo`
    opcional entre eles). O que já existe é pulado, nada é duplicado.

    Devolve {'criados', 'existentes', 'por_agenda'}.
    """
    hoje = hoje or timezone.localdate()

    if not agendas:
        raise ErroAgendamento('Escolha ao menos uma maquiadora.')
    if dia < hoje:
        raise ErroAgendamento('Essa data já passou. Confira o dia informado.')
    if not 5 <= duracao <= 240:
        raise ErroAgendamento(
            'A duração de cada horário deve ficar entre 5 e 240 minutos.'
        )
    if not 0 <= intervalo <= 120:
        raise ErroAgendamento('O intervalo deve ficar entre 0 e 120 minutos.')

    fuso = timezone.get_current_timezone()
    comeco = timezone.make_aware(datetime.combine(dia, inicio), fuso)
    limite = timezone.make_aware(datetime.combine(dia, fim), fuso)

    if limite <= comeco:
        raise ErroAgendamento('O horário final precisa ser depois do inicial.')

    duracao_td = timedelta(minutes=duracao)
    passo = timedelta(minutes=duracao + intervalo)

    horarios = []
    atual = comeco
    while atual + duracao_td <= limite:
        horarios.append(atual)
        atual += passo
        if len(horarios) > MAX_HORARIOS_POR_MAQUIADORA:
            raise ErroAgendamento(
                f'Isso criaria mais de {MAX_HORARIOS_POR_MAQUIADORA} horários '
                f'por maquiadora. Confira o início, o fim e a duração.'
            )

    if not horarios:
        raise ErroAgendamento(
            f'Esse período não comporta nenhum horário de {duracao} minutos.'
        )

    criados = 0
    existentes = 0
    with transaction.atomic():
        for agenda in agendas:
            ja_existem = set(
                HorarioMaquiagem.objects.filter(
                    agenda=agenda, horario__in=horarios
                ).values_list('horario', flat=True)
            )
            novos = [
                HorarioMaquiagem(
                    agenda=agenda, horario=h, duracao_minutos=duracao
                )
                for h in horarios
                if h not in ja_existem
            ]
            HorarioMaquiagem.objects.bulk_create(novos)
            criados += len(novos)
            existentes += len(horarios) - len(novos)

    return {
        'criados': criados,
        'existentes': existentes,
        'por_agenda': len(horarios),
    }


# ---------------------------------------------------------------------------
# Agendar e remover
# ---------------------------------------------------------------------------

def agendar_aluna(espetaculo, turma, horario_id, aluna_id, tipo_servico):
    """
    Agenda a aluna no horário. Recusa (ErroAgendamento) se: o horário não é da
    turma, a aluna não é da turma, o serviço é inválido, a aluna já tem horário
    neste espetáculo ou o horário já foi ocupado.
    """
    if tipo_servico not in dict(AgendamentoMaquiagem.TIPO_CHOICES):
        raise ErroAgendamento('Escolha o tipo de serviço.')

    try:
        aluna_id = int(aluna_id)
        horario_id = int(horario_id)
    except (TypeError, ValueError):
        raise ErroAgendamento('Escolha uma aluna na lista e um horário livre.')

    with transaction.atomic():
        # Trava a aluna e o horário: duas pessoas clicando ao mesmo tempo não
        # agendam a mesma aluna duas vezes nem ocupam o mesmo horário.
        aluna = Aluna.objects.select_for_update(of=('self',)).filter(
            pk=aluna_id, turmas=turma, ativa=True
        ).first()
        if aluna is None:
            raise ErroAgendamento(
                'Essa aluna não está ativa nesta turma. Atualize a página.'
            )

        horario = HorarioMaquiagem.objects.select_for_update(
            of=('self',)
        ).select_related('agenda').filter(
            pk=horario_id,
            agenda__espetaculo=espetaculo,
            agenda__turma=turma,
        ).first()
        if horario is None:
            raise ErroAgendamento('Horário não encontrado para esta turma.')

        existente = agendamento_da_aluna(aluna, espetaculo)
        if existente is not None:
            raise ErroAgendamento(
                f'{aluna.nome} já tem horário: '
                f'{formatar_horario(existente.horario.horario)} com '
                f'{existente.horario.agenda.maquiadora}. '
                f'Remova esse agendamento antes de marcar outro.'
            )

        if horario.esta_reservado_expirado:
            horario.liberar()

        if horario.status != 'disponivel':
            raise ErroAgendamento(
                'Esse horário não está mais disponível. Atualize a página.'
            )

        agendamento = AgendamentoMaquiagem.objects.create(
            horario=horario,
            aluna=aluna,
            tipo_servico=tipo_servico,
            criado_por_admin=True,
        )
        horario.marcar_como_agendado()

    return agendamento


def remover_agendamento(espetaculo, agendamento_id):
    """Remove o agendamento, libera o horário e devolve o nome da aluna."""
    with transaction.atomic():
        agendamento = AgendamentoMaquiagem.objects.select_related(
            'horario', 'horario__agenda', 'aluna'
        ).filter(
            pk=agendamento_id, horario__agenda__espetaculo=espetaculo
        ).first()
        if agendamento is None:
            raise ErroAgendamento('Agendamento não encontrado.')

        horario = agendamento.horario
        nome = agendamento.aluna.nome
        agendamento.delete()
        horario.liberar()

    return nome
