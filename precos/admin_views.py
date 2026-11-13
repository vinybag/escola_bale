"""Telas do admin personalizado: Preços e descontos."""

from datetime import date
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from usuarios.models import Aluna, Turma

from . import motor
from .models import (
    Combinacao, CombinacaoItem, CombinacaoPrecoGrupo, Configuracao, GrauParentesco, GrupoDesconto, RegraDesconto,
)
from .motor import Entrada, Familia
from .util import ler_data, ler_decimal


def somente_staff(view):
    @wraps(view)
    @login_required
    def interno(request, *args, **kwargs):
        if not request.user.is_staff:
            return redirect('home')

        return view(request, *args, **kwargs)

    return interno


def _turmas_com_mensalidade():
    return Turma.objects.filter(tipo='turma').order_by('nome')


# ------------------------------------------------------------------ regras

def _situacao(regra, hoje):
    if not regra.ativa:
        return ('desligada', 'Desligada')

    if regra.fim and regra.fim < hoje:
        return ('encerrada', 'Encerrada')

    if regra.inicio and regra.inicio > hoje:
        return ('futura', f'Começa em {regra.inicio:%d/%m/%Y}')

    if regra.fim:
        return ('ativa', f'Ativa até {regra.fim:%d/%m/%Y}')

    return ('ativa', 'Ativa')


@somente_staff
def regras(request):
    hoje = timezone.localdate()
    lista = list(RegraDesconto.objects.select_related('grupo', 'grau').prefetch_related('turmas'))

    for regra in lista:
        regra.situacao_chave, regra.situacao_texto = _situacao(regra, hoje)

    return render(request, 'precos/admin/regras.html', {
        'aba': 'regras',
        'regras': lista,
        'turmas_sem_valor': _turmas_com_mensalidade().filter(valor_mensalidade__isnull=True).count(),
    })


def _valores_da_regra(regra):
    """Valores iniciais do formulário a partir de uma regra existente (ou padrões)."""
    if regra is None:
        return {
            'nome': '', 'ativa': True, 'efeito': RegraDesconto.PERCENTUAL, 'valor': '',
            'incide_em': 'segunda', 'publico': 'todas', 'grupo': '', 'grupos_excecao': [],
            'familia': 'nenhuma', 'grau': '', 'turmas': [], 'inicio': '', 'fim': '',
            'so_turmas_entradas_no_periodo': False, 'substitui_outros': False, 'observacao': '',
        }

    return {
        'nome': regra.nome, 'ativa': regra.ativa, 'efeito': regra.efeito,
        'valor': f'{regra.valor:.2f}'.replace('.', ',').replace(',00', ''),
        'incide_em': regra.incide_em, 'publico': regra.publico,
        'grupo': regra.grupo_id or '', 'grupos_excecao': [g.pk for g in regra.grupos_excecao.all()],
        'familia': regra.familia, 'grau': regra.grau_id or '', 'turmas': [t.pk for t in regra.turmas.all()],
        'inicio': regra.inicio.isoformat() if regra.inicio else '',
        'fim': regra.fim.isoformat() if regra.fim else '',
        'so_turmas_entradas_no_periodo': regra.so_turmas_entradas_no_periodo,
        'substitui_outros': regra.substitui_outros, 'observacao': regra.observacao,
    }


def _valores_do_post(post):
    return {
        'nome': post.get('nome', '').strip(), 'ativa': post.get('ativa') == 'on',
        'efeito': post.get('efeito', ''), 'valor': post.get('valor', '').strip(),
        'incide_em': post.get('incide_em', ''), 'publico': post.get('publico', ''),
        'grupo': post.get('grupo', ''), 'grupos_excecao': [int(x) for x in post.getlist('grupos_excecao') if x.isdigit()],
        'familia': post.get('familia', ''), 'grau': post.get('grau', ''),
        'turmas': [int(x) for x in post.getlist('turmas') if x.isdigit()],
        'inicio': post.get('inicio', '').strip(), 'fim': post.get('fim', '').strip(),
        'so_turmas_entradas_no_periodo': post.get('so_turmas_entradas_no_periodo') == 'on',
        'substitui_outros': post.get('substitui_outros') == 'on', 'observacao': post.get('observacao', '').strip(),
    }


