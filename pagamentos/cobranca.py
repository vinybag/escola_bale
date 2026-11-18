"""
Cobrança única por responsável.

Por dentro cada aluna continua com a sua mensalidade (relatórios e histórico não mudam).
Para a responsável, as mensalidades EM ABERTO do mesmo login, do mesmo mês e com o mesmo
vencimento viram UMA cobrança: um valor total, um pix e uma descrição só.

Quem fica junto é quem tem o mesmo login de pagamento (`Mensalidade.responsavel`): as filhas
de uma mesma responsável e a mãe que também é aluna. Primas e outras famílias, que têm login
próprio, nunca entram na mesma cobrança.
"""

from collections import OrderedDict
from decimal import Decimal

from .models import Mensalidade

ABERTAS = ('pendente', 'atrasado')


def juntar_nomes(nomes):
    """['Ana'] -> 'Ana' · ['Ana', 'Bia'] -> 'Ana e Bia' · ['Ana', 'Bia', 'Cléo'] -> 'Ana, Bia e Cléo'."""
    nomes = [n for n in nomes if n]

    if len(nomes) <= 1:
        return ''.join(nomes)

    return ', '.join(nomes[:-1]) + ' e ' + nomes[-1]


def esta_em_aberto(mensalidade):
    return mensalidade.status_atual in ABERTAS


class Cobranca:
    """Uma ou mais mensalidades que a responsável paga de uma vez."""

    def __init__(self, itens):
        self.itens = sorted(itens, key=lambda m: (m.aluna.nome.lower(), m.pk))

    # --- identificação
    @property
    def principal(self):
        return self.itens[0]

    @property
    def id(self):
        """Número usado nos links: o da primeira mensalidade da cobrança."""
        return self.principal.pk

    @property
    def ids(self):
        return [m.pk for m in self.itens]

    @property
    def responsavel(self):
        return self.principal.responsavel

    @property
    def mes_referencia(self):
        return self.principal.mes_referencia

    @property
    def data_vencimento(self):
        return self.principal.data_vencimento

    @property
    def varias(self):
        return len(self.itens) > 1

    @property
    def nomes_alunas(self):
        return juntar_nomes([m.aluna.nome for m in self.itens])

    @property
    def descricao(self):
        return f'Mensalidade {self.nomes_alunas} - {self.mes_referencia.strftime("%m/%Y")}'

    @property
    def referencia_externa(self):
        """Texto guardado no Asaas para o webhook achar as mensalidades."""
        if not self.varias:
            return f'mensalidade:{self.id}'

        return 'mensalidades:' + ','.join(str(i) for i in self.ids)

    # --- valores
    @property
    def valor(self):
        return sum((Decimal(m.valor) for m in self.itens), Decimal('0.00')).quantize(Decimal('0.01'))

    @property
    def acrescimo_atraso(self):
        return sum((m.acrescimo_atraso for m in self.itens), Decimal('0.00'))

    @property
    def valor_atualizado(self):
        """Soma do valor atualizado de cada mensalidade (o acréscimo de atraso segue a regra de sempre)."""
        return sum((m.valor_atualizado for m in self.itens), Decimal('0.00')).quantize(Decimal('0.01'))

    # --- situação
    @property
    def dias_atraso(self):
        return max((m.dias_atraso for m in self.itens), default=0)

    @property
    def esta_atrasada(self):
        return self.dias_atraso > 0

    @property
    def status_atual(self):
        estados = {m.status_atual for m in self.itens}

        if 'atrasado' in estados:
            return 'atrasado'

        if 'pendente' in estados:
            return 'pendente'

        if 'pago' in estados:
            return 'pago'

        return 'cancelado'

    @property
    def data_pagamento(self):
        datas = [m.data_pagamento for m in self.itens if m.data_pagamento]
        return max(datas) if datas else None

    @property
    def payment_id_existente(self):
        for m in self.itens:
            if m.asaas_payment_id:
                return m.asaas_payment_id

        return ''

    def __iter__(self):
        return iter(self.itens)


def _chave(mensalidade):
    return (mensalidade.responsavel_id, mensalidade.mes_referencia, mensalidade.data_vencimento)


def agrupar(mensalidades):
    """
    Agrupa mensalidades em cobranças, na ordem em que aparecem.

    Em aberto com o mesmo login/mês/vencimento ficam juntas. Pagas do mesmo login/mês/vencimento
    também (para o histórico mostrar "Ana e Bia — pago"). Canceladas nunca se juntam a nada.
    """
    grupos = OrderedDict()

    for m in mensalidades:
        situacao = m.status_atual

        if situacao == 'cancelado':
            chave = ('cancelado', m.pk)
        elif situacao == 'pago':
            chave = ('pago', m.asaas_payment_id or '') + _chave(m)
        else:
            chave = ('aberto',) + _chave(m)

        grupos.setdefault(chave, []).append(m)

    return [Cobranca(itens) for itens in grupos.values()]


def cobranca_da_mensalidade(mensalidade):
    """
    A cobrança que a responsável paga ao clicar em "Pagar" nesta mensalidade.

    Mensalidade em aberto: ela mais as outras em aberto do mesmo login, mês e vencimento.
    Qualquer outra situação: só ela.
    """
    if not esta_em_aberto(mensalidade):
        return Cobranca([mensalidade])

    irmas = Mensalidade.objects.filter(
        responsavel_id=mensalidade.responsavel_id,
        mes_referencia=mensalidade.mes_referencia,
        data_vencimento=mensalidade.data_vencimento,
        data_pagamento__isnull=True,
    ).exclude(status='cancelado').select_related('aluna', 'responsavel')

    itens = [m for m in irmas if esta_em_aberto(m)]

    if not any(m.pk == mensalidade.pk for m in itens):
        itens.append(mensalidade)

    return Cobranca(itens)


def itens_do_pagamento(payment_id):
    """Todas as mensalidades ligadas a um pagamento do Asaas."""
    if not payment_id:
        return []

    return list(Mensalidade.objects.filter(asaas_payment_id=payment_id).select_related('aluna', 'responsavel'))


def ids_da_referencia(referencia):
    """'mensalidade:7' -> [7] · 'mensalidades:7,9' -> [7, 9] · outra coisa -> []."""
    if not referencia:
        return []

    for prefixo in ('mensalidades:', 'mensalidade:'):
        if referencia.startswith(prefixo):
            return [int(x) for x in referencia[len(prefixo):].split(',') if x.strip().isdigit()]

    return []
