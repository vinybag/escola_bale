"""
Cria o superusuário inicial do site, se ele ainda não existir.

NUNCA escreva senha neste arquivo: o repositório é público. Os dados vêm de
variáveis de ambiente (no Railway: serviço -> Variables):

    ADMIN_INITIAL_PASSWORD   obrigatória para criar a conta (mínimo de 10 caracteres).
                             Sem ela, nenhuma conta é criada (e o deploy segue normalmente).
    ADMIN_USERNAME           opcional; padrão: admin
    ADMIN_EMAIL              opcional

Se a conta já existir, nada é alterado (a senha dela nunca é trocada por aqui).
"""

import os

TAMANHO_MINIMO_SENHA = 10


def criar_superusuario_inicial():
    """Devolve True se criou a conta; False se não criou (já existe ou faltam dados)."""
    from django.contrib.auth.models import User

    username = (os.environ.get('ADMIN_USERNAME') or 'admin').strip()
    email = (os.environ.get('ADMIN_EMAIL') or '').strip()
    senha = os.environ.get('ADMIN_INITIAL_PASSWORD') or ''

    if User.objects.filter(username=username).exists():
        print('⚠️ Superusuário já existe!')
        return False

    if not senha:
        print(
            '⚠️ Superusuário NÃO criado: defina a variável ADMIN_INITIAL_PASSWORD '
            'se quiser que ele seja criado automaticamente.'
        )
        return False

    if len(senha) < TAMANHO_MINIMO_SENHA:
        print(
            f'⚠️ Superusuário NÃO criado: ADMIN_INITIAL_PASSWORD precisa ter pelo '
            f'menos {TAMANHO_MINIMO_SENHA} caracteres.'
        )
        return False

    User.objects.create_superuser(username=username, email=email, password=senha)
    print('✅ Superusuário criado com sucesso!')

    return True


if __name__ == '__main__':
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

    import django

    django.setup()
    criar_superusuario_inicial()
