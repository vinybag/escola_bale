from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('espetaculo', '0026_maquiagem_familia_escolhe_horario'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='espetaculo',
            name='link_filmagem',
            field=models.URLField(blank=True, help_text='Link do Google Drive (ou outro) com a filmagem deste dia.', max_length=500, verbose_name='Link da filmagem'),
        ),
        migrations.AddField(
            model_name='espetaculo',
            name='usuarios_filmagem',
            field=models.ManyToManyField(blank=True, related_name='filmagens_liberadas', to=settings.AUTH_USER_MODEL, verbose_name='Logins com acesso à filmagem'),
        ),
    ]
