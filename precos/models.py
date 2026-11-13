from decimal import Decimal

from django.db import models


def formatar_percentual(valor):
    texto = format(Decimal(valor).normalize(), 'f').replace('.', ',')
    return f'{texto}%'


def formatar_moeda(valor):
    valor = Decimal(valor).quantize(Decimal('0.01'))
    inteiro, _, centavos = f'{valor:.2f}'.partition('.')
    inteiro = f'{int(inteiro):,}'.replace(',', '.')

    return f'R$ {inteiro},{centavos}'


class Configuracao(models.Model):
    """Configurações gerais do cálculo (um único registro)."""

    passo_arredondamento = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.10'),
        verbose_name='Arredondar para baixo em múltiplos de',
        help_text=(
            'O valor final da mensalidade é arredondado PARA BAIXO em múltiplos deste valor. '
            'Exemplo com 0,10: 125,33 vira 125,30. Use 0,01 para não arredondar.'
        ),
    )
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Configuração de preços'
        verbose_name_plural = 'Configuração de preços'

    @classmethod
    def atual(cls):
        configuracao, _ = cls.objects.get_or_create(pk=1)

        return configuracao


class GrupoDesconto(models.Model):
    """Grupo de alunas que recebem um desconto (ex.: Golden). Quem participa é escolhido na tela."""

    nome = models.CharField(max_length=80, unique=True)
    descricao = models.CharField(max_length=200, blank=True)
    ativo = models.BooleanField(default=True)
    alunas = models.ManyToManyField('usuarios.Aluna', blank=True, related_name='grupos_desconto')
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['nome']
        verbose_name = 'Grupo de desconto'
        verbose_name_plural = 'Grupos de desconto'

    def __str__(self):
        return self.nome


class GrauParentesco(models.Model):
    """Tipo de parentesco que pode ser marcado entre duas alunas (ex.: Prima, Irmã adulta)."""

    nome = models.CharField(max_length=60, unique=True)

    class Meta:
        ordering = ['nome']
        verbose_name = 'Grau de parentesco'
        verbose_name_plural = 'Graus de parentesco'

    def __str__(self):
        return self.nome


