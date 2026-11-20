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
    eh_familia = models.BooleanField(
        default=False, verbose_name='Grupo de família',
        help_text='As mensalidades das integrantes são geradas no login do representante.',
    )
    representante = models.ForeignKey(
        'auth.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
        verbose_name='Representante da família',
    )
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
        ('total_grupo_familia', 'Desconto sobre o TOTAL das mensalidades do grupo de família'),
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

    QUEM_RECEBE = [
        ('automatico', 'Automático (irmãs: a que entrou depois · parentes: todas as marcadas)'),
        ('depois', 'Só a que entrou depois'),
        ('ambas', 'As duas (todas as ligadas)'),
        ('marcada', 'Só a que eu marcar na ficha da aluna'),
    ]
    quem_recebe = models.CharField(
        max_length=12, choices=QUEM_RECEBE, default='automatico',
        help_text='Vale para regras de irmãs e de parentesco: quem, entre as ligadas, recebe o desconto.',
    )

    familias_desconto = models.ManyToManyField(
        GrupoDesconto, blank=True, related_name='regras_total_familia',
        help_text='Só para "desconto sobre o total do grupo de família": quais famílias (grupos de família) recebem.',
    )
    minimo_integrantes = models.PositiveSmallIntegerField(
        default=2,
        help_text='Só para "desconto sobre o total do grupo de família": mínimo de integrantes (com valor calculado).',
    )
    arredondar_total_para = models.DecimalField(
        max_digits=6, decimal_places=2, default=Decimal('1.00'),
        help_text='Só para "desconto sobre o total do grupo de família": o total da família é arredondado para baixo neste valor (ex.: 1 = reais inteiros).',
    )

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
        elif self.familia == 'total_grupo_familia':
            nomes = ', '.join(g.nome for g in self.familias_desconto.all()) or 'todas as famílias'
            partes.append(f'sobre o total da família: {nomes} (mín. {self.minimo_integrantes} integrantes)')
        elif self.familia == 'parentesco' and self.grau_id:
            partes.append(f'parentesco: {self.grau.nome}')

        if self.familia in ('irma_mesma_responsavel', 'parentesco') and self.quem_recebe != 'automatico':
            partes.append(f'recebe: {dict(self.QUEM_RECEBE)[self.quem_recebe].lower()}')

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
    aceita_desconto_familia = models.BooleanField(
        default=False,
        help_text='A turma deste item entra na base do desconto sobre o total do grupo de família.',
    )

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



class EntradaTurma(models.Model):
    """
    Quando a aluna entrou em cada turma (guarda a ORDEM de entrada, que define 1ª/2ª/3ª turma).

    É mantida sozinha: quando uma turma é marcada na ficha da aluna, nasce uma entrada com a
    data de hoje; quando é desmarcada, a entrada some. "Já era aluna" = entrou depois do dia
    do primeiro cadastro da aluna.
    """

    aluna = models.ForeignKey('usuarios.Aluna', on_delete=models.CASCADE, related_name='entradas_turma')
    turma = models.ForeignKey('usuarios.Turma', on_delete=models.CASCADE, related_name='entradas_aluna')
    data_entrada = models.DateField()
    ordem = models.PositiveSmallIntegerField(
        default=0, help_text='Desempata turmas que entraram no mesmo dia (1 = conta primeiro).',
    )

    class Meta:
        unique_together = [('aluna', 'turma')]
        ordering = ['data_entrada', 'ordem', 'pk']
        verbose_name = 'Entrada em turma'
        verbose_name_plural = 'Entradas em turmas'

    def __str__(self):
        return f'{self.aluna} → {self.turma} ({self.data_entrada:%d/%m/%Y})'


class PrecoAluna(models.Model):
    """
    Como a mensalidade de uma aluna é definida. Sem registro = valor MANUAL (alunas antigas).

    valor_manual=True: o valor digitado na ficha é o que vale; nada é recalculado sozinho.
    valor_manual=False: o valor vem do cálculo (turmas + descontos) e acompanha o mês cobrado.
    """

    aluna = models.OneToOneField('usuarios.Aluna', on_delete=models.CASCADE, related_name='preco')
    valor_manual = models.BooleanField(default=True, verbose_name='Valor manual')
    recebe_desconto_familiar = models.BooleanField(
        default=False, verbose_name='Marcada para receber o desconto de irmã/parentesco',
        help_text='Vale nas regras configuradas como "só a que eu marcar".',
    )
    pagador = models.ForeignKey(
        'auth.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
        verbose_name='Gerar a mensalidade no login de',
        help_text='Vazio = automático (responsável da ficha ou grupo de família).',
    )
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Preço da aluna'
        verbose_name_plural = 'Preços das alunas'

    def __str__(self):
        return f'{self.aluna} ({"manual" if self.valor_manual else "calculado"})'


class LigacaoFamiliar(models.Model):
    """Parentesco marcado entre duas alunas (ex.: primas, irmãs adultas). Vale nos dois sentidos."""

    aluna = models.ForeignKey('usuarios.Aluna', on_delete=models.CASCADE, related_name='ligacoes_familiares')
    parente = models.ForeignKey('usuarios.Aluna', on_delete=models.CASCADE, related_name='ligacoes_como_parente')
    grau = models.ForeignKey(GrauParentesco, on_delete=models.CASCADE, related_name='ligacoes')

    class Meta:
        unique_together = [('aluna', 'parente', 'grau')]
        verbose_name = 'Ligação familiar'
        verbose_name_plural = 'Ligações familiares'

    def __str__(self):
        return f'{self.aluna} — {self.parente} ({self.grau})'
