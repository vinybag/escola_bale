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

    # PDF com informações completas
    arquivo_informacoes = models.FileField(upload_to='espetaculos/pdfs/', blank=True, null=True, help_text='PDF com sinopse, personagens, audição, etc.')

    # NOVO CAMPO - Edital/Arquivo para download
    arquivo_edital = models.FileField(upload_to='espetaculos/editais/', blank=True, null=True, help_text='PDF com edital, regulamento ou material de apoio')

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


# Classe fora da Espetaculo
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
    espetaculo = models.ForeignKey(Espetaculo, on_delete=models.CASCADE, related_name='inscricoes', null=True, blank=True)
    data_inscricao = models.DateTimeField(auto_now_add=True)
    lida = models.BooleanField(default=False, verbose_name='Inscrição lida')

    def __str__(self):
        return f'{self.nome_completo} - {self.personagens}'

    class Meta:
        verbose_name = 'Inscrição para Audição'
        verbose_name_plural = 'Inscrições para Audição'
        ordering = ['-data_inscricao']