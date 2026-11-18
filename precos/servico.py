"""
Cálculo da mensalidade de uma aluna de verdade (liga o motor aos dados do sistema).

Nada aqui muda as alunas antigas sozinho: sem registro em `PrecoAluna` o valor é MANUAL.
"""

from dataclasses import dataclass, field
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone

from usuarios.models import Aluna, Turma

from . import motor
from .models import EntradaTurma, GrauParentesco, LigacaoFamiliar, PrecoAluna
from .motor import Entrada, Familia
from .util import ler_data

SEM_PK = 10 ** 12  # aluna ainda não gravada: conta como a mais nova de todas


# ------------------------------------------------------------------ leitura

def valor_e_manual(aluna):
    """True se a aluna usa o valor digitado (padrão das alunas antigas)."""
    preco = PrecoAluna.objects.filter(aluna=aluna).first()
    return True if preco is None else preco.valor_manual


def marcada_para_receber(aluna):
    preco = PrecoAluna.objects.filter(aluna=aluna).first()
    return bool(preco and preco.recebe_desconto_familiar)


def garantir_entradas(aluna):
    """Cria as entradas que faltam (alunas antigas) com a data da matrícula e tira as que sobraram."""
    turmas_ids = set(aluna.turmas.values_list('pk', flat=True))
    existentes = set(EntradaTurma.objects.filter(aluna=aluna).values_list('turma_id', flat=True))

    for turma in Turma.objects.filter(pk__in=turmas_ids - existentes).order_by('-valor_mensalidade', 'nome'):
        EntradaTurma.objects.create(aluna=aluna, turma=turma, data_entrada=aluna.data_matricula or timezone.localdate())

    EntradaTurma.objects.filter(aluna=aluna).exclude(turma_id__in=turmas_ids).delete()


def entradas_da_aluna(aluna):
    """Entradas gravadas da aluna, na ordem em que ela entrou."""
    garantir_entradas(aluna)
    entradas = EntradaTurma.objects.filter(aluna=aluna, turma__tipo='turma').select_related('turma')

    return [
        Entrada(turma=e.turma, data=e.data_entrada, apos_cadastro=e.data_entrada > aluna.data_matricula)
        for e in entradas
    ]


def grupos_da_aluna(aluna):
    if aluna is None or aluna.pk is None:
        return set()

    return set(aluna.grupos_desconto.filter(ativo=True).values_list('pk', flat=True))


def _chave(aluna_ou_none, data_matricula=None):
    """Chave para saber quem entrou antes na escola: (data da matrícula, número)."""
    if aluna_ou_none is None:
        return (data_matricula or timezone.localdate(), SEM_PK)

    return (aluna_ou_none.data_matricula, aluna_ou_none.pk)


def montar_familia(*, aluna=None, responsavel_id=None, usuario_id=None, ligacoes=None, marcada=False):
    """
    O que o motor precisa saber da família.

    aluna: a aluna já gravada (ou None numa aluna nova).
    ligacoes: lista de (parente_id, grau_id) a usar no lugar das gravadas (formulário ainda não salvo).
    """
    minha = _chave(aluna)
    meu_pk = aluna.pk if aluna is not None else None

    if responsavel_id is None and aluna is not None:
        responsavel_id = aluna.responsavel_id

    if usuario_id is None and aluna is not None:
        usuario_id = aluna.usuario_id

    irmas = (
        Aluna.objects.filter(responsavel_id=responsavel_id, ativa=True).exclude(pk=meu_pk)
        if responsavel_id else Aluna.objects.none()
    )
    irmas = list(irmas)
    irma_anterior = any(_chave(i) < minha for i in irmas)

    responsavel_aluna = bool(usuario_id and Aluna.objects.filter(responsavel_id=usuario_id).exists())

    # parentescos: os marcados nesta ficha (ou no formulário) e os marcados na ficha da parente
    pares = []

    if ligacoes is not None:
        pares.extend((int(p), int(g)) for p, g in ligacoes)
    elif meu_pk:
        pares.extend(LigacaoFamiliar.objects.filter(aluna_id=meu_pk).values_list('parente_id', 'grau_id'))

    if meu_pk:
        pares.extend(LigacaoFamiliar.objects.filter(parente_id=meu_pk).values_list('aluna_id', 'grau_id'))

    parentes = {a.pk: a for a in Aluna.objects.filter(pk__in={p for p, _ in pares}, ativa=True)}
    graus = set()
    graus_antes = set()

    for parente_id, grau_id in pares:
        parente = parentes.get(parente_id)

        if parente is None:
            continue

        graus.add(grau_id)

        if _chave(parente) < minha:
            graus_antes.add(grau_id)

    return Familia(
        irma_anterior=irma_anterior, tem_irma=bool(irmas), responsavel_aluna=responsavel_aluna,
        graus=frozenset(graus), graus_antes=frozenset(graus_antes), marcada=bool(marcada),
    )


