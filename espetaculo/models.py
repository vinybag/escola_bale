from decimal import Decimal, ROUND_HALF_UP
from django.db import models
from django.utils import timezone


class Espetaculo(models.Model):
    # Informações básicas
    titulo = models.CharField(max_length=200)
    subtitulo = models.CharField(max_length=200, blank=True)
    descricao = models.TextField()

    # Data e local
    data_apresentacao = models.DateTimeField()
    local = models.CharField(max_length=200)
    endereco = models.TextField()

    # Imagem (opcional)
    imagem = models.ImageField(upload_to='espetaculos/', blank=True, null=True)

    # PDF com informações completas
    arquivo_informacoes = models.FileField(
        upload_to='espetaculos/pdfs/',
        blank=True,
        null=True,
        help_text='PDF com sinopse, personagens, audição, etc.'
    )

    # Edital/Arquivo para download
    arquivo_edital = models.FileField(
        upload_to='espetaculos/editais/',
        blank=True,
        null=True,
        help_text='PDF com edital, regulamento ou material de apoio'
    )

    # Audição
    audicao_aberta = models.BooleanField(default=False)
    audicao_data_inicio = models.DateField(blank=True, null=True)
    audicao_data_fim = models.DateField(blank=True, null=True)
    audicao_instrucoes = models.TextField(blank=True)

    # Venda de ingressos
    venda_aberta = models.BooleanField(default=False)
    venda_data_inicio = models.DateField(blank=True, null=True)
    preco_ingresso = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Controle
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Espetáculo'
        verbose_name_plural = 'Espetáculos'
        ordering = ['-data_apresentacao']

    def __str__(self):
        return self.titulo


class InscricaoAudicao(models.Model):
    PERSONAGENS_CHOICES = [
        ('thessalia', 'Thessália'),
        ('zyara', 'Zyara'),
        ('zyar', 'Zyar'),
        ('astela_nur', 'Astela Nur'),
        ('kai_ignus', 'Kai Ignus'),
        ('eldrick_felicius', 'Eldrick Felicius'),
        ('florine', 'Florine'),
        ('odessa', 'Odessa'),
        ('aurelia', 'Aurélia'),
        ('cora_del_amour', 'Cora del Amour'),
        ('3_marias', '3 Marias'),
    ]

    nome_completo = models.CharField(max_length=200, verbose_name='Nome completo')
    whatsapp = models.CharField(max_length=20, verbose_name='Whatsapp')
    idade = models.IntegerField(verbose_name='Idade')
    personagens = models.CharField(max_length=500, verbose_name='Personagens escolhidos')
    espetaculo = models.ForeignKey(
        Espetaculo,
        on_delete=models.CASCADE,
        related_name='inscricoes',
        null=True,
        blank=True
    )
    data_inscricao = models.DateTimeField(auto_now_add=True)
    lida = models.BooleanField(default=False, verbose_name='Inscrição lida')

    def __str__(self):
        return f'{self.nome_completo} - {self.personagens}'

    class Meta:
        verbose_name = 'Inscrição para Audição'
        verbose_name_plural = 'Inscrições para Audição'
        ordering = ['-data_inscricao']


class AvaliacaoAudicao(models.Model):
    NIVEL_OPCOES = [
        ('regular', 'Regular'),
        ('bom', 'Bom'),
        ('muito_bom', 'Muito Bom'),
        ('excelente', 'Excelente'),
        ('destaque', 'Destaque'),
    ]

    inscricao = models.ForeignKey('InscricaoAudicao', on_delete=models.CASCADE, related_name='avaliacoes')
    personagem = models.CharField(max_length=100)
    nome_participante = models.CharField(max_length=200)
    nivel = models.CharField(max_length=20, choices=NIVEL_OPCOES, default='regular')
    observacoes = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.nome_participante} - {self.personagem}"

    class Meta:
        verbose_name = 'Avaliação de Audição'
        verbose_name_plural = 'Avaliações de Audição'


