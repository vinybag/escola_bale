import re
from datetime import date
from decimal import Decimal, InvalidOperation


def ler_decimal(texto):
    """'110', '110,50', 'R$ 1.250,00' ou '15%' -> Decimal; vazio -> None; inválido -> ValueError."""
    t = (texto or '').replace('R$', '').replace('%', '').strip().replace(' ', '')

    if not t:
        return None

    if ',' in t:
        t = t.replace('.', '').replace(',', '.')
    elif re.fullmatch(r'\d{1,3}(\.\d{3})+', t):
        t = t.replace('.', '')

    try:
        valor = Decimal(t)
    except InvalidOperation:
        raise ValueError(texto)

    if not valor.is_finite():
        raise ValueError(texto)

    return valor


def ler_data(texto):
    texto = (texto or '').strip()

    if not texto:
        return None

    try:
        return date.fromisoformat(texto)
    except ValueError:
        raise ValueError(texto)


def ler_preco_da_turma(post):
    """
    Lê os campos de preço do formulário de turma.

    Devolve (valor_mensalidade, regime_preco, erro). `erro` é uma mensagem ou None.
    """
    regimes = {'normal', 'fixo', 'fixo_conta'}
    regime = post.get('regime_preco', 'normal')
    regime = regime if regime in regimes else 'normal'

    try:
        valor = ler_decimal(post.get('valor_mensalidade'))
    except ValueError:
        return None, regime, 'O valor da mensalidade da turma é inválido. Use números, como 110 ou 110,50.'

    if valor is not None and (valor < 0 or valor > Decimal('99999')):
        return None, regime, 'O valor da mensalidade da turma é inválido.'

    return valor, regime, None
