from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from usuarios.models import Turma, Aluna
from calendario_avisos.models import Aviso

class Command(BaseCommand):
    help = 'Cria grupos e permissões para professores'

    def handle(self, *args, **options):
        # Criar grupo Professores
        grupo, created = Group.objects.get_or_create(name='Professores')
        
        if created:
            self.stdout.write(self.style.SUCCESS('Grupo "Professores" criado!'))
        else:
            self.stdout.write('Grupo "Professores" já existe')
        
        # Permissões de visualização
        permissoes = [
            ('view_turma', 'usuarios', 'turma'),
            ('view_aluna', 'usuarios', 'aluna'),
            ('view_aviso', 'calendario_avisos', 'aviso'),
        ]
        
        for codename, app, model in permissoes:
            try:
                content_type = ContentType.objects.get(app_label=app, model=model)
                permissao = Permission.objects.get(codename=codename, content_type=content_type)
                grupo.permissions.add(permissao)
                self.stdout.write(f'  + Adicionada permissão: {codename}')
            except Exception as e:
                self.stdout.write(f'  Erro ao adicionar {codename}: {e}')
        
        self.stdout.write(self.style.SUCCESS('Configuração concluída!'))