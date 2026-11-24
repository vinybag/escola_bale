from decimal import Decimal

from django.conf import settings
from django.db import models


class Produto(models.Model):
    """Produto da cantina. O código de barras é opcional (serve para o leitor, quando a venda chegar)."""

    nome = models.CharField(max_length=120)
    categoria = models.CharField(max_length=60, blank=True, help_text='Ex.: Bebidas, Salgados, Doces.')
    preco = models.DecimalField('preço de venda', max_digits=8, decimal_places=2)
    custo = models.DecimalField('preço de custo', max_digits=8, decimal_places=2, null=True, blank=True)
    quantidade = models.IntegerField('quantidade em estoque', default=0)
    estoque_minimo = models.PositiveIntegerField(
        default=0, help_text='Avisa quando a quantidade chegar neste número ou menos. 0 = sem aviso.',
    )
    codigo_barras = models.CharField(
        'código de barras', max_length=64, unique=True, null=True, blank=True,
        help_text='Opcional. Aponte o leitor para o campo e leia o código.',
    )
    ativo = models.BooleanField(default=True)
    observacao = models.CharField('observação', max_length=300, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['nome']
        verbose_name = 'Produto da cantina'
        verbose_name_plural = 'Produtos da cantina'

    def __str__(self):
        return self.nome

    def save(self, *args, **kwargs):
        self.nome = (self.nome or '').strip()
        self.codigo_barras = (self.codigo_barras or '').strip().replace(' ', '') or None
        super().save(*args, **kwargs)

    @property
    def sem_estoque(self):
        return self.quantidade <= 0

    @property
    def estoque_baixo(self):
        return self.estoque_minimo > 0 and 0 < self.quantidade <= self.estoque_minimo

    @property
    def situacao_estoque(self):
        if self.sem_estoque:
            return 'zerado'

        return 'baixo' if self.estoque_baixo else 'ok'

    @property
    def valor_em_estoque(self):
        return self.preco * max(self.quantidade, 0)

    @property
    def margem(self):
        """Lucro por unidade (preço − custo), quando o custo está cadastrado."""
        return None if self.custo is None else self.preco - self.custo


class MovimentoEstoque(models.Model):
    ENTRADA, SAIDA, PERDA, AJUSTE, VENDA = 'entrada', 'saida', 'perda', 'ajuste', 'venda'
    TIPOS = [
        (ENTRADA, 'Entrada (compra / reposição)'),
        (SAIDA, 'Saída (consumo interno, doação)'),
        (PERDA, 'Perda (vencido, quebrado)'),
        (AJUSTE, 'Contagem (definir a quantidade certa)'),
        (VENDA, 'Venda'),
    ]

    produto = models.ForeignKey(Produto, on_delete=models.CASCADE, related_name='movimentos')
    tipo = models.CharField(max_length=10, choices=TIPOS)
    variacao = models.IntegerField(help_text='Quanto entrou (+) ou saiu (−).')
    saldo_depois = models.IntegerField()
    motivo = models.CharField(max_length=200, blank=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-criado_em', '-pk']
        verbose_name = 'Movimentação de estoque'
        verbose_name_plural = 'Movimentações de estoque'

    def __str__(self):
        return f'{self.produto} {self.variacao:+d}'
