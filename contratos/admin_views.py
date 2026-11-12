"""Telas do admin personalizado: Contratos, Modelos e Opções de bolsa."""

from decimal import Decimal, InvalidOperation
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Exists, OuterRef, Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import regras, servicos
from .models import BolsaAluna, Contrato, ModeloContrato, OpcaoBolsa

ROTULOS_CATEGORIA = {
    'pessoal': 'Dado da responsável/aluna (preenchido pelo sistema)',
    'assinatura': 'Assinatura (preenchida pelo sistema)',
    'bolsa': 'Bolsa (preenchida pelo sistema)',
    'contratada': 'Assinatura da Contratada (texto editável abaixo)',
    'ano': 'Campo do ano (você preenche abaixo)',
}


def somente_staff(view):
    @wraps(view)
    @login_required
    def interno(request, *args, **kwargs):
        if not request.user.is_staff:
            return redirect('home')

        return view(request, *args, **kwargs)

    return interno


def _entregar(conteudo, content_type, nome):
    resposta = HttpResponse(conteudo, content_type=content_type)
    resposta['Content-Disposition'] = f'inline; filename="{nome}"'
    resposta['Cache-Control'] = 'private, no-store'

    return resposta


# ---------------------------------------------------------------- contratos

@somente_staff
def lista(request):
    anos = list(Contrato.objects.order_by('-ano').values_list('ano', flat=True).distinct())
    ano_padrao = regras.ano_ativo() or (anos[0] if anos else None)

    try:
        ano = int(request.GET.get('ano') or ano_padrao or 0) or None
    except ValueError:
        ano = ano_padrao

    status = request.GET.get('status', '')
    tipo = request.GET.get('tipo', '')
    busca = (request.GET.get('q') or '').strip()

    base = (
        Contrato.objects
        .select_related('aluna', 'contratante')
        .defer('pdf_assinado', 'scan_arquivo')
        .annotate(eh_bolsista=Exists(BolsaAluna.objects.filter(aluna=OuterRef('aluna'))))
    )

    if ano:
        base = base.filter(ano=ano)

    contagem = {
        item['status']: item['n'] for item in base.values('status').annotate(n=Count('id'))
    }

    contratos = base

    if status:
        contratos = contratos.filter(status=status)
    else:
        contratos = contratos.exclude(status=Contrato.ANULADO)

    if tipo == 'bolsista':
        contratos = contratos.filter(Q(tipo='bolsista') | Q(tipo='', eh_bolsista=True))
    elif tipo == 'padrao':
        contratos = contratos.filter(Q(tipo='padrao') | Q(tipo='', eh_bolsista=False))

    if busca:
        contratos = contratos.filter(
            Q(aluna_nome__icontains=busca)
            | Q(contratante__first_name__icontains=busca)
            | Q(contratante__last_name__icontains=busca)
            | Q(contratante__email__icontains=busca)
        )

    pagina = Paginator(contratos.order_by('aluna_nome'), 50).get_page(request.GET.get('pagina'))

    resumo = [
        (rotulo, contagem.get(chave, 0), chave)
        for chave, rotulo in Contrato.STATUS
        if chave != Contrato.ANULADO
    ]

    return render(request, 'contratos/admin/lista.html', {
        'aba': 'contratos',
        'pagina': pagina,
        'anos': anos,
        'ano': ano,
        'status': status,
        'tipo': tipo,
        'busca': busca,
        'status_opcoes': Contrato.STATUS,
        'resumo': resumo,
        'total_anulados': contagem.get(Contrato.ANULADO, 0),
        'ano_ativo': regras.ano_ativo(),
        'tem_modelo': ModeloContrato.objects.filter(ativo=True).exists(),
    })


