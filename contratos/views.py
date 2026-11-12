"""Telas da família: ver, preencher, imprimir e assinar o contrato."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import regras, servicos
from .models import Contrato


def _meu_contrato(request, pk):
    contrato = get_object_or_404(
        Contrato.objects.select_related('aluna', 'modelo').defer('scan_arquivo'), pk=pk,
    )

    if not regras.pode_acessar(request.user, contrato):
        raise Http404

    return contrato


def _entregar_pdf(conteudo, nome, inline=True):
    resposta = HttpResponse(conteudo, content_type='application/pdf')
    resposta['Content-Disposition'] = f'{"inline" if inline else "attachment"}; filename="{nome}"'
    # São documentos com dados pessoais: nunca guardar em cache compartilhado.
    resposta['Cache-Control'] = 'private, no-store'

    return resposta


def _ip(request):
    encaminhado = request.META.get('HTTP_X_FORWARDED_FOR', '')

    return (encaminhado.split(',')[0].strip() or request.META.get('REMOTE_ADDR') or '')[:45]


def _valores_iniciais(contrato, user):
    c = (contrato.dados or {}).get('contratante') or {}
    perfil = getattr(user, 'perfil', None)

    def do_perfil(campo):
        return (getattr(perfil, campo, '') or '') if perfil else ''

    informada = ((contrato.dados or {}).get('aluna') or {}).get('data_nascimento')
    cadastro = contrato.aluna.data_nascimento if contrato.aluna else None

    return {
        'nome': c.get('nome') or user.get_full_name() or '',
        'cpf': regras.formatar_cpf(c.get('cpf') or do_perfil('cpf')),
        'rg': c.get('rg') or do_perfil('rg'),
        'endereco': c.get('endereco') or do_perfil('endereco'),
        'telefone': c.get('telefone') or do_perfil('telefone'),
        'data_nascimento': informada or (cadastro.isoformat() if cadastro else ''),
        'nao_autoriza_imagem': bool((contrato.dados or {}).get('nao_autoriza_imagem')),
    }


@login_required
def lista(request):
    user = request.user

    contratos = (
        Contrato.objects
        .filter(Q(aluna__responsavel=user) | Q(aluna__usuario=user) | Q(contratante=user))
        .exclude(status=Contrato.ANULADO)
        .select_related('aluna')
        .defer('pdf_assinado', 'scan_arquivo')
        .distinct()
        .order_by('-ano', 'aluna_nome')
    )

    return render(request, 'contratos/lista.html', {'contratos': contratos})


@login_required
def dados(request, pk):
    contrato = _meu_contrato(request, pk)

    if not contrato.esta_aberto:
        messages.info(request, 'Este contrato já foi concluído.')
        return redirect('contratos:lista')

    valores = _valores_iniciais(contrato, request.user)
    erros = {}

    if request.method == 'POST':
        valores = {
            'nome': request.POST.get('nome', ''),
            'cpf': request.POST.get('cpf', ''),
            'rg': request.POST.get('rg', ''),
            'endereco': request.POST.get('endereco', ''),
            'telefone': request.POST.get('telefone', ''),
            'data_nascimento': request.POST.get('data_nascimento', ''),
            'nao_autoriza_imagem': request.POST.get('nao_autoriza_imagem') == 'on',
        }
        erros = servicos.validar_dados(valores, request.user.email)

        if not erros:
            try:
                servicos.salvar_dados(contrato, request.user, valores)
            except servicos.ContratoIndisponivel as erro:
                messages.error(request, str(erro))
                return redirect('contratos:lista')

            return redirect('contratos:revisar', pk=contrato.pk)

    return render(request, 'contratos/dados.html', {
        'contrato': contrato,
        'valores': valores,
        'erros': erros,
        'email': request.user.email,
        'hoje': timezone.localdate().isoformat(),
    })


@login_required
def revisar(request, pk):
    contrato = _meu_contrato(request, pk)

    if contrato.status not in (Contrato.DADOS, Contrato.AGUARDANDO_PAPEL):
        if contrato.status == Contrato.PENDENTE:
            return redirect('contratos:dados', pk=contrato.pk)

        messages.info(request, 'Este contrato já foi concluído.')
        return redirect('contratos:lista')

    try:
        _, avisos = servicos.preparar_revisao(contrato)
    except (servicos.ContratoIndisponivel, ValueError) as erro:
        messages.error(request, str(erro))
        return redirect('contratos:lista')

    return render(request, 'contratos/revisar.html', {
        'contrato': contrato,
        'dados': contrato.dados.get('contratante', {}),
        'cpf': regras.formatar_cpf(contrato.dados.get('contratante', {}).get('cpf', '')),
        'nascimento': servicos.nascimento_formatado(contrato),
        'nao_autoriza_imagem': contrato.dados.get('nao_autoriza_imagem'),
        'avisos': avisos,
        'email_mascarado': servicos.mascarar_email(request.user.email),
    })


@login_required
def pdf(request, pk, tipo):
    contrato = _meu_contrato(request, pk)

    if tipo == 'assinado':
        if contrato.status != Contrato.ASSINADO_DIGITAL:
            raise Http404

        return _entregar_pdf(
            contrato.pdf_assinado_bytes, f'contrato-assinado-{contrato.ano}.pdf', inline=False,
        )

    if tipo not in ('previa', 'imprimir') or contrato.status not in (Contrato.DADOS, Contrato.AGUARDANDO_PAPEL):
        raise Http404

    try:
        conteudo, _ = servicos.preparar_revisao(contrato)
    except (servicos.ContratoIndisponivel, ValueError) as erro:
        messages.error(request, str(erro))
        return redirect('contratos:lista')

    if tipo == 'imprimir':
        servicos.marcar_impresso(contrato)

    return _entregar_pdf(conteudo, f'contrato-{contrato.ano}.pdf')


@login_required
@require_POST
def enviar_codigo(request, pk):
    contrato = _meu_contrato(request, pk)

    if contrato.status not in (Contrato.DADOS, Contrato.AGUARDANDO_PAPEL):
        raise Http404

    try:
        email = servicos.enviar_codigo(contrato)
    except servicos.ErroAssinatura as erro:
        messages.error(request, str(erro))
        return redirect('contratos:revisar', pk=contrato.pk)

    messages.success(request, f'Enviamos um código de 6 dígitos para {email}.')
    return redirect('contratos:assinar', pk=contrato.pk)


@login_required
def assinar(request, pk):
    contrato = _meu_contrato(request, pk)

    if contrato.status not in (Contrato.DADOS, Contrato.AGUARDANDO_PAPEL):
        messages.info(request, 'Este contrato já foi concluído.')
        return redirect('contratos:lista')

    if request.method == 'POST':
        if request.POST.get('concordo') != 'on':
            messages.error(request, 'Marque a caixa confirmando que você leu e concorda com o contrato.')
        else:
            try:
                servicos.confirmar_assinatura(
                    contrato.pk,
                    request.user,
                    request.POST.get('codigo', ''),
                    _ip(request),
                    request.META.get('HTTP_USER_AGENT', ''),
                )
            except servicos.ErroAssinatura as erro:
                messages.error(request, str(erro))

                if 'atualizado' in str(erro):
                    return redirect('contratos:revisar', pk=contrato.pk)
            except servicos.ContratoIndisponivel as erro:
                messages.error(request, str(erro))
                return redirect('contratos:lista')
            else:
                messages.success(
                    request,
                    'Contrato assinado! Enviamos uma cópia para o seu e-mail e você pode baixá-lo abaixo.',
                )
                return redirect('contratos:lista')

    if not contrato.codigos.filter(usado=False).exists():
        messages.info(request, 'Peça o código de confirmação para assinar.')
        return redirect('contratos:revisar', pk=contrato.pk)

    return render(request, 'contratos/assinar.html', {
        'contrato': contrato,
        'email_mascarado': servicos.mascarar_email(request.user.email),
    })
