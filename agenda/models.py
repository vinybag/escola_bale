from decimal import Decimal

from django.db import models


# Classe antiga. Pode ser removida futuramente.
class Aula(models.Model):
    nome = models.CharField(max_length=100)

    dia_semana = models.CharField(
        max_length=20,
        choices=[
            ("Segunda", "Segunda-feira"),
            ("Terça", "Terça-feira"),
            ("Quarta", "Quarta-feira"),
            ("Quinta", "Quinta-feira"),
            ("Sexta", "Sexta-feira"),
            ("Sábado", "Sábado"),
        ],
    )

    horario = models.TimeField()
    ativa = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.nome} - {self.dia_semana} às {self.horario}"


class Agendamento(models.Model):
    STATUS_PAGAMENTO_CHOICES = [
        ("gratuito", "Gratuito"),
        ("pendente", "Pagamento pendente"),
        ("pago", "Pago"),
    ]

    nome_responsavel = models.CharField(
        max_length=100,
        verbose_name="Nome do responsável",
    )

    nome_aluna = models.CharField(
        max_length=100,
        verbose_name="Nome da aluna(o)",
    )

    idade_aluna = models.PositiveIntegerField(
        verbose_name="Idade da aluna(o)",
    )

    email = models.EmailField(
        verbose_name="E-mail",
    )

    telefone = models.CharField(
        max_length=20,
        verbose_name="Telefone",
    )

    data = models.DateField(
        verbose_name="Data da aula",
    )

    horario = models.TimeField(
        verbose_name="Horário da aula",
    )

    criado_em = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Criado em",
    )

    aula = models.ForeignKey(
        "usuarios.Turma",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Turma/Aula escolhida",
    )

    aluna_vinculada = models.ForeignKey(
        "usuarios.Aluna",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="agendamentos_experimentais",
        verbose_name="Aluna vinculada (se já for aluna Bailah)",
    )

    status_pagamento = models.CharField(
        max_length=20,
        choices=STATUS_PAGAMENTO_CHOICES,
        default="pago",
        verbose_name="Status do pagamento",
    )

    valor = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Valor da aula experimental",
    )

    asaas_payment_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
    )

    asaas_customer_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
    )

    evento_calendario_criado = models.BooleanField(
        default=True,
        verbose_name="Evento criado no Google Agenda",
    )

    def __str__(self):
        return f"{self.nome_aluna} - {self.data} às {self.horario}"


class ConfiguracaoAgendamento(models.Model):
    campanha_gratuita_ativa = models.BooleanField(
        default=False,
        verbose_name="Campanha de aula experimental gratuita ativa",
    )

    turmas_gratuitas = models.ManyToManyField(
        "usuarios.Turma",
        blank=True,
        related_name="configuracoes_campanha_gratuita",
        verbose_name="Turmas gratuitas",
    )

    valor_aula_experimental = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("25.00"),
        verbose_name="Valor da aula experimental",
    )

    atualizado_em = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        verbose_name = "Configuração de Agendamento"
        verbose_name_plural = "Configurações de Agendamento"

    def __str__(self):
        return "Configurações da Aula Experimental"

    @classmethod
    def obter(cls):
        configuracao, _ = cls.objects.get_or_create(pk=1)
        return configuracao

    def turma_e_gratuita(self, turma):
        """
        Retorna True se a turma estiver gratuita no momento.

        Regras:
        - campanha desligada: nenhuma turma gratuita;
        - campanha ligada sem turmas selecionadas: todas gratuitas;
        - campanha ligada com turmas selecionadas: somente as selecionadas.
        """
        if not self.campanha_gratuita_ativa:
            return False

        if not self.turmas_gratuitas.exists():
            return True

        return self.turmas_gratuitas.filter(pk=turma.pk).exists()