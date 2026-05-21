from django.db import models
from django.contrib.auth.models import User
from usuarios.models import Aluna
from datetime import date


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
    
    def __str__(self):
        return f"{self.aluna.nome} - {self.mes_referencia.strftime('%m/%Y')}"
    
    @property
    def esta_atrasada(self):
        if self.status == 'pendente' and self.data_vencimento < date.today():
            return True
        return False
    
    def save(self, *args, **kwargs):
        if self.status == 'vencida':
            self.status = 'atrasado'

        if self.data_pagamento and self.status in ['pendente', 'atrasado']:
            self.status = 'pago'
        elif self.esta_atrasada and self.status == 'pendente':
            self.status = 'atrasado'

        super().save(*args, **kwargs)