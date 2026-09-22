"""
Dispara, por WhatsApp, os avisos do tipo "ensaio" marcados com
enviar_whatsapp=True:

- Toda segunda-feira, manda um resumo pra quem tem ensaio nessa semana
  (segunda a domingo).
- No próprio dia do ensaio, manda um lembrete.

Cada um desses dois envios só acontece uma vez por aviso (controlado
pelos campos notificacao_semana_enviada / notificacao_dia_enviada),
então rodar o comando mais de uma vez no mesmo dia não duplica
mensagem.

Pré-requisito: os templates 'aviso_ensaio_semana' e 'aviso_ensaio_dia'
precisam existir e estar aprovados na conta de WhatsApp Business
(Meta) usada por essa instância.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from calendario_avisos.models import Aviso
from pagamentos.services_whatsapp import enviar_whatsapp_template


def _telefone_valido(user):
    """
    Mesma lógica usada no comando de avisos de mensalidade: pega o
    telefone do Perfil do usuário e formata pro padrão que a API do
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


def _destinatarios_do_aviso(aviso):
    """
    Retorna uma lista de tuplas (nome, numero_whatsapp), sem duplicar
    a mesma pessoa, juntando alunas (via responsável ou conta própria,
    se for aluna adulta) e professoras.
    """
    destinatarios = {}

    for aluna in aviso.alunas_destinatarias():
        user_contato = aluna.usuario if aluna.usuario_id else aluna.responsavel
        numero = _telefone_valido(user_contato)
        if numero and numero not in destinatarios:
            nome_contato = user_contato.get_full_name() or user_contato.username
            destinatarios[numero] = (nome_contato, aluna.nome)

    for professora in aviso.professoras.all():
        numero = _telefone_valido(professora)
        if numero and numero not in destinatarios:
            nome_contato = professora.get_full_name() or professora.username
            destinatarios[numero] = (nome_contato, None)

    return [
        (numero, nome_contato, nome_aluna)
        for numero, (nome_contato, nome_aluna) in destinatarios.items()
    ]


class Command(BaseCommand):
    help = 'Envia avisos de ensaio (início de semana e do dia) via WhatsApp'

    def handle(self, *args, **options):
        hoje = timezone.localdate()
        inicio_semana = hoje - timedelta(days=hoje.weekday())  # segunda-feira desta semana
        fim_semana = inicio_semana + timedelta(days=6)  # domingo

        enviados = 0
        erros = 0

        avisos = Aviso.objects.filter(
            ativo=True,
            tipo='ensaio',
            enviar_whatsapp=True,
            data_evento__isnull=False,
        )

        # Resumo da semana: só roda às segundas-feiras.
        if hoje.weekday() == 0:
            avisos_da_semana = avisos.filter(
                data_evento__gte=inicio_semana,
                data_evento__lte=fim_semana,
                notificacao_semana_enviada=False,
            )
            for aviso in avisos_da_semana:
                ok, falhas = self._enviar(aviso, 'aviso_ensaio_semana')
                enviados += ok
                erros += falhas
                aviso.notificacao_semana_enviada = True
                aviso.save(update_fields=['notificacao_semana_enviada'])

        # Lembrete do dia: avisos cujo ensaio é hoje.
        avisos_de_hoje = avisos.filter(
            data_evento=hoje,
            notificacao_dia_enviada=False,
        )
        for aviso in avisos_de_hoje:
            ok, falhas = self._enviar(aviso, 'aviso_ensaio_dia')
            enviados += ok
            erros += falhas
            aviso.notificacao_dia_enviada = True
            aviso.save(update_fields=['notificacao_dia_enviada'])

        self.stdout.write(f'Avisos de ensaio enviados: {enviados} | Erros: {erros}')

    def _enviar(self, aviso, nome_template):
        enviados = 0
        erros = 0

        data_formatada = aviso.data_evento.strftime('%d/%m/%Y')
        horario = aviso.horario or 'horário a confirmar'

        for numero, nome_contato, nome_aluna in _destinatarios_do_aviso(aviso):
            # Ordem dos parâmetros conforme o template aprovado na Meta:
            # {{1}} nome do contato
            # {{2}} título do aviso
            # {{3}} data do ensaio
            # {{4}} horário do ensaio
            parametros = [nome_contato, aviso.titulo, data_formatada, horario]

            status, _ = enviar_whatsapp_template(numero, nome_template, parametros)

            if status == 200:
                enviados += 1
            else:
                erros += 1

        return enviados, erros
