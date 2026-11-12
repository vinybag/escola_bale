import hashlib

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


def _bytes(valor):
    """BinaryField volta como memoryview no PostgreSQL; sempre trabalhamos com bytes."""
    if valor is None:
        return b''
    return bytes(valor)


class OpcaoBolsa(models.Model):
    """Uma das opções de bolsa oferecidas pela escola (ex.: "Bolsa 50%")."""

    nome = models.CharField(max_length=100)
    percentual = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text='Percentual de desconto sobre a mensalidade (de 0,01 a 100).',
    )
    ativa = models.BooleanField(
        default=True,
        help_text='Opções inativas não aparecem para novas bolsistas.',
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['percentual', 'nome']
        verbose_name = 'Opção de bolsa'
        verbose_name_plural = 'Opções de bolsa'

    def __str__(self):
        from .regras import formatar_percentual

        return f'{self.nome} ({formatar_percentual(self.percentual)})'


class BolsaAluna(models.Model):
    """Marca uma aluna como bolsista e guarda qual opção de bolsa ela tem."""

    aluna = models.OneToOneField(
        'usuarios.Aluna',
        on_delete=models.CASCADE,
        related_name='bolsa',
    )
    opcao = models.ForeignKey(
        OpcaoBolsa,
        on_delete=models.PROTECT,
        related_name='bolsistas',
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Bolsa da aluna'
        verbose_name_plural = 'Bolsas das alunas'

    def __str__(self):
        return f'{self.aluna} - {self.opcao}'


class ModeloContrato(models.Model):
    """PDF-modelo do contrato (com marcadores [[ASSIM]]) enviado pelo admin."""

    TIPO_PADRAO = 'padrao'
    TIPO_BOLSISTA = 'bolsista'
    TIPOS = [
        (TIPO_PADRAO, 'Contrato padrão'),
        (TIPO_BOLSISTA, 'Contrato de bolsista'),
    ]

    tipo = models.CharField(max_length=10, choices=TIPOS)
    nome = models.CharField(max_length=120)
    ano = models.PositiveSmallIntegerField()

    arquivo_pdf = models.BinaryField(editable=False)
    nome_arquivo = models.CharField(max_length=200, blank=True)
    hash_arquivo = models.CharField(max_length=64, blank=True)

    # Marcadores encontrados no PDF: [{nome, pagina, contexto, largura_livre}]
    marcadores = models.JSONField(default=list, blank=True)
    # Valores dos "campos do ano" (ANO, VALOR_*...) e do texto da assinatura da Contratada.
    valores = models.JSONField(default=dict, blank=True)

    ativo = models.BooleanField(default=False)
    criado_em = models.DateTimeField(auto_now_add=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
    )

    class Meta:
        ordering = ['-ano', 'tipo', '-criado_em']
        verbose_name = 'Modelo de contrato'
        verbose_name_plural = 'Modelos de contrato'

    def __str__(self):
        return f'{self.get_tipo_display()} - {self.nome} ({self.ano})'

    @property
    def pdf_bytes(self):
        return _bytes(self.arquivo_pdf)

    def nomes_marcadores(self):
        return {m['nome'] for m in self.marcadores}


class Contrato(models.Model):
    """Contrato de uma aluna para um ano (um por aluna por ano)."""

    PENDENTE = 'pendente'
    DADOS = 'dados_preenchidos'
    AGUARDANDO_PAPEL = 'aguardando_papel'
    ASSINADO_DIGITAL = 'assinado_digital'
    ASSINADO_PAPEL = 'assinado_papel'
    ANULADO = 'anulado'

    STATUS = [
        (PENDENTE, 'Pendente'),
        (DADOS, 'Dados preenchidos'),
        (AGUARDANDO_PAPEL, 'Aguardando assinatura em papel'),
        (ASSINADO_DIGITAL, 'Assinado digitalmente'),
        (ASSINADO_PAPEL, 'Assinado em papel'),
        (ANULADO, 'Anulado'),
    ]

    STATUS_ABERTOS = (PENDENTE, DADOS, AGUARDANDO_PAPEL)
    STATUS_ASSINADOS = (ASSINADO_DIGITAL, ASSINADO_PAPEL)

    aluna = models.ForeignKey(
        'usuarios.Aluna',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='contratos',
    )
    # Guardado à parte para o registro continuar legível mesmo se a aluna for excluída.
    aluna_nome = models.CharField(max_length=100)
    contratante = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='contratos_como_contratante',
    )

    ano = models.PositiveSmallIntegerField()
    tipo = models.CharField(max_length=10, blank=True, choices=ModeloContrato.TIPOS)
    modelo = models.ForeignKey(
        ModeloContrato,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='contratos',
    )

    status = models.CharField(max_length=20, choices=STATUS, default=PENDENTE, db_index=True)

    # Dados informados pela família (congelados na assinatura).
    dados = models.JSONField(default=dict, blank=True)
    previa_hash = models.CharField(max_length=64, blank=True)

    # Assinatura digital
    pdf_assinado = models.BinaryField(null=True, blank=True, editable=False)
    hash_conteudo = models.CharField(max_length=64, blank=True)
    hash_arquivo = models.CharField(max_length=64, blank=True)
    codigo_verificacao = models.CharField(max_length=20, blank=True)
    assinado_em = models.DateTimeField(null=True, blank=True)
    assinado_ip = models.GenericIPAddressField(null=True, blank=True)
    assinado_user_agent = models.CharField(max_length=300, blank=True)

    # Assinatura em papel
    impresso_em = models.DateTimeField(null=True, blank=True)
    scan_arquivo = models.BinaryField(null=True, blank=True, editable=False)
    scan_nome = models.CharField(max_length=200, blank=True)
    scan_tipo = models.CharField(max_length=60, blank=True)
    scan_enviado_em = models.DateTimeField(null=True, blank=True)
    scan_enviado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
    )

    anulado_em = models.DateTimeField(null=True, blank=True)
    anulado_motivo = models.CharField(max_length=300, blank=True)

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-ano', 'aluna_nome']
        verbose_name = 'Contrato'
        verbose_name_plural = 'Contratos'
        constraints = [
            models.UniqueConstraint(
                fields=['aluna', 'ano'],
                condition=~Q(status='anulado'),
                name='contrato_unico_por_aluna_e_ano',
            ),
        ]

    def __str__(self):
        return f'Contrato {self.ano} - {self.aluna_nome} ({self.get_status_display()})'

    @property
    def esta_assinado(self):
        return self.status in self.STATUS_ASSINADOS

    @property
    def esta_aberto(self):
        return self.status in self.STATUS_ABERTOS

    @property
    def pdf_assinado_bytes(self):
        return _bytes(self.pdf_assinado)

    @property
    def scan_bytes(self):
        return _bytes(self.scan_arquivo)

    @property
    def tem_scan(self):
        return bool(self.scan_arquivo)


class CodigoAssinatura(models.Model):
    """Código de 6 dígitos enviado por e-mail para confirmar a assinatura digital."""

    contrato = models.ForeignKey(Contrato, on_delete=models.CASCADE, related_name='codigos')
    codigo_hash = models.CharField(max_length=64)
    criado_em = models.DateTimeField(auto_now_add=True)
    expira_em = models.DateTimeField()
    tentativas = models.PositiveSmallIntegerField(default=0)
    usado = models.BooleanField(default=False)

    class Meta:
        ordering = ['-criado_em']

    @staticmethod
    def calcular_hash(contrato_id, codigo):
        bruto = f'{contrato_id}:{codigo}:{settings.SECRET_KEY}'
        return hashlib.sha256(bruto.encode('utf-8')).hexdigest()

    @property
    def expirado(self):
        return timezone.now() >= self.expira_em