def calcular_para_aluna(aluna, quando=None):
    """Cálculo da aluna gravada, com os dados que estão no banco."""
    return motor.calcular(
        entradas_da_aluna(aluna),
        grupos=grupos_da_aluna(aluna),
        familia=montar_familia(aluna=aluna, marcada=marcada_para_receber(aluna)),
        quando=quando,
    )


def valor_para_mes(aluna, mes_referencia):
    """
    Valor a cobrar da aluna no mês. Manual (ou cálculo impossível): o valor da ficha.
    Calculado: o cálculo para aquele mês (campanhas valem só dentro do período).
    """
    if valor_e_manual(aluna):
        return aluna.valor_mensalidade

    resultado = calcular_para_aluna(aluna, quando=mes_referencia)

    if not resultado.ok:
        return aluna.valor_mensalidade

    return resultado.total


def valor_para_cobrar(aluna, mes_referencia):
    """Como `valor_para_mes`, mas já deixa a ficha da aluna igual ao valor que vai ser cobrado."""
    valor = valor_para_mes(aluna, mes_referencia)

    if valor is not None and not valor_e_manual(aluna) and aluna.valor_mensalidade != valor:
        aluna.valor_mensalidade = valor
        aluna.save(update_fields=['valor_mensalidade'])

    return valor


# --------------------------------------------------------------- formulário

@dataclass
class DadosFormulario:
    """Tudo que a ficha da aluna informa sobre o cálculo."""

    turmas: list = field(default_factory=list)        # Turma, na ordem de entrada
    entradas: list = field(default_factory=list)      # Entrada, na ordem de entrada
    datas: dict = field(default_factory=dict)         # turma_id -> data de entrada
    ordens: dict = field(default_factory=dict)        # turma_id -> ordem
    ligacoes: list = field(default_factory=list)      # (parente_id, grau_id)
    manual: bool = False
    marcada: bool = False
    responsavel_id: int | None = None
    usuario_id: int | None = None
    erros: list = field(default_factory=list)


def _inteiro(texto):
    texto = (texto or '').strip()
    return int(texto) if texto.isdigit() else None


def ler_formulario(post, aluna=None):
    """
    Lê da ficha: turmas, ordem/data de entrada, parentes, "valor manual" e "marcada".

    Para uma aluna já gravada, turmas que ela já tinha mantêm a data de entrada gravada;
    turmas novas entram hoje (depois do cadastro = "já era aluna").
    """
    dados = DadosFormulario()
    hoje = timezone.localdate()
    ids = [i for i in (_inteiro(x) for x in post.getlist('turmas')) if i]
    turmas = {t.pk: t for t in Turma.objects.filter(pk__in=ids, ativa=True)}
    gravadas = {}

    if aluna is not None and aluna.pk:
        garantir_entradas(aluna)
        gravadas = {e.turma_id: e for e in EntradaTurma.objects.filter(aluna=aluna)}

    linhas = []

    for turma_id in ids:
        turma = turmas.get(turma_id)

        if turma is None or any(l[0].pk == turma_id for l in linhas):
            continue

        atual = gravadas.get(turma_id)

        try:
            digitada = ler_data(post.get(f'entrada_data_{turma_id}'))
        except ValueError:
            digitada = None
            dados.erros.append(f'Data de entrada inválida em "{turma.nome}".')

        if digitada is not None:
            data = digitada
        elif atual is not None:
            data = atual.data_entrada
        else:
            data = hoje

        ordem = _inteiro(post.get(f'entrada_ordem_{turma_id}'))

        if ordem is None:
            ordem = atual.ordem if atual is not None else None

        linhas.append((turma, data, ordem))

    # Sem ordem informada: a turma mais cara conta primeiro (o desconto cai na mais barata).
    sem_ordem = sorted(
        (l for l in linhas if l[2] is None), key=lambda l: (-(l[0].valor_mensalidade or Decimal('0')), l[0].nome),
    )
    proxima = max([l[2] for l in linhas if l[2] is not None] + [0])
    ordem_padrao = {}

    for turma, _, _ in sem_ordem:
        proxima += 1
        ordem_padrao[turma.pk] = proxima

    linhas = [(t, d, o if o is not None else ordem_padrao[t.pk]) for t, d, o in linhas]
    linhas.sort(key=lambda l: (l[1], l[2], l[0].nome))

    matricula = aluna.data_matricula if aluna is not None and aluna.pk else hoje

    for turma, data, ordem in linhas:
        dados.turmas.append(turma)
        dados.datas[turma.pk] = data
        dados.ordens[turma.pk] = ordem

        if turma.tipo == 'turma':
            dados.entradas.append(Entrada(turma=turma, data=data, apos_cadastro=data > matricula))

    parentes = post.getlist('lig_parente')
    graus = post.getlist('lig_grau')
    vistos = set()

    for parente, grau in zip(parentes, graus):
        parente_id, grau_id = _inteiro(parente), _inteiro(grau)

        if not parente_id or not grau_id or (parente_id, grau_id) in vistos:
            continue

        if aluna is not None and aluna.pk == parente_id:
            dados.erros.append('Uma aluna não pode ser parente dela mesma.')
            continue

        vistos.add((parente_id, grau_id))
        dados.ligacoes.append((parente_id, grau_id))

    dados.ligacoes = [
        (p, g) for p, g in dados.ligacoes
        if Aluna.objects.filter(pk=p).exists() and GrauParentesco.objects.filter(pk=g).exists()
    ]

    if aluna is not None and aluna.pk:
        # parentes marcados na ficha da outra aluna continuam valendo; não duplica
        dados.ligacoes = [
            (p, g) for p, g in dados.ligacoes
            if not LigacaoFamiliar.objects.filter(aluna_id=p, parente_id=aluna.pk, grau_id=g).exists()
        ]

    dados.manual = post.get('valor_manual') == 'on'
    dados.marcada = post.get('recebe_desconto_familiar') == 'on'
    dados.responsavel_id = _inteiro(post.get('responsavel'))
    dados.usuario_id = _inteiro(post.get('usuario'))

    return dados


