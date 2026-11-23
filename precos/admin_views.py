"""Telas do admin personalizado: Preços e descontos."""

from datetime import date
from functools import wraps

import logging
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from usuarios.models import Aluna, Turma

from . import motor, servico
from .models import (
    Combinacao, CombinacaoItem, CombinacaoPrecoGrupo, Configuracao, GrauParentesco, GrupoDesconto, PrecoAluna,
    RegraDesconto,
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
            'familia': 'nenhuma', 'grau': '', 'quem_recebe': 'automatico', 'turmas': [], 'inicio': '', 'fim': '',
            'so_turmas_entradas_no_periodo': False, 'substitui_outros': False, 'observacao': '',
            'minimo_integrantes': '2', 'arredondar_total_para': '1', 'familias_desconto': [], 'em_sequencia': False,
        }

    return {
        'nome': regra.nome, 'ativa': regra.ativa, 'efeito': regra.efeito,
        'valor': f'{regra.valor:.2f}'.replace('.', ',').replace(',00', ''),
        'incide_em': regra.incide_em, 'publico': regra.publico,
        'grupo': regra.grupo_id or '', 'grupos_excecao': [g.pk for g in regra.grupos_excecao.all()],
        'familia': regra.familia, 'grau': regra.grau_id or '', 'quem_recebe': regra.quem_recebe,
        'turmas': [t.pk for t in regra.turmas.all()],
        'inicio': regra.inicio.isoformat() if regra.inicio else '',
        'fim': regra.fim.isoformat() if regra.fim else '',
        'so_turmas_entradas_no_periodo': regra.so_turmas_entradas_no_periodo,
        'substitui_outros': regra.substitui_outros, 'observacao': regra.observacao,
        'familias_desconto': [g.pk for g in regra.familias_desconto.all()],
        'em_sequencia': regra.em_sequencia,
        'minimo_integrantes': str(regra.minimo_integrantes),
        'arredondar_total_para': f'{regra.arredondar_total_para:.2f}'.replace('.', ',').replace(',00', ''),
    }


