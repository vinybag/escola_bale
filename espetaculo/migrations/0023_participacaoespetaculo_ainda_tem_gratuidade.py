from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('espetaculo', '0022_patrocinador'),
    ]

    operations = [
        migrations.AddField(
            model_name='participacaoespetaculo',
            name='ainda_tem_gratuidade',
            field=models.BooleanField(
                default=True,
                help_text='Controle manual do admin: desmarque para impedir que esta aluna apareça como elegível à gratuidade deste evento (no site e no admin), mesmo que ela nunca tenha de fato usado o ingresso grátis. Útil para corrigir manualmente casos onde a gratuidade precisou ser ajustada fora do fluxo normal.',
                verbose_name='Ainda tem ingresso gratuito',
            ),
        ),
    ]