def calcular_do_formulario(post, aluna=None, quando=None):
    """Cálculo com o que está na ficha (ainda sem salvar). Devolve (Resultado, DadosFormulario)."""
    dados = ler_formulario(post, aluna)
    tipo = post.get('tipo_aluna') or (aluna.tipo_aluna if aluna is not None else 'infantil')
    familia = montar_familia(
        aluna=aluna if aluna is not None and aluna.pk else None,
        responsavel_id=dados.responsavel_id if tipo == 'infantil' else None,
        usuario_id=dados.usuario_id if tipo == 'adulto' else None,
        ligacoes=dados.ligacoes,
        marcada=dados.marcada,
    )

    grupos = grupos_da_aluna(aluna if aluna is not None and aluna.pk else None)
    resultado = motor.calcular(dados.entradas, grupos=grupos, familia=familia, quando=quando)

    return resultado, dados


def salvar_formulario(aluna, dados, *, valor=None):
    """
    Grava o que a ficha informou: data/ordem de entrada, parentes, "manual" e "marcada".

    Chame DEPOIS de gravar as turmas da aluna. `valor`: se vier, vira o valor da mensalidade.
    """
    garantir_entradas(aluna)

    for turma_id, data in dados.datas.items():
        EntradaTurma.objects.filter(aluna=aluna, turma_id=turma_id).update(
            data_entrada=data, ordem=dados.ordens.get(turma_id, 0),
        )

    LigacaoFamiliar.objects.filter(aluna=aluna).delete()

    for parente_id, grau_id in dados.ligacoes:
        LigacaoFamiliar.objects.get_or_create(aluna=aluna, parente_id=parente_id, grau_id=grau_id)

    PrecoAluna.objects.update_or_create(aluna=aluna, defaults={
        'valor_manual': dados.manual, 'recebe_desconto_familiar': dados.marcada,
    })

    if valor is not None and aluna.valor_mensalidade != valor:
        aluna.valor_mensalidade = valor
        aluna.save(update_fields=['valor_mensalidade'])


def valor_calculado_do_formulario(post, aluna=None):
    """
    Para o salvamento da ficha. Devolve (DadosFormulario, valor, erro).

    Valor manual → valor None (mantém o que foi digitado). Calculado → total do cálculo, ou
    um erro em português quando não dá para calcular.
    """
    resultado, dados = calcular_do_formulario(post, aluna)

    if dados.erros:
        return dados, None, ' '.join(dados.erros)

    if dados.manual:
        return dados, None, None

    if not dados.entradas:
        return dados, None, None

    if not resultado.ok:
        return dados, None, (
            'Não foi possível calcular a mensalidade: ' + ' '.join(resultado.avisos)
            + ' Marque "Valor manual" para digitar o valor, ou cadastre o valor da turma.'
        )

    return dados, resultado.total, None
