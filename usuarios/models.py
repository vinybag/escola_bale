from django.db import models
from django.contrib.auth.models import User

class Perfil(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='perfil')
    telefone = models.CharField(max_length=20)
    cpf = models.CharField(max_length=14, unique=True)
    data_nascimento = models.DateField(null=True, blank=True)
    endereco = models.CharField(max_length=200, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Perfil de {self.user.get_full_name() or self.user.username}"

class Aluna(models.Model):
    responsavel = models.ForeignKey(User, on_delete=models.CASCADE, related_name='alunas')
    nome = models.CharField(max_length=100)
    data_nascimento = models.DateField()
    turma_atual = models.CharField(max_length=50, blank=True)
    ativa = models.BooleanField(default=True)
    data_matricula = models.DateField(auto_now_add=True)
    observacoes = models.TextField(blank=True)
    
    def __str__(self):
        return self.nome
    
    @property
    def idade(self):
        from datetime import date
        hoje = date.today()
        return hoje.year - self.data_nascimento.year - ((hoje.month, hoje.day) < (self.data_nascimento.month, self.data_nascimento.day))