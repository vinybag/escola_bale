"""
Regras de negócio dos contratos (sem nada de PDF aqui).

Marcadores
----------
No PDF-modelo, tudo que aparece como [[NOME]] é um marcador. Eles se dividem em:

* dados da responsável/aluna, preenchidos pelo sistema (NOME_RESPONSAVEL, CPF...);
* assinatura (ASSINATURA, DATA, ASSINATURA_CONTRATADA);
* bolsa (BOLSA_PERCENTUAL, BOLSA_MENSALIDADE_CHEIA, BOLSA_MENSALIDADE_A_PAGAR);
* "campos do ano": qualquer outro nome (ANO, VALOR_MENSALIDADE_1...). O valor é
  digitado pelo admin na tela do modelo. Nomes que começam com VALOR_ são
  dinheiro e saem escritos como "R$ 110,00 (cento e dez reais)".
"""

import re
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

# ------------------------------------------------------------------ marcadores

PESSOAIS = {
    'NOME_RESPONSAVEL',
    'NOME_ALUNA',
    'DATA_NASCIMENTO_ALUNA',
    'CPF',
    'RG',
    'ENDERECO',
    'TELEFONE',
    'EMAIL',
    'AUTORIZACAO_IMAGEM',
}
ASSINATURA = {'DATA', 'ASSINATURA'}
BOLSA = {
    'BOLSA_PERCENTUAL',
    'BOLSA_MENSALIDADE_CHEIA',
    'BOLSA_MENSALIDADE_A_PAGAR',
}
# Tem texto editável no admin (na assinatura digital); na versão impressa vira linha em branco.
TEXTO_CONTRATADA = 'ASSINATURA_CONTRATADA'
TEXTO_CONTRATADA_PADRAO = 'BAILAH CORPO E CIA (Gabriela Sikorski e Vinicius Ferrari)'

BUILTIN = PESSOAIS | ASSINATURA | BOLSA | {TEXTO_CONTRATADA}

OBRIGATORIOS_PADRAO = {
    'NOME_RESPONSAVEL', 'NOME_ALUNA', 'DATA_NASCIMENTO_ALUNA', 'CPF', 'RG', 'ENDERECO',
    'ASSINATURA', 'DATA',
}
OBRIGATORIOS_BOLSISTA = OBRIGATORIOS_PADRAO | BOLSA

# Exemplos do maior valor esperado em cada marcador (para avisar se o espaço for curto).
AMOSTRAS = {
    'NOME_RESPONSAVEL': 'Maria Aparecida de Albuquerque Santos Oliveira',
    'NOME_ALUNA': 'Ana Beatriz de Albuquerque Santos Oliveira',
    'DATA_NASCIMENTO_ALUNA': '00/00/0000',
    'CPF': '000.000.000-00',
    'RG': '00.000.000-0 SSP/SP',
    'ENDERECO': 'Rua das Palmeiras Imperiais, 1234, apto 56, Jardim Primavera, Piedade - SP',
    'TELEFONE': '(00) 00000-0000',
    'EMAIL': 'maria.aparecida.albuquerque@provedor.com.br',
    'DATA': '00/00/0000',
    'ASSINATURA': 'Assinado eletronicamente por Maria Aparecida de Albuquerque Santos Oliveira',
    TEXTO_CONTRATADA: TEXTO_CONTRATADA_PADRAO,
    'AUTORIZACAO_IMAGEM': 'NÃO AUTORIZA o uso da imagem da aluna.',
    'BOLSA_PERCENTUAL': '100%',
    'BOLSA_MENSALIDADE_CHEIA': 'R$ 1.250,00 (mil duzentos e cinquenta reais)',
    'BOLSA_MENSALIDADE_A_PAGAR': 'R$ 1.250,00 (mil duzentos e cinquenta reais)',
}
AMOSTRA_DINHEIRO = 'R$ 125,00 (cento e vinte e cinco reais)'
AMOSTRA_TEXTO = 'Texto do campo'


def categoria_marcador(nome):
    """Devolve 'pessoal', 'assinatura', 'bolsa', 'contratada' ou 'ano'."""
    if nome in PESSOAIS:
        return 'pessoal'
    if nome in ASSINATURA:
        return 'assinatura'
    if nome in BOLSA:
        return 'bolsa'
    if nome == TEXTO_CONTRATADA:
        return 'contratada'
    return 'ano'


def e_dinheiro(nome):
    return categoria_marcador(nome) == 'ano' and nome.startswith('VALOR_')


def amostra_marcador(nome):
    if nome in AMOSTRAS:
        return AMOSTRAS[nome]
    return AMOSTRA_DINHEIRO if e_dinheiro(nome) else AMOSTRA_TEXTO


# ----------------------------------------------------------------------- datas

def interpretar_data(texto):
    """'2015-03-20' ou '20/03/2015' -> date; inválido -> None."""
    t = (texto or '').strip()

    for formato in ('%Y-%m-%d', '%d/%m/%Y'):
        try:
            return datetime.strptime(t, formato).date()
        except ValueError:
            continue

    return None


# ------------------------------------------------------------------------ CPF

def so_digitos(texto):
    return re.sub(r'\D', '', texto or '')


def validar_cpf(cpf):
    """Confere os dígitos verificadores do CPF."""
    d = so_digitos(cpf)

    if len(d) != 11 or d == d[0] * 11:
        return False

    for tamanho in (9, 10):
        soma = sum(int(d[i]) * (tamanho + 1 - i) for i in range(tamanho))
        digito = (soma * 10) % 11 % 10

        if digito != int(d[tamanho]):
            return False

    return True