def _validar_regra(v):
    """Valida os valores do formulário. Devolve (dados_limpos, erros)."""
    erros = []
    dados = {}

    if not v['nome']:
        erros.append('Dê um nome para a regra.')

    if v['efeito'] not in dict(RegraDesconto.EFEITOS):
        erros.append('Escolha o efeito da regra.')

    try:
        valor = ler_decimal(v['valor'])
    except ValueError:
        valor = None

    if valor is None or valor <= 0:
        erros.append('Informe um valor maior que zero (ex.: 15 para 15%, ou 50 para R$ 50).')
    elif v['efeito'] == RegraDesconto.PERCENTUAL and valor > 100:
        erros.append('Um desconto em porcentagem não pode passar de 100%.')

    for campo, rotulos in (('incide_em', RegraDesconto.INCIDE_EM), ('publico', RegraDesconto.PUBLICOS), ('familia', RegraDesconto.FAMILIAS)):
        if v[campo] not in dict(rotulos):
            erros.append(f'Escolha uma opção válida em "{campo}".')

    if v['familia'] == 'parentesco' and not str(v['grau']).isdigit():
        erros.append('Escolha qual grau de parentesco vale para esta regra.')

    try:
        inicio, fim = ler_data(v['inicio']), ler_data(v['fim'])
    except ValueError:
        inicio = fim = None
        erros.append('Data inválida.')

    if inicio and fim and fim < inicio:
        erros.append('A data final não pode ser antes da data inicial.')

    if v['so_turmas_entradas_no_periodo'] and not (inicio or fim):
        erros.append('Para valer só para turmas que entraram no período, informe as datas do período.')

    if not erros:
        dados = {
            'nome': v['nome'], 'ativa': v['ativa'], 'efeito': v['efeito'], 'valor': valor,
            'incide_em': v['incide_em'], 'publico': v['publico'],
            'grupo': GrupoDesconto.objects.filter(pk=v['grupo']).first() if str(v['grupo']).isdigit() else None,
            'familia': v['familia'],
            'grau': GrauParentesco.objects.filter(pk=v['grau']).first() if v['familia'] == 'parentesco' and str(v['grau']).isdigit() else None,
            'inicio': inicio, 'fim': fim,
            'so_turmas_entradas_no_periodo': v['so_turmas_entradas_no_periodo'],
            'substitui_outros': v['substitui_outros'], 'observacao': v['observacao'][:300],
        }

    return dados, erros


def _tela_regra(request, regra):
    if request.method == 'POST':
        valores = _valores_do_post(request.POST)
        dados, erros = _validar_regra(valores)

        if not erros:
            if regra is None:
                regra = RegraDesconto.objects.create(**dados)
            else:
                for campo, valor in dados.items():
                    setattr(regra, campo, valor)

                regra.save()

            regra.grupos_excecao.set(GrupoDesconto.objects.filter(pk__in=valores['grupos_excecao']))
            regra.turmas.set(Turma.objects.filter(pk__in=valores['turmas']))
            messages.success(request, f'Regra "{regra.nome}" salva.')
            return redirect('precos_admin:regras')

        for erro in erros:
            messages.error(request, erro)
    else:
        valores = _valores_da_regra(regra)

    return render(request, 'precos/admin/regra_form.html', {
        'aba': 'regras',
        'regra': regra,
        'v': valores,
        'grupos': GrupoDesconto.objects.all(),
        'graus': GrauParentesco.objects.all(),
        'turmas': _turmas_com_mensalidade(),
        'efeitos': RegraDesconto.EFEITOS,
        'incide_em_opcoes': RegraDesconto.INCIDE_EM,
        'publicos': RegraDesconto.PUBLICOS,
        'familias': RegraDesconto.FAMILIAS,
    })


@somente_staff
def regra_nova(request):
    return _tela_regra(request, None)


