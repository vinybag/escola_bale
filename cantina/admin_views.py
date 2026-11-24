"""Telas do admin personalizado: Cantina."""

from decimal import Decimal
from functools import wraps
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import DecimalField, ExpressionWrapper, F, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from precos.util import ler_decimal

from . import servico
from .models import MovimentoEstoque, Produto

LIMITE_PRECO = Decimal('99999.99')


def somente_staff(view):
    @wraps(view)
    @login_required
    def interno(request, *args, **kwargs):
        if not request.user.is_staff:
            return redirect('home')

        return view(request, *args, **kwargs)

    return interno


def _inteiro(texto, padrao=0):
    texto = (texto or '').strip()

    if not texto:
        return padrao

    if not texto.isdigit():
        raise ValueError(texto)

    return int(texto)


@somente_staff
def lista(request):
    busca = request.GET.get('q', '').strip()
    filtro = request.GET.get('filtro', '')
    produtos = Produto.objects.all()

    if busca:
        produtos = produtos.filter(
            Q(nome__icontains=busca) | Q(categoria__icontains=busca) | Q(codigo_barras__iexact=busca)
        )

    if filtro == 'baixo':
        produtos = [p for p in produtos.filter(ativo=True) if p.situacao_estoque != 'ok']
    elif filtro == 'inativos':
        produtos = produtos.filter(ativo=False)
    else:
        produtos = produtos.filter(ativo=True)

    ativos = Produto.objects.filter(ativo=True)
    valor = ativos.filter(quantidade__gt=0).aggregate(
        total=Sum(ExpressionWrapper(F('preco') * F('quantidade'), output_field=DecimalField(max_digits=14, decimal_places=2)))
    )['total'] or Decimal('0')
    precisam_atencao = sum(1 for p in ativos if p.situacao_estoque != 'ok')

    return render(request, 'cantina/admin/lista.html', {
        'aba': 'produtos', 'produtos': produtos, 'busca': busca, 'filtro': filtro,
        'total_ativos': ativos.count(), 'valor_em_estoque': valor, 'precisam_atencao': precisam_atencao,
    })


@somente_staff
def buscar_codigo(request):
    """O leitor digita o código e dá Enter: abre o produto, ou começa um novo já com o código preenchido."""
    codigo = request.GET.get('codigo', '').strip().replace(' ', '')

    if not codigo:
        return redirect('cantina_admin:lista')

    produto = Produto.objects.filter(codigo_barras=codigo).first()

    if produto:
        return redirect('cantina_admin:editar', pk=produto.pk)

    messages.info(request, f'O código {codigo} ainda não está cadastrado. Preencha os dados do produto.')
    return redirect(_url_novo(codigo))


def _url_novo(codigo):
    return f"{reverse('cantina_admin:novo')}?{urlencode({'codigo': codigo})}"


def _ler_produto(post):
    """Devolve (valores_para_o_formulario, dados_validos, erros)."""
    erros = []
    v = {
        'nome': post.get('nome', '').strip(), 'categoria': post.get('categoria', '').strip(),
        'preco': post.get('preco', '').strip(), 'custo': post.get('custo', '').strip(),
        'quantidade': post.get('quantidade', '').strip(), 'estoque_minimo': post.get('estoque_minimo', '').strip(),
        'codigo_barras': post.get('codigo_barras', '').strip().replace(' ', ''),
        'observacao': post.get('observacao', '').strip(), 'ativo': post.get('ativo', 'on') == 'on',
    }
    dados = {}

    if not v['nome']:
        erros.append('Dê um nome para o produto.')

    try:
        preco = ler_decimal(v['preco'])
    except ValueError:
        preco = None

    if preco is None or preco < 0 or preco > LIMITE_PRECO:
        erros.append('Informe o preço de venda (ex.: 5 ou 5,50).')

    try:
        custo = ler_decimal(v['custo'])
    except ValueError:
        custo = None
        erros.append('O preço de custo é inválido. Deixe em branco se não quiser informar.')

    if custo is not None and (custo < 0 or custo > LIMITE_PRECO):
        erros.append('O preço de custo é inválido.')

    try:
        minimo = _inteiro(v['estoque_minimo'])
        quantidade = _inteiro(v['quantidade'])
    except ValueError:
        minimo = quantidade = 0
        erros.append('Quantidade e estoque mínimo devem ser números inteiros (ex.: 12).')

    if len(v['codigo_barras']) > 64:
        erros.append('O código de barras é muito longo.')

    dados.update({
        'nome': v['nome'][:120], 'categoria': v['categoria'][:60], 'preco': preco, 'custo': custo,
        'estoque_minimo': minimo, 'codigo_barras': v['codigo_barras'] or None,
        'observacao': v['observacao'][:300], 'ativo': v['ativo'], '_quantidade': quantidade,
    })
    return v, dados, erros


