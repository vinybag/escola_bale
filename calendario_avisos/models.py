from django.db import models
from django.contrib.auth.models import User

class Aviso(models.Model):
    TIPO_CHOICES = [
        ('geral', 'Geral'),
        ('evento', 'Evento'),
        ('feriado', 'Feriado'),
        ('reposicao', 'Reposição'),
        ('apresentacao', 'Apresentação'),
    ]
    
    titulo = models.CharField(max_length=200)
    descricao = models.TextField()
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default='geral')
    data_evento = models.DateField(null=True, blank=True, help_text="Data do evento (se aplicável)")
    data_publicacao = models.DateTimeField(auto_now_add=True)
    ativo = models.BooleanField(default=True)
    autor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    class Meta:
        ordering = ['-data_publicacao']
        verbose_name = 'Aviso'
        verbose_name_plural = 'Avisos'
    
    def __str__(self):
        return self.titulo
