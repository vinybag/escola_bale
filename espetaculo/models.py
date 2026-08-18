import uuid
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO

import qrcode
from PIL import Image, ImageDraw, ImageFont

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils import timezone


class Espetaculo(models.Model):
    TIPO_CHOICES = [
        ('espetaculo', 'Espetáculo'),
        ('evento', 'Evento'),
    ]

    # Informações básicas
    titulo = models.CharField(max_length=200)
    subtitulo = models.CharField(max_length=200, blank=True)
    descricao = models.TextField()

    tipo = models.CharField(
        max_length=20,
        choices=TIPO_CHOICES,
        default='espetaculo',
        verbose_name='Tipo'
    )
    publico = models.BooleanField(
        default=True,
        verbose_name='Aberto ao público',
        help_text='Desmarque para eventos privados'
    )

    # Data e local
    data_apresentacao = models.DateTimeField()
    local = models.CharField(max_length=200)
    endereco = models.TextField()

    # Imagem principal
    imagem = models.ImageField(
        upload_to='espetaculos/',
        blank=True,
        null=True
    )

    # Imagem base do ingresso
    imagem_ingresso = models.ImageField(
        upload_to='eventos/ingressos/',
        blank=True,
        null=True,
        help_text='Imagem base usada para compor o ingresso com QR Code'
    )

    # Arquivo de divulgação (imagem ou PDF)
    arquivo_divulgacao = models.FileField(
        upload_to='eventos/divulgacao/',
        blank=True,
        null=True,
        validators=[FileExtensionValidator(['png', 'jpg', 'jpeg', 'pdf'])],
        help_text='Arquivo de divulgação: PNG, JPG, JPEG ou PDF'
    )

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

    # Ingresso gratuito para alunas
    permite_ingresso_gratuito_aluna = models.BooleanField(
        default=False,
        verbose_name='Ingresso gratuito para alunas',
        help_text='Se marcado, alunas logadas poderão gerar ingresso sem pagamento.'
    )

    # Assentos numerados e restrição de login
    venda_com_assentos_numerados = models.BooleanField(
        default=False,
        verbose_name='Venda com assentos numerados',
        help_text='Se marcado, exibe o mapa de assentos para escolha no momento da compra.'
    )

    exige_login_para_compra = models.BooleanField(
        default=False,
        verbose_name='Exigir login para comprar ingresso',
        help_text='Se marcado, apenas usuários autenticados podem comprar ingressos deste evento.'
    )

    # Controle
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Espetáculo / Evento'
        verbose_name_plural = 'Espetáculos / Eventos'
        ordering = ['-data_apresentacao']

    def __str__(self):
        return self.titulo

    @property
    def is_evento(self):
        return self.tipo == 'evento'

    @property
    def arquivo_divulgacao_extensao(self):
        if not self.arquivo_divulgacao:
            return ''
        nome = self.arquivo_divulgacao.name.lower()
        return nome.split('.')[-1] if '.' in nome else ''

    @property
    def tem_mapa_assentos(self):
        return (
            self.venda_com_assentos_numerados
            and hasattr(self, 'mapa_assentos')
        )


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
        ('rosa_branca', 'Rosa Branca'),
    ]

    nome_completo = models.CharField(max_length=200, verbose_name='Nome completo')
    whatsapp = models.CharField(max_length=20, verbose_name='Whatsapp')
    idade = models.IntegerField(verbose_name='Idade')
    personagens = models.CharField(max_length=500, verbose_name='Personagens escolhidos')
    espetaculo = models.ForeignKey(
        'Espetaculo',
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

    inscricao = models.ForeignKey(
        'InscricaoAudicao',
        on_delete=models.CASCADE,
        related_name='avaliacoes'
    )
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

    desconto_irmaos = models.BooleanField(
        default=False,
        help_text='Aplicar desconto especial para irmãos/irmãs'
    )

    sem_desconto = models.BooleanField(
        default=False,
        verbose_name='Sem desconto (à vista e parcelado)',
        help_text='Se marcado, ignora os descontos automáticos e usa o valor exato lançado, tanto à vista quanto parcelado.'
    )

    valor_figurino_avista = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Preencha apenas para cobranças do tipo figurino.'
    )
    valor_figurino_parcelado = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Preencha apenas para cobranças do tipo figurino parcelado.'
    )

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

    def clean(self):
        super().clean()

        if self.max_parcelas < 1:
            raise ValidationError({'max_parcelas': 'O número máximo de parcelas deve ser pelo menos 1.'})

        if not self.permitir_parcelamento:
            self.max_parcelas = 1

        if self.tipo == 'figurino':
            if self.valor_figurino_avista is None:
                raise ValidationError({
                    'valor_figurino_avista': 'Informe o valor à vista do figurino.'
                })

            if self.permitir_parcelamento:
                if self.valor_figurino_parcelado is None:
                    raise ValidationError({
                        'valor_figurino_parcelado': 'Informe o valor parcelado do figurino.'
                    })

            if self.valor_figurino_avista is not None and self.valor_figurino_avista <= Decimal('0.00'):
                raise ValidationError({
                    'valor_figurino_avista': 'O valor à vista do figurino deve ser maior que zero.'
                })

            if (
                self.permitir_parcelamento
                and self.valor_figurino_parcelado is not None
                and self.valor_figurino_parcelado <= Decimal('0.00')
            ):
                raise ValidationError({
                    'valor_figurino_parcelado': 'O valor parcelado do figurino deve ser maior que zero.'
                })

    def _parcelas_prefetch(self):
        cache = getattr(self, '_prefetched_objects_cache', {})
        if 'parcelas' in cache:
            return list(cache['parcelas'])
        return None

    @property
    def pode_pagar_a_vista(self):
        hoje = timezone.now().date()

        if hoje.month <= 10:
            return True

        return False

    @property
    def max_parcelas_permitidas_hoje(self):
        hoje = timezone.now().date()

        if hoje.month <= 6:
            return min(self.max_parcelas or 1, 5)
        if hoje.month == 7:
            return min(self.max_parcelas or 1, 4)
        if hoje.month == 8:
            return min(self.max_parcelas or 1, 3)
        if hoje.month == 9:
            return min(self.max_parcelas or 1, 2)
        if hoje.month == 10:
            return min(self.max_parcelas or 1, 1)
        return 0

    @property
    def opcoes_parcelas(self):
        max_permitidas = self.max_parcelas_permitidas_hoje

        if max_permitidas <= 0:
            return []

        if not self.permitir_parcelamento:
            return [1] if self.pode_pagar_a_vista else []

        opcoes = list(range(1, max_permitidas + 1))

        if not self.pode_pagar_a_vista:
            opcoes = [n for n in opcoes if n > 1]

        return opcoes

    @property
    def valor_por_parcela_de(self):
        resultado = {}
        for n in self.opcoes_parcelas:
            if n > 0:
                valor_total_final = self.valor_com_desconto(n)
                valor = (valor_total_final / n).quantize(
                    Decimal('0.01'),
                    rounding=ROUND_HALF_UP,
                )
                resultado[n] = valor
        return resultado

    def percentual_desconto_para(self, parcelas):
        parcelas = int(parcelas)

        if self.sem_desconto:
            return Decimal('0.00')

        if self.tipo == 'figurino':
            return Decimal('0.00')

        if self.tipo == 'taxa_palco':
            if parcelas == 1:
                return Decimal('12.00') if self.desconto_irmaos else Decimal('5.00')
            return Decimal('10.00') if self.desconto_irmaos else Decimal('0.00')

        return Decimal('0.00')

    def valor_com_desconto(self, parcelas):
        parcelas = int(parcelas)

        if self.sem_desconto:
            return Decimal(str(self.valor_total)).quantize(
                Decimal('0.01'),
                rounding=ROUND_HALF_UP,
            )

        if self.tipo == 'figurino':
            if parcelas == 1:
                valor = self.valor_figurino_avista if self.valor_figurino_avista is not None else self.valor_total
                return Decimal(str(valor)).quantize(
                    Decimal('0.01'),
                    rounding=ROUND_HALF_UP,
                )

            valor = self.valor_figurino_parcelado if self.valor_figurino_parcelado is not None else self.valor_total
            return Decimal(str(valor)).quantize(
                Decimal('0.01'),
                rounding=ROUND_HALF_UP,
            )

        percentual = self.percentual_desconto_para(parcelas)
        desconto = (Decimal(str(self.valor_total)) * percentual / Decimal('100')).quantize(
            Decimal('0.01'),
            rounding=ROUND_HALF_UP,
        )
        return (Decimal(str(self.valor_total)) - desconto).quantize(
            Decimal('0.01'),
            rounding=ROUND_HALF_UP,
        )

    @property
    def opcoes_pagamento_exibicao(self):
        opcoes = []

        for parcelas in self.opcoes_parcelas:
            valor_final = self.valor_com_desconto(parcelas)
            valor_parcela = (valor_final / parcelas).quantize(
                Decimal('0.01'),
                rounding=ROUND_HALF_UP,
            )
            percentual_desconto = self.percentual_desconto_para(parcelas)

            if parcelas == 1:
                label = 'À vista'
                texto_valor = f'R$ {valor_final}'

                if self.sem_desconto:
                    observacao = 'Sem desconto (valor integral)'
                elif self.tipo == 'taxa_palco':
                    if self.desconto_irmaos:
                        observacao = '12% de desconto para irmãs(ãos)'
                    else:
                        observacao = '5% de desconto à vista'
                elif self.tipo == 'figurino':
                    observacao = 'Valor à vista definido no cadastro'
                else:
                    observacao = 'Pagamento à vista'
            else:
                label = f'{parcelas}x'
                texto_valor = f'R$ {valor_parcela} por parcela'

                if self.sem_desconto:
                    observacao = 'Sem desconto (valor integral)'
                elif self.tipo == 'figurino':
                    observacao = 'Valor parcelado definido no cadastro'
                elif self.tipo == 'taxa_palco' and self.desconto_irmaos:
                    observacao = '10% de desconto para irmãs(ãos)'
                else:
                    observacao = 'Sem desconto'

            opcoes.append({
                'parcelas': parcelas,
                'label': label,
                'texto_valor': texto_valor,
                'observacao': observacao,
                'valor_final': valor_final,
                'valor_parcela': valor_parcela,
                'percentual_desconto': percentual_desconto,
            })

        return opcoes

    def total_pago(self):
        parcelas_cache = self._parcelas_prefetch()
        if parcelas_cache is not None:
            total = sum(
                ((p.valor_pago or Decimal('0.00')) for p in parcelas_cache),
                Decimal('0.00')
            )
            return total

        total = self.parcelas.aggregate(
            total=models.Sum('valor_pago')
        )['total']
        return total or Decimal('0.00')

    def valor_total_efetivo(self):
        parcelas_cache = self._parcelas_prefetch()
        if parcelas_cache is not None:
            if parcelas_cache:
                total = sum(
                    (p.valor or Decimal('0.00') for p in parcelas_cache),
                    Decimal('0.00')
                )
                return total
            return self.valor_total

        if self.parcelas.exists():
            total = self.parcelas.aggregate(
                total=models.Sum('valor')
            )['total']
            return total or Decimal('0.00')

        return self.valor_total

    def total_pendente(self):
        pendente = self.valor_total_efetivo() - self.total_pago()
        return pendente if pendente > Decimal('0.00') else Decimal('0.00')

    def atualizar_status(self):
        total_pago = self.total_pago()
        total_efetivo = self.valor_total_efetivo()

        if total_pago <= Decimal('0.00'):
            self.status = 'pendente'
        elif total_pago >= total_efetivo:
            self.status = 'pago'
        else:
            self.status = 'parcial'

        self.save(update_fields=['status'])


