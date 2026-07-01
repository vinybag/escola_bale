from django.db import models
from django.contrib.auth.models import User
from usuarios.models import Aluna
from datetime import date
from decimal import Decimal


class Mensalidade(models.Model):
    STATUS_CHOICES = [
        ('pendente', 'Pendente'),
        ('pago', 'Pago'),
        ('atrasado', 'Atrasado'),
        ('cancelado', 'Cancelado'),
    ]

    FORMA_PAGAMENTO_CHOICES = [
        ('pix', 'PIX'),
        ('cartao', 'Cartão de Crédito'),
        ('dinheiro', 'Dinheiro'),
        ('transferencia', 'Transferência'),
    ]

    aluna = models.ForeignKey(Aluna, on_delete=models.CASCADE, related_name='mensalidades')
    responsavel = models.ForeignKey(User, on_delete=models.CASCADE, related_name='mensalidades')
    mes_referencia = models.DateField(verbose_name="Mês de referência")
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    data_vencimento = models.DateField()
    data_pagamento = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pendente')
    forma_pagamento = models.CharField(max_length=20, choices=FORMA_PAGAMENTO_CHOICES, null=True, blank=True)
    comprovante = models.TextField(blank=True, help_text="ID da transação ou observações")
    asaas_payment_id = models.CharField(max_length=100, blank=True, null=True)
    asaas_customer_id = models.CharField(max_length=100, blank=True, null=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-mes_referencia']
        verbose_name = 'Mensalidade'
        verbose_name_plural = 'Mensalidades'
        constraints = [
            models.UniqueConstraint(
                fields=['aluna', 'mes_referencia'],
                name='unique_mensalidade_aluna_mes_referencia'
            )
        ]

    def __str__(self):
        return f"{self.aluna.nome} - {self.mes_referencia.strftime('%m/%Y')}"

    @property
    def dias_atraso(self):
        if self.status == 'cancelado':
            return 0
        if self.data_pagamento or self.status == 'pago':
            return 0
        if not self.data_vencimento:
            return 0

        dias = (date.today() - self.data_vencimento).days
        return dias if dias > 0 else 0

    @property
    def esta_atrasada(self):
        return self.dias_atraso > 0

    @property
    def acrescimo_atraso(self):
        if self.status == 'cancelado':
            return Decimal('0.00')
        if self.data_pagamento or self.status == 'pago':
            return Decimal('0.00')

        if self.dias_atraso <= 0:
            return Decimal('0.00')
        if self.dias_atraso <= 9:
            return Decimal('10.00')
        return Decimal('15.00')

    @property
    def valor_atualizado(self):
        return (Decimal(self.valor) + self.acrescimo_atraso).quantize(Decimal('0.01'))

    @property
    def status_atual(self):
        if self.status == 'cancelado':
            return 'cancelado'
        if self.data_pagamento or self.status == 'pago':
            return 'pago'
        if self.esta_atrasada:
            return 'atrasado'
        return 'pendente'

    def save(self, *args, **kwargs):
        if self.data_pagamento:
            self.status = 'pago'
        elif self.status != 'cancelado':
            self.status = self.status_atual

        super().save(*args, **kwargs)