class RegraDesconto(models.Model):
    """
    Uma regra de desconto ou de campanha, criada e apagada pela tela (nada fixo no código).

    O cálculo, para cada turma da aluna, olha todas as regras ligadas que se aplicam e SOMA
    os percentuais sobre o valor cheio da turma.
    """

    PERCENTUAL = 'percentual'
    PRECO_FIXO = 'preco_fixo'
    EFEITOS = [
        (PERCENTUAL, 'Desconto em porcentagem'),
        (PRECO_FIXO, 'A turma passa a custar um valor fixo'),
    ]

    INCIDE_EM = [
        ('primeira', 'Na 1ª turma'),
        ('segunda', 'Na 2ª turma'),
        ('terceira', 'Na 3ª turma'),
        ('segunda_em_diante', 'Da 2ª turma em diante'),
        ('terceira_em_diante', 'Da 3ª turma em diante'),
        ('todas', 'Em todas as turmas'),
    ]

    PUBLICOS = [
        ('todas', 'Todas as turmas'),
        ('ja_aluna', 'Só turmas em que a aluna entrou depois do primeiro cadastro (já era aluna)'),
        ('nova', 'Só turmas escolhidas no primeiro cadastro (aluna nova)'),
    ]

    FAMILIAS = [
        ('nenhuma', 'Não depende de parentesco'),
        ('irma_mesma_responsavel', 'Irmãs com a mesma responsável (recebe a que entrou depois)'),
        ('responsavel_aluna', 'Responsável que também é aluna (recebe a responsável)'),
        ('parentesco', 'Parentesco marcado na ficha da aluna'),
    ]

    nome = models.CharField(max_length=120)
    ativa = models.BooleanField(default=True)

    efeito = models.CharField(max_length=12, choices=EFEITOS, default=PERCENTUAL)
    valor = models.DecimalField(
        max_digits=8, decimal_places=2,
        help_text='Porcentagem (ex.: 15) ou valor em reais (ex.: 50), conforme o efeito.',
    )
    incide_em = models.CharField(max_length=20, choices=INCIDE_EM, default='segunda')
    publico = models.CharField(max_length=10, choices=PUBLICOS, default='todas')

    grupo = models.ForeignKey(
        GrupoDesconto, null=True, blank=True, on_delete=models.CASCADE, related_name='regras',
        help_text='Se escolher um grupo, só quem está nele recebe.',
    )
    grupos_excecao = models.ManyToManyField(
        GrupoDesconto, blank=True, related_name='regras_excecao',
        help_text='Quem está nestes grupos NÃO recebe esta regra.',
    )
    familia = models.CharField(max_length=24, choices=FAMILIAS, default='nenhuma')
    grau = models.ForeignKey(GrauParentesco, null=True, blank=True, on_delete=models.CASCADE, related_name='regras')

    turmas = models.ManyToManyField(
        'usuarios.Turma', blank=True, related_name='regras_desconto',
        help_text='Se escolher turmas, a regra só vale para elas. Vazio = todas.',
    )
    inicio = models.DateField(null=True, blank=True)
    fim = models.DateField(null=True, blank=True)
    so_turmas_entradas_no_periodo = models.BooleanField(
        default=False,
        help_text='Só vale para turmas em que a aluna entrou dentro do período (campanhas).',
    )
    substitui_outros = models.BooleanField(
        default=False,
        help_text='Nas turmas em que esta regra vale, nenhum outro desconto é aplicado.',
    )
    observacao = models.CharField(max_length=300, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-ativa', 'nome']
        verbose_name = 'Regra de desconto'
        verbose_name_plural = 'Regras de desconto'

    def __str__(self):
        return self.nome

    def resumo(self):
        """Descrição em português para a lista da tela."""
        if self.efeito == self.PERCENTUAL:
            partes = [f'{formatar_percentual(self.valor)} de desconto']
        else:
            partes = [f'Turma custa {formatar_moeda(self.valor)}']

        partes.append(dict(self.INCIDE_EM)[self.incide_em].lower())

        if self.publico == 'ja_aluna':
            partes.append('só se já era aluna')
        elif self.publico == 'nova':
            partes.append('só aluna nova')

        if self.grupo_id:
            partes.append(f'grupo {self.grupo.nome}')

        if self.familia == 'irma_mesma_responsavel':
            partes.append('irmã (mesma responsável)')
        elif self.familia == 'responsavel_aluna':
            partes.append('responsável que é aluna')
        elif self.familia == 'parentesco' and self.grau_id:
            partes.append(f'parentesco: {self.grau.nome}')

        if self.inicio or self.fim:
            de = self.inicio.strftime('%d/%m/%Y') if self.inicio else '…'
            ate = self.fim.strftime('%d/%m/%Y') if self.fim else '…'
            partes.append(f'de {de} a {ate}')

        if self.substitui_outros:
            partes.append('sem outros descontos')

        return ' · '.join(partes)


class Combinacao(models.Model):
    """
    Preço especial para quem faz certas turmas JUNTAS (ex.: balé + ginástica = R$ 100 cada).

    Cada "item" da combinação tem as turmas que valem e o preço que a turma passa a ter.
    O conjunto conta como UMA modalidade só e nenhum outro desconto soma nessas turmas:
    o preço de cada turma é o que está cadastrado aqui (ou o preço do grupo, se houver).
    """

    nome = models.CharField(max_length=120)
    ativa = models.BooleanField(default=True)
    inicio = models.DateField(null=True, blank=True)
    fim = models.DateField(null=True, blank=True)
    observacao = models.CharField(max_length=300, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-ativa', 'nome']
        verbose_name = 'Combinação de turmas'
        verbose_name_plural = 'Combinações de turmas'

    def __str__(self):
        return self.nome

    def resumo(self):
        itens = list(self.itens.all())
        partes = [' + '.join(f'{i.nome} {formatar_moeda(i.preco)}' for i in itens)]

        for item in itens:
            for especial in item.precos_grupo.all():
                partes.append(f'{especial.grupo.nome}: {item.nome} {formatar_moeda(especial.preco)}')

        if self.inicio or self.fim:
            de = self.inicio.strftime('%d/%m/%Y') if self.inicio else '…'
            ate = self.fim.strftime('%d/%m/%Y') if self.fim else '…'
            partes.append(f'de {de} a {ate}')

        return ' · '.join(partes)


class CombinacaoItem(models.Model):
    combinacao = models.ForeignKey(Combinacao, on_delete=models.CASCADE, related_name='itens')
    nome = models.CharField(max_length=80)
    turmas = models.ManyToManyField('usuarios.Turma', related_name='itens_de_combinacao')
    preco = models.DecimalField(max_digits=8, decimal_places=2)
    ordem = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['ordem', 'pk']

    def __str__(self):
        return f'{self.combinacao.nome}: {self.nome}'


class CombinacaoPrecoGrupo(models.Model):
    """Preço diferente, dentro de uma combinação, para quem está em um grupo (ex.: Golden)."""

    item = models.ForeignKey(CombinacaoItem, on_delete=models.CASCADE, related_name='precos_grupo')
    grupo = models.ForeignKey(GrupoDesconto, on_delete=models.CASCADE, related_name='precos_combinacao')
    preco = models.DecimalField(max_digits=8, decimal_places=2)

    class Meta:
        unique_together = [('item', 'grupo')]
