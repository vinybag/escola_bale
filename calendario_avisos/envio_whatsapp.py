"""
Envio de avisos de ensaio por WhatsApp.

Este módulo reúne a lógica usada por DOIS caminhos:

  * o comando agendado (cron) `enviar_avisos_ensaio`, que manda o resumo da
    semana aos domingos e o lembrete no dia do ensaio; e
  * o botão "Enviar agora por WhatsApp", na edição do aviso, para quando um
    aviso foi criado/esquecido depois do envio de domingo.

Os dois usam as mesmas regras de destinatários e os mesmos modelos de
mensagem (templates) já aprovados na Meta, então não é preciso aprovar nada
novo.

O envio manual marca os mesmos controles que o cron usa
(notificacao_semana_enviada / notificacao_dia_enviada), para o cron não
mandar a mesma mensagem outra vez.
"""

import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from pagamentos.services_whatsapp import enviar_whatsapp_template

from .models import Aviso, AvisoEnvioManual

logger = logging.getLogger(__name__)

TEMPLATE_SEMANA = 'aviso_ensaio_semana'
TEMPLATE_DIA = 'aviso_ensaio_dia_certo'

ROTULOS_TEMPLATE = {
    TEMPLATE_SEMANA: 'Aviso do ensaio, com data e horário',
    TEMPLATE_DIA: 'Lembrete de hoje',
}

# Dois envios do mesmo aviso em menos tempo que isso são tratados como clique
# duplo e o segundo é recusado.
JANELA_ANTIDUPLICIDADE = timedelta(seconds=60)

# Um envio "em andamento" há mais tempo que isso é considerado interrompido.
TEMPO_MAXIMO_EM_ANDAMENTO = timedelta(minutes=10)


# ---------------------------------------------------------------------------
# Destinatários e parâmetros (compartilhados com o comando do cron)
# ---------------------------------------------------------------------------

def telefone_valido(user):
    """
    Pega o telefone do Perfil do usuário e formata pro padrão que a API do
    WhatsApp espera (só dígitos, com o 55 na frente).
    """
    if not user or not hasattr(user, 'perfil'):
        return None

    telefone = user.perfil.telefone
    if not telefone:
        return None

    numero = ''.join(filter(str.isdigit, telefone))
    if not numero.startswith('55'):
        numero = '55' + numero

    return numero


def destinatarios_do_aviso(aviso):
    """
    Retorna uma lista de tuplas (numero_whatsapp, nome_contato, nome_aluna),
    sem duplicar a mesma pessoa, juntando alunas (via responsável ou conta
    própria, se for aluna adulta) e professoras.
    """
    destinatarios = {}

    for aluna in aviso.alunas_destinatarias():
        user_contato = aluna.usuario if aluna.usuario_id else aluna.responsavel
        numero = telefone_valido(user_contato)
        if numero and numero not in destinatarios:
            nome_contato = user_contato.get_full_name() or user_contato.username
            destinatarios[numero] = (nome_contato, aluna.nome)

    for professora in aviso.professoras.all():
        numero = telefone_valido(professora)
        if numero and numero not in destinatarios:
            nome_contato = professora.get_full_name() or professora.username
            destinatarios[numero] = (nome_contato, None)

    return [
        (numero, nome_contato, nome_aluna)
        for numero, (nome_contato, nome_aluna) in destinatarios.items()
    ]


def contatos_sem_whatsapp(aviso):
    """
    Nomes de quem DEVERIA receber o aviso mas não tem telefone cadastrado
    (ou nem tem responsável). Serve para a equipe corrigir o cadastro ou
    avisar essas pessoas por fora.
    """
    sem_numero = []

    for aluna in aviso.alunas_destinatarias():
        user_contato = aluna.usuario if aluna.usuario_id else aluna.responsavel
        if not telefone_valido(user_contato):
            sem_numero.append(aluna.nome)

    for professora in aviso.professoras.all():
        if not telefone_valido(professora):
            sem_numero.append(
                professora.get_full_name() or professora.username
            )

    return sem_numero


def parametros_base_template(aviso, nome_template):
    """
    Parâmetros do template, SEM o nome do contato (que vai na frente).

    aviso_ensaio_dia_certo:  {{1}} nome, {{2}} título, {{3}} horário
    aviso_ensaio_semana:     {{1}} nome, {{2}} título, {{3}} data, {{4}} horário
    """
    horario = aviso.horario or 'horário a confirmar'

    if nome_template == TEMPLATE_DIA:
        return [aviso.titulo, horario]

    data_formatada = aviso.data_evento.strftime('%d/%m/%Y')
    return [aviso.titulo, data_formatada, horario]


# ---------------------------------------------------------------------------
# Envio manual ("Enviar agora")
# ---------------------------------------------------------------------------

class EnvioNaoPermitido(Exception):
    """O envio não pode ser feito agora; a mensagem explica o motivo."""


class ReenvioPrecisaConfirmacao(EnvioNaoPermitido):
    """As pessoas já receberam este aviso; é preciso confirmar o reenvio."""


class ResultadoEnvio:
    def __init__(self, template, total, enviados, falhas, registro):
        self.template = template
        self.total = total
        self.enviados = enviados
        self.falhas = falhas  # lista de (nome_contato, motivo)
        self.registro = registro

    @property
    def erros(self):
        return len(self.falhas)