@somente_staff
@require_POST
def gerar_pendentes(request):
    criados, ano, sem_contratante = servicos.gerar_pendentes()

    if ano is None:
        messages.error(
            request,
            'Ative primeiro um modelo de contrato (aba Modelos). Sem modelo ativo não há contrato para gerar.',
        )
    else:
        messages.success(
            request,
            f'{criados} contrato(s) pendente(s) criado(s) para {ano}.'
            if criados else f'Todas as alunas ativas já têm contrato de {ano}.',
        )

        if sem_contratante:
            nomes = ', '.join(a.nome for a in sem_contratante[:8])
            messages.warning(
                request,
                f'{len(sem_contratante)} aluna(s) ficaram de fora por não terem responsável '
                f'nem login cadastrado: {nomes}{"..." if len(sem_contratante) > 8 else ""}.',
            )

    return redirect('contratos_admin:lista')


@somente_staff
@require_POST
def gerar_para_aluna(request, aluna_id):
    from usuarios.models import Aluna

    aluna = get_object_or_404(Aluna, pk=aluna_id)

    if not regras.ano_ativo():
        messages.error(request, 'Ative primeiro um modelo de contrato (aba Modelos).')
    elif not regras.contratante_da_aluna(aluna):
        messages.error(request, 'A aluna não tem responsável nem login cadastrado.')
    elif servicos.criar_contrato_pendente(aluna):
        messages.success(request, f'Contrato pendente criado para {aluna.nome}.')
    else:
        messages.info(request, f'{aluna.nome} já tem contrato neste ano.')

    return redirect('admin_dashboard:aluna_detalhes', pk=aluna.pk)


@somente_staff
def detalhe(request, pk):
    contrato = get_object_or_404(
        Contrato.objects.select_related('aluna', 'modelo', 'contratante', 'scan_enviado_por')
        .defer('pdf_assinado', 'scan_arquivo'),
        pk=pk,
    )

    dados = (contrato.dados or {}).get('contratante', {})
    cadastro = contrato.aluna.data_nascimento if contrato.aluna else None
    informada = regras.interpretar_data(((contrato.dados or {}).get('aluna') or {}).get('data_nascimento'))

    return render(request, 'contratos/admin/detalhe.html', {
        'aba': 'contratos',
        'contrato': contrato,
        'dados': dados,
        'nascimento_informado': informada,
        'nascimento_cadastro': cadastro,
        'nascimento_difere': bool(informada and cadastro and informada != cadastro),
        'cpf': regras.formatar_cpf(dados.get('cpf', '')),
        'nao_autoriza_imagem': (contrato.dados or {}).get('nao_autoriza_imagem'),
        'campos_ano': (contrato.dados or {}).get('campos_ano', {}),
        'pode_scan': contrato.status in (Contrato.PENDENTE, Contrato.DADOS, Contrato.AGUARDANDO_PAPEL, Contrato.ASSINADO_PAPEL),
        'pode_anular': contrato.status != Contrato.ANULADO,
        'tem_dados': bool(dados),
    })


@somente_staff
@require_POST
def acao(request, pk):
    contrato = get_object_or_404(Contrato.objects.defer('pdf_assinado', 'scan_arquivo'), pk=pk)
    qual = request.POST.get('acao')
    origem = request.POST.get('voltar')

    def voltar():
        if origem == 'aluna' and contrato.aluna_id:
            return redirect('admin_dashboard:aluna_detalhes', pk=contrato.aluna_id)

        return redirect('contratos_admin:detalhe', pk=contrato.pk)

    if qual == 'scan':
        arquivo = request.FILES.get('arquivo')

        if not arquivo:
            messages.error(request, 'Escolha o arquivo do contrato assinado.')
            return voltar()

        try:
            servicos.registrar_scan(contrato, arquivo, request.user)
        except ValueError as erro:
            messages.error(request, str(erro))
        else:
            messages.success(request, 'Contrato assinado em papel registrado.')

        return voltar()

    if qual == 'anular':
        if contrato.status == Contrato.ANULADO:
            return voltar()

        motivo = request.POST.get('motivo', '')

        if not motivo.strip():
            messages.error(request, 'Informe o motivo da anulação.')
            return voltar()

        servicos.anular(contrato, motivo)
        messages.success(
            request,
            'Contrato anulado. Se quiser que a família assine outro, gere um novo contrato para a aluna.',
        )
        return voltar()

    messages.error(request, 'Ação inválida.')
    return voltar()


@somente_staff
def download(request, pk, tipo):
    contrato = get_object_or_404(Contrato.objects.select_related('aluna', 'modelo'), pk=pk)

    if tipo == 'assinado' and contrato.status == Contrato.ASSINADO_DIGITAL:
        return _entregar(
            contrato.pdf_assinado_bytes, 'application/pdf', f'contrato-assinado-{contrato.ano}-{contrato.pk}.pdf',
        )

    if tipo == 'scan' and contrato.tem_scan:
        return _entregar(contrato.scan_bytes, contrato.scan_tipo or 'application/octet-stream', contrato.scan_nome)

    if tipo == 'impresso' and contrato.esta_aberto and (contrato.dados or {}).get('contratante'):
        try:
            conteudo, _ = servicos.gerar_pdf(contrato, 'impresso')
        except servicos.ContratoIndisponivel as erro:
            messages.error(request, str(erro))
            return redirect('contratos_admin:detalhe', pk=contrato.pk)

        return _entregar(conteudo, 'application/pdf', f'contrato-{contrato.ano}-{contrato.pk}.pdf')

    raise Http404


# ------------------------------------------------------------------ modelos

@somente_staff
def modelos(request):
    if request.method == 'POST':
        tipo = request.POST.get('tipo')
        arquivo = request.FILES.get('arquivo')
        nome = (request.POST.get('nome') or '').strip()

        try:
            ano = int(request.POST.get('ano') or 0)
        except ValueError:
            ano = 0

        if tipo not in dict(ModeloContrato.TIPOS):
            messages.error(request, 'Escolha o tipo do contrato.')
        elif not 2000 <= ano <= 2100:
            messages.error(request, 'Informe o ano do contrato (ex.: 2026).')
        elif not arquivo:
            messages.error(request, 'Escolha o arquivo PDF do contrato.')
        else:
            nome = nome or f'Contrato {ano}'
            modelo, erro, _ = servicos.criar_modelo(arquivo, tipo, nome, ano, request.user)

            if erro:
                messages.error(request, erro)
            else:
                messages.success(
                    request,
                    'PDF enviado e analisado. Confira os marcadores, preencha os campos do ano e ative o modelo.',
                )
                return redirect('contratos_admin:modelo_detalhe', pk=modelo.pk)

        return redirect('contratos_admin:modelos')

    lista_modelos = ModeloContrato.objects.defer('arquivo_pdf').annotate(total=Count('contratos'))

    return render(request, 'contratos/admin/modelos.html', {
        'aba': 'modelos',
        'modelos': lista_modelos,
        'tipos': ModeloContrato.TIPOS,
        'ano_sugerido': timezone.localdate().year,
    })


def _formatar_valor_para_campo(nome, valor):
    if valor in (None, ''):
        return ''

    if regras.e_dinheiro(nome):
        dec = regras.parse_dinheiro(str(valor))

        return f'{dec:.2f}'.replace('.', ',') if dec is not None else str(valor)

    return str(valor)


