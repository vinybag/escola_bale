from datetime import date, timedelta
from django.core.management.base import BaseCommand
from pagamentos.models import Mensalidade
from pagamentos.services_whatsapp import enviar_whatsapp_template

REGRA_ATRASO = {
    1: 'atraso_1',
    3: 'atraso_3',
    7: 'atraso_7',
    15: 'atraso_15',
    30: 'atraso_30',
}


class Command(BaseCommand):
    help = 'Envia avisos automáticos de vencimento e atraso de mensalidades via WhatsApp'

    def handle(self, *args, **options):
        hoje = date.today()
        amanha = hoje + timedelta(days=1)

        enviados = 0
        erros = 0

        mensalidades_amanha = Mensalidade.objects.filter(
            data_vencimento=amanha,
            data_pagamento__isnull=True
        ).exclude(status='cancelado').exclude(
            ultimo_aviso_enviado='vencimento_amanha',
            data_ultimo_aviso=hoje
        ).select_related('aluna', 'responsavel__perfil')

        for m in mensalidades_amanha:
            if self._enviar_vencimento(m, 'aviso_vencimento_amanha', 'vencimento_amanha'):
                enviados += 1
            else:
                erros += 1

        mensalidades_hoje = Mensalidade.objects.filter(
            data_vencimento=hoje,
            data_pagamento__isnull=True
        ).exclude(status='cancelado').exclude(
            ultimo_aviso_enviado='vencimento_hoje',
            data_ultimo_aviso=hoje
        ).select_related('aluna', 'responsavel__perfil')

        for m in mensalidades_hoje:
            if self._enviar_vencimento(m, 'aviso_vencimento_hoje', 'vencimento_hoje'):
                enviados += 1
            else:
                erros += 1

        mensalidades_atrasadas = Mensalidade.objects.filter(
            data_vencimento__lt=hoje,
            data_pagamento__isnull=True
        ).exclude(status='cancelado').select_related('aluna', 'responsavel__perfil')

        for m in mensalidades_atrasadas:
            dias = m.dias_atraso

            if dias in REGRA_ATRASO:
                codigo = REGRA_ATRASO[dias]

                if m.ultimo_aviso_enviado == codigo and m.data_ultimo_aviso == hoje:
                    continue

                if self._enviar_atraso(m, codigo):
                    enviados += 1
                else:
                    erros += 1

        self.stdout.write(f'Avisos enviados: {enviados} | Erros: {erros}')

    def _telefone_valido(self, mensalidade):
        responsavel = mensalidade.responsavel

        if not responsavel or not hasattr(responsavel, 'perfil'):
            return None

        telefone = responsavel.perfil.telefone

        if not telefone:
            return None

        numero = ''.join(filter(str.isdigit, telefone))
        if not numero.startswith('55'):
            numero = '55' + numero

        return numero

    def _enviar_vencimento(self, mensalidade, nome_template, codigo_aviso):
        numero = self._telefone_valido(mensalidade)
        if not numero:
            return False

        nome_responsavel = mensalidade.responsavel.get_full_name() or mensalidade.responsavel.username

        parametros = [
            nome_responsavel,
            mensalidade.mes_referencia.strftime('%m/%Y'),
            mensalidade.aluna.nome,
            mensalidade.data_vencimento.strftime('%d/%m/%Y'),
            f'{mensalidade.valor:.2f}'.replace('.', ','),
        ]

        status, _ = enviar_whatsapp_template(numero, nome_template, parametros)

        if status == 200:
            mensalidade.ultimo_aviso_enviado = codigo_aviso
            mensalidade.data_ultimo_aviso = date.today()
            mensalidade.save(update_fields=['ultimo_aviso_enviado', 'data_ultimo_aviso'])
            return True

        return False

    def _enviar_atraso(self, mensalidade, codigo_aviso):
        numero = self._telefone_valido(mensalidade)
        if not numero:
            return False

        nome_responsavel = mensalidade.responsavel.get_full_name() or mensalidade.responsavel.username

        parametros = [
            nome_responsavel,
            mensalidade.mes_referencia.strftime('%m/%Y'),
            mensalidade.aluna.nome,
            str(mensalidade.dias_atraso),
            mensalidade.data_vencimento.strftime('%d/%m/%Y'),
            f'{mensalidade.valor_atualizado:.2f}'.replace('.', ','),
        ]

        status, _ = enviar_whatsapp_template(numero, 'aviso_atraso', parametros)

        if status == 200:
            mensalidade.ultimo_aviso_enviado = codigo_aviso
            mensalidade.data_ultimo_aviso = date.today()
            mensalidade.save(update_fields=['ultimo_aviso_enviado', 'data_ultimo_aviso'])
            return True

        return False