def formatar_cpf(cpf):
    d = so_digitos(cpf)
    return f'{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}' if len(d) == 11 else (cpf or '')


# -------------------------------------------------------------------- dinheiro

def parse_dinheiro(texto):
    """'110', '110,00', '1.250,50' ou 'R$ 110' -> Decimal; inválido -> None."""
    t = (texto or '').replace('R$', '').strip().replace(' ', '')

    if not t:
        return None

    if ',' in t:
        t = t.replace('.', '').replace(',', '.')
    elif '.' in t and re.fullmatch(r'\d{1,3}(\.\d{3})+', t):
        t = t.replace('.', '')

    try:
        valor = Decimal(t)
    except InvalidOperation:
        return None

    if valor < 0 or not valor.is_finite():
        return None

    return valor.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


_UNIDADES = [
    'zero', 'um', 'dois', 'três', 'quatro', 'cinco', 'seis', 'sete', 'oito', 'nove', 'dez',
    'onze', 'doze', 'treze', 'catorze', 'quinze', 'dezesseis', 'dezessete', 'dezoito', 'dezenove',
]
_DEZENAS = ['', '', 'vinte', 'trinta', 'quarenta', 'cinquenta', 'sessenta', 'setenta', 'oitenta', 'noventa']
_CENTENAS = [
    '', 'cento', 'duzentos', 'trezentos', 'quatrocentos', 'quinhentos',
    'seiscentos', 'setecentos', 'oitocentos', 'novecentos',
]


def _ate_999(n):
    """Número de 1 a 999 por extenso."""
    if n < 20:
        return _UNIDADES[n]

    if n < 100:
        dezena, unidade = divmod(n, 10)
        return _DEZENAS[dezena] + (f' e {_UNIDADES[unidade]}' if unidade else '')

    if n == 100:
        return 'cem'

    centena, resto = divmod(n, 100)

    return _CENTENAS[centena] + (f' e {_ate_999(resto)}' if resto else '')


def _juntar(esquerda, resto):
    """Junta "mil"/"milhão" com o que vem depois: "e" só se o resto for < 100 ou centena exata."""
    if not resto:
        return esquerda

    conector = ' e ' if (resto < 100 or resto % 100 == 0) else ' '

    return esquerda + conector + _extenso(resto)


def _extenso(n):
    """
    Inteiro de 0 a 999.999 por extenso, em português do Brasil.

    Acima disso (nunca acontece numa mensalidade) devolve só os dígitos.
    """
    if n < 1000:
        return _ate_999(n)

    if n < 1_000_000:
        milhares, resto = divmod(n, 1000)
        esquerda = 'mil' if milhares == 1 else f'{_ate_999(milhares)} mil'

        return _juntar(esquerda, resto)

    return str(n)


def dinheiro(valor, com_extenso=True):
    """Decimal -> 'R$ 110,00 (cento e dez reais)'."""
    valor = Decimal(valor).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    reais = int(valor)
    centavos = int((valor - reais) * 100)

    numero = f'R$ {reais:,}'.replace(',', '.') + f',{centavos:02d}'

    if not com_extenso:
        return numero

    partes = []

    if reais or not centavos:
        partes.append(_extenso(reais) + (' real' if reais == 1 else ' reais'))

    if centavos:
        partes.append(_extenso(centavos) + (' centavo' if centavos == 1 else ' centavos'))

    return f"{numero} ({' e '.join(partes)})"


def formatar_percentual(percentual):
    """Decimal('50.00') -> '50%'; Decimal('33.5') -> '33,5%'."""
    p = Decimal(percentual).normalize()
    return format(p, 'f').replace('.', ',') + '%'


def calcular_a_pagar(valor_cheio, percentual):
    """Valor da mensalidade depois da bolsa."""
    cheio = Decimal(valor_cheio)
    desconto = Decimal(percentual)
    return (cheio * (Decimal('100') - desconto) / Decimal('100')).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP,
    )


# ---------------------------------------------------------- modelo / contratante

def bolsa_da_aluna(aluna):
    """BolsaAluna da aluna, ou None se ela não é bolsista."""
    from .models import BolsaAluna

    return BolsaAluna.objects.select_related('opcao').filter(aluna=aluna).first()


def tipo_para_aluna(aluna):
    from .models import ModeloContrato

    if bolsa_da_aluna(aluna):
        return ModeloContrato.TIPO_BOLSISTA

    return ModeloContrato.TIPO_PADRAO


def modelo_ativo(tipo):
    from .models import ModeloContrato

    return (
        ModeloContrato.objects
        .filter(ativo=True, tipo=tipo)
        .order_by('-ano', '-criado_em')
        .first()
    )


def ano_ativo():
    """Ano dos contratos em vigor: o maior ano entre os modelos ativos (ou None)."""
    from django.db.models import Max

    from .models import ModeloContrato

    return ModeloContrato.objects.filter(ativo=True).aggregate(a=Max('ano'))['a']


def contratante_da_aluna(aluna):
    """Quem assina: a aluna adulta (com login) ou a responsável da conta."""
    if aluna.tipo_aluna != 'infantil' and aluna.usuario_id:
        return aluna.usuario

    return aluna.responsavel or aluna.usuario


def pode_acessar(user, contrato):
    """A pessoa pode ver/assinar este contrato? (admin, contratante ou responsável da aluna)"""
    if not user.is_authenticated:
        return False

    if user.is_staff:
        return True

    if contrato.contratante_id == user.id:
        return True

    aluna = contrato.aluna

    return bool(aluna and (aluna.responsavel_id == user.id or aluna.usuario_id == user.id))
