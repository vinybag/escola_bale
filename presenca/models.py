import secrets

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


# 0 = segunda ... 6 = domingo (mesma numeração do date.weekday() do Python)
DIAS_SEMANA = [
    (0, 'Segunda-feira'),
    (1, 'Terça-feira'),
    (2, 'Quarta-feira'),
    (3, 'Quinta-feira'),
    (4, 'Sexta-feira'),
    (5, 'Sábado'),
    (6, 'Domingo'),
]
DIAS_CURTOS = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom']


def gerar_token():
    """Código secreto que vai dentro do QR Code (impossível de adivinhar)."""
    return secrets.token_urlsafe(24)


class ConfiguracaoPresenca(models.Model):
    """
    Configuração única (uma linha só) do controle de presença.
    Sempre use ConfiguracaoPresenca.obter().
    """

    data_inicio_controle = models.DateField(
        default=timezone.localdate,
        verbose_name='Início do controle de presença',
        help_text=(
            'Aulas anteriores a esta data nunca contam como falta. '
            'Serve para as alunas não "ganharem" faltas de antes do sistema existir.'
        ),
    )
    minutos_antes = models.PositiveSmallIntegerField(
        default=30,
        verbose_name='Minutos antes da aula em que o registro abre',
    )
    minutos_depois = models.PositiveSmallIntegerField(
        default=0,
        verbose_name='Minutos depois do fim da aula em que o registro ainda vale',
    )
    token_qr = models.CharField(max_length=64, default=gerar_token)
    qr_gerado_em = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'Configuração da presença'
        verbose_name_plural = 'Configuração da presença'

    def __str__(self):
        return 'Configuração da lista de presença'

    @classmethod
    def obter(cls):
        config, _ = cls.objects.get_or_create(pk=1)
        return config

    def regenerar_token(self):
        self.token_qr = gerar_token()
        self.qr_gerado_em = timezone.now()
        self.save(update_fields=['token_qr', 'qr_gerado_em'])


class HorarioTurma(models.Model):
    """Dia da semana + hora de início/fim de uma aula da turma."""

    turma = models.ForeignKey(
        'usuarios.Turma',
        on_delete=models.CASCADE,
        related_name='horarios_aula',
    )
    dia_semana = models.PositiveSmallIntegerField(choices=DIAS_SEMANA)
    hora_inicio = models.TimeField()
    hora_fim = models.TimeField()
    preenchido_automaticamente = models.BooleanField(
        default=False,
        help_text='Preenchido pelo sistema a partir do texto antigo do horário. Precisa ser conferido.',
    )

    class Meta:
        verbose_name = 'Horário da turma'
        verbose_name_plural = 'Horários das turmas'
        ordering = ['dia_semana', 'hora_inicio']
        constraints = [
            models.UniqueConstraint(
                fields=['turma', 'dia_semana'],
                name='presenca_um_horario_por_dia_na_turma',
            ),
        ]

    def __str__(self):
        return f'{self.turma} - {self.dia_nome} {self.intervalo_texto}'

    def clean(self):
        if self.hora_inicio and self.hora_fim and self.hora_fim <= self.hora_inicio:
            raise ValidationError('A hora de fim precisa ser depois da hora de início.')

    @property
    def dia_nome(self):
        return dict(DIAS_SEMANA).get(self.dia_semana, '')

    @property
    def dia_curto(self):
        return DIAS_CURTOS[self.dia_semana]

    @property
    def intervalo_texto(self):
        return f'{self.hora_inicio:%H:%M}–{self.hora_fim:%H:%M}'


class DiaSemAula(models.Model):
    """Feriado/recesso: nesses dias ninguém recebe falta."""

    data = models.DateField()
    turma = models.ForeignKey(
        'usuarios.Turma',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='dias_sem_aula',
        help_text='Vazio = vale para todas as turmas.',
    )
    motivo = models.CharField(max_length=120, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Dia sem aula'
        verbose_name_plural = 'Dias sem aula'
        ordering = ['-data']

    def __str__(self):
        alvo = self.turma.nome if self.turma_id else 'todas as turmas'
        return f'{self.data:%d/%m/%Y} - {alvo}'


class Presenca(models.Model):
    """
    Presença de uma aluna em UMA aula (turma + data).

    "Desmarcar" não apaga: marca como anulada (guarda quem e quando) e a aula
    passa a contar como falta. Como existe uma única linha por aluna/turma/dia,
    a aluna também não consegue registrar de novo pelo QR Code depois disso.
    """

    ORIGEM_QR = 'qr'
    ORIGEM_MANUAL = 'manual'
    ORIGENS = [
        (ORIGEM_QR, 'QR Code'),
        (ORIGEM_MANUAL, 'Marcada pela escola'),
    ]

    aluna = models.ForeignKey(
        'usuarios.Aluna',
        on_delete=models.CASCADE,
        related_name='presencas',
    )
    turma = models.ForeignKey(
        'usuarios.Turma',
        on_delete=models.CASCADE,
        related_name='presencas',
    )
    data = models.DateField()
    registrada_em = models.DateTimeField(default=timezone.now)
    registrada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='presencas_registradas',
    )
    origem = models.CharField(max_length=10, choices=ORIGENS, default=ORIGEM_QR)

    anulada = models.BooleanField(default=False)
    anulada_em = models.DateTimeField(null=True, blank=True)
    anulada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='presencas_desmarcadas',
    )
    motivo_anulacao = models.CharField(max_length=200, blank=True)

    class Meta:
        verbose_name = 'Presença'
        verbose_name_plural = 'Presenças'
        ordering = ['-data', '-registrada_em']
        constraints = [
            models.UniqueConstraint(
                fields=['aluna', 'turma', 'data'],
                name='presenca_unica_por_aluna_turma_dia',
            ),
        ]
        indexes = [
            models.Index(fields=['data']),
        ]

    def __str__(self):
        return f'{self.aluna} - {self.turma} - {self.data:%d/%m/%Y}'

    def anular(self, usuario, motivo=''):
        self.anulada = True
        self.anulada_em = timezone.now()
        self.anulada_por = usuario
        self.motivo_anulacao = (motivo or '')[:200]
        self.save(update_fields=['anulada', 'anulada_em', 'anulada_por', 'motivo_anulacao'])

    def restaurar(self, usuario=None):
        self.anulada = False
        self.anulada_em = None
        self.anulada_por = None
        self.motivo_anulacao = ''
        self.save(update_fields=['anulada', 'anulada_em', 'anulada_por', 'motivo_anulacao'])
