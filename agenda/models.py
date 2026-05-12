from django.db import models


# Classe Aula será removida depois, por enquanto vamos mantê-la mas não usar mais
class Aula(models.Model):
    nome = models.CharField(max_length=100)
    dia_semana = models.CharField(
        max_length=20,
        choices=[
            ('Segunda', 'Segunda-feira'),
            ('Terça', 'Terça-feira'),
            ('Quarta', 'Quarta-feira'),
            ('Quinta', 'Quinta-feira'),
            ('Sexta', 'Sexta-feira'),
            ('Sábado', 'Sábado'),
        ]
    )
    horario = models.TimeField()
    ativa = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.nome} - {self.dia_semana} às {self.horario}"


class Agendamento(models.Model):
    nome_responsavel = models.CharField(
        max_length=100,
        verbose_name="Nome do responsável"
    )
    nome_aluna = models.CharField(
        max_length=100,
        verbose_name="Nome da aluna(o)"
    )
    idade_aluna = models.PositiveIntegerField(
        verbose_name="Idade da aluna(o)"
    )
    email = models.EmailField(
        verbose_name="E-mail"
    )
    telefone = models.CharField(
        max_length=20,
        verbose_name="Telefone"
    )
    data = models.DateField(
        verbose_name="Data da aula"
    )
    horario = models.TimeField(
        verbose_name="Horário da aula"
    )
    criado_em = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Criado em"
    )
    
    # ALTERADO: Agora usa Turma do app usuarios
    aula = models.ForeignKey(
        'usuarios.Turma',  # Mudou para o modelo Turma
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Turma/Aula escolhida'
    )

    def __str__(self):
        return f"{self.nome_aluna} - {self.data} às {self.horario}"



 
