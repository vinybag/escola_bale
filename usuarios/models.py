from django.db import models
from django.contrib.auth.models import User
import secrets
from datetime import timedelta
from django.utils import timezone

class Perfil(models.Model):
    """Perfil completo do usuario/responsavel"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='perfil')
    telefone = models.CharField(max_length=20, blank=True)
    cpf = models.CharField(max_length=14, blank=True)
    data_nascimento = models.DateField(null=True, blank=True)
    endereco = models.CharField(max_length=200, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Perfil de {self.user.get_full_name() or self.user.username}"
    
    class Meta:
        verbose_name = 'Perfil'
        verbose_name_plural = 'Perfis'


class Aluna(models.Model):
    """Modelo para as alunas de ballet"""
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
        return hoje.year - self.data_nascimento.year - (
            (hoje.month, hoje.day) < (self.data_nascimento.month, self.data_nascimento.day)
        )
    
    class Meta:
        verbose_name = 'Aluna'
        verbose_name_plural = 'Alunas'
        ordering = ['nome']


class RecuperacaoSenha(models.Model):
    """Token para recuperacao de senha via SMS"""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    token = models.CharField(max_length=100, unique=True)
    codigo_sms = models.CharField(max_length=6, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    usado = models.BooleanField(default=False)
    
    def __str__(self):
        return f"Token de {self.user.email}"
    
    def is_valido(self):
        """Verifica se token ainda e valido (24h)"""
        expiracao = self.criado_em + timedelta(hours=24)
        return not self.usado and timezone.now() < expiracao
    
    @classmethod
    def criar_token(cls, user):
        """Cria um novo token de recuperacao"""
        token = secrets.token_urlsafe(32)
        return cls.objects.create(user=user, token=token)