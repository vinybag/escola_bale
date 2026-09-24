from django.db import models
from django.contrib.auth.models import User


class Aviso(models.Model):
    TIPO_CHOICES = [
        ('geral', 'Geral'),
        ('evento', 'Evento'),
        ('feriado', 'Feriado'),
        ('reposicao', 'Reposição'),
        ('apresentacao', 'Apresentação'),
        ('ensaio', 'Ensaio'),
    ]

    titulo = models.CharField(max_length=200)
    descricao = models.TextField()
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default='geral')
    data_evento = models.DateField(null=True, blank=True, help_text="Data do evento (se aplicável)")
    horario = models.CharField(max_length=50, blank=True, verbose_name='Horário', help_text='Ex: 14h ou 14h às 16h')
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

    personagens = models.ManyToManyField(
        'espetaculo.Personagem',
        blank=True,
        related_name='avisos',
        verbose_name='Personagens destinatários',
        help_text='Avisa só quem está escalado nesses personagens (ex: ensaio só das protagonistas).',
    )

    enviar_whatsapp = models.BooleanField(
        default=False,
        verbose_name='Enviar por WhatsApp também',
        help_text='Além de aparecer no site, manda mensagem de WhatsApp pros destinatários.',
    )
    notificacao_semana_enviada = models.BooleanField(default=False, editable=False)
    notificacao_dia_enviada = models.BooleanField(default=False, editable=False)

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
            and not self.personagens.exists()
        )

    def alunas_destinatarias(self):
        """
        Une, sem repetir, todas as alunas que devem ver/receber este
        aviso: as diretas, as das turmas selecionadas (respeitando o
        recorte feito em "alunas específicas"), e as escaladas nos
        personagens selecionados.

        Regra de recorte por turma (é o que o campo "Alunas
        específicas" promete no formulário: "restringe ainda mais
        dentro das turmas escolhidas"):
        - Se uma turma foi selecionada e NENHUMA aluna dela foi
          marcada em "alunas", o aviso vai para a turma inteira.
        - Se uma turma foi selecionada e uma ou mais alunas dela
          também foram marcadas em "alunas", o aviso vai SOMENTE para
          essas alunas marcadas (não para a turma toda).
        - Alunas marcadas em "alunas" que não pertencem a nenhuma das
          turmas selecionadas continuam sendo adicionadas normalmente
          (uso do campo para gente fora das turmas escolhidas).
        """
        from collections import defaultdict

        from usuarios.models import Aluna

        ids = set()

        turmas = list(self.turmas.all())
        alunas_diretas_ids = set(self.alunas.values_list('id', flat=True))

        if turmas:
            turma_ids = [t.id for t in turmas]

            # De quais turmas (dentre as selecionadas) cada aluna
            # marcada diretamente faz parte.
            aluna_id_para_turmas = defaultdict(set)
            for aluna_id, turma_id in Aluna.objects.filter(
                id__in=alunas_diretas_ids, turmas__id__in=turma_ids
            ).values_list('id', 'turmas__id'):
                aluna_id_para_turmas[aluna_id].add(turma_id)
                ids.add(aluna_id)

            turmas_com_recorte_ids = {
                turma_id
                for turmas_da_aluna in aluna_id_para_turmas.values()
                for turma_id in turmas_da_aluna
            }
            turmas_sem_recorte_ids = [
                t.id for t in turmas if t.id not in turmas_com_recorte_ids
            ]

            if turmas_sem_recorte_ids:
                ids |= set(
                    Aluna.objects.filter(
                        turmas__id__in=turmas_sem_recorte_ids, ativa=True
                    ).values_list('id', flat=True)
                )

            # Alunas marcadas que não pertencem a nenhuma turma
            # selecionada: são adições, não recorte.
            ids |= alunas_diretas_ids - set(aluna_id_para_turmas.keys())
        else:
            # Nenhuma turma selecionada: "alunas" funciona sozinho,
            # como antes.
            ids |= alunas_diretas_ids

        ids |= set(
            Aluna.objects.filter(personagens_elenco__personagem__in=self.personagens.all(), ativa=True)
            .values_list('id', flat=True)
        )
        return Aluna.objects.filter(id__in=ids)
