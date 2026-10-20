"""
Dispara, por WhatsApp, os avisos do tipo "ensaio" marcados com
enviar_whatsapp=True:

- Aos domingos, manda um resumo pra quem tem ensaio na semana seguinte
  (segunda a domingo).
- Nos outros dias, manda o resumo (de última hora) dos ensaios desta semana
  que o domingo não cobriu: avisos criados, ligados ao WhatsApp ou com a data
  mudada depois do domingo. Ver avisos_para_resumo_atrasado. Dá para desligar
  com AVISOS_ENSAIO_ENVIO_ATRASADO_ATIVO=false.
- Na véspera, para os avisos marcados com "Lembrar também um dia antes",
  manda um lembrete ("amanhã"). Se o aviso acabou de receber o resumo (ou um
  envio manual) no mesmo dia, a véspera é dispensada para não repetir.
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

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from calendario_avisos.envio_whatsapp import (
    TEMPLATE_VESPERA,
    avisos_para_resumo_atrasado,
    avisos_para_vespera,
    destinatarios_do_aviso,
    parametros_base_template,
    recebeu_envio_manual_hoje,
    telefone_valido,
)
from calendario_avisos.models import Aviso, AvisoEnvioAutomatico
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

        # Avisos que já receberam o resumo nesta execução (domingo ou última
        # hora): a véspera, se marcada, só repetiria a mesma informação.
        ids_com_resumo_hoje = set()

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
                if ok > 0:
                    ids_com_resumo_hoje.add(aviso.pk)
                aviso.notificacao_semana_enviada = True
                aviso.save(update_fields=['notificacao_semana_enviada'])

            # Os que caem hoje não recebem o resumo (só o lembrete do dia,
            # mais abaixo), mas marcamos como "tratados" mesmo assim, pra
            # manter o registro consistente.
            avisos.filter(
                data_evento=hoje,
                notificacao_semana_enviada=False,
            ).update(notificacao_semana_enviada=True)

        # Resumo de última hora: ensaios DESTA semana cujo resumo o domingo não
        # mandou (criados/ligados ao WhatsApp depois dele). Só marca como
        # enviado se alguém recebeu; se tudo falhar, tenta de novo no próximo
        # disparo.
        if getattr(settings, 'AVISOS_ENSAIO_ENVIO_ATRASADO_ATIVO', True):
            enviados_atrasados = 0
            for aviso in avisos_para_resumo_atrasado(hoje):
                ok, falhas = self._enviar(aviso, 'aviso_ensaio_semana')
                enviados += ok
                erros += falhas
                enviados_atrasados += ok
                if ok > 0:
                    ids_com_resumo_hoje.add(aviso.pk)
                    aviso.notificacao_semana_enviada = True
                    aviso.save(update_fields=['notificacao_semana_enviada'])

            if enviados_atrasados:
                self.stdout.write(
                    f'Resumos de última hora enviados: {enviados_atrasados}'
                )

        # Lembrete de véspera: avisos com "Lembrar também um dia antes" cujo
        # ensaio é amanhã. Se o aviso acabou de receber o resumo (domingo ou
        # última hora) ou um envio manual hoje, a véspera repetiria a mesma
        # informação: só é marcada como tratada. Como nos demais, só conta como
        # enviada se alguém recebeu; se tudo falhar, a próxima execução do dia
        # tenta de novo.
        enviados_vespera = 0
        for aviso in avisos_para_vespera(hoje):
            if aviso.pk in ids_com_resumo_hoje or recebeu_envio_manual_hoje(aviso, hoje):
                aviso.notificacao_vespera_enviada = True
                aviso.save(update_fields=['notificacao_vespera_enviada'])
                continue

            ok, falhas = self._enviar(aviso, TEMPLATE_VESPERA)
            enviados += ok
            erros += falhas
            enviados_vespera += ok
            if ok > 0:
                aviso.notificacao_vespera_enviada = True
                aviso.save(update_fields=['notificacao_vespera_enviada'])

        if enviados_vespera:
            self.stdout.write(
                f'Lembretes de véspera enviados: {enviados_vespera}'
            )

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

        self._registrar_envio(aviso, nome_template, enviados, erros)

        return enviados, erros

    def _registrar_envio(self, aviso, nome_template, enviados, erros):
        """
        Guarda quantas mensagens saíram e quantas falharam. É isso que o pin
        "Já enviado" dos avisos usa para dizer se deu tudo certo. Uma falha ao
        registrar nunca pode atrapalhar o envio em si.
        """
        if enviados + erros == 0:
            return

        try:
            AvisoEnvioAutomatico.objects.create(
                aviso=aviso,
                template=nome_template,
                total_destinatarios=enviados + erros,
                enviados=enviados,
                erros=erros,
            )
        except Exception as exc:
            self.stdout.write(self.style.ERROR(
                f'Não foi possível registrar o envio do aviso {aviso.pk}: {exc}'
            ))