def _valores_do_post(post):
    return {
        'nome': post.get('nome', '').strip(), 'ativa': post.get('ativa') == 'on',
        'efeito': post.get('efeito', ''), 'valor': post.get('valor', '').strip(),
        'incide_em': post.get('incide_em', ''), 'publico': post.get('publico', ''),
        'grupo': post.get('grupo', ''), 'grupos_excecao': [int(x) for x in post.getlist('grupos_excecao') if x.isdigit()],
        'familia': post.get('familia', ''), 'grau': post.get('grau', ''), 'quem_recebe': post.get('quem_recebe', 'automatico'),
        'turmas': [int(x) for x in post.getlist('turmas') if x.isdigit()],
        'inicio': post.get('inicio', '').strip(), 'fim': post.get('fim', '').strip(),
        'so_turmas_entradas_no_periodo': post.get('so_turmas_entradas_no_periodo') == 'on',
        'substitui_outros': post.get('substitui_outros') == 'on', 'observacao': post.get('observacao', '').strip(),
        'familias_desconto': [int(x) for x in post.getlist('familias_desconto') if x.isdigit()],
        'em_sequencia': post.get('em_sequencia') == 'on',
        'minimo_integrantes': post.get('minimo_integrantes', '2').strip(),
        'arredondar_total_para': post.get('arredondar_total_para', '1').strip(),
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

    if v['quem_recebe'] not in dict(RegraDesconto.QUEM_RECEBE):
        erros.append('Escolha quem recebe o desconto de família.')

    minimo, arredondar = 2, Decimal('1')

    if v['familia'] == 'total_grupo_familia':
        if v['efeito'] != RegraDesconto.PERCENTUAL:
            erros.append('O desconto sobre o total do grupo de família é em porcentagem.')

        if not v['familias_desconto']:
            erros.append('Marque para quais famílias vale este desconto.')

        if not str(v['minimo_integrantes']).isdigit() or int(v['minimo_integrantes']) < 2:
            erros.append('O mínimo de integrantes da família deve ser 2 ou mais.')
        else:
            minimo = int(v['minimo_integrantes'])

        try:
            arredondar = ler_decimal(v['arredondar_total_para'])
        except ValueError:
            arredondar = None

        if arredondar is None or arredondar <= 0:
            erros.append('Informe o arredondamento do total (ex.: 1 para reais inteiros, 0,10 para centavos).')
            arredondar = Decimal('1')

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
            'quem_recebe': v['quem_recebe'] if v['familia'] in ('irma_mesma_responsavel', 'parentesco') else 'automatico',
            'grau': GrauParentesco.objects.filter(pk=v['grau']).first() if v['familia'] == 'parentesco' and str(v['grau']).isdigit() else None,
            'minimo_integrantes': minimo, 'arredondar_total_para': arredondar,
            'inicio': inicio, 'fim': fim,
            'so_turmas_entradas_no_periodo': v['so_turmas_entradas_no_periodo'],
            'em_sequencia': v['em_sequencia'] and v['efeito'] == RegraDesconto.PERCENTUAL,
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
            regra.familias_desconto.set(
                GrupoDesconto.objects.filter(pk__in=valores['familias_desconto'], eh_familia=True)
                if regra.familia == 'total_grupo_familia' else [],
            )
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
        'grupos_familia': GrupoDesconto.objects.filter(eh_familia=True),
        'graus': GrauParentesco.objects.all(),
        'turmas': _turmas_com_mensalidade(),
        'efeitos': RegraDesconto.EFEITOS,
        'incide_em_opcoes': RegraDesconto.INCIDE_EM,
        'publicos': RegraDesconto.PUBLICOS,
        'familias': RegraDesconto.FAMILIAS,
        'quem_recebe_opcoes': RegraDesconto.QUEM_RECEBE,
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
        {'n': i, 'nome': '', 'turmas': [], 'preco': '', 'familia': False} for i in range(1, MAX_ITENS_COMBINACAO + 1)
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
                'familia': item.aceita_desconto_familia,
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
            'familia': post.get(f'item_{i}_familia') == 'on',
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
        validos.append({'n': i, 'nome': item['nome'] or f'Item {i}', 'turmas': item['turmas'], 'preco': preco, 'familia': item['familia']})

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
                    aceita_desconto_familia=dados['familia'],
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


def _atualizar_familia_do_grupo(grupo):
    """Grupo de família mudou: deixa gravado o valor de cada integrante (com o desconto sobre o total)."""
    if not (grupo.ativo and grupo.eh_familia):
        return

    primeira = grupo.alunas.filter(ativa=True).first()

    if primeira is not None:
        try:
            servico.atualizar_valores_da_familia(primeira)
        except Exception:
            logger.exception('Grupo de família %s: erro ao atualizar os valores', grupo.pk)


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
                eh_familia = request.POST.get('eh_familia') == 'on'
                representante = User.objects.filter(pk=request.POST.get('representante')).first() if (
                    request.POST.get('representante', '').isdigit()
                ) else None

                if eh_familia and representante is None:
                    messages.error(
                        request, 'Para um grupo de família, escolha o representante (o login que recebe as mensalidades).',
                    )
                    return redirect('precos_admin:grupo_detalhe', pk=grupo.pk)

                grupo.eh_familia = eh_familia
                grupo.representante = representante if eh_familia else None
                grupo.save()
                _atualizar_familia_do_grupo(grupo)
                messages.success(request, 'Grupo salvo.')

        elif acao == 'adicionar':
            ids = [int(x) for x in request.POST.getlist('alunas') if x.isdigit()]
            alunas = Aluna.objects.filter(pk__in=ids)
            grupo.alunas.add(*alunas)
            _atualizar_familia_do_grupo(grupo)
            messages.success(request, f'{alunas.count()} aluna(s) adicionada(s) ao grupo.')

        elif acao == 'remover':
            aluna = Aluna.objects.filter(pk=request.POST.get('aluna')).first()

            if aluna:
                grupo.alunas.remove(aluna)
                _atualizar_familia_do_grupo(grupo)
                servico.atualizar_valores_da_familia(aluna)
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
        'logins': User.objects.filter(is_staff=False).order_by('first_name', 'last_name', 'username'),
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

        graus_marcados = frozenset(int(x) for x in post.getlist('graus') if x.isdigit())
        familia = Familia(
            irma_anterior=post.get('irma_anterior') == 'on',
            tem_irma=post.get('tem_irma') == 'on',
            responsavel_aluna=post.get('responsavel_aluna') == 'on',
            graus=graus_marcados,
            graus_antes=graus_marcados if post.get('parente_antes') == 'on' else frozenset(),
            marcada=post.get('marcada') == 'on',
        )
        grupos_escolhidos = {int(x) for x in post.getlist('grupos') if x.isdigit()}
        resultado = motor.calcular(entradas, grupos=grupos_escolhidos, familia=familia, quando=quando)

        escolhido = {
            'turmas': [post.get(f'turma_{i}', '') for i in range(1, QTD_TURMAS_SIMULADOR + 1)],
            'apos': [post.get(f'apos_{i}', '0') for i in range(1, QTD_TURMAS_SIMULADOR + 1)],
            'datas': [post.get(f'data_{i}', '') for i in range(1, QTD_TURMAS_SIMULADOR + 1)],
            'quando': quando.isoformat(), 'grupos': grupos_escolhidos,
            'irma_anterior': familia.irma_anterior, 'responsavel_aluna': familia.responsavel_aluna, 'graus': familia.graus,
            'tem_irma': familia.tem_irma, 'parente_antes': bool(familia.graus_antes), 'marcada': familia.marcada,
        }
    else:
        escolhido = {
            'turmas': [''] * QTD_TURMAS_SIMULADOR, 'apos': ['0'] * QTD_TURMAS_SIMULADOR, 'datas': [''] * QTD_TURMAS_SIMULADOR,
            'quando': hoje.isoformat(), 'grupos': set(), 'irma_anterior': False, 'responsavel_aluna': False, 'graus': frozenset(),
            'tem_irma': False, 'parente_antes': False, 'marcada': False,
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


# ------------------------------------------------- cálculo na ficha da aluna

@somente_staff
@require_POST
def calcular_aluna(request):
    """
    Cálculo ao vivo da ficha da aluna (não grava nada).

    Recebe o mesmo formulário da ficha e devolve o passo a passo e o total.
    """
    aluna = None

    if request.POST.get('aluna_id', '').isdigit():
        aluna = Aluna.objects.filter(pk=int(request.POST['aluna_id'])).first()

    try:
        quando = ler_data(request.POST.get('quando'))
    except ValueError:
        quando = None

    resultado, dados = servico.calcular_do_formulario(request.POST, aluna, quando=quando)
    atual = aluna.valor_mensalidade if aluna is not None else None
    html = render_to_string('precos/_calculo_resultado.html', {
        'resultado': resultado, 'erros': dados.erros, 'sem_turmas': not dados.entradas,
        'atual': atual, 'tem_aluna': aluna is not None,
    }, request=request)

    return JsonResponse({
        'ok': resultado.ok and not dados.erros,
        'total': f'{resultado.total:.2f}' if resultado.ok else '',
        'html': html,
    })


# ------------------------------------------------------ conferir todas as alunas

logger = logging.getLogger(__name__)


def _linhas_de_conferencia():
    """
    Uma linha por aluna ativa: valor da ficha x valor pelo cálculo.

    Só lê (não grava nada) e carrega tudo de uma vez, para a tela abrir rápido mesmo com muitas
    alunas. Se o cálculo de UMA aluna falhar, a linha mostra o erro e as demais continuam.
    """
    hoje = timezone.localdate()
    contexto = servico.carregar_contexto()
    linhas = []

    alunas = (
        Aluna.objects.filter(ativa=True)
        .select_related('responsavel')
        .prefetch_related('turmas', 'entradas_turma', 'grupos_desconto')
        .order_by('nome')
    )

    for aluna in alunas:
        atual = aluna.valor_mensalidade
        manual = servico.valor_e_manual(aluna)
        turmas = ', '.join(t.nome for t in aluna.turmas.all() if t.tipo == 'turma')
        erro = ''

        try:
            resultado, calculado, _ = servico.calcular_valor(aluna, quando=hoje, contexto=contexto, escrever=False)
            avisos = resultado.avisos
        except Exception as e:  # uma aluna com dado estranho não derruba a tela inteira
            logger.exception('Conferir alunas: erro ao calcular a aluna %s', aluna.pk)
            calculado, avisos, erro = None, [], f'{type(e).__name__}: {e}'

        diferenca = (calculado - atual) if (calculado is not None and atual is not None) else None
        linhas.append({
            'aluna': aluna, 'manual': manual, 'atual': atual, 'calculado': calculado,
            'diferenca': diferenca, 'avisos': avisos, 'erro': erro,
            'igual': diferenca is not None and diferenca == 0,
            'turmas': turmas,
        })

    return linhas


@somente_staff
def conferir(request):
    """Compara, aluna por aluna, o valor da ficha com o valor do cálculo. Não muda nada sozinha."""
    linhas = _linhas_de_conferencia()
    filtro = request.GET.get('ver', 'diferentes')

    if filtro == 'diferentes':
        linhas = [l for l in linhas if not l['igual']]

    return render(request, 'precos/admin/conferir.html', {
        'aba': 'conferir', 'linhas': linhas, 'filtro': filtro,
    })


@somente_staff
@require_POST
def conferir_aplicar(request):
    """Troca para o valor calculado SÓ nas alunas que a dona marcou (e passa a recalcular sozinho)."""
    ids = [int(x) for x in request.POST.getlist('alunas') if x.isdigit()]
    aplicadas = 0
    hoje = timezone.localdate()

    contexto = servico.carregar_contexto()

    for aluna in Aluna.objects.filter(pk__in=ids, ativa=True):
        try:
            resultado, valor, _ = servico.calcular_valor(aluna, quando=hoje, contexto=contexto)
        except Exception:
            logger.exception('Conferir alunas: erro ao aplicar na aluna %s', aluna.pk)
            continue

        if not resultado.ok or valor is None:
            continue

        aluna.valor_mensalidade = valor
        aluna.save(update_fields=['valor_mensalidade'])
        preco, _ = PrecoAluna.objects.get_or_create(aluna=aluna)
        preco.valor_manual = False
        preco.save(update_fields=['valor_manual'])
        aplicadas += 1

    if aplicadas:
        messages.success(request, f'{aplicadas} aluna(s) passaram a usar o valor calculado.')
    else:
        messages.warning(request, 'Nenhuma aluna foi alterada.')

    return redirect('precos_admin:conferir')
