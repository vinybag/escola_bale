from django.apps import AppConfig


class PrecosConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'precos'
    verbose_name = 'Preços e descontos'

    def ready(self):
        # Mantém a data/ordem de entrada em cada turma quando as turmas da aluna mudam.
        from . import signals  # noqa: F401
