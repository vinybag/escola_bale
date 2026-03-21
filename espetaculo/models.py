from django.db import models

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
    
    # PDF com informações completas - ADICIONA ESSA LINHA
    arquivo_informacoes = models.FileField(upload_to='espetaculos/pdfs/', blank=True, null=True, help_text='PDF com sinopse, personagens, audição, etc.')
    
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
