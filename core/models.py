from django.db import models

# Create your models here.


class ConfiguracaoEscola(models.Model):
    """
    Conteúdo editável da home pública (a página que qualquer visitante
    vê antes de fazer login). Existe como uma "linha única" por
    instância: cada cliente tem a sua própria, preenchida pelo painel.

    Usamos o padrão de "singleton": sempre buscamos/criamos o registro
    de id=1, então nunca existe ambiguidade sobre qual configuração usar.
    """

    subtitulo_hero = models.CharField(
        max_length=150,
        blank=True,
        default='Transformando sonhos em movimento',
        verbose_name='Frase de destaque (abaixo do nome da escola)',
    )
    texto_sobre = models.TextField(
        blank=True,
        default='Em breve em novo endereço',
        verbose_name='Texto da seção "Sobre"',
    )
    endereco = models.CharField(
        max_length=200,
        blank=True,
        default='Praça Cel. João Rosa, 176 - Sobreloja - Centro, Piedade - SP',
        verbose_name='Endereço',
    )
    telefone = models.CharField(
        max_length=30,
        blank=True,
        default='15 99751-7185',
        verbose_name='Telefone',
    )
    email_contato = models.EmailField(
        blank=True,
        default='berkana.arte.magia@gmail.com',
        verbose_name='E-mail de contato exibido no site',
    )

    class Meta:
        verbose_name = 'Configuração da escola'
        verbose_name_plural = 'Configuração da escola'

    def __str__(self):
        return 'Configuração da home pública'

    @classmethod
    def obter(cls):
        """Retorna a configuração única, criando com valores padrão na primeira vez."""
        config, _ = cls.objects.get_or_create(pk=1)
        return config
