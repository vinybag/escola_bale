import logging
import time

from django.conf import settings
from django.db import connection

logger = logging.getLogger('lentidao')


class RegistrarPaginasLentasMiddleware:
    """
    Escreve uma linha no registro (log) do servidor sempre que uma página
    demora mais que o limite (padrão: 3 segundos), dizendo QUAL página foi,
    quanto demorou e quantas consultas fez ao banco de dados.

    Serve para descobrir, com dados reais de produção, o que está
    deixando o site lento — em vez de adivinhar. Páginas rápidas não
    geram nenhuma linha. O limite pode ser mudado pela variável de
    ambiente LENTO_LIMITE_SEGUNDOS.

    Não altera a resposta enviada ao usuário em nada: só observa.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        contador = {'consultas': 0}

        def contar_consulta(execute, sql, params, many, context):
            contador['consultas'] += 1
            return execute(sql, params, many, context)

        inicio = time.perf_counter()

        with connection.execute_wrapper(contar_consulta):
            response = self.get_response(request)

        duracao = time.perf_counter() - inicio

        try:
            limite = getattr(settings, 'LENTO_LIMITE_SEGUNDOS', 3)

            if duracao >= limite:
                logger.warning(
                    '[PÁGINA LENTA] %s %s levou %.1fs e fez %d consultas ao '
                    'banco (resposta %s)',
                    request.method,
                    request.path,
                    duracao,
                    contador['consultas'],
                    getattr(response, 'status_code', '?'),
                )
        except Exception:
            # O registro nunca pode atrapalhar a página.
            pass

        return response