class ParcelaCobrancaEspetaculo(models.Model):
    STATUS_CHOICES = (
        ('pendente', 'Pendente'),
        ('parcial', 'Parcial'),
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
    valor_pago = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    vencimento = models.DateField(blank=True, null=True)
    mes_liberacao = models.DateField(blank=True, null=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pendente')
    data_pagamento = models.DateTimeField(blank=True, null=True)
    observacao_pagamento = models.TextField(blank=True, null=True)
    forma_pagamento_manual = models.CharField(max_length=30, blank=True, null=True)

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

    def saldo_pendente(self):
        saldo = (self.valor or Decimal('0.00')) - (self.valor_pago or Decimal('0.00'))
        return saldo if saldo > Decimal('0.00') else Decimal('0.00')

    def atualizar_status_local(self, salvar=True):
        valor = self.valor or Decimal('0.00')
        valor_pago = self.valor_pago or Decimal('0.00')

        if valor_pago <= Decimal('0.00'):
            self.status = 'pendente'
            self.data_pagamento = None
        elif valor_pago < valor:
            self.status = 'parcial'
        else:
            self.status = 'pago'
            self.valor_pago = valor
            if not self.data_pagamento:
                self.data_pagamento = timezone.now()

        if salvar:
            self.save(update_fields=['status', 'data_pagamento', 'valor_pago'])

    def registrar_pagamento(self, valor, forma_pagamento=None, observacao=None):
        valor = Decimal(str(valor or '0')).quantize(Decimal('0.01'))

        if valor <= Decimal('0.00'):
            raise ValidationError('O valor do pagamento deve ser maior que zero.')

        novo_total = (self.valor_pago or Decimal('0.00')) + valor

        if novo_total > (self.valor or Decimal('0.00')):
            raise ValidationError('O valor informado ultrapassa o saldo pendente da parcela.')

        self.valor_pago = novo_total

        if forma_pagamento:
            self.forma_pagamento_manual = forma_pagamento

        if observacao:
            texto_atual = (self.observacao_pagamento or '').strip()
            complemento = observacao.strip()
            self.observacao_pagamento = f'{texto_atual}\n{complemento}'.strip() if texto_atual else complemento

        self.atualizar_status_local(salvar=True)
        self.cobranca.atualizar_status()

    def marcar_como_pago(self):
        self.valor_pago = self.valor or Decimal('0.00')
        self.status = 'pago'
        self.data_pagamento = timezone.now()
        self.save(update_fields=['valor_pago', 'status', 'data_pagamento'])
        self.cobranca.atualizar_status()

    def atualizar_status_asaas(self, novo_status):
        novo_status = (novo_status or '').strip()

        campos_para_salvar = ['asaas_status']
        self.asaas_status = novo_status

        valor_integral = self.valor or Decimal('0.00')
        valor_pago_atual = self.valor_pago or Decimal('0.00')

        status_pago_asaas = {'RECEIVED', 'CONFIRMED', 'RECEIVED_IN_CASH', 'PAID'}

        if novo_status in status_pago_asaas:
            if valor_pago_atual != valor_integral:
                self.valor_pago = valor_integral
                campos_para_salvar.append('valor_pago')

            if self.status != 'pago':
                self.status = 'pago'
                campos_para_salvar.append('status')

            if not self.data_pagamento:
                self.data_pagamento = timezone.now()
                campos_para_salvar.append('data_pagamento')

        elif valor_pago_atual > Decimal('0.00'):
            if valor_pago_atual >= valor_integral:
                if self.status != 'pago':
                    self.status = 'pago'
                    campos_para_salvar.append('status')
                if not self.data_pagamento:
                    self.data_pagamento = timezone.now()
                    campos_para_salvar.append('data_pagamento')
            else:
                if self.status != 'parcial':
                    self.status = 'parcial'
                    campos_para_salvar.append('status')

        else:
            if self.status != 'pendente':
                self.status = 'pendente'
                campos_para_salvar.append('status')

            if self.data_pagamento is not None:
                self.data_pagamento = None
                campos_para_salvar.append('data_pagamento')

        self.save(update_fields=list(dict.fromkeys(campos_para_salvar)))
        self.cobranca.atualizar_status()


class PedidoIngressoEvento(models.Model):
    STATUS_CHOICES = [
        ('pendente', 'Pendente'),
        ('pago', 'Pago'),
        ('cancelado', 'Cancelado'),
        ('expirado', 'Expirado'),
    ]

    evento = models.ForeignKey(
        'Espetaculo',
        on_delete=models.CASCADE,
        related_name='pedidos_ingresso'
    )
    nome_completo = models.CharField(max_length=200)
    email = models.EmailField(blank=True)
    whatsapp = models.CharField(max_length=20)
    cpf = models.CharField(max_length=14, blank=True)
    quantidade = models.PositiveIntegerField(default=1)

    valor_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    valor_total = models.DecimalField(max_digits=10, decimal_places=2)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pendente'
    )
    data_pagamento = models.DateTimeField(blank=True, null=True)

    asaas_payment_id = models.CharField(max_length=100, blank=True, null=True)
    asaas_customer_id = models.CharField(max_length=100, blank=True, null=True)
    asaas_status = models.CharField(max_length=50, blank=True, null=True)
    asaas_invoice_url = models.URLField(blank=True, null=True)

    codigo_pix = models.TextField(blank=True, null=True)
    qr_code_pix = models.TextField(blank=True, null=True)
    external_reference = models.CharField(max_length=100, blank=True, null=True)

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Pedido de ingresso'
        verbose_name_plural = 'Pedidos de ingressos'
        ordering = ['-criado_em']

    def __str__(self):
        return f'{self.nome_completo} - {self.evento.titulo}'

    def marcar_como_pago(self):
        if self.status != 'pago':
            self.status = 'pago'
            self.data_pagamento = timezone.now()
            self.save(update_fields=['status', 'data_pagamento', 'atualizado_em'])

    @property
    def ingresso_gerado(self):
        return self.ingressos.exists()


class IngressoEvento(models.Model):
    STATUS_CHOICES = [
        ('ativo', 'Ativo'),
        ('usado', 'Usado'),
        ('cancelado', 'Cancelado'),
    ]

    pedido = models.ForeignKey(
        PedidoIngressoEvento,
        on_delete=models.CASCADE,
        related_name='ingressos'
    )
    evento = models.ForeignKey(
        'Espetaculo',
        on_delete=models.CASCADE,
        related_name='ingressos'
    )

    assento = models.ForeignKey(
        'Assento',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ingressos',
        help_text='Preenchido apenas quando o evento usa venda com assentos numerados.',
    )

    codigo_unico = models.CharField(
        max_length=50,
        unique=True,
        editable=False
    )

    nome_participante = models.CharField(max_length=200, blank=True)

    qrcode_image = models.ImageField(
        upload_to='ingressos/qrcodes/',
        blank=True,
        null=True
    )
    imagem_ingresso = models.ImageField(
        upload_to='ingressos/finais/',
        blank=True,
        null=True
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='ativo'
    )
    validado_em = models.DateTimeField(blank=True, null=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Ingresso'
        verbose_name_plural = 'Ingressos'
        ordering = ['-criado_em']

    def __str__(self):
        return f'{self.evento.titulo} - {self.codigo_unico}'

    def save(self, *args, **kwargs):
        if not self.codigo_unico:
            self.codigo_unico = self.gerar_codigo()
        super().save(*args, **kwargs)

    @staticmethod
    def gerar_codigo():
        return uuid.uuid4().hex[:12].upper()

    def marcar_como_usado(self):
        if self.status != 'usado':
            self.status = 'usado'
            self.validado_em = timezone.now()
            self.save(update_fields=['status', 'validado_em'])

    def cancelar_e_liberar_assento(self):
        """
        Cancela o ingresso e devolve o assento vinculado
        (se houver) para disponível. Usado nos testes e
        em cancelamentos manuais pelo admin.
        """
        if self.status != 'cancelado':
            self.status = 'cancelado'
            self.save(update_fields=['status'])

        if self.assento_id:
            self.assento.liberar()

    def qr_payload(self):
        return (
            f"Ingresso: {self.codigo_unico}\n"
            f"Evento: {self.evento.titulo}\n"
            f"Participante: {self.nome_participante}\n"
            f"Pedido: {self.pedido_id}"
        )

    def gerar_qrcode_image(self, force=False):
        if self.qrcode_image and not force:
            storage = self.qrcode_image.storage
            if self.qrcode_image.name and storage.exists(self.qrcode_image.name):
                return

        qr = qrcode.QRCode(
            version=1,
            box_size=10,
            border=4,
        )
        qr.add_data(self.qr_payload())
        qr.make(fit=True)

        img_qr = qr.make_image(fill_color="black", back_color="white").convert("RGB")

        buffer = BytesIO()
        img_qr.save(buffer, format='PNG')
        buffer.seek(0)

        filename = f"qr-{self.codigo_unico}.png"
        self.qrcode_image.save(filename, ContentFile(buffer.read()), save=False)

    def gerar_imagem_ingresso(self, force=False):
        if self.imagem_ingresso and not force:
            storage = self.imagem_ingresso.storage
            if self.imagem_ingresso.name and storage.exists(self.imagem_ingresso.name):
                return

        if not self.qrcode_image or not self.qrcode_image.name or not self.qrcode_image.storage.exists(self.qrcode_image.name):
            self.gerar_qrcode_image(force=force)

        largura, altura = 1200, 1600
        canvas = Image.new("RGB", (largura, altura), "white")
        draw = ImageDraw.Draw(canvas)

        fonte_titulo = ImageFont.load_default()
        fonte_texto = ImageFont.load_default()
        fonte_codigo = ImageFont.load_default()

        imagem_evento = None
        if hasattr(self.evento, 'imagem') and self.evento.imagem:
            try:
                self.evento.imagem.open('rb')
                imagem_evento = Image.open(self.evento.imagem).convert("RGB")
            except Exception:
                imagem_evento = None

        if imagem_evento:
            imagem_evento = imagem_evento.resize((largura, 700))
            canvas.paste(imagem_evento, (0, 0))
            draw.rectangle([(0, 700), (largura, altura)], fill="white")
        else:
            draw.rectangle([(0, 0), (largura, 700)], fill=(230, 230, 230))
            draw.rectangle([(0, 700), (largura, altura)], fill="white")

        draw.text((60, 760), self.evento.titulo or "Evento", fill="black", font=fonte_titulo)
        draw.text((60, 840), f"Participante: {self.nome_participante or '-'}", fill="black", font=fonte_texto)
        draw.text((60, 900), f"Código: {self.codigo_unico}", fill="black", font=fonte_codigo)

        if self.assento_id:
            draw.text(
                (60, 930),
                f"Assento: {self.assento.fileira}{self.assento.numero}",
                fill="black",
                font=fonte_texto
            )

        data_evento = getattr(self.evento, 'data_apresentacao', None)
        if data_evento:
            draw.text(
                (60, 960),
                f"Data: {timezone.localtime(data_evento).strftime('%d/%m/%Y %H:%M')}" if timezone.is_aware(data_evento) else f"Data: {data_evento.strftime('%d/%m/%Y %H:%M')}",
                fill="black",
                font=fonte_texto
            )

        if self.qrcode_image and self.qrcode_image.name:
            self.qrcode_image.open('rb')
            qr_img = Image.open(self.qrcode_image).convert("RGB")
            qr_img = qr_img.resize((320, 320))
            canvas.paste(qr_img, (60, 1080))

        draw.text((420, 1120), "Apresente este ingresso na entrada.", fill="black", font=fonte_texto)
        draw.text((420, 1180), "Formato digital válido com QR code.", fill="black", font=fonte_texto)

        buffer = BytesIO()
        canvas.save(buffer, format='PNG')
        buffer.seek(0)

        filename = f"ingresso-{self.codigo_unico}.png"
        self.imagem_ingresso.save(filename, ContentFile(buffer.read()), save=False)

    def garantir_arquivos(self, force=False, save=True):
        self.gerar_qrcode_image(force=force)
        self.gerar_imagem_ingresso(force=force)

        if save:
            self.save(update_fields=['qrcode_image', 'imagem_ingresso'])


class MapaAssentos(models.Model):
    """
    Guarda o mapa de assentos de um evento: a imagem do teatro
    e o conjunto de assentos posicionados sobre ela.
    """

    evento = models.OneToOneField(
        'Espetaculo',
        on_delete=models.CASCADE,
        related_name='mapa_assentos',
    )

    imagem_mapa = models.ImageField(
        upload_to='espetaculos/mapas_assentos/',
        blank=True,
        null=True,
        help_text='Imagem de fundo do teatro/salão usada no mapa.',
    )

    largura_original = models.PositiveIntegerField(
        default=1600,
        help_text='Largura original (em pixels) usada para gerar as coordenadas.',
    )

    altura_original = models.PositiveIntegerField(
        default=1200,
        help_text='Altura original (em pixels) usada para gerar as coordenadas.',
    )

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Mapa de assentos'
        verbose_name_plural = 'Mapas de assentos'

    def __str__(self):
        return f'Mapa de assentos - {self.evento.titulo}'

    @property
    def total_assentos(self):
        return self.assentos.count()

    @property
    def total_disponiveis(self):
        return self.assentos.filter(status='disponivel').count()

    @property
    def total_vendidos(self):
        return self.assentos.filter(status='vendido').count()

    @property
    def total_bloqueados(self):
        return self.assentos.filter(status='bloqueado_manual').count()

    @property
    def total_reservados_temporariamente(self):
        return self.assentos.filter(status='reservado_temporario').count()


class Assento(models.Model):
    """
    Um assento específico dentro do mapa de um evento.
    O status controla se ele pode ser escolhido, está em
    processo de pagamento, foi vendido ou foi bloqueado
    manualmente pelo admin (ex: reservado para patrocinador).
    """

    STATUS_CHOICES = [
        ('disponivel', 'Disponível'),
        ('reservado_temporario', 'Reservado temporariamente'),
        ('vendido', 'Vendido'),
        ('bloqueado_manual', 'Bloqueado manualmente'),
    ]

    mapa = models.ForeignKey(
        'MapaAssentos',
        on_delete=models.CASCADE,
        related_name='assentos',
    )

    identificador = models.CharField(
        max_length=20,
        help_text='ID do assento vindo do JSON (ex: A1, A2).',
    )

    setor = models.CharField(
        max_length=50,
        blank=True,
    )

    fileira = models.CharField(max_length=10)

    numero = models.PositiveIntegerField()

    x_pct = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        help_text='Posição horizontal em porcentagem (0 a 100) sobre a imagem do mapa.',
    )

    y_pct = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        help_text='Posição vertical em porcentagem (0 a 100) sobre a imagem do mapa.',
    )

    status = models.CharField(
        max_length=25,
        choices=STATUS_CHOICES,
        default='disponivel',
    )

    reservado_em = models.DateTimeField(
        blank=True,
        null=True,
        help_text='Momento em que a reserva temporária começou.',
    )

    reservado_por_sessao = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text='Identificador da sessão/comprador que reservou temporariamente.',
    )

    bloqueado_motivo = models.CharField(
        max_length=200,
        blank=True,
        help_text='Motivo do bloqueio manual (ex: patrocinador, família).',
    )

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Assento'
        verbose_name_plural = 'Assentos'
        ordering = ['fileira', 'numero']
        unique_together = ('mapa', 'identificador')

    def __str__(self):
        return f'{self.fileira}{self.numero} - {self.mapa.evento.titulo} ({self.get_status_display()})'

    @property
    def esta_disponivel(self):
        return self.status == 'disponivel'

    @property
    def esta_reservado_expirado(self):
        """
        Verifica se uma reserva temporária já passou do tempo limite
        (usado depois para liberar assentos abandonados no pagamento).
        """
        if self.status != 'reservado_temporario' or not self.reservado_em:
            return False

        limite = self.reservado_em + timezone.timedelta(minutes=15)
        return timezone.now() > limite

    def reservar_temporariamente(self, identificador_sessao):
        self.status = 'reservado_temporario'
        self.reservado_em = timezone.now()
        self.reservado_por_sessao = identificador_sessao
        self.save(update_fields=[
            'status',
            'reservado_em',
            'reservado_por_sessao',
            'atualizado_em',
        ])

    def marcar_como_vendido(self):
        self.status = 'vendido'
        self.reservado_em = None
        self.reservado_por_sessao = None
        self.save(update_fields=[
            'status',
            'reservado_em',
            'reservado_por_sessao',
            'atualizado_em',
        ])

    def liberar(self):
        """Devolve o assento para disponível (cancelamento, reserva expirada, etc.)."""
        self.status = 'disponivel'
        self.reservado_em = None
        self.reservado_por_sessao = None
        self.bloqueado_motivo = ''
        self.save(update_fields=[
            'status',
            'reservado_em',
            'reservado_por_sessao',
            'bloqueado_motivo',
            'atualizado_em',
        ])

    def bloquear_manualmente(self, motivo=''):
        """Uso pelo admin: reserva o assento sem passar por venda (patrocinador, família, etc.)."""
        self.status = 'bloqueado_manual'
        self.reservado_em = None
        self.reservado_por_sessao = None
        self.bloqueado_motivo = motivo
        self.save(update_fields=[
            'status',
            'reservado_em',
            'reservado_por_sessao',
            'bloqueado_motivo',
            'atualizado_em',
        ])


class IngressoGratuitoAluna(models.Model):
    """
    Controla quantos ingressos gratuitos uma aluna já resgatou
    para um determinado evento (1 por evento por aluna).
    """

    aluna = models.ForeignKey(
        'usuarios.Aluna',
        on_delete=models.CASCADE,
        related_name='ingressos_gratuitos',
    )

    evento = models.ForeignKey(
        'Espetaculo',
        on_delete=models.CASCADE,
        related_name='ingressos_gratuitos_alunas',
    )

    pedido = models.ForeignKey(
        PedidoIngressoEvento,
        on_delete=models.CASCADE,
        related_name='ingressos_gratuitos_aluna',
    )

    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Ingresso gratuito de aluna'
        verbose_name_plural = 'Ingressos gratuitos de alunas'
        unique_together = ('aluna', 'evento')

    def __str__(self):
        return f'{self.aluna.nome} - {self.evento.titulo}'