@somente_staff
def modelo_detalhe(request, pk):
    modelo = get_object_or_404(ModeloContrato, pk=pk)

    agrupados = {}

    for m in modelo.marcadores:
        agrupados.setdefault(m['nome'], []).append(m)

    campos_editaveis = sorted(
        nome for nome in agrupados
        if regras.categoria_marcador(nome) in ('ano', 'contratada')
    )

    if request.method == 'POST':
        qual = request.POST.get('acao')

        if qual == 'salvar_valores':
            valores = dict(modelo.valores or {})
            erros = []

            for nome in campos_editaveis:
                bruto = (request.POST.get(f'valor_{nome}') or '').strip()

                if not bruto:
                    valores.pop(nome, None)
                elif regras.e_dinheiro(nome):
                    dec = regras.parse_dinheiro(bruto)

                    if dec is None:
                        erros.append(f'"{bruto}" não é um valor válido para {nome}.')
                    else:
                        valores[nome] = f'{dec:.2f}'
                else:
                    valores[nome] = bruto

            modelo.valores = valores
            modelo.save(update_fields=['valores'])

            for erro in erros:
                messages.error(request, erro)

            if not erros:
                messages.success(request, 'Valores salvos.')

        elif qual == 'ativar':
            problemas = servicos.problemas_para_ativar(modelo)

            if problemas:
                for problema in problemas:
                    messages.error(request, problema)
            else:
                servicos.ativar_modelo(modelo)
                messages.success(
                    request,
                    'Modelo ativado. Para as alunas que já existem, use "Gerar contratos pendentes" na aba Contratos.',
                )

        elif qual == 'desativar':
            modelo.ativo = False
            modelo.save(update_fields=['ativo'])
            messages.success(request, 'Modelo desativado.')

        return redirect('contratos_admin:modelo_detalhe', pk=modelo.pk)

    linhas = []

    for nome, itens in sorted(agrupados.items()):
        categoria = regras.categoria_marcador(nome)
        linhas.append({
            'nome': nome,
            'categoria': categoria,
            'rotulo': ROTULOS_CATEGORIA[categoria],
            'ocorrencias': itens,
            'editavel': nome in campos_editaveis,
            'dinheiro': regras.e_dinheiro(nome),
            'valor': _formatar_valor_para_campo(nome, (modelo.valores or {}).get(nome)),
            'padrao': regras.TEXTO_CONTRATADA_PADRAO if nome == regras.TEXTO_CONTRATADA else '',
        })

    try:
        from . import pdf

        avisos_espaco = pdf.avisos_de_espaco(modelo.marcadores)
    except Exception:
        avisos_espaco = []

    return render(request, 'contratos/admin/modelo_detalhe.html', {
        'aba': 'modelos',
        'modelo': modelo,
        'linhas': linhas,
        'tem_editaveis': bool(campos_editaveis),
        'problemas': servicos.problemas_para_ativar(modelo),
        'avisos_espaco': avisos_espaco,
        'total_contratos': modelo.contratos.count(),
    })


@somente_staff
def modelo_pdf(request, pk):
    modelo = get_object_or_404(ModeloContrato, pk=pk)

    return _entregar(modelo.pdf_bytes, 'application/pdf', modelo.nome_arquivo or f'modelo-{modelo.pk}.pdf')


# -------------------------------------------------------------------- bolsas

def _parse_percentual(texto):
    try:
        valor = Decimal((texto or '').replace('%', '').replace(',', '.').strip())
    except InvalidOperation:
        return None

    if not Decimal('0') < valor <= Decimal('100'):
        return None

    return valor.quantize(Decimal('0.01'))


@somente_staff
def bolsas(request):
    if request.method == 'POST':
        qual = request.POST.get('acao')
        nome = (request.POST.get('nome') or '').strip()
        percentual = _parse_percentual(request.POST.get('percentual'))

        if qual == 'criar':
            if not nome:
                messages.error(request, 'Informe o nome da bolsa.')
            elif percentual is None:
                messages.error(request, 'Informe um percentual entre 0,01 e 100.')
            else:
                OpcaoBolsa.objects.create(nome=nome, percentual=percentual)
                messages.success(request, 'Opção de bolsa criada.')

        elif qual == 'editar':
            opcao = get_object_or_404(OpcaoBolsa, pk=request.POST.get('id'))

            if not nome or percentual is None:
                messages.error(request, 'Informe o nome e um percentual entre 0,01 e 100.')
            else:
                opcao.nome = nome
                opcao.percentual = percentual
                opcao.save()
                messages.success(
                    request,
                    'Opção atualizada. Contratos já assinados não mudam; os pendentes passam a usar o novo percentual.',
                )

        elif qual == 'alternar':
            opcao = get_object_or_404(OpcaoBolsa, pk=request.POST.get('id'))
            opcao.ativa = not opcao.ativa
            opcao.save(update_fields=['ativa'])
            messages.success(request, 'Opção ativada.' if opcao.ativa else 'Opção desativada.')

        return redirect('contratos_admin:bolsas')

    return render(request, 'contratos/admin/bolsas.html', {
        'aba': 'bolsas',
        'opcoes': OpcaoBolsa.objects.annotate(total=Count('bolsistas')),
    })
