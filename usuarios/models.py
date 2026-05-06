from django.db import models
from django.contrib.auth.models import User
import secrets
from datetime import timedelta
from django.utils import timezone

class Perfil(models.Model):
    """Perfil completo do usuario/responsavel"""
    
    GENERO_CHOICES = [
        ('M', 'Masculino'),
        ('F', 'Feminino'),
        ('O', 'Outro'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='perfil')
    telefone = models.CharField(max_length=20, blank=True, null=True)
    cpf = models.CharField(max_length=14, blank=True, null=True)
    data_nascimento = models.DateField(null=True, blank=True)
    endereco = models.CharField(max_length=200, blank=True, null=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    is_responsavel = models.BooleanField(default=True)  # Indica se é responsável de verdade
    is_tambem_aluno = models.BooleanField(default=False)  # Responsável também é aluno
    genero = models.CharField(max_length=1, choices=GENERO_CHOICES, blank=True, null=True)
    
    def __str__(self):
        return f"Perfil de {self.user.get_full_name() or self.user.username}"
    
    class Meta:
        verbose_name = 'Perfil'
        verbose_name_plural = 'Perfis'


class Turma(models.Model):
    """Turmas de ballet"""
    nome = models.CharField(max_length=100, unique=True)
    descricao = models.TextField(blank=True)
    horario = models.CharField(max_length=100, blank=True, help_text="Ex: Segunda e Quarta 14h-15h")
    professor = models.CharField(max_length=100, blank=True)
    capacidade_maxima = models.IntegerField(default=20, help_text="Número máximo de alunas")
    ativa = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.nome
    
    @property
    def total_alunas(self):
        """Total de alunas ativas na turma"""
        return self.alunas.filter(ativa=True).count()
    
    @property
    def vagas_disponiveis(self):
        """Vagas disponíveis"""
        return self.capacidade_maxima - self.total_alunas
    
    @property
    def percentual_ocupacao(self):
        """Percentual de ocupação da turma"""
        if self.capacidade_maxima == 0:
            return 0
        return int((self.total_alunas / self.capacidade_maxima) * 100)
    
    class Meta:
        verbose_name = 'Turma'
        verbose_name_plural = 'Turmas'
        ordering = ['nome']


class Aluna(models.Model):
    TIPO_ALUNAS = [
        ('infantil', 'Infantil (com responsável)'),
        ('adulto', 'Adulto (sem responsável)'),
    ]
    
    GENERO_CHOICES = [
        ('M', 'Masculino'),
        ('F', 'Feminino'),
        ('O', 'Outro'),
    ]
    
    responsavel = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='alunas')
    tipo_aluna = models.CharField(max_length=20, choices=TIPO_ALUNAS, default='infantil')
    nome = models.CharField(max_length=100)
    genero = models.CharField(max_length=1, choices=GENERO_CHOICES, blank=True, null=True)
    data_nascimento = models.DateField(null=True, blank=True)
    turmas = models.ManyToManyField('Turma', blank=True, related_name='alunas')
    ativa = models.BooleanField(default=True)
    data_matricula = models.DateField(auto_now_add=True)
    observacoes = models.TextField(blank=True)
    
    def __str__(self):
        genero_texto = dict(self.GENERO_CHOICES).get(self.genero, '')
        return f"{self.nome} ({genero_texto})" if genero_texto else self.nome
    
    @property
    def idade(self):
        """Calcula a idade da aluna com base na data de nascimento"""
        from datetime import date
        if not self.data_nascimento:
            return None
        hoje = date.today()
        idade = hoje.year - self.data_nascimento.year
        if (hoje.month, hoje.day) < (self.data_nascimento.month, self.data_nascimento.day):
            idade -= 1
        return idade
    
    class Meta:
        verbose_name = 'Aluna'
        verbose_name_plural = 'Alunas'
        ordering = ['nome']


class RecuperacaoSenha(models.Model):
    """Token para recuperacao de senha via email"""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    token = models.CharField(max_length=100, unique=True)
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
    
    class Meta:
        verbose_name = 'Recuperacao de Senha'
        verbose_name_plural = 'Recuperacoes de Senha'