@somente_staff
def regra_editar(request, pk):
    return _tela_regra(request, get_object_or_404(RegraDesconto, pk=pk))


@somente_staff
@require_POST
def regra_alternar(request, pk):
    regra = get_object_or_404(RegraDesconto, pk=pk)
    regra.ativa = not regra.ativa
    regra.save(update_fields=['ativa'])
    messages.success(request, f'Regra "{regra.nome}" {"ligada" if regra.ativa else "desligada"}.')

    return redirect('precos_admin:regras')


@somente_staff
@require_POST
def regra_excluir(request, pk):
    regra = get_object_or_404(RegraDesconto, pk=pk)
    nome = regra.nome
    regra.delete()
    messages.success(request, f'Regra "{nome}" excluída.')

    return redirect('precos_admin:regras')


# ------------------------------------------------------------- combinações

MAX_ITENS_COMBINACAO = 4


@somente_staff
def combinacoes(request):
    hoje = timezone.localdate()
    lista = list(Combinacao.objects.prefetch_related('itens__turmas', 'itens__precos_grupo__grupo'))

    for combinacao in lista:
        combinacao.situacao_chave, combinacao.situacao_texto = _situacao(combinacao, hoje)

    return render(request, 'precos/admin/combinacoes.html', {'aba': 'combinacoes', 'combinacoes': lista})


def _formulario_da_combinacao(combinacao, grupos):
    """Valores iniciais do formulário a partir de uma combinação existente (ou vazio)."""
    itens = [
        {'n': i, 'nome': '', 'turmas': [], 'preco': ''} for i in range(1, MAX_ITENS_COMBINACAO + 1)
    ]
    especiais = {g.pk: [''] * MAX_ITENS_COMBINACAO for g in grupos}
    valores = {'nome': '', 'ativa': True, 'inicio': '', 'fim': '', 'observacao': ''}

    if combinacao is not None:
        valores.update({
            'nome': combinacao.nome, 'ativa': combinacao.ativa, 'observacao': combinacao.observacao,
            'inicio': combinacao.inicio.isoformat() if combinacao.inicio else '',
            'fim': combinacao.fim.isoformat() if combinacao.fim else '',
        })

        for posicao, item in enumerate(combinacao.itens.all()[:MAX_ITENS_COMBINACAO]):
            itens[posicao].update({
                'nome': item.nome, 'turmas': [t.pk for t in item.turmas.all()],
                'preco': f'{item.preco:.2f}'.replace('.', ',').replace(',00', ''),
            })

            for especial in item.precos_grupo.all():
                if especial.grupo_id in especiais:
                    especiais[especial.grupo_id][posicao] = f'{especial.preco:.2f}'.replace('.', ',').replace(',00', '')

    return valores, itens, especiais


def _ler_combinacao(post, grupos):
    """Lê e valida o formulário. Devolve (valores, itens, especiais, itens_validos, erros)."""
    erros = []
    valores = {
        'nome': post.get('nome', '').strip(), 'ativa': post.get('ativa') == 'on',
        'inicio': post.get('inicio', '').strip(), 'fim': post.get('fim', '').strip(),
        'observacao': post.get('observacao', '').strip()[:300],
    }
    itens = []
    especiais = {g.pk: [''] * MAX_ITENS_COMBINACAO for g in grupos}
    validos = []
    turmas_vistas = set()

    for i in range(1, MAX_ITENS_COMBINACAO + 1):
        item = {
            'n': i, 'nome': post.get(f'item_{i}_nome', '').strip(),
            'turmas': [int(x) for x in post.getlist(f'item_{i}_turmas') if x.isdigit()],
            'preco': post.get(f'item_{i}_preco', '').strip(),
        }
        itens.append(item)

        for g in grupos:
            especiais[g.pk][i - 1] = post.get(f'grupo_{g.pk}_item_{i}', '').strip()

        if not (item['nome'] or item['turmas'] or item['preco']):
            continue

        try:
            preco = ler_decimal(item['preco'])
        except ValueError:
            preco = None

        if not item['turmas']:
            erros.append(f'Item {i}: escolha pelo menos uma turma.')
        elif turmas_vistas & set(item['turmas']):
            erros.append(f'Item {i}: uma turma não pode estar em dois itens da mesma combinação.')

        if preco is None or preco < 0:
            erros.append(f'Item {i}: informe o preço da turma na combinação (ex.: 100).')

        turmas_vistas |= set(item['turmas'])
        validos.append({'n': i, 'nome': item['nome'] or f'Item {i}', 'turmas': item['turmas'], 'preco': preco})

    if not valores['nome']:
        erros.append('Dê um nome para a combinação.')

    if len(validos) < 2:
        erros.append('Uma combinação precisa de pelo menos 2 itens (por exemplo, balé e ginástica).')

    try:
        inicio, fim = ler_data(valores['inicio']), ler_data(valores['fim'])
    except ValueError:
        inicio = fim = None
        erros.append('Data inválida.')

    if inicio and fim and fim < inicio:
        erros.append('A data final não pode ser antes da data inicial.')

    valores['inicio_data'], valores['fim_data'] = inicio, fim

    for g in grupos:
        for i, texto in enumerate(especiais[g.pk], start=1):
            if not texto:
                continue

            try:
                preco = ler_decimal(texto)
            except ValueError:
                preco = None

            if preco is None or preco < 0:
                erros.append(f'Preço do grupo {g.nome} no item {i} é inválido.')

    return valores, itens, especiais, validos, erros


def _tela_combinacao(request, combinacao):
    grupos = list(GrupoDesconto.objects.all())

    if request.method == 'POST':
        valores, itens, especiais, validos, erros = _ler_combinacao(request.POST, grupos)

        if not erros:
            if combinacao is None:
                combinacao = Combinacao()

            combinacao.nome = valores['nome']
            combinacao.ativa = valores['ativa']
            combinacao.inicio = valores['inicio_data']
            combinacao.fim = valores['fim_data']
            combinacao.observacao = valores['observacao']
            combinacao.save()
            combinacao.itens.all().delete()

            for ordem, dados in enumerate(validos):
                item = CombinacaoItem.objects.create(
                    combinacao=combinacao, nome=dados['nome'][:80], preco=dados['preco'], ordem=ordem,
                )
                item.turmas.set(Turma.objects.filter(pk__in=dados['turmas']))

                for g in grupos:
                    texto = especiais[g.pk][dados['n'] - 1]

                    if texto:
                        CombinacaoPrecoGrupo.objects.create(item=item, grupo=g, preco=ler_decimal(texto))

            messages.success(request, f'Combinação "{combinacao.nome}" salva.')
            return redirect('precos_admin:combinacoes')

        for erro in erros:
            messages.error(request, erro)
    else:
        valores, itens, especiais = _formulario_da_combinacao(combinacao, grupos)

    return render(request, 'precos/admin/combinacao_form.html', {
        'aba': 'combinacoes',
        'combinacao': combinacao,
        'v': valores,
        'itens': itens,
        'turmas': _turmas_com_mensalidade(),
        'grupos_precos': [{'grupo': g, 'precos': especiais[g.pk]} for g in grupos],
    })


@somente_staff
def combinacao_nova(request):
    return _tela_combinacao(request, None)


@somente_staff
def combinacao_editar(request, pk):
    return _tela_combinacao(request, get_object_or_404(Combinacao, pk=pk))


@somente_staff
@require_POST
def combinacao_alternar(request, pk):
    combinacao = get_object_or_404(Combinacao, pk=pk)
    combinacao.ativa = not combinacao.ativa
    combinacao.save(update_fields=['ativa'])
    messages.success(request, f'Combinação "{combinacao.nome}" {"ligada" if combinacao.ativa else "desligada"}.')

    return redirect('precos_admin:combinacoes')


@somente_staff
@require_POST
def combinacao_excluir(request, pk):
    combinacao = get_object_or_404(Combinacao, pk=pk)
    nome = combinacao.nome
    combinacao.delete()
    messages.success(request, f'Combinação "{nome}" excluída.')

    return redirect('precos_admin:combinacoes')


# ------------------------------------------------------------------ grupos

@somente_staff
def grupos(request):
    if request.method == 'POST':
        nome = request.POST.get('nome', '').strip()

        if not nome:
            messages.error(request, 'Dê um nome para o grupo.')
        elif GrupoDesconto.objects.filter(nome__iexact=nome).exists():
            messages.error(request, 'Já existe um grupo com esse nome.')
        else:
            grupo = GrupoDesconto.objects.create(nome=nome, descricao=request.POST.get('descricao', '').strip()[:200])
            messages.success(request, f'Grupo "{nome}" criado. Agora escolha quem participa.')
            return redirect('precos_admin:grupo_detalhe', pk=grupo.pk)

        return redirect('precos_admin:grupos')

    return render(request, 'precos/admin/grupos.html', {
        'aba': 'grupos',
        'grupos': GrupoDesconto.objects.annotate(total=Count('alunas', distinct=True), total_regras=Count('regras', distinct=True)),
    })


@somente_staff
def grupo_detalhe(request, pk):
    grupo = get_object_or_404(GrupoDesconto, pk=pk)

    if request.method == 'POST':
        acao = request.POST.get('acao')

        if acao == 'salvar':
            nome = request.POST.get('nome', '').strip()

            if not nome:
                messages.error(request, 'O grupo precisa de um nome.')
            elif GrupoDesconto.objects.filter(nome__iexact=nome).exclude(pk=grupo.pk).exists():
                messages.error(request, 'Já existe um grupo com esse nome.')
            else:
                grupo.nome = nome
                grupo.descricao = request.POST.get('descricao', '').strip()[:200]
                grupo.ativo = request.POST.get('ativo') == 'on'
                grupo.save()
                messages.success(request, 'Grupo salvo.')

        elif acao == 'adicionar':
            ids = [int(x) for x in request.POST.getlist('alunas') if x.isdigit()]
            alunas = Aluna.objects.filter(pk__in=ids)
            grupo.alunas.add(*alunas)
            messages.success(request, f'{alunas.count()} aluna(s) adicionada(s) ao grupo.')

        elif acao == 'remover':
            aluna = Aluna.objects.filter(pk=request.POST.get('aluna')).first()

            if aluna:
                grupo.alunas.remove(aluna)
                messages.success(request, f'{aluna.nome} saiu do grupo.')

        elif acao == 'excluir':
            nome = grupo.nome
            grupo.delete()
            messages.success(request, f'Grupo "{nome}" excluído.')
            return redirect('precos_admin:grupos')

        return redirect('precos_admin:grupo_detalhe', pk=grupo.pk)

    membros = grupo.alunas.order_by('nome')

    return render(request, 'precos/admin/grupo_detalhe.html', {
        'aba': 'grupos',
        'grupo': grupo,
        'membros': membros,
        'candidatas': Aluna.objects.filter(ativa=True).exclude(pk__in=membros.values('pk')).order_by('nome'),
        'regras_do_grupo': grupo.regras.all(),
        'total_precos_combinacao': grupo.precos_combinacao.count(),
    })


# --------------------------------------------------------------- parentescos

@somente_staff
def graus(request):
    if request.method == 'POST':
        acao = request.POST.get('acao')

        if acao == 'criar':
            nome = request.POST.get('nome', '').strip()

            if not nome:
                messages.error(request, 'Informe o nome do grau de parentesco.')
            elif GrauParentesco.objects.filter(nome__iexact=nome).exists():
                messages.error(request, 'Esse grau já existe.')
            else:
                GrauParentesco.objects.create(nome=nome[:60])
                messages.success(request, f'Grau "{nome}" criado.')

        elif acao == 'excluir':
            grau = get_object_or_404(GrauParentesco, pk=request.POST.get('id'))
            nome = grau.nome
            grau.delete()
            messages.success(request, f'Grau "{nome}" excluído.')

        return redirect('precos_admin:graus')

    return render(request, 'precos/admin/graus.html', {
        'aba': 'graus',
        'graus': GrauParentesco.objects.annotate(total_regras=Count('regras')),
    })