def _tela_produto(request, produto):
    if request.method == 'POST':
        valores, dados, erros = _ler_produto(request.POST)
        codigo = dados['codigo_barras']

        if codigo and Produto.objects.filter(codigo_barras=codigo).exclude(pk=produto.pk if produto else None).exists():
            erros.append('Já existe outro produto com este código de barras.')

        if not erros:
            quantidade = dados.pop('_quantidade')

            try:
                with transaction.atomic():
                    if produto is None:
                        produto = Produto.objects.create(quantidade=0, **dados)

                        if quantidade:
                            servico.movimentar(
                                produto, MovimentoEstoque.ENTRADA, quantidade,
                                usuario=request.user, motivo='Estoque inicial',
                            )
                    else:
                        for campo, valor in dados.items():
                            setattr(produto, campo, valor)

                        produto.save()
            except IntegrityError:
                messages.error(request, 'Já existe outro produto com este código de barras.')
            else:
                messages.success(request, f'Produto "{produto.nome}" salvo.')
                return redirect('cantina_admin:lista')

        for erro in erros:
            messages.error(request, erro)
    elif produto is not None:
        valores = {
            'nome': produto.nome, 'categoria': produto.categoria, 'preco': _num(produto.preco),
            'custo': _num(produto.custo), 'quantidade': '', 'estoque_minimo': str(produto.estoque_minimo),
            'codigo_barras': produto.codigo_barras or '', 'observacao': produto.observacao, 'ativo': produto.ativo,
        }
    else:
        valores = {
            'nome': '', 'categoria': '', 'preco': '', 'custo': '', 'quantidade': '', 'estoque_minimo': '0',
            'codigo_barras': request.GET.get('codigo', '').strip(), 'observacao': '', 'ativo': True,
        }

    categorias = Produto.objects.exclude(categoria='').order_by('categoria').values_list('categoria', flat=True).distinct()
    return render(request, 'cantina/admin/produto_form.html', {
        'aba': 'produtos', 'produto': produto, 'v': valores, 'categorias': list(categorias),
        'movimentos': produto.movimentos.select_related('usuario')[:30] if produto else [],
        'tipos': MovimentoEstoque.TIPOS if produto else [],
    })


def _num(valor):
    if valor is None:
        return ''

    return f'{valor:.2f}'.replace('.', ',').replace(',00', '')


@somente_staff
def novo(request):
    return _tela_produto(request, None)


@somente_staff
def editar(request, pk):
    return _tela_produto(request, get_object_or_404(Produto, pk=pk))


@somente_staff
@require_POST
def ajustar(request, pk):
    produto = get_object_or_404(Produto, pk=pk)

    try:
        quantidade = _inteiro(request.POST.get('quantidade'), padrao=None)

        if quantidade is None:
            raise ValueError
    except ValueError:
        messages.error(request, 'Informe uma quantidade inteira, sem sinal (ex.: 12).')
        return redirect('cantina_admin:editar', pk=pk)

    try:
        movimento = servico.movimentar(
            produto, request.POST.get('tipo', ''), quantidade,
            usuario=request.user, motivo=request.POST.get('motivo', ''),
        )
    except ValueError as erro:
        messages.error(request, str(erro))
    else:
        if movimento is None:
            messages.info(request, 'A quantidade já era essa. Nada foi alterado.')
        else:
            messages.success(request, f'Estoque de "{produto.nome}": agora {produto.quantidade}.')

    return redirect('cantina_admin:editar', pk=pk)


@somente_staff
@require_POST
def alternar(request, pk):
    produto = get_object_or_404(Produto, pk=pk)
    produto.ativo = not produto.ativo
    produto.save(update_fields=['ativo', 'atualizado_em'])
    messages.success(request, f'"{produto.nome}" {"voltou para a lista" if produto.ativo else "foi desativado"}.')
    return redirect('cantina_admin:lista')


@somente_staff
@require_POST
def excluir(request, pk):
    produto = get_object_or_404(Produto, pk=pk)
    nome = produto.nome
    produto.delete()
    messages.success(request, f'"{nome}" foi excluído.')
    return redirect('cantina_admin:lista')


@somente_staff
def movimentacoes(request):
    movimentos = MovimentoEstoque.objects.select_related('produto', 'usuario')[:200]
    return render(request, 'cantina/admin/movimentacoes.html', {'aba': 'movimentacoes', 'movimentos': movimentos})
