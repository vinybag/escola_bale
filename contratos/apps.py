from django.apps import AppConfig


class ContratosConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'contratos'
    verbose_name = 'Contratos'

    def ready(self):
        # Registra o sinal que cria o contrato pendente quando uma aluna é criada.
        from . import signals  # noqa: F401
