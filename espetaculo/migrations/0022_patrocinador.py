# Generated manually (mesmo padrão das migrações anteriores do app)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('espetaculo', '0021_personagem_elencopersonagem'),
    ]

    operations = [
        migrations.CreateModel(
            name='Patrocinador',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nome', models.CharField(blank=True, help_text='Nome do patrocinador/marca. Usado como texto alternativo da imagem (acessibilidade e SEO); não é exibido como texto visível ao lado da logo.', max_length=150)),
                ('logo', models.ImageField(help_text='Recomendado: PNG com fundo transparente.', upload_to='patrocinadores/')),
                ('nivel', models.CharField(choices=[('rodape', 'Logo no rodapé do mapa de assentos'), ('medio', 'Logo em destaque médio'), ('maximo', 'Logo em destaque máximo')], max_length=20, verbose_name='Posição/destaque da logo')),
                ('site_url', models.URLField(blank=True, help_text='Se preenchido, a logo vira um link clicável para este site.', verbose_name='Link do patrocinador (opcional)')),
                ('exibir_na_listagem', models.BooleanField(default=True, verbose_name='Exibir na listagem de espetáculos')),
                ('exibir_no_mapa_assentos', models.BooleanField(default=True, verbose_name='Exibir no mapa de assentos')),
                ('ativo', models.BooleanField(default=True, help_text='Desmarque para ocultar temporariamente sem excluir o cadastro.', verbose_name='Ativo')),
                ('ordem', models.PositiveSmallIntegerField(default=0, help_text='Logos com número menor aparecem primeiro dentro do mesmo nível.')),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'Patrocinador',
                'verbose_name_plural': 'Patrocinadores',
                'ordering': ['nivel', 'ordem', 'id'],
            },
        ),
    ]
