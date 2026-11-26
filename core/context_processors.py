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
    contexto = {
        'SITE_NAME': settings.SITE_NAME,
        'TEMA_ESCOLA_CSS': '',
        'LOGO_ESCOLA_URL': '',
        'LOGO_PLACEHOLDER': False,
    }

    # Só as telas das famílias e do site público usam estes dois: a administração não muda.
    if request.path.startswith(('/admin-dashboard/', '/static/', '/media/')):
        return contexto

    try:
        from core.aparencia import css_do_tema
        from core.models import ConfiguracaoEscola

        config = ConfiguracaoEscola.objects.filter(pk=1).only('cor_principal', 'logo_tipo', 'logo_versao').first()

        if config is not None:
            contexto['TEMA_ESCOLA_CSS'] = css_do_tema(config.cor_principal)

            if config.logo_tipo:
                contexto['LOGO_ESCOLA_URL'] = f'/escola/logo/?v={config.logo_versao}'

        contexto['LOGO_PLACEHOLDER'] = bool(getattr(settings, 'DEMO_MODE', False)) and not contexto['LOGO_ESCOLA_URL']
    except Exception:  # banco ainda sem as colunas novas, etc.: segue com o visual padrão
        pass

    return contexto


def demonstracao(request):
    """{{ DEMO_MODE }} nos templates: mostra a faixa de demonstração e os botões de entrada."""
    return {'DEMO_MODE': bool(getattr(settings, 'DEMO_MODE', False))}
