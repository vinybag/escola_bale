from django.db import transaction

from .models import MovimentoEstoque, Produto

LIMITE = 1_000_000


def movimentar(produto, tipo, quantidade, *, usuario=None, motivo=''):
    """
    Mexe no estoque e guarda a movimentação.

    entrada: soma; saida/perda/venda: tira (não deixa ficar negativo);
    ajuste: `quantidade` é a contagem certa (o estoque passa a ser esse número).
    Levanta ValueError com mensagem em português quando o pedido não faz sentido.
    """
    if tipo not in dict(MovimentoEstoque.TIPOS):
        raise ValueError('Tipo de movimentação inválido.')

    if not isinstance(quantidade, int) or quantidade < 0 or quantidade > LIMITE:
        raise ValueError('Informe uma quantidade inteira, sem sinal (ex.: 12).')

    if quantidade == 0 and tipo != MovimentoEstoque.AJUSTE:
        raise ValueError('A quantidade precisa ser maior que zero.')

    with transaction.atomic():
        atual = Produto.objects.select_for_update().get(pk=produto.pk)

        if tipo == MovimentoEstoque.ENTRADA:
            variacao = quantidade
        elif tipo == MovimentoEstoque.AJUSTE:
            variacao = quantidade - atual.quantidade
        else:
            variacao = -quantidade

        novo = atual.quantidade + variacao

        if novo < 0:
            raise ValueError(f'Estoque insuficiente: há {atual.quantidade} em estoque.')

        if variacao == 0:
            produto.quantidade = atual.quantidade
            return None

        atual.quantidade = novo
        atual.save(update_fields=['quantidade', 'atualizado_em'])
        movimento = MovimentoEstoque.objects.create(
            produto=atual, tipo=tipo, variacao=variacao, saldo_depois=novo,
            motivo=(motivo or '').strip()[:200], usuario=usuario,
        )

    produto.quantidade = novo
    return movimento
