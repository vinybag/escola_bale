"""
Motor de cálculo da mensalidade.

Não grava nada no banco: recebe as turmas da aluna NA ORDEM EM QUE ELA ENTROU e
devolve o passo a passo. As regras vêm da tela "Preços e descontos" (nada fixo aqui).

Como o cálculo funciona
-----------------------
Para cada turma, em ordem:
  1. A turma recebe uma posição (1ª, 2ª, 3ª...). Turmas de preço fixo não contam, a menos
     que a turma esteja configurada como "preço fixo, mas conta como modalidade".
  2. Vale cada regra ativa que se aplica: posição, período, turma, grupo, parentesco e se
     a aluna "já era aluna" quando entrou naquela turma.
  3. Os PERCENTUAIS são SOMADOS, cada um sobre o valor cheio da turma.
  4. Uma regra de preço fixo (campanha) troca o preço da turma; se ela "substitui outros",
     nenhum outro desconto é aplicado naquela turma.
  5. COMBINAÇÕES: se a aluna faz, ao mesmo tempo, uma turma de cada "item" de uma combinação
     (ex.: balé + ginástica), cada turma passa a ter o preço da combinação (ou o preço do
     grupo dela). Em qualquer ordem de entrada. O conjunto conta como UMA modalidade e nenhum
     outro desconto soma nessas turmas.
O total é arredondado PARA BAIXO em múltiplos do passo configurado (padrão: R$ 0,10).
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_FLOOR, Decimal

from django.utils import timezone

from .models import Combinacao, Configuracao, RegraDesconto

ZERO = Decimal('0')
CEM = Decimal('100')


@dataclass
class Entrada:
    """Uma turma da aluna, na ordem de entrada."""

    turma: object
    data: date | None = None
    # True = a aluna já era aluna quando entrou nesta turma (entrou depois do primeiro cadastro).
    apos_cadastro: bool = False


@dataclass
class Familia:
    """O que o sistema sabe sobre a família da aluna (preenchido por quem chama o motor)."""

    irma_anterior: bool = False       # tem irmã (mesma responsável) que entrou antes
    responsavel_aluna: bool = False   # é responsável por alguma aluna
    graus: frozenset = frozenset()    # graus de parentesco em que ela recebe desconto


@dataclass
class LinhaDesconto:
    regra_id: int
    nome: str
    tipo: str          # 'percentual' ou 'preco_fixo'
    percentual: Decimal | None
    valor: Decimal     # quanto sai do preço da turma (positivo)


@dataclass
class LinhaTurma:
    turma_id: int
    nome: str
    posicao: int | None
    preco_cheio: Decimal | None
    preco_base: Decimal | None     # depois de uma regra de preço fixo
    descontos: list = field(default_factory=list)
    final: Decimal = ZERO
    sem_descontos: bool = False
    combinacao: str | None = None


@dataclass
class Resultado:
    ok: bool
    linhas: list
    total_exato: Decimal
    total: Decimal
    ajuste_arredondamento: Decimal
    avisos: list


def _esta_no_periodo(regra, dia):
    if regra.inicio and dia < regra.inicio:
        return False

    if regra.fim and dia > regra.fim:
        return False

    return True


def _posicao_confere(incide_em, posicao):
    return {
        'primeira': posicao == 1,
        'segunda': posicao == 2,
        'terceira': posicao == 3,
        'segunda_em_diante': posicao >= 2,
        'terceira_em_diante': posicao >= 3,
        'todas': True,
    }[incide_em]


def _regra_se_aplica(regra, entrada, posicao, grupos, familia, quando):
    if not regra.ativa or not _esta_no_periodo(regra, quando):
        return False

    if not _posicao_confere(regra.incide_em, posicao):
        return False

    turmas_da_regra = {t.pk for t in regra.turmas.all()}

    if turmas_da_regra and entrada.turma.pk not in turmas_da_regra:
        return False

    if regra.publico == 'ja_aluna' and not entrada.apos_cadastro:
        return False

    if regra.publico == 'nova' and entrada.apos_cadastro:
        return False

    if regra.so_turmas_entradas_no_periodo:
        if entrada.data is None or not _esta_no_periodo(regra, entrada.data):
            return False

    if regra.grupo_id and regra.grupo_id not in grupos:
        return False

    if {g.pk for g in regra.grupos_excecao.all()} & grupos:
        return False

    if regra.familia == 'irma_mesma_responsavel' and not familia.irma_anterior:
        return False

    if regra.familia == 'responsavel_aluna' and not familia.responsavel_aluna:
        return False

    if regra.familia == 'parentesco' and regra.grau_id not in familia.graus:
        return False

    return True


def _arredondar_para_baixo(valor, passo):
    if not passo or passo <= 0:
        return valor.quantize(Decimal('0.01'), rounding=ROUND_FLOOR)

    return (valor / passo).to_integral_value(rounding=ROUND_FLOOR) * passo


def combinacoes_ativas():
    return list(Combinacao.objects.filter(ativa=True).prefetch_related('itens__turmas', 'itens__precos_grupo'))


def _casar_combinacoes(entradas, grupos, quando, combinacoes):
    """
    Descobre quais turmas da aluna entram em combinações.

    Devolve {posição da entrada: (combinação, preço da turma, número da combinação)}.
    Cada turma só entra em uma combinação; vale a combinação com mais itens primeiro.
    """
    usadas = {}
    numero = 0

    for combinacao in sorted(combinacoes, key=lambda c: (-len(c.itens.all()), c.pk)):
        itens = list(combinacao.itens.all())

        if not combinacao.ativa or not _esta_no_periodo(combinacao, quando) or len(itens) < 2:
            continue

        escolhidas = []

        for item in itens:
            ids = {t.pk for t in item.turmas.all()}
            ja_escolhidas = {i for i, _ in escolhidas}
            achada = next(
                (
                    i for i, e in enumerate(entradas)
                    if i not in usadas and i not in ja_escolhidas
                    and e.turma.pk in ids
                    and e.turma.regime_preco == 'normal'
                    and e.turma.valor_mensalidade is not None
                ),
                None,
            )

            if achada is None:
                escolhidas = []
                break

            escolhidas.append((achada, item))

        if not escolhidas:
            continue

        numero += 1

        for posicao_da_entrada, item in escolhidas:
            do_grupo = [p.preco for p in item.precos_grupo.all() if p.grupo_id in grupos]
            usadas[posicao_da_entrada] = (combinacao, min(do_grupo) if do_grupo else item.preco, numero)

    return usadas


def regras_ativas():
    return list(
        RegraDesconto.objects.filter(ativa=True)
        .select_related('grupo', 'grau')
        .prefetch_related('turmas', 'grupos_excecao')
    )


def calcular(entradas, *, grupos=(), familia=None, quando=None, regras=None, passo=None, combinacoes=None):
    """
    entradas: lista de Entrada, na ordem em que a aluna entrou nas turmas.
    grupos:   ids dos grupos de desconto (ativos) a que a aluna pertence.
    familia:  Familia (parentescos que dão desconto a ela).
    quando:   dia para o qual calcular (padrão: hoje). Regras fora do período não valem.
    """
    quando = quando or timezone.localdate()
    familia = familia or Familia()
    grupos = set(grupos)
    regras = regras_ativas() if regras is None else list(regras)
    passo = Configuracao.atual().passo_arredondamento if passo is None else passo
    combinacoes = combinacoes_ativas() if combinacoes is None else list(combinacoes)
    em_combinacao = _casar_combinacoes(list(entradas), grupos, quando, combinacoes)
    posicao_da_combinacao = {}

    linhas = []
    avisos = []
    posicao = 0

    for indice, entrada in enumerate(entradas):
        turma = entrada.turma
        preco = turma.valor_mensalidade
        conta = turma.regime_preco in ('normal', 'fixo_conta')

        if indice in em_combinacao:
            combinacao, preco_combinacao, numero = em_combinacao[indice]

            if numero not in posicao_da_combinacao:
                posicao += 1  # a combinação inteira conta como UMA modalidade
                posicao_da_combinacao[numero] = posicao

            linha = LinhaTurma(
                turma_id=turma.pk, nome=turma.nome, posicao=posicao_da_combinacao[numero],
                preco_cheio=preco, preco_base=preco_combinacao, final=preco_combinacao,
                combinacao=combinacao.nome,
            )
            linha.descontos.append(LinhaDesconto(
                regra_id=combinacao.pk, nome=f'Combinação: {combinacao.nome}', tipo='combinacao',
                percentual=None, valor=preco - preco_combinacao,
            ))
            linhas.append(linha)
            continue

        if conta:
            posicao += 1

        linha = LinhaTurma(
            turma_id=turma.pk,
            nome=turma.nome,
            posicao=posicao if conta else None,
            preco_cheio=preco,
            preco_base=preco,
            sem_descontos=turma.regime_preco != 'normal',
        )

        if preco is None:
            avisos.append(f'A turma "{turma.nome}" ainda não tem valor de mensalidade cadastrado.')
            linhas.append(linha)
            continue

        linha.final = preco

        if turma.regime_preco == 'normal':
            aplicaveis = [
                r for r in regras
                if _regra_se_aplica(r, entrada, posicao, grupos, familia, quando)
            ]
            fixas = [r for r in aplicaveis if r.efeito == RegraDesconto.PRECO_FIXO]
            percentuais = [r for r in aplicaveis if r.efeito == RegraDesconto.PERCENTUAL]
            base = preco

            if fixas:
                escolhida = min(fixas, key=lambda r: r.valor)
                base = escolhida.valor
                linha.preco_base = base
                linha.descontos.append(LinhaDesconto(
                    regra_id=escolhida.pk, nome=escolhida.nome, tipo=RegraDesconto.PRECO_FIXO,
                    percentual=None, valor=preco - base,
                ))

                if escolhida.substitui_outros:
                    percentuais = []

            for regra in percentuais:
                linha.descontos.append(LinhaDesconto(
                    regra_id=regra.pk, nome=regra.nome, tipo=RegraDesconto.PERCENTUAL,
                    percentual=regra.valor, valor=base * regra.valor / CEM,
                ))

            descontos_percentuais = sum(
                (d.valor for d in linha.descontos if d.tipo == RegraDesconto.PERCENTUAL), ZERO,
            )
            linha.final = max(ZERO, base - descontos_percentuais)

        linhas.append(linha)

    if not linhas:
        avisos.append('Nenhuma turma informada.')

    total_exato = sum((linha.final for linha in linhas), ZERO)
    total = _arredondar_para_baixo(total_exato, passo)

    return Resultado(
        ok=bool(linhas) and not avisos,
        linhas=linhas,
        total_exato=total_exato,
        total=total,
        ajuste_arredondamento=total_exato - total,
        avisos=avisos,
    )
