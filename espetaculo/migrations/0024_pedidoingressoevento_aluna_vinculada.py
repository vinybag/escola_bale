import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('espetaculo', '0023_participacaoespetaculo_ainda_tem_gratuidade'),
        ('usuarios', '0017_turma_faixa_etaria'),
    ]

    operations = [
        migrations.AddField(
            model_name='pedidoingressoevento',
            name='aluna_vinculada',
            field=models.ForeignKey(
                blank=True,
                help_text='Aluna vinculada a este pedido, independente de ser cortesia ou pago — permite saber de quem é o pedido (e localizar o e-mail da responsável) mesmo em vendas pagas onde nenhuma gratuidade foi usada.',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='pedidos_ingresso',
                to='usuarios.aluna',
                verbose_name='Aluna vinculada',
            ),
        ),
    ]