# --------------------------------------------------------------- configuração

@somente_staff
def configuracao(request):
    config = Configuracao.atual()

    if request.method == 'POST':
        try:
            passo = ler_decimal(request.POST.get('passo_arredondamento'))
        except ValueError:
            passo = None

        if passo is None or passo <= 0 or passo > 100:
            messages.error(request, 'Informe um valor válido (por exemplo 0,10). Use 0,01 para não arredondar.')
        else:
            config.passo_arredondamento = passo
            config.save()
            messages.success(request, 'Configuração salva.')

        return redirect('precos_admin:configuracao')

    return render(request, 'precos/admin/configuracao.html', {
        'aba': 'configuracao',
        'passo_texto': f'{config.passo_arredondamento:.2f}'.replace('.', ','),
    })


# ------------------------------------------------------------------ simulador

QTD_TURMAS_SIMULADOR = 5


@somente_staff
def simulador(request):
    hoje = timezone.localdate()
    turmas = _turmas_com_mensalidade()
    grupos_ativos = GrupoDesconto.objects.filter(ativo=True)
    graus_lista = GrauParentesco.objects.all()
    resultado = None
    erro = None

    if request.method == 'POST':
        post = request.POST
        entradas = []

        for i in range(1, QTD_TURMAS_SIMULADOR + 1):
            turma = turmas.filter(pk=post.get(f'turma_{i}')).first() if post.get(f'turma_{i}', '').isdigit() else None

            if turma is None:
                continue

            try:
                data = ler_data(post.get(f'data_{i}'))
            except ValueError:
                data = None

            entradas.append(Entrada(turma=turma, data=data, apos_cadastro=post.get(f'apos_{i}') == '1'))

        try:
            quando = ler_data(post.get('quando')) or hoje
        except ValueError:
            quando = hoje
            erro = 'Data inválida: usei a de hoje.'

        familia = Familia(
            irma_anterior=post.get('irma_anterior') == 'on',
            responsavel_aluna=post.get('responsavel_aluna') == 'on',
            graus=frozenset(int(x) for x in post.getlist('graus') if x.isdigit()),
        )
        grupos_escolhidos = {int(x) for x in post.getlist('grupos') if x.isdigit()}
        resultado = motor.calcular(entradas, grupos=grupos_escolhidos, familia=familia, quando=quando)

        escolhido = {
            'turmas': [post.get(f'turma_{i}', '') for i in range(1, QTD_TURMAS_SIMULADOR + 1)],
            'apos': [post.get(f'apos_{i}', '0') for i in range(1, QTD_TURMAS_SIMULADOR + 1)],
            'datas': [post.get(f'data_{i}', '') for i in range(1, QTD_TURMAS_SIMULADOR + 1)],
            'quando': quando.isoformat(), 'grupos': grupos_escolhidos,
            'irma_anterior': familia.irma_anterior, 'responsavel_aluna': familia.responsavel_aluna, 'graus': familia.graus,
        }
    else:
        escolhido = {
            'turmas': [''] * QTD_TURMAS_SIMULADOR, 'apos': ['0'] * QTD_TURMAS_SIMULADOR, 'datas': [''] * QTD_TURMAS_SIMULADOR,
            'quando': hoje.isoformat(), 'grupos': set(), 'irma_anterior': False, 'responsavel_aluna': False, 'graus': frozenset(),
        }

    espacos = [
        {'n': i + 1, 'turma': escolhido['turmas'][i], 'apos': escolhido['apos'][i], 'data': escolhido['datas'][i]}
        for i in range(QTD_TURMAS_SIMULADOR)
    ]

    return render(request, 'precos/admin/simulador.html', {
        'aba': 'simulador',
        'turmas': turmas,
        'grupos': grupos_ativos,
        'graus': graus_lista,
        'espacos': espacos,
        'e': escolhido,
        'resultado': resultado,
        'erro': erro,
    })
