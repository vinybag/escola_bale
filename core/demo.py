"""
Modo demonstração.

Serve para mostrar o sistema a quem tem interesse, em uma instalação SEPARADA (com DEMO_MODE=1)
e só com dados inventados. Nada aqui roda na instalação de verdade: sem DEMO_MODE nada acontece.
"""

from datetime import date, datetime, time
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.core.management import call_command
from django.http import HttpResponse
from django.shortcuts import redirect
from django.utils import timezone

ADMIN = 'demo_admin'
RESPONSAVEL = 'demo_responsavel'

# Páginas que ficam fechadas na demonstração (senha, cadastro novo, painel técnico do Django).
CAMINHOS_BLOQUEADOS = (
    '/admin/', '/conta/alterar-senha/', '/conta/esqueci-senha/', '/conta/redefinir-senha/',
    '/conta/cadastro/', '/setup-inicial/',
)


def ativo():
    return bool(getattr(settings, 'DEMO_MODE', False))


class DemoMiddleware:
    """Fecha o que não faz sentido numa demonstração pública e pede aos buscadores para não indexar."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not ativo():
            return self.get_response(request)

        if request.path.startswith(CAMINHOS_BLOQUEADOS):
            messages.info(request, 'Esta parte está desligada na demonstração.')
            return redirect('/')

        resposta = self.get_response(request)
        resposta['X-Robots-Tag'] = 'noindex, nofollow'
        return resposta


def entrar(request, quem):
    """Entra sem senha como a administradora ou como a responsável da escola de exemplo (só na demo)."""
    from django.contrib.auth import login
    from django.contrib.auth.models import User
    from django.http import Http404

    if not ativo() or request.method != 'POST':
        raise Http404

    username = {'administradora': ADMIN, 'responsavel': RESPONSAVEL}.get(quem)
    usuario = User.objects.filter(username=username).first() if username else None

    if usuario is None:
        messages.error(request, 'Os dados de demonstração ainda não foram criados.')
        return redirect('/')

    login(request, usuario, backend='django.contrib.auth.backends.ModelBackend')
    return redirect('/admin-dashboard/' if quem == 'administradora' else '/conta/dashboard/')


# --------------------------------------------------------------------------- dados fictícios

def _mes_atras(dia, meses):
    ano, mes = dia.year, dia.month - meses

    while mes < 1:
        mes += 12
        ano -= 1

    return date(ano, mes, 1)


def apagar_tudo():
    """Apaga TODOS os dados do banco. Só é chamado com DEMO_MODE ligado (ver o comando popular_demo)."""
    call_command('flush', interactive=False, verbosity=0)


def popular(hoje=None):
    """Cria uma escola de exemplo completa, com datas relativas ao dia de hoje."""
    from django.contrib.auth.models import User

    from cantina.models import MovimentoEstoque, Produto
    from cantina import servico as cantina_servico
    from core.models import ConfiguracaoEscola
    from pagamentos.models import Mensalidade
    from precos import servico
    from precos.models import GrupoDesconto, PrecoAluna, RegraDesconto
    from usuarios.models import Aluna, Perfil, Turma

    hoje = hoje or timezone.localdate()

    def usuario(username, nome, sobrenome, telefone, staff=False):
        u = User(username=username, first_name=nome, last_name=sobrenome, is_staff=staff,
                 email=f'{username}@exemplo.com.br')
        u.set_unusable_password()  # só se entra pelos botões da demonstração
        u.save()
        Perfil.objects.create(user=u, telefone=telefone, is_responsavel=not staff)
        return u

    config = ConfiguracaoEscola.obter()
    config.subtitulo_hero = 'Escola de dança de exemplo'
    config.texto_sobre = 'Esta é uma escola fictícia, criada para você conhecer o sistema.'
    config.endereco = 'Rua das Flores, 100 - Centro'
    config.telefone = '(11) 90000-0000'
    config.email_contato = 'contato@exemplo.com.br'
    config.save()

    usuario(ADMIN, 'Administradora', 'Demonstração', '(11) 90000-0001', staff=True)
    mariana = usuario(RESPONSAVEL, 'Mariana', 'Souza', '(11) 90000-0002')
    carla = usuario('demo_carla', 'Carla', 'Ribeiro', '(11) 90000-0003')
    paulo = usuario('demo_paulo', 'Paulo', 'Mendes', '(11) 90000-0004')

    def turma(nome, valor, horario, dia, professor, regime='normal'):
        return Turma.objects.create(
            nome=nome, valor_mensalidade=Decimal(valor), horario=horario, dia_semana=dia,
            professor=professor, capacidade_maxima=15, regime_preco=regime,
        )

    ballet = turma('Ballet Infantil', '150', 'Segunda e Quarta, 14h às 15h', 'Segunda', 'Profª Ana')
    juvenil = turma('Ballet Juvenil', '150', 'Terça e Quinta, 16h às 17h', 'Terça', 'Profª Ana')
    jazz = turma('Jazz', '140', 'Sexta, 15h às 16h', 'Sexta', 'Prof. Bruno')
    ginastica = turma('Ginástica Rítmica', '130', 'Quarta, 17h às 18h', 'Quarta', 'Profª Clara')
    vocal = turma('Técnica Vocal em Grupo', '50', 'Sábado, 10h às 11h', 'Sábado', 'Profª Dora', regime='fixo')

    def aluna(nome, nascimento, responsavel, turmas, vencimento=10):
        a = Aluna.objects.create(
            nome=nome, genero='F', data_nascimento=nascimento, responsavel=responsavel,
            dia_vencimento=vencimento, tipo_aluna='infantil',
        )
        a.turmas.set(turmas)
        PrecoAluna.objects.create(aluna=a, valor_manual=False)  # o sistema calcula o valor
        return a

    alice = aluna('Alice Souza', date(hoje.year - 9, 3, 14), mariana, [ballet, jazz])
    helena = aluna('Helena Souza', date(hoje.year - 7, 8, 2), mariana, [ballet])
    beatriz = aluna('Beatriz Ribeiro', date(hoje.year - 12, 5, 21), carla, [juvenil, ginastica, vocal])
    sofia = aluna('Sofia Mendes', date(hoje.year - 6, 11, 30), paulo, [ballet], vencimento=5)

    # Descontos (tudo isso é editável na tela "Preços e descontos")
    golden = GrupoDesconto.objects.create(nome='Golden', descricao='Alunas com desconto de 10%')
    golden.alunas.add(alice, helena)
    familia = GrupoDesconto.objects.create(nome='Família Souza', eh_familia=True, representante=mariana)
    familia.alunas.add(alice, helena)
    RegraDesconto.objects.create(nome='Grupo Golden (10%)', efeito='percentual', valor=Decimal('10'),
                                 incide_em='todas', grupo=golden)
    RegraDesconto.objects.create(nome='Desconto de segunda modalidade (15%)', efeito='percentual',
                                 valor=Decimal('15'), incide_em='segunda')
    RegraDesconto.objects.create(nome='Desconto família', efeito='percentual', valor=Decimal('7.5'),
                                 incide_em='todas', familia='total_grupo_familia',
                                 minimo_integrantes=2, arredondar_total_para=Decimal('1')).familias_desconto.add(familia)

    # Mensalidades: 3 meses pagos e o mês atual em aberto (com uma atrasada, se o dia já passou)
    for atras in (3, 2, 1, 0):
        mes = _mes_atras(hoje, atras)

        for a in (alice, helena, beatriz, sofia):
            valor = servico.valor_para_mes(a, mes)
            pagador = servico.pagador_da_aluna(a, usar_login_proprio=False) or a.responsavel
            vencimento = mes.replace(day=min(a.dia_vencimento, 28))
            pago = atras > 0
            status = 'pago' if pago else ('atrasado' if vencimento < hoje else 'pendente')
            Mensalidade.objects.create(
                aluna=a, responsavel=pagador, mes_referencia=mes, valor=valor, data_vencimento=vencimento,
                status=status, forma_pagamento='pix' if pago else None,
                data_pagamento=timezone.make_aware(datetime.combine(vencimento, time(10, 0))) if pago else None,
            )

    # Cantina
    produtos = [
        ('Água mineral 500 ml', 'Bebidas', '3.00', '1.20', 48, 12, '7890000000011'),
        ('Suco de uva 200 ml', 'Bebidas', '5.00', '2.50', 30, 10, '7890000000028'),
        ('Barra de cereal', 'Lanches', '4.50', '2.00', 8, 10, '7890000000035'),
        ('Pão de queijo', 'Salgados', '6.00', '2.80', 0, 6, '7890000000042'),
        ('Gelatina', 'Doces', '3.50', '1.30', 20, 5, '7890000000059'),
    ]
    for nome, categoria, preco, custo, qtd, minimo, codigo in produtos:
        p = Produto.objects.create(
            nome=nome, categoria=categoria, preco=Decimal(preco), custo=Decimal(custo),
            estoque_minimo=minimo, codigo_barras=codigo,
        )
        if qtd:
            cantina_servico.movimentar(p, MovimentoEstoque.ENTRADA, qtd, motivo='Estoque inicial')

    return {'usuarios': User.objects.count(), 'alunas': Aluna.objects.count(), 'mensalidades': Mensalidade.objects.count()}


# --------------------------------------------------------------------------- pagamento simulado

SEGUNDOS_PARA_PAGAR = 12


def id_pagamento_demo(valor):
    return f'pay_demo_{int(timezone.now().timestamp())}_{int(Decimal(str(valor)) * 100)}'


def ler_id_pagamento_demo(payment_id):
    """('pay_demo_<instante>_<centavos>') -> (instante, valor) ou None."""
    try:
        _, _, instante, centavos = str(payment_id).split('_')
        return int(instante), Decimal(int(centavos)) / 100
    except (ValueError, TypeError):
        return None
