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

Pré-requisito: os templates 'aviso_ensaio_semana' e 'aviso_ensaio_dia_certo'
precisam existir e estar aprovados na conta de WhatsApp Business
(Meta) usada por essa instância.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from calendario_avisos.envio_whatsapp import (
    destinatarios_do_aviso,
    parametros_base_template,
    telefone_valido,
)
from calendario_avisos.models import Aviso
from pagamentos.services_whatsapp import enviar_whatsapp_template


# A lógica de destinatários e de parâmetros fica em envio_whatsapp.py, porque
# o botão "Enviar agora" (edição do aviso) usa exatamente a mesma. Os nomes
# antigos continuam existindo aqui.
_telefone_valido = telefone_valido
_destinatarios_do_aviso = destinatarios_do_aviso


class Command(BaseCommand):
    help = 'Envia avisos de ensaio (início de semana e do dia) via WhatsApp'

    def handle(self, *args, **options):
        hoje = timezone.localdate()
        inicio_semana = hoje + timedelta(days=1)  # segunda-feira da semana que vem
        fim_semana = inicio_semana + timedelta(days=6)  # domingo seguinte

        enviados = 0
        erros = 0

        avisos = Aviso.objects.filter(
            ativo=True,
            tipo='ensaio',
            enviar_whatsapp=True,
            data_evento__isnull=False,
        )

        # Resumo da semana: só roda às segundas-feiras. Se o ensaio for
        # justamente hoje, pula o resumo — a pessoa já vai receber o
        # lembrete do dia logo abaixo, e mandar os dois seria repetir
        # a mesma informação duas vezes.
        if hoje.weekday() == 6:
            avisos_da_semana = avisos.filter(
                data_evento__gte=inicio_semana,
                data_evento__lte=fim_semana,
                notificacao_semana_enviada=False,
            ).exclude(data_evento=hoje)
            for aviso in avisos_da_semana:
                ok, falhas = self._enviar(aviso, 'aviso_ensaio_semana')
                enviados += ok
                erros += falhas
                aviso.notificacao_semana_enviada = True
                aviso.save(update_fields=['notificacao_semana_enviada'])

            # Os que caem hoje não recebem o resumo (só o lembrete do dia,
            # mais abaixo), mas marcamos como "tratados" mesmo assim, pra
            # manter o registro consistente.
            avisos.filter(
                data_evento=hoje,
                notificacao_semana_enviada=False,
            ).update(notificacao_semana_enviada=True)

        # Lembrete do dia: avisos cujo ensaio é hoje.
        avisos_de_hoje = avisos.filter(
            data_evento=hoje,
            notificacao_dia_enviada=False,
        )
        for aviso in avisos_de_hoje:
            ok, falhas = self._enviar(aviso, 'aviso_ensaio_dia_certo')
            enviados += ok
            erros += falhas
            if falhas == 0:
                aviso.notificacao_dia_enviada = True
                aviso.save(update_fields=['notificacao_dia_enviada'])

        self.stdout.write(f'Avisos de ensaio enviados: {enviados} | Erros: {erros}')

    def _enviar(self, aviso, nome_template):
        enviados = 0
        erros = 0

        # {{1}} é o nome do contato (vai na frente, abaixo); o resto depende
        # do template. Ver parametros_base_template.
        parametros_base = parametros_base_template(aviso, nome_template)

        for numero, nome_contato, nome_aluna in _destinatarios_do_aviso(aviso):
            parametros = [nome_contato] + parametros_base
            status, resposta_json = enviar_whatsapp_template(numero, nome_template, parametros)

            if status == 200:
                enviados += 1
            else:
                erros += 1
                self.stdout.write(self.style.ERROR(
                    f'Falha ao enviar para {numero} ({nome_contato}): {status} - {resposta_json}'
                ))

        return enviados, erros