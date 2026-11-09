"""
Regras de negócio da lista de presença.

Tudo que mostra falta (cards das alunas, lista de presença, resumo, detalhe da
aluna) passa por registros_periodo(): é UMA só conta, então os números nunca
divergem entre as telas.
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from django.db import transaction
from django.db.models import Prefetch, Q
from django.utils import timezone

from usuarios.models import Aluna, Turma

from .models import (
    DIAS_CURTOS,
    ConfiguracaoPresenca,
    DiaSemAula,
    HorarioTurma,
    Presenca,
)

MESES_PT = {
    1: 'janeiro', 2: 'fevereiro', 3: 'março', 4: 'abril', 5: 'maio', 6: 'junho',
    7: 'julho', 8: 'agosto', 9: 'setembro', 10: 'outubro', 11: 'novembro', 12: 'dezembro',
}

STATUS_PRESENTE = 'presente'
STATUS_FALTA = 'falta'
STATUS_AGUARDANDO = 'aguardando'


# ---------------------------------------------------------------------------
# Datas e períodos
# ---------------------------------------------------------------------------

def aware(dia, hora):
    return timezone.make_aware(datetime.combine(dia, hora))


def rotulo_mes(ano, mes):
    return f'{MESES_PT[mes]}/{ano}'


def rotulo_mes_atual():
    hoje = timezone.localdate()
    return rotulo_mes(hoje.year, hoje.month)


def primeiro_dia_mes(d):
    return d.replace(day=1)


def ultimo_dia_mes(d):
    if d.month == 12:
        return date(d.year, 12, 31)
    return date(d.year, d.month + 1, 1) - timedelta(days=1)


def somar_meses(d, n):
    indice = d.year * 12 + (d.month - 1) + n
    return date(indice // 12, indice % 12 + 1, 1)


def intervalo_do_periodo(periodo, referencia):
    """periodo: 'dia' | 'semana' (segunda a domingo) | 'mes'."""
    if periodo == 'semana':
        ini = referencia - timedelta(days=referencia.weekday())
        return ini, ini + timedelta(days=6)
    if periodo == 'mes':
        return primeiro_dia_mes(referencia), ultimo_dia_mes(referencia)
    return referencia, referencia


def deslocar_referencia(periodo, referencia, direcao):
    """Move a referência para o período anterior (-1) ou seguinte (+1)."""
    if periodo == 'semana':
        return referencia + timedelta(days=7 * direcao)
    if periodo == 'mes':
        return somar_meses(referencia, direcao)
    return referencia + timedelta(days=direcao)


# ---------------------------------------------------------------------------
# Registros (uma linha = uma aluna em uma aula de um dia)
# ---------------------------------------------------------------------------

@dataclass
class Registro:
    aluna: object
    turma: object
    horario: object
    data: date
    inicio: datetime
    fim: datetime
    status: str
    presenca: object = None

    @property
    def desmarcada(self):
        return bool(self.presenca and self.presenca.anulada)


def alunas_para_presenca(queryset):
    """Carrega, de uma vez só, as turmas (ativas) e horários de cada aluna."""
    turmas = Turma.objects.filter(ativa=True, tipo='turma').prefetch_related('horarios_aula')
    return queryset.prefetch_related(
        Prefetch('turmas', queryset=turmas, to_attr='turmas_presenca')
    )


def registros_periodo(alunas_qs, data_ini, data_fim, turma_id=None, agora=None):
    """
    Devolve todos os registros (presente / falta / aguardando) das alunas no período.

    - Só considera dias até hoje e a partir do "início do controle".
    - Ignora dias antes da matrícula da aluna e dias sem aula (feriado/recesso).
    - Uma presença desmarcada pela escola vira falta (depois que a aula acabou).
    """
    config = ConfiguracaoPresenca.obter()
    agora = agora or timezone.localtime()
    hoje = agora.date()

    data_ini = max(data_ini, config.data_inicio_controle)
    data_fim = min(data_fim, hoje)
    if data_ini > data_fim:
        return []

    alunas = list(alunas_para_presenca(alunas_qs))
    if not alunas:
        return []

    presencas = {
        (p.aluna_id, p.turma_id, p.data): p
        for p in Presenca.objects.filter(
            aluna_id__in=[a.pk for a in alunas],
            data__range=(data_ini, data_fim),
        )
    }

    sem_aula_geral = set()
    sem_aula_turma = set()
    for folga in DiaSemAula.objects.filter(data__range=(data_ini, data_fim)):
        if folga.turma_id is None:
            sem_aula_geral.add(folga.data)
        else:
            sem_aula_turma.add((folga.turma_id, folga.data))

    datas_por_dia_semana = defaultdict(list)
    dia = data_ini
    while dia <= data_fim:
        datas_por_dia_semana[dia.weekday()].append(dia)
        dia += timedelta(days=1)

    margem = timedelta(minutes=config.minutos_depois)
    registros = []
    for aluna in alunas:
        for turma in aluna.turmas_presenca:
            if turma_id and turma.pk != turma_id:
                continue
            for horario in turma.horarios_aula.all():
                for dia in datas_por_dia_semana.get(horario.dia_semana, ()):
                    if dia < aluna.data_matricula:
                        continue
                    if dia in sem_aula_geral or (turma.pk, dia) in sem_aula_turma:
                        continue

                    inicio = aware(dia, horario.hora_inicio)
                    fim = aware(dia, horario.hora_fim)
                    presenca = presencas.get((aluna.pk, turma.pk, dia))

                    if presenca and not presenca.anulada:
                        status = STATUS_PRESENTE
                    elif agora > fim + margem:
                        status = STATUS_FALTA
                    else:
                        status = STATUS_AGUARDANDO

                    registros.append(Registro(
                        aluna=aluna, turma=turma, horario=horario, data=dia,
                        inicio=inicio, fim=fim, status=status, presenca=presenca,
                    ))

    registros.sort(key=lambda r: (r.data, r.inicio, r.turma.nome, r.aluna.nome))
    return registros


def totais(registros):
    """Conta presenças/faltas/aguardando de uma lista de registros."""
    resumo = {STATUS_PRESENTE: 0, STATUS_FALTA: 0, STATUS_AGUARDANDO: 0}
    for r in registros:
        resumo[r.status] += 1
    aulas = resumo[STATUS_PRESENTE] + resumo[STATUS_FALTA]
    resumo['aulas'] = aulas
    resumo['frequencia'] = round(resumo[STATUS_PRESENTE] * 100 / aulas) if aulas else None
    return resumo


def totais_por_aluna(registros):
    por_aluna = defaultdict(list)
    for r in registros:
        por_aluna[r.aluna.pk].append(r)
    return {pk: totais(lista) for pk, lista in por_aluna.items()}


def sequencias_de_faltas(registros):
    """(sequência atual, maior sequência) de faltas seguidas, ignorando aulas futuras."""
    encerrados = [r for r in registros if r.status != STATUS_AGUARDANDO]
    encerrados.sort(key=lambda r: (r.data, r.inicio))
    maior = atual = 0
    for r in encerrados:
        if r.status == STATUS_FALTA:
            atual += 1
            maior = max(maior, atual)
        else:
            atual = 0
    return atual, maior


# ---------------------------------------------------------------------------
# Cards da lista de alunas
# ---------------------------------------------------------------------------

def anexar_faltas_do_mes(alunas):
    """
    Recebe as alunas da página de listagem e coloca em cada uma o atributo
    `faltas_mes` (só o mês atual). Alunas inativas ficam com None.
    """
    alunas = list(alunas)
    for aluna in alunas:
        aluna.faltas_mes = None
    if not alunas:
        return alunas

    hoje = timezone.localdate()
    registros = registros_periodo(
        Aluna.objects.filter(pk__in=[a.pk for a in alunas], ativa=True),
        primeiro_dia_mes(hoje),
        ultimo_dia_mes(hoje),
    )
    faltas = defaultdict(int)
    for r in registros:
        if r.status == STATUS_FALTA:
            faltas[r.aluna.pk] += 1

    for aluna in alunas:
        if aluna.ativa:
            aluna.faltas_mes = faltas.get(aluna.pk, 0)
    return alunas


# ---------------------------------------------------------------------------
# Registro de presença pelo QR Code
# ---------------------------------------------------------------------------

@dataclass
class AulaAberta:
    turma: object
    horario: object
    inicio: datetime
    fim: datetime
    presenca: object = None

    @property
    def ja_registrada(self):
        return bool(self.presenca and not self.presenca.anulada)

    @property
    def desmarcada(self):
        return bool(self.presenca and self.presenca.anulada)


def alunas_do_usuario(usuario):
    """Alunas que esta pessoa pode registrar: a própria (adulta) ou as filhas (responsável)."""
    return (
        Aluna.objects.filter(ativa=True)
        .filter(Q(responsavel=usuario) | Q(usuario=usuario))
        .distinct()
        .order_by('nome')
    )


def aulas_abertas(aluna, agora=None, config=None):
    """Aulas da aluna cujo registro está aberto neste exato momento."""
    config = config or ConfiguracaoPresenca.obter()
    agora = agora or timezone.localtime()
    hoje = agora.date()

    sem_aula_geral = DiaSemAula.objects.filter(data=hoje, turma__isnull=True).exists()
    if sem_aula_geral:
        return []
    turmas_sem_aula = set(
        DiaSemAula.objects.filter(data=hoje, turma__isnull=False).values_list('turma_id', flat=True)
    )

    antes = timedelta(minutes=config.minutos_antes)
    depois = timedelta(minutes=config.minutos_depois)

    turmas = aluna.turmas.filter(ativa=True, tipo='turma').prefetch_related('horarios_aula')
    abertas = []
    for turma in turmas:
        if turma.pk in turmas_sem_aula:
            continue
        for horario in turma.horarios_aula.all():
            if horario.dia_semana != hoje.weekday():
                continue
            inicio = aware(hoje, horario.hora_inicio)
            fim = aware(hoje, horario.hora_fim)
            if inicio - antes <= agora <= fim + depois:
                abertas.append(AulaAberta(turma=turma, horario=horario, inicio=inicio, fim=fim))

    existentes = {
        p.turma_id: p
        for p in Presenca.objects.filter(
            aluna=aluna, data=hoje, turma_id__in=[a.turma.pk for a in abertas]
        )
    }
    for aula in abertas:
        aula.presenca = existentes.get(aula.turma.pk)

    abertas.sort(key=lambda a: (a.inicio, a.turma.nome))
    return abertas


def proxima_aula(aluna, agora=None):
    """Próxima aula (nos próximos 7 dias) para mostrar quando o registro não está aberto."""
    agora = agora or timezone.localtime()
    turmas = aluna.turmas.filter(ativa=True, tipo='turma').prefetch_related('horarios_aula')
    candidatas = []
    for turma in turmas:
        for horario in turma.horarios_aula.all():
            for delta in range(0, 8):
                dia = agora.date() + timedelta(days=delta)
                if dia.weekday() != horario.dia_semana:
                    continue
                inicio = aware(dia, horario.hora_inicio)
                if inicio > agora:
                    candidatas.append((inicio, turma, horario))
                    break
    if not candidatas:
        return None
    candidatas.sort(key=lambda c: c[0])
    inicio, turma, horario = candidatas[0]
    return {'turma': turma, 'horario': horario, 'inicio': inicio}


ESTADO_CRIADA = 'criada'
ESTADO_JA_REGISTRADA = 'ja_registrada'
ESTADO_DESMARCADA = 'desmarcada'


def registrar_presenca(aluna, turma, dia, usuario, origem=Presenca.ORIGEM_QR, agora=None):
    """
    Cria a presença (uma só por aluna/turma/dia). Devolve (presenca, estado):
      criada | ja_registrada | desmarcada (a escola desmarcou, não dá para registrar de novo)
    """
    agora = agora or timezone.now()
    with transaction.atomic():
        presenca, criada = Presenca.objects.get_or_create(
            aluna=aluna, turma=turma, data=dia,
            defaults={'registrada_em': agora, 'registrada_por': usuario, 'origem': origem},
        )
    if criada:
        return presenca, ESTADO_CRIADA
    if presenca.anulada:
        return presenca, ESTADO_DESMARCADA
    return presenca, ESTADO_JA_REGISTRADA


def marcar_presenca_manual(aluna, turma, dia, usuario):
    """
    Uso da escola: marca (ou restaura) a presença de uma aula que realmente existe.
    Devolve (presenca, mensagem_de_erro). Em caso de erro, presenca é None.
    """
    if dia > timezone.localdate():
        return None, 'Não é possível marcar presença em uma data futura.'
    if not aluna.turmas.filter(pk=turma.pk).exists():
        return None, 'Esta aluna não faz parte da turma.'
    if not turma.horarios_aula.filter(dia_semana=dia.weekday()).exists():
        return None, 'A turma não tem aula neste dia da semana.'

    with transaction.atomic():
        presenca, criada = Presenca.objects.get_or_create(
            aluna=aluna, turma=turma, data=dia,
            defaults={
                'registrada_em': timezone.now(),
                'registrada_por': usuario,
                'origem': Presenca.ORIGEM_MANUAL,
            },
        )
        if not criada and presenca.anulada:
            presenca.restaurar(usuario)
    return presenca, None


# ---------------------------------------------------------------------------
# Horários da turma (formulário de criar/editar turma)
# ---------------------------------------------------------------------------

def _hora(texto):
    texto = (texto or '').strip()
    if not texto:
        return None
    for formato in ('%H:%M', '%H:%M:%S'):
        try:
            return datetime.strptime(texto, formato).time()
        except ValueError:
            continue
    raise ValueError(f'Hora inválida: "{texto}"')


def salvar_horarios_turma(turma, post):
    """
    Lê os horários enviados no formulário da turma e substitui os atuais.
    Só mexe nos horários se o formulário realmente trouxe essa seção.
    Devolve a lista de avisos (vazia se deu tudo certo).
    """
    if not post.get('horarios_enviados'):
        return []

    dias = post.getlist('horario_dia')
    inicios = post.getlist('horario_inicio')
    fins = post.getlist('horario_fim')

    novos, avisos, vistos = [], [], set()
    for dia, ini, fim in zip(dias, inicios, fins):
        if not dia and not ini and not fim:
            continue  # linha em branco
        try:
            dia_num = int(dia)
            hora_ini, hora_fim = _hora(ini), _hora(fim)
        except (ValueError, TypeError):
            avisos.append('Há um horário com dados inválidos; ele não foi salvo.')
            continue
        if not (0 <= dia_num <= 6) or hora_ini is None or hora_fim is None:
            avisos.append('Há um horário incompleto (dia, início e fim são obrigatórios); ele não foi salvo.')
            continue
        if hora_fim <= hora_ini:
            avisos.append(f'{DIAS_CURTOS[dia_num]}: a hora de fim precisa ser depois do início; este horário não foi salvo.')
            continue
        if dia_num in vistos:
            avisos.append(f'{DIAS_CURTOS[dia_num]}: a turma só pode ter um horário por dia da semana; o repetido foi ignorado.')
            continue
        vistos.add(dia_num)
        novos.append((dia_num, hora_ini, hora_fim))

    with transaction.atomic():
        turma.horarios_aula.all().delete()
        HorarioTurma.objects.bulk_create([
            HorarioTurma(turma=turma, dia_semana=d, hora_inicio=i, hora_fim=f)
            for d, i, f in novos
        ])
    return avisos
