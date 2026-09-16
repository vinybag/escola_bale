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

    turmas = models.ManyToManyField(
        'usuarios.Turma',
        blank=True,
        related_name='avisos',
        verbose_name='Turmas destinatárias',
        help_text=(
            'Deixe em branco junto com "Alunas" e "Professoras" '
            'para exibir este aviso para todas.'
        ),
    )

    alunas = models.ManyToManyField(
        'usuarios.Aluna',
        blank=True,
        related_name='avisos_diretos',
        verbose_name='Alunas destinatárias',
        help_text='Use quando o aviso for para alunas específicas, além ou em vez das turmas.',
    )

    professoras = models.ManyToManyField(
        User,
        blank=True,
        related_name='avisos_professora',
        verbose_name='Professoras destinatárias',
        limit_choices_to={'groups__name': 'Professores'},
        help_text='Professoras que devem ver este aviso mesmo sem serem alunas da turma.',
    )

    class Meta:
        ordering = ['-data_publicacao']
        verbose_name = 'Aviso'
        verbose_name_plural = 'Avisos'

    def __str__(self):
        return self.titulo

    @property
    def visivel_para_todos(self):
        """
        Um aviso é geral (aparece para todo mundo) quando nenhum dos três
        filtros de destinatário foi configurado.
        """
        return (
            not self.turmas.exists()
            and not self.alunas.exists()
            and not self.professoras.exists()
        )