class ParticipacaoEspetaculo(models.Model):
    espetaculo = models.ForeignKey(
        Espetaculo,
        on_delete=models.CASCADE,
        related_name='participacoes'
    )
    aluna = models.ForeignKey(
        'usuarios.Aluna',
        on_delete=models.CASCADE,
        related_name='participacoes_espetaculo'
    )
    vai_dancar = models.BooleanField(default=True)
    observacoes = models.TextField(blank=True, null=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Participação no espetáculo'
        verbose_name_plural = 'Participações no espetáculo'
        unique_together = ('espetaculo', 'aluna')

    def __str__(self):
        return f'{self.aluna.nome} - {self.espetaculo.titulo}'


class CobrancaEspetaculo(models.Model):
    TIPO_CHOICES = (
        ('taxa_palco', 'Taxa de palco'),
        ('figurino', 'Figurino'),
    )

    STATUS_CHOICES = (
        ('pendente', 'Pendente'),
        ('parcial', 'Parcial'),
        ('pago', 'Pago'),
    )

    participacao = models.ForeignKey(
        ParticipacaoEspetaculo,
        on_delete=models.CASCADE,
        related_name='cobrancas'
    )
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    descricao = models.CharField(max_length=255)
    valor_total = models.DecimalField(max_digits=10, decimal_places=2)
    permitir_parcelamento = models.BooleanField(default=False)
    max_parcelas = models.PositiveIntegerField(default=1)
    vencimento_primeira_parcela = models.DateField(blank=True, null=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pendente')
    ativo = models.BooleanField(default=True)

    enviado_asaas = models.BooleanField(default=False)
    asaas_customer_id = models.CharField(max_length=100, blank=True, null=True)
    billing_type = models.CharField(max_length=30, blank=True, null=True)

    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Cobrança do espetáculo'
        verbose_name_plural = 'Cobranças do espetáculo'

    def __str__(self):
        return f'{self.get_tipo_display()} - {self.participacao.aluna.nome}'

    @property
    def opcoes_parcelas(self):
        """Retorna lista [1, 2, 3, ...] até max_parcelas."""
        if not self.permitir_parcelamento:
            return [1]
        return list(range(1, (self.max_parcelas or 1) + 1))

    @property
    def valor_por_parcela_de(self):
        """Retorna dict {n: valor} para cada opção de parcelamento."""
        resultado = {}
        for n in self.opcoes_parcelas:
            if n > 0:
                valor = (Decimal(str(self.valor_total)) / n).quantize(
                    Decimal('0.01'),
                    rounding=ROUND_HALF_UP,
                )
                resultado[n] = valor
        return resultado

    def total_pago(self):
        total = self.parcelas.filter(status='pago').aggregate(
            total=models.Sum('valor')
        )['total']
        return total or Decimal('0.00')

    def total_pendente(self):
        return self.valor_total - self.total_pago()

    def atualizar_status(self):
        parcelas = self.parcelas.all()

        if parcelas.exists():
            total = parcelas.count()
            pagas = parcelas.filter(status='pago').count()

            if pagas == 0:
                self.status = 'pendente'
            elif pagas == total:
                self.status = 'pago'
            else:
                self.status = 'parcial'
        else:
            self.status = 'pendente'

        self.save(update_fields=['status'])


class ParcelaCobrancaEspetaculo(models.Model):
    STATUS_CHOICES = (
        ('pendente', 'Pendente'),
        ('pago', 'Pago'),
    )

    cobranca = models.ForeignKey(
        CobrancaEspetaculo,
        on_delete=models.CASCADE,
        related_name='parcelas'
    )
    numero_parcela = models.PositiveIntegerField()
    total_parcelas = models.PositiveIntegerField(default=1)
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    vencimento = models.DateField(blank=True, null=True)
    mes_liberacao = models.DateField(blank=True, null=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pendente')
    data_pagamento = models.DateTimeField(blank=True, null=True)

    asaas_payment_id = models.CharField(max_length=100, blank=True, null=True)
    asaas_installment_id = models.CharField(max_length=100, blank=True, null=True)
    asaas_invoice_url = models.URLField(blank=True, null=True)
    asaas_bank_slip_url = models.URLField(blank=True, null=True)
    asaas_transaction_receipt_url = models.URLField(blank=True, null=True)
    asaas_nosso_numero = models.CharField(max_length=100, blank=True, null=True)
    asaas_status = models.CharField(max_length=50, blank=True, null=True)
    billing_type = models.CharField(max_length=30, blank=True, null=True)

    codigo_pix = models.TextField(blank=True, null=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Parcela da cobrança do espetáculo'
        verbose_name_plural = 'Parcelas da cobrança do espetáculo'
        unique_together = ('cobranca', 'numero_parcela')
        ordering = ['numero_parcela']

    def __str__(self):
        return f'{self.cobranca} - parcela {self.numero_parcela}/{self.total_parcelas}'

    def esta_liberada(self):
        if not self.mes_liberacao:
            return True
        hoje = timezone.now().date()
        return hoje >= self.mes_liberacao

    def marcar_como_pago(self):
        self.status = 'pago'
        self.data_pagamento = timezone.now()
        self.save(update_fields=['status', 'data_pagamento'])
        self.cobranca.atualizar_status()