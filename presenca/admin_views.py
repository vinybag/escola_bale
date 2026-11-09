"""
Telas do admin personalizado (admin_dashboard) para o controle de presença.
Só quem tem is_staff acessa, igual ao resto do painel.
"""
import io
from datetime import datetime
from functools import wraps
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from usuarios.models import Aluna, Turma

from .models import ConfiguracaoPresenca, DiaSemAula, HorarioTurma, Presenca
from .services import (
    STATUS_AGUARDANDO,
    STATUS_FALTA,
    STATUS_PRESENTE,
    deslocar_referencia,
    intervalo_do_periodo,
    marcar_presenca_manual,
    registros_periodo,
    rotulo_mes,
    sequencias_de_faltas,
    totais,
    totais_por_aluna,
)

PERIODOS_LISTA = ('dia', 'semana', 'mes')
STATUS_VALIDOS = (STATUS_PRESENTE, STATUS_FALTA, STATUS_AGUARDANDO)


def staff_required(view):
    @login_required
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_staff:
            return redirect('home')
        return view(request, *args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# utilidades
# ---------------------------------------------------------------------------

def _data(valor, padrao):
    try:
        return datetime.strptime(valor, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return padrao


def _inteiro(valor):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _url(nome, **params):
    limpos = {k: v for k, v in params.items() if v not in (None, '')}
    base = reverse(nome)
    return f'{base}?{urlencode(limpos)}' if limpos else base


def _voltar(request, padrao='admin_dashboard:presenca_lista'):
    destino = request.POST.get('next', '')
    if destino and url_has_allowed_host_and_scheme(
        url=destino,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(destino)
    return redirect(padrao)


def _turmas_de_aula():
    return Turma.objects.filter(ativa=True, tipo='turma').order_by('nome')


def _rotulo_periodo(periodo, ini, fim):
    if periodo == 'dia':
        return ini.strftime('%d/%m/%Y')
    if periodo == 'mes':
        return rotulo_mes(ini.year, ini.month)
    return f'{ini:%d/%m} a {fim:%d/%m/%Y}'


def _avisos_de_horarios():
    pendentes = (
        Turma.objects.filter(ativa=True, tipo='turma', horarios_aula__isnull=True, alunas__ativa=True)
        .distinct().order_by('nome')
    )
    automaticos = HorarioTurma.objects.filter(preenchido_automaticamente=True).count()
    return pendentes, automaticos


# ---------------------------------------------------------------------------
# Lista de presença (aulas do dia, separadas) + filtros
# ---------------------------------------------------------------------------

@staff_required
def lista(request):
    config = ConfiguracaoPresenca.obter()
    hoje = timezone.localdate()

    periodo = request.GET.get('periodo')
    if periodo not in PERIODOS_LISTA:
        periodo = 'dia'
    referencia = _data(request.GET.get('data'), hoje)
    turma_id = _inteiro(request.GET.get('turma'))
    aluna_id = _inteiro(request.GET.get('aluna'))
    status = request.GET.get('status')
    if status not in STATUS_VALIDOS:
        status = ''

    ini, fim = intervalo_do_periodo(periodo, referencia)

    alunas_qs = Aluna.objects.filter(ativa=True)
    if aluna_id:
        alunas_qs = alunas_qs.filter(pk=aluna_id)
    todos = registros_periodo(alunas_qs, ini, fim, turma_id=turma_id)
    resumo = totais(todos)
    registros = [r for r in todos if not status or r.status == status]

    folgas = {}
    for folga in DiaSemAula.objects.filter(data__range=(ini, fim)).select_related('turma'):
        alvo = folga.turma.nome if folga.turma_id else 'todas as turmas'
        texto = f'{folga.motivo} ({alvo})' if folga.motivo else alvo
        folgas.setdefault(folga.data, []).append(texto)

    agrupado = {}
    for r in registros:
        dia = agrupado.setdefault(r.data, {})
        bloco = dia.setdefault(r.turma.pk, {
            'turma': r.turma, 'horario': r.horario,
            'inicio': r.inicio, 'fim': r.fim, 'linhas': [],
        })
        bloco['linhas'].append(r)

    dias = []
    for d in sorted(agrupado, reverse=(periodo != 'dia')):
        blocos = sorted(agrupado[d].values(), key=lambda b: (b['inicio'], b['turma'].nome))
        for bloco in blocos:
            contagem = totais(bloco['linhas'])
            bloco['presentes'] = contagem[STATUS_PRESENTE]
            bloco['faltas'] = contagem[STATUS_FALTA]
            bloco['aguardando'] = contagem[STATUS_AGUARDANDO]
        dias.append({'data': d, 'blocos': blocos})

    # Mensagem quando não há nada para mostrar
    if not dias:
        if periodo == 'dia' and referencia > hoje:
            vazio = 'Esta data ainda não chegou.'
        elif fim < config.data_inicio_controle:
            vazio = f'O controle de presença começa em {config.data_inicio_controle:%d/%m/%Y}.'
        elif status or turma_id or aluna_id:
            vazio = 'Nenhum registro com esses filtros.'
        elif folgas:
            vazio = 'Dia sem aula no período (veja o aviso acima).'
        else:
            vazio = 'Nenhuma aula neste período.'
    else:
        vazio = ''

    filtros = {'turma': turma_id, 'aluna': aluna_id, 'status': status}
    nome_url = 'admin_dashboard:presenca_lista'
    pendentes, automaticos = _avisos_de_horarios()

    contexto = {
        'dias': dias,
        'folgas_periodo': [(d, folgas[d]) for d in sorted(folgas)],
        'resumo': resumo,
        'vazio': vazio,
        'periodo': periodo,
        'referencia': referencia,
        'rotulo_periodo': _rotulo_periodo(periodo, ini, fim),
        'e_hoje': periodo == 'dia' and referencia == hoje,
        'turma_id': turma_id,
        'aluna_id': aluna_id,
        'status': status,
        'turmas': _turmas_de_aula(),
        'alunas': Aluna.objects.filter(ativa=True).order_by('nome'),
        'url_anterior': _url(nome_url, periodo=periodo, data=deslocar_referencia(periodo, referencia, -1), **filtros),
        'url_proximo': _url(nome_url, periodo=periodo, data=deslocar_referencia(periodo, referencia, 1), **filtros),
        'url_hoje': _url(nome_url, periodo=periodo, **filtros),
        'url_dia': _url(nome_url, periodo='dia', data=referencia, **filtros),
        'url_semana': _url(nome_url, periodo='semana', data=referencia, **filtros),
        'url_mes': _url(nome_url, periodo='mes', data=referencia, **filtros),
        'url_atual': request.get_full_path(),
        'turmas_pendentes': pendentes,
        'horarios_automaticos': automaticos,
        'hoje': hoje,
    }
    return render(request, 'presenca/admin/lista.html', contexto)


# ---------------------------------------------------------------------------
# Ações: desmarcar / restaurar / marcar manualmente
# ---------------------------------------------------------------------------

@staff_required
@require_POST
def desmarcar(request, pk):
    presenca = get_object_or_404(Presenca.objects.select_related('aluna', 'turma'), pk=pk)
    if presenca.anulada:
        messages.info(request, 'Esta presença já estava desmarcada.')
    else:
        presenca.anular(request.user, request.POST.get('motivo', ''))
        messages.success(
            request,
            f'Presença de {presenca.aluna.nome} em {presenca.data:%d/%m} ({presenca.turma.nome}) '
            f'desmarcada. A aula passa a contar como falta.',
        )
    return _voltar(request)


@staff_required
@require_POST
def restaurar(request, pk):
    presenca = get_object_or_404(Presenca.objects.select_related('aluna', 'turma'), pk=pk)
    if presenca.anulada:
        presenca.restaurar(request.user)
        messages.success(
            request,
            f'Presença de {presenca.aluna.nome} em {presenca.data:%d/%m} ({presenca.turma.nome}) restaurada.',
        )
    return _voltar(request)


@staff_required
@require_POST
def marcar_manual(request):
    aluna = get_object_or_404(Aluna, pk=_inteiro(request.POST.get('aluna')) or 0)
    turma = get_object_or_404(Turma, pk=_inteiro(request.POST.get('turma')) or 0)
    dia = _data(request.POST.get('data'), None)
    if dia is None:
        messages.error(request, 'Data inválida.')
        return _voltar(request)

    presenca, erro = marcar_presenca_manual(aluna, turma, dia, request.user)
    if erro:
        messages.error(request, erro)
    else:
        messages.success(request, f'Presença de {aluna.nome} em {dia:%d/%m} ({turma.nome}) marcada.')
    return _voltar(request)


# ---------------------------------------------------------------------------
# Resumo por aluna
# ---------------------------------------------------------------------------

@staff_required
def resumo(request):
    config = ConfiguracaoPresenca.obter()
    hoje = timezone.localdate()

    periodo = request.GET.get('periodo')
    if periodo not in ('mes', 'semana', 'tudo'):
        periodo = 'mes'
    referencia = _data(request.GET.get('data'), hoje)
    turma_id = _inteiro(request.GET.get('turma'))
    busca = (request.GET.get('busca') or '').strip()
    ordem = request.GET.get('ordem')
    if ordem not in ('faltas', 'nome', 'frequencia'):
        ordem = 'faltas'

    if periodo == 'tudo':
        ini, fim = config.data_inicio_controle, hoje
        rotulo = f'desde {config.data_inicio_controle:%d/%m/%Y}'
    else:
        ini, fim = intervalo_do_periodo(periodo, referencia)
        rotulo = _rotulo_periodo(periodo, ini, fim)

    alunas_qs = Aluna.objects.filter(ativa=True)
    if busca:
        alunas_qs = alunas_qs.filter(nome__icontains=busca)
    if turma_id:
        alunas_qs = alunas_qs.filter(turmas__pk=turma_id).distinct()

    registros = registros_periodo(alunas_qs, ini, fim, turma_id=turma_id)
    por_aluna = totais_por_aluna(registros)
    vazio = totais([])

    linhas = []
    for aluna in alunas_qs.order_by('nome').prefetch_related('turmas'):
        dados = por_aluna.get(aluna.pk, vazio)
        linhas.append({'aluna': aluna, 'dados': dados})

    if ordem == 'faltas':
        linhas.sort(key=lambda l: (-l['dados'][STATUS_FALTA], l['aluna'].nome.lower()))
    elif ordem == 'frequencia':
        linhas.sort(key=lambda l: (l['dados']['frequencia'] is None,
                                   l['dados']['frequencia'] if l['dados']['frequencia'] is not None else 0,
                                   l['aluna'].nome.lower()))

    geral = totais(registros)
    nome_url = 'admin_dashboard:presenca_resumo'
    filtros = {'turma': turma_id, 'busca': busca, 'ordem': ordem}

    contexto = {
        'linhas': linhas,
        'geral': geral,
        'alunas_com_falta': sum(1 for l in linhas if l['dados'][STATUS_FALTA] > 0),
        'periodo': periodo,
        'rotulo': rotulo,
        'turma_id': turma_id,
        'busca': busca,
        'ordem': ordem,
        'turmas': _turmas_de_aula(),
        'referencia': referencia,
        'url_anterior': _url(nome_url, periodo=periodo, data=deslocar_referencia(periodo, referencia, -1), **filtros) if periodo != 'tudo' else '',
        'url_proximo': _url(nome_url, periodo=periodo, data=deslocar_referencia(periodo, referencia, 1), **filtros) if periodo != 'tudo' else '',
        'url_mes': _url(nome_url, periodo='mes', **filtros),
        'url_semana': _url(nome_url, periodo='semana', **filtros),
        'url_tudo': _url(nome_url, periodo='tudo', **filtros),
        'url_atual_mes': _url(nome_url, periodo='mes', **filtros),
    }
    return render(request, 'presenca/admin/resumo.html', contexto)


# ---------------------------------------------------------------------------
# Detalhe de uma aluna
# ---------------------------------------------------------------------------

@staff_required
def aluna_detalhe(request, pk):
    aluna = get_object_or_404(Aluna.objects.prefetch_related('turmas'), pk=pk)
    config = ConfiguracaoPresenca.obter()
    hoje = timezone.localdate()

    mes_texto = request.GET.get('mes') or ''
    try:
        mes_ref = datetime.strptime(mes_texto + '-01', '%Y-%m-%d').date()
    except ValueError:
        mes_ref = hoje.replace(day=1)

    todos = registros_periodo(Aluna.objects.filter(pk=aluna.pk), config.data_inicio_controle, hoje)
    do_mes = [r for r in todos if (r.data.year, r.data.month) == (mes_ref.year, mes_ref.month)]
    do_mes.sort(key=lambda r: (r.data, r.inicio), reverse=True)

    por_mes = {}
    for r in todos:
        por_mes.setdefault((r.data.year, r.data.month), []).append(r)
    historico = []
    for (ano, mes) in sorted(por_mes, reverse=True):
        dados = totais(por_mes[(ano, mes)])
        historico.append({
            'rotulo': rotulo_mes(ano, mes),
            'chave': f'{ano}-{mes:02d}',
            'dados': dados,
            'ativo': (ano, mes) == (mes_ref.year, mes_ref.month),
        })
    maximo = max([h['dados'][STATUS_FALTA] for h in historico] + [1])
    for h in historico:
        h['largura'] = round(h['dados'][STATUS_FALTA] * 100 / maximo)

    atual, maior = sequencias_de_faltas(todos)

    contexto = {
        'aluna': aluna,
        'turmas': aluna.turmas.filter(ativa=True, tipo='turma').prefetch_related('horarios_aula'),
        'geral': totais(todos),
        'mes_dados': totais(do_mes),
        'mes_rotulo': rotulo_mes(mes_ref.year, mes_ref.month),
        'registros': do_mes,
        'historico': historico,
        'sequencia_atual': atual,
        'maior_sequencia': maior,
        'inicio_controle': config.data_inicio_controle,
        'url_atual': request.get_full_path(),
    }
    return render(request, 'presenca/admin/aluna.html', contexto)


# ---------------------------------------------------------------------------
# Dias sem aula (feriados / recessos)
# ---------------------------------------------------------------------------

@staff_required
def dias_sem_aula(request):
    if request.method == 'POST':
        dia = _data(request.POST.get('data'), None)
        turma_id = _inteiro(request.POST.get('turma'))
        motivo = (request.POST.get('motivo') or '').strip()[:120]
        if dia is None:
            messages.error(request, 'Informe uma data válida.')
        else:
            turma = Turma.objects.filter(pk=turma_id).first() if turma_id else None
            DiaSemAula.objects.get_or_create(data=dia, turma=turma, defaults={'motivo': motivo})
            messages.success(request, f'{dia:%d/%m/%Y} marcado como dia sem aula. Ninguém recebe falta nesse dia.')
        return redirect('admin_dashboard:presenca_dias_sem_aula')

    contexto = {
        'folgas': DiaSemAula.objects.select_related('turma').order_by('-data')[:120],
        'turmas': _turmas_de_aula(),
    }
    return render(request, 'presenca/admin/dias_sem_aula.html', contexto)


@staff_required
@require_POST
def dia_sem_aula_excluir(request, pk):
    folga = get_object_or_404(DiaSemAula, pk=pk)
    folga.delete()
    messages.success(request, 'Dia sem aula removido. As faltas desse dia voltam a valer.')
    return redirect('admin_dashboard:presenca_dias_sem_aula')


# ---------------------------------------------------------------------------
# QR Code + ajustes
# ---------------------------------------------------------------------------

def _url_do_qr(request, config):
    return request.build_absolute_uri(reverse('presenca:marcar', args=[config.token_qr]))


@staff_required
def ajustes(request):
    config = ConfiguracaoPresenca.obter()

    if request.method == 'POST':
        acao = request.POST.get('acao')

        if acao == 'salvar':
            inicio = _data(request.POST.get('data_inicio_controle'), None)
            antes = _inteiro(request.POST.get('minutos_antes'))
            depois = _inteiro(request.POST.get('minutos_depois'))
            if inicio is None or antes is None or depois is None or not (0 <= antes <= 240) or not (0 <= depois <= 240):
                messages.error(request, 'Confira os campos: datas válidas e minutos entre 0 e 240.')
            else:
                config.data_inicio_controle = inicio
                config.minutos_antes = antes
                config.minutos_depois = depois
                config.save()
                messages.success(request, 'Ajustes salvos.')

        elif acao == 'novo_qr':
            config.regenerar_token()
            messages.success(
                request,
                'QR Code novo gerado. O QR Code antigo deixou de funcionar: imprima o novo e troque o da escola.',
            )

        elif acao == 'confirmar_horarios':
            HorarioTurma.objects.filter(preenchido_automaticamente=True).update(preenchido_automaticamente=False)
            messages.success(request, 'Horários conferidos.')

        return redirect('admin_dashboard:presenca_ajustes')

    pendentes, automaticos = _avisos_de_horarios()
    contexto = {
        'config': config,
        'url_qr': _url_do_qr(request, config),
        'turmas_pendentes': pendentes,
        'horarios_automaticos': automaticos,
    }
    return render(request, 'presenca/admin/ajustes.html', contexto)


@staff_required
def qr_png(request):
    import qrcode
    from qrcode.constants import ERROR_CORRECT_M

    config = ConfiguracaoPresenca.obter()
    codigo = qrcode.QRCode(error_correction=ERROR_CORRECT_M, box_size=14, border=3)
    codigo.add_data(_url_do_qr(request, config))
    codigo.make(fit=True)
    imagem = codigo.make_image(fill_color='black', back_color='white')

    buffer = io.BytesIO()
    imagem.save(buffer, format='PNG')
    resposta = HttpResponse(buffer.getvalue(), content_type='image/png')
    resposta['Cache-Control'] = 'no-store'
    if request.GET.get('baixar'):
        resposta['Content-Disposition'] = 'attachment; filename="qrcode-presenca.png"'
    return resposta


@staff_required
def qr_imprimir(request):
    config = ConfiguracaoPresenca.obter()
    return render(request, 'presenca/admin/qr_imprimir.html', {
        'url_qr': _url_do_qr(request, config),
        'minutos_antes': config.minutos_antes,
    })
