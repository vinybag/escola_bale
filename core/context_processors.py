from django.conf import settings


def marca(request):
    """
    Deixa o nome da escola/marca disponível em qualquer template como
    {{ SITE_NAME }}, sem precisar passar isso view por view.

    O valor vem de settings.SITE_NAME, que por sua vez lê a variável de
    ambiente SITE_NAME (com o nome atual da escola como default). Isso é
    o que permite "clonar" o sistema para outra escola só trocando o
    .env do deploy, sem tocar em nenhum template.
    """
    return {
        'SITE_NAME': settings.SITE_NAME,
    }