def motivo_bloqueio(aviso, hoje=None):
    """
    Devolve o motivo (texto) pelo qual este aviso NÃO pode ser enviado agora,
    ou None se pode.
    """
    hoje = hoje or timezone.localdate()

    if aviso.tipo != 'ensaio':
        return (
            'Só avisos do tipo "Ensaio" podem ser enviados por aqui: os '
            'modelos de mensagem do WhatsApp são de ensaio.'
        )

    if not aviso.ativo:
        return 'Este aviso está desativado.'

    if not aviso.enviar_whatsapp:
        return (
            'Marque "Enviar por WhatsApp também" e salve o aviso para poder '
            'enviar.'
        )

    if aviso.data_evento is None:
        return 'Informe a data do ensaio e salve o aviso.'

    if aviso.data_evento < hoje:
        return 'Este ensaio já passou, não faz sentido avisar agora.'

    return None


def template_para(aviso, hoje=None):
    """
    Ensaio hoje -> lembrete do dia ("hoje"); ensaio futuro -> aviso com a
    data. Mesma escolha que o cron faz: o resumo da semana nunca inclui o
    ensaio do próprio dia.
    """
    hoje = hoje or timezone.localdate()
    return TEMPLATE_DIA if aviso.data_evento == hoje else TEMPLATE_SEMANA


def _ja_enviado(aviso, template):
    """
    Já foi enviada ao menos uma vez a MESMA mensagem? Pelo cron (controles do
    aviso) ou por um envio manual anterior.
    """
    if template == TEMPLATE_DIA and aviso.notificacao_dia_enviada:
        return True
    if template == TEMPLATE_SEMANA and aviso.notificacao_semana_enviada:
        return True

    return aviso.envios_manuais.filter(
        template=template, enviados__gt=0
    ).exists()


def situacao_do_envio(aviso, hoje=None):
    """Resumo para mostrar na tela: o que será enviado e se é repetição."""
    hoje = hoje or timezone.localdate()

    if aviso.data_evento is None:
        return {'template': None, 'rotulo': '', 'ja_enviado': False}

    template = template_para(aviso, hoje)
    return {
        'template': template,
        'rotulo': ROTULOS_TEMPLATE[template],
        'ja_enviado': _ja_enviado(aviso, template),
    }


def historico_de_envios(aviso, limite=5):
    return list(aviso.envios_manuais.select_related('enviado_por')[:limite])


def enviar_agora(aviso, usuario, hoje=None, confirmou_reenvio=False):
    """
    Envia o aviso AGORA, por WhatsApp, para todos os destinatários.

    Levanta EnvioNaoPermitido / ReenvioPrecisaConfirmacao quando não deve
    enviar. Devolve um ResultadoEnvio.

    Proteções:
      * o aviso é travado no banco durante a checagem, e o registro do envio
        é criado antes de enviar: dois cliques seguidos não duplicam;
      * se as pessoas já receberam essa mesma mensagem, exige confirmação;
      * os controles do cron são marcados só se ao menos uma mensagem saiu,
        então uma falha total deixa o cron livre para tentar depois.
    """
    hoje = hoje or timezone.localdate()

    with transaction.atomic():
        aviso = Aviso.objects.select_for_update().get(pk=aviso.pk)

        motivo = motivo_bloqueio(aviso, hoje)
        if motivo:
            raise EnvioNaoPermitido(motivo)

        agora = timezone.now()
        if aviso.envios_manuais.filter(
            criado_em__gte=agora - JANELA_ANTIDUPLICIDADE
        ).exists():
            raise EnvioNaoPermitido(
                'Este aviso acabou de ser enviado. Aguarde um minuto antes '
                'de enviar de novo.'
            )

        template = template_para(aviso, hoje)

        if _ja_enviado(aviso, template) and not confirmou_reenvio:
            raise ReenvioPrecisaConfirmacao(
                'As pessoas já receberam este aviso. Marque a confirmação '
                'para enviar de novo.'
            )

        destinatarios = destinatarios_do_aviso(aviso)
        if not destinatarios:
            raise EnvioNaoPermitido(
                'Nenhum destinatário tem WhatsApp cadastrado para este aviso.'
            )

        registro = AvisoEnvioManual.objects.create(
            aviso=aviso,
            enviado_por=usuario if getattr(usuario, 'pk', None) else None,
            template=template,
            total_destinatarios=len(destinatarios),
        )

    # O envio em si acontece FORA da transação: são várias chamadas de rede e
    # não faz sentido segurar o banco travado durante elas.
    parametros_base = parametros_base_template(aviso, template)
    enviados = 0
    falhas = []

    try:
        for numero, nome_contato, _nome_aluna in destinatarios:
            try:
                status, resposta = enviar_whatsapp_template(
                    numero, template, [nome_contato] + parametros_base
                )
            except Exception as exc:  # uma pessoa com problema não pára o resto
                logger.exception('Erro ao enviar aviso manual')
                status, resposta = 0, {'error': {'message': str(exc)}}

            if status == 200:
                enviados += 1
            else:
                detalhe = ''
                if isinstance(resposta, dict):
                    detalhe = str(
                        (resposta.get('error') or {}).get('message') or ''
                    )
                falhas.append((nome_contato, f'{status} {detalhe}'.strip()))
    finally:
        registro.enviados = enviados
        registro.erros = len(falhas)
        registro.detalhe_erros = '\n'.join(
            f'{nome}: {motivo}' for nome, motivo in falhas
        )[:4000]
        registro.concluido = True
        registro.save(update_fields=[
            'enviados', 'erros', 'detalhe_erros', 'concluido',
        ])

        # Marca os controles do cron só se alguém recebeu. update() para não
        # sobrescrever uma edição feita enquanto o envio rodava.
        if enviados > 0:
            if template == TEMPLATE_DIA:
                Aviso.objects.filter(pk=aviso.pk).update(
                    notificacao_dia_enviada=True,
                    notificacao_semana_enviada=True,
                )
            else:
                Aviso.objects.filter(pk=aviso.pk).update(
                    notificacao_semana_enviada=True,
                )

    return ResultadoEnvio(
        template, len(destinatarios), enviados, falhas, registro
    )
