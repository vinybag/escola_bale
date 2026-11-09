"""
Páginas que a aluna / responsável vê depois de escanear o QR Code da escola.

Fluxo:
  /presenca/<token>/
    - sem login  -> /conta/login/?next=/presenca/<token>/ (depois do login volta
                    para cá e a presença já é registrada, sem escanear de novo)
    - com login  -> descobre a aluna (pergunta, se houver mais de uma),
                    descobre a aula (pergunta, se houver mais de uma aberta)
                    e registra.
"""
from hmac import compare_digest

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from .models import ConfiguracaoPresenca
from .services import (
    ESTADO_CRIADA,
    ESTADO_DESMARCADA,
    ESTADO_JA_REGISTRADA,
    alunas_do_usuario,
    aulas_abertas,
    proxima_aula,
    registrar_presenca,
)


def _resultado(request, tipo, **contexto):
    contexto['tipo'] = tipo
    return render(request, 'presenca/resultado.html', contexto)


@login_required
def marcar_presenca(request, token):
    config = ConfiguracaoPresenca.obter()

    # QR Code antigo/errado: a escola pode trocar o código a qualquer momento.
    if not compare_digest(str(token), str(config.token_qr)):
        return _resultado(request, 'qr_invalido')

    agora = timezone.localtime()
    alunas = list(alunas_do_usuario(request.user))
    if not alunas:
        return _resultado(request, 'sem_aluna')

    # 1) Qual aluna? (a própria aluna adulta, ou uma das filhas do responsável)
    aluna = None
    escolhida = request.POST.get('aluna') or request.GET.get('aluna')
    if escolhida:
        # Só aceita quem realmente pertence a esta pessoa (impede trocar o id na URL).
        aluna = next((a for a in alunas if str(a.pk) == str(escolhida)), None)
    elif len(alunas) == 1:
        aluna = alunas[0]

    if aluna is None:
        return render(request, 'presenca/escolher_aluna.html', {'alunas': alunas})

    # 2) Quais aulas estão abertas agora para ela?
    aulas = aulas_abertas(aluna, agora=agora, config=config)
    mais_de_uma_aluna = len(alunas) > 1

    if not aulas:
        return _resultado(
            request, 'fora_da_janela',
            aluna=aluna,
            proxima=proxima_aula(aluna, agora=agora),
            minutos_antes=config.minutos_antes,
            mais_de_uma_aluna=mais_de_uma_aluna,
        )

    # 3) Qual aula? Só pergunta se houver mais de uma aberta.
    if len(aulas) == 1:
        escolhidas = aulas
    elif request.method == 'POST':
        ids = set(request.POST.getlist('aula'))
        escolhidas = [a for a in aulas if str(a.turma.pk) in ids]
        if not escolhidas:
            messages.error(request, 'Marque pelo menos uma aula para registrar a presença.')
    else:
        escolhidas = []

    if not escolhidas:
        if all(a.ja_registrada for a in aulas) and request.method != 'POST':
            return _resultado(
                request, 'ja_registrada', aluna=aluna,
                itens=[{'aula': a, 'estado': ESTADO_JA_REGISTRADA, 'presenca': a.presenca} for a in aulas],
                mais_de_uma_aluna=mais_de_uma_aluna,
            )
        return render(request, 'presenca/escolher_aulas.html', {
            'aluna': aluna,
            'aulas': aulas,
            'mais_de_uma_aluna': mais_de_uma_aluna,
        })

    # 4) Registra.
    itens = []
    for aula in escolhidas:
        presenca, estado = registrar_presenca(
            aluna, aula.turma, agora.date(), request.user, agora=timezone.now(),
        )
        itens.append({'aula': aula, 'estado': estado, 'presenca': presenca})

    if any(i['estado'] == ESTADO_CRIADA for i in itens):
        tipo = 'sucesso'
    elif all(i['estado'] == ESTADO_DESMARCADA for i in itens):
        tipo = 'desmarcada'
    else:
        tipo = 'ja_registrada'

    return _resultado(
        request, tipo, aluna=aluna, itens=itens, mais_de_uma_aluna=mais_de_uma_aluna,
    )
