"""
Serviços dos contratos: a lógica que as telas (admin e família) chamam.

Nenhuma biblioteca de PDF é importada aqui no topo: `pdf` só é carregado quando
um contrato é de fato gerado (ver contratos/pdf.py).
"""

import hashlib
import json
import logging
import secrets
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.mail import EmailMessage
from django.db import IntegrityError, transaction
from django.utils import timezone

from . import regras
from .models import BolsaAluna, CodigoAssinatura, Contrato, ModeloContrato, OpcaoBolsa

logger = logging.getLogger(__name__)

LINHA_ASSINATURA = '_' * 38
LINHA_DATA = '____ / ____ / ________'
MINUTOS_VALIDADE_CODIGO = 15
MAX_TENTATIVAS_CODIGO = 5
SEGUNDOS_ENTRE_CODIGOS = 60
TAMANHO_MAXIMO_SCAN = 8 * 1024 * 1024


class ContratoIndisponivel(Exception):
    """O contrato não pode ser gerado agora (sem modelo ativo, cadastro incompleto...)."""


class ErroAssinatura(Exception):
    """Erro ao confirmar a assinatura (código errado, expirado, contrato atualizado...)."""


# ----------------------------------------------------------------- criação

def criar_contrato_pendente(aluna, ano=None):
    """Cria o contrato pendente da aluna no ano ativo, se ainda não houver um."""
    ano = ano or regras.ano_ativo()

    if not ano:
        return None

    if Contrato.objects.filter(aluna=aluna, ano=ano).exclude(status=Contrato.ANULADO).exists():
        return None

    try:
        with transaction.atomic():
            return Contrato.objects.create(
                aluna=aluna,
                aluna_nome=aluna.nome,
                contratante=regras.contratante_da_aluna(aluna),
                ano=ano,
            )
    except IntegrityError:
        return None


def gerar_pendentes():
    """
    Cria o contrato pendente de todas as alunas ativas que ainda não têm um.

    Devolve (criados, ano, sem_contratante), onde sem_contratante é a lista de
    alunas sem responsável nem login (ficam de fora).
    """
    from usuarios.models import Aluna

    ano = regras.ano_ativo()

    if not ano:
        return 0, None, []

    ja_tem = set(
        Contrato.objects.filter(ano=ano).exclude(status=Contrato.ANULADO)
        .values_list('aluna_id', flat=True)
    )

    criados = 0
    sem_contratante = []

    for aluna in Aluna.objects.filter(ativa=True).select_related('responsavel', 'usuario'):
        if aluna.pk in ja_tem:
            continue

        if not regras.contratante_da_aluna(aluna):
            sem_contratante.append(aluna)
            continue

        if criar_contrato_pendente(aluna, ano):
            criados += 1

    return criados, ano, sem_contratante


# ------------------------------------------------------------ preparo / valores

def resolver_modelo(contrato):
    """Escolhe o modelo certo (padrão ou bolsista) para a situação atual da aluna."""
    aluna = contrato.aluna

    if aluna is None:
        raise ContratoIndisponivel('Este contrato não está mais ligado a uma aluna.')

    tipo = regras.tipo_para_aluna(aluna)
    modelo = regras.modelo_ativo(tipo)

    if modelo is None:
        nome = 'de bolsista' if tipo == ModeloContrato.TIPO_BOLSISTA else 'padrão'
        raise ContratoIndisponivel(
            f'O contrato {nome} ainda não está disponível. Fale com a escola.'
        )

    if tipo == ModeloContrato.TIPO_BOLSISTA and not aluna.valor_mensalidade:
        raise ContratoIndisponivel(
            'O cadastro da bolsa está incompleto (falta o valor da mensalidade). '
            'Fale com a escola.'
        )

    return tipo, modelo


def _valores_bolsa(contrato):
    aluna = contrato.aluna
    bolsa = regras.bolsa_da_aluna(aluna)

    if bolsa is None:
        raise ContratoIndisponivel('A aluna não está cadastrada como bolsista.')

    percentual = bolsa.opcao.percentual
    cheio = aluna.valor_mensalidade
    a_pagar = regras.calcular_a_pagar(cheio, percentual)

    return {
        'BOLSA_PERCENTUAL': regras.formatar_percentual(percentual),
        'BOLSA_MENSALIDADE_CHEIA': regras.dinheiro(cheio),
        'BOLSA_MENSALIDADE_A_PAGAR': regras.dinheiro(a_pagar),
    }


def nascimento_formatado(contrato):
    """Data de nascimento da aluna como dd/mm/aaaa (a informada no contrato, senão a do cadastro)."""
    informada = ((contrato.dados or {}).get('aluna') or {}).get('data_nascimento')
    data = regras.interpretar_data(informada) or (contrato.aluna.data_nascimento if contrato.aluna else None)

    return data.strftime('%d/%m/%Y') if data else ''


def montar_valores(contrato, modelo, tipo, modo, assinado_em=None):
    """
    Dicionário nome -> texto para preencher o PDF.

    modo='impresso': assinatura e datas ficam em branco (para conferir ou assinar à mão).
    modo='digital':  assinatura e data preenchidas (usa `assinado_em`).
    """
    dados = contrato.dados or {}
    c = dados.get('contratante', {})
    nome = c.get('nome', '')

    valores = {
        'NOME_RESPONSAVEL': nome,
        'NOME_ALUNA': contrato.aluna_nome,
        'DATA_NASCIMENTO_ALUNA': nascimento_formatado(contrato),
        'CPF': regras.formatar_cpf(c.get('cpf', '')),
        'RG': c.get('rg', ''),
        'ENDERECO': c.get('endereco', ''),
        'TELEFONE': c.get('telefone', ''),
        'EMAIL': c.get('email', ''),
        'AUTORIZACAO_IMAGEM': (
            'NÃO AUTORIZA o uso da imagem da aluna.'
            if dados.get('nao_autoriza_imagem')
            else 'AUTORIZA o uso da imagem da aluna.'
        ),
    }

    if modo == 'digital':
        valores['DATA'] = timezone.localtime(assinado_em).strftime('%d/%m/%Y')
        valores['ASSINATURA'] = f'Assinado eletronicamente por {nome}'
        valores[regras.TEXTO_CONTRATADA] = (
            (modelo.valores or {}).get(regras.TEXTO_CONTRATADA) or regras.TEXTO_CONTRATADA_PADRAO
        )
    else:
        valores['DATA'] = LINHA_DATA
        valores['ASSINATURA'] = LINHA_ASSINATURA
        valores[regras.TEXTO_CONTRATADA] = LINHA_ASSINATURA

    nomes = modelo.nomes_marcadores()

    if nomes & regras.BOLSA:
        if tipo != ModeloContrato.TIPO_BOLSISTA:
            raise ContratoIndisponivel('Este modelo tem campos de bolsa, mas a aluna não é bolsista.')

        valores.update(_valores_bolsa(contrato))

    for marcador in nomes:
        if marcador in valores or regras.categoria_marcador(marcador) != 'ano':
            continue

        bruto = (modelo.valores or {}).get(marcador, '')

        if regras.e_dinheiro(marcador):
            valor = regras.parse_dinheiro(bruto)

            if valor is None:
                raise ContratoIndisponivel(
                    f'O valor de {marcador} ainda não foi definido no modelo do contrato.'
                )

            valores[marcador] = regras.dinheiro(valor)
        else:
            if not str(bruto).strip():
                raise ContratoIndisponivel(
                    f'O campo {marcador} ainda não foi preenchido no modelo do contrato.'
                )

            valores[marcador] = str(bruto).strip()

    return valores


def _assinatura_do_conteudo(modelo, valores):
    """Identifica o conteúdo (modelo + valores, sem assinatura/data) para detectar mudanças."""
    base = {
        k: v for k, v in valores.items()
        if k not in ('DATA', 'ASSINATURA', regras.TEXTO_CONTRATADA)
    }
    bruto = json.dumps({'modelo': modelo.hash_arquivo, 'valores': base}, sort_keys=True)

    return hashlib.sha256(bruto.encode('utf-8')).hexdigest()


def gerar_pdf(contrato, modo, assinado_em=None):
    """Gera o PDF do contrato (impresso ou digital). Devolve (bytes, avisos)."""
    from . import pdf

    tipo, modelo = resolver_modelo(contrato)
    valores = montar_valores(contrato, modelo, tipo, modo, assinado_em)

    try:
        return pdf.preencher(modelo.pdf_bytes, valores)
    except ValueError as erro:
        raise ContratoIndisponivel(str(erro))


def preparar_revisao(contrato):
    """
    Gera a versão para conferir/imprimir e guarda o identificador do conteúdo.

    Devolve (pdf_bytes, avisos). A assinatura digital só é aceita se o conteúdo
    ainda for o mesmo que a pessoa conferiu aqui.
    """
    tipo, modelo = resolver_modelo(contrato)
    valores = montar_valores(contrato, modelo, tipo, 'impresso')

    conteudo, avisos = gerar_pdf(contrato, 'impresso')

    contrato.tipo = tipo
    contrato.modelo = modelo
    contrato.previa_hash = _assinatura_do_conteudo(modelo, valores)
    contrato.save(update_fields=['tipo', 'modelo', 'previa_hash', 'atualizado_em'])

    return conteudo, avisos


# ------------------------------------------------------------ dados da família

def validar_dados(campos, email_login):
    """Valida o formulário da família. Devolve dict campo -> mensagem de erro."""
    erros = {}

    nome = ' '.join((campos.get('nome') or '').split())

    if len(nome.split()) < 2 or len(nome) < 5:
        erros['nome'] = 'Informe o nome completo.'

    if not regras.validar_cpf(campos.get('cpf')):
        erros['cpf'] = 'CPF inválido. Confira os números.'

    nascimento = regras.interpretar_data(campos.get('data_nascimento'))

    if nascimento is None:
        erros['data_nascimento'] = 'Informe a data de nascimento da aluna.'
    elif nascimento > timezone.localdate() or nascimento.year < 1920:
        erros['data_nascimento'] = 'Confira a data de nascimento da aluna.'

    if len((campos.get('rg') or '').strip()) < 4:
        erros['rg'] = 'Informe o RG.'

    if len((campos.get('endereco') or '').strip()) < 10:
        erros['endereco'] = 'Informe o endereço completo (rua, número, bairro e cidade).'

    if len(regras.so_digitos(campos.get('telefone'))) < 10:
        erros['telefone'] = 'Informe o telefone com DDD.'

    if not email_login:
        erros['email'] = (
            'Sua conta não tem e-mail cadastrado. O e-mail é necessário para '
            'confirmar a assinatura. Fale com a escola.'
        )

    return erros


def salvar_dados(contrato, user, campos):
    """
    Guarda os dados informados no contrato e no perfil da pessoa (para o próximo ano).

    Levanta ContratoIndisponivel se o modelo certo ainda não existe.
    """
    from usuarios.models import Perfil

    tipo, modelo = resolver_modelo(contrato)

    nome = ' '.join(campos['nome'].split())
    cpf = regras.so_digitos(campos['cpf'])
    nascimento = regras.interpretar_data(campos['data_nascimento'])

    contrato.dados = {
        'contratante': {
            'nome': nome,
            'cpf': cpf,
            'rg': campos['rg'].strip(),
            'endereco': campos['endereco'].strip(),
            'telefone': campos['telefone'].strip(),
            'email': user.email,
        },
        'aluna': {'data_nascimento': nascimento.isoformat()},
        'nao_autoriza_imagem': bool(campos.get('nao_autoriza_imagem')),
        'preenchido_em': timezone.now().isoformat(),
        'preenchido_por': user.pk,
    }
    contrato.tipo = tipo
    contrato.modelo = modelo
    contrato.status = Contrato.DADOS
    contrato.impresso_em = None
    contrato.save()

    # Se o cadastro da aluna ainda não tem a data de nascimento, ela passa a ficar salva lá.
    # Se já tem e a família informou outra, o cadastro NÃO é alterado: o admin vê o aviso.
    aluna = contrato.aluna

    if aluna is not None and aluna.data_nascimento is None:
        aluna.data_nascimento = nascimento
        aluna.save(update_fields=['data_nascimento'])

    perfil, _ = Perfil.objects.get_or_create(
        user=user, defaults={'telefone': campos['telefone'].strip(), 'is_responsavel': False},
    )
    perfil.cpf = regras.formatar_cpf(cpf)
    perfil.rg = campos['rg'].strip()
    perfil.endereco = campos['endereco'].strip()
    perfil.telefone = campos['telefone'].strip()
    perfil.save()


# -------------------------------------------------------------------- papel

def marcar_impresso(contrato):
    if contrato.status in (Contrato.DADOS, Contrato.AGUARDANDO_PAPEL):
        contrato.status = Contrato.AGUARDANDO_PAPEL
        contrato.impresso_em = timezone.now()
        contrato.save(update_fields=['status', 'impresso_em', 'atualizado_em'])


def tipo_de_arquivo(conteudo):
    """Confere pelo começo do arquivo se é PDF, JPG ou PNG. Devolve (content_type, extensão) ou None."""
    if conteudo[:5] == b'%PDF-':
        return 'application/pdf', 'pdf'

    if conteudo[:3] == b'\xff\xd8\xff':
        return 'image/jpeg', 'jpg'

    if conteudo[:8] == b'\x89PNG\r\n\x1a\n':
        return 'image/png', 'png'

    return None


def registrar_scan(contrato, arquivo, user):
    """Guarda o contrato assinado em papel (escaneado). Levanta ValueError se for inválido."""
    if contrato.status in (Contrato.ASSINADO_DIGITAL, Contrato.ANULADO):
        raise ValueError('Este contrato já foi assinado digitalmente ou está anulado.')

    conteudo = arquivo.read()

    if not conteudo:
        raise ValueError('O arquivo está vazio.')

    if len(conteudo) > TAMANHO_MAXIMO_SCAN:
        raise ValueError('O arquivo é maior que 8 MB. Reduza a qualidade do scanner e tente de novo.')

    tipo = tipo_de_arquivo(conteudo)

    if tipo is None:
        raise ValueError('Envie o contrato escaneado em PDF, JPG ou PNG.')

    content_type, extensao = tipo

    contrato.scan_arquivo = conteudo
    contrato.scan_nome = f'contrato-assinado-{contrato.ano}-{contrato.pk}.{extensao}'
    contrato.scan_tipo = content_type
    contrato.scan_enviado_em = timezone.now()
    contrato.scan_enviado_por = user
    contrato.status = Contrato.ASSINADO_PAPEL
    contrato.save()


def anular(contrato, motivo):
    contrato.status = Contrato.ANULADO
    contrato.anulado_em = timezone.now()
    contrato.anulado_motivo = (motivo or '').strip()[:300]
    contrato.save(update_fields=['status', 'anulado_em', 'anulado_motivo', 'atualizado_em'])


# ------------------------------------------------------------ assinatura digital

def mascarar_email(email):
    usuario, _, dominio = (email or '').partition('@')

    if not dominio:
        return email or ''

    return f'{usuario[:1]}{"*" * max(len(usuario) - 1, 2)}@{dominio}'


def enviar_codigo(contrato):
    """Envia por e-mail o código de 6 dígitos. Devolve o e-mail (mascarado)."""
    email = (contrato.dados or {}).get('contratante', {}).get('email')

    if not email:
        raise ErroAssinatura('Não há e-mail cadastrado para enviar o código.')

    agora = timezone.now()
    ultimo = contrato.codigos.first()

    if ultimo and (agora - ultimo.criado_em).total_seconds() < SEGUNDOS_ENTRE_CODIGOS:
        faltam = SEGUNDOS_ENTRE_CODIGOS - int((agora - ultimo.criado_em).total_seconds())
        raise ErroAssinatura(f'Aguarde {faltam} segundos para pedir um novo código.')

    contrato.codigos.filter(usado=False).update(usado=True)

    codigo = f'{secrets.randbelow(10 ** 6):06d}'
    registro = CodigoAssinatura.objects.create(
        contrato=contrato,
        codigo_hash=CodigoAssinatura.calcular_hash(contrato.pk, codigo),
        expira_em=agora + timedelta(minutes=MINUTOS_VALIDADE_CODIGO),
    )

    corpo = (
        f'Seu código para assinar o contrato é: {codigo}\n\n'
        f'Ele vale por {MINUTOS_VALIDADE_CODIGO} minutos.\n\n'
        'Se você não pediu este código, ignore esta mensagem.\n\n'
        'BAILAH Corpo e Cia'
    )

    try:
        EmailMessage(
            subject='Código para assinar o contrato - BAILAH Corpo e Cia',
            body=corpo,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[email],
        ).send()
    except Exception:
        registro.delete()
        logger.exception('Falha ao enviar o código de assinatura (contrato %s)', contrato.pk)
        raise ErroAssinatura(
            'Não foi possível enviar o e-mail agora. Tente de novo em alguns minutos.'
        )

    return mascarar_email(email)


def _agrupar(codigo):
    return '-'.join(codigo[i:i + 4] for i in range(0, len(codigo), 4))


def confirmar_assinatura(contrato_id, user, codigo, ip, user_agent):
    """
    Confere o código e assina o contrato. Levanta ErroAssinatura com uma mensagem
    para a pessoa se algo estiver errado.

    Atenção: os erros são levantados DEPOIS de sair da transação. Se fossem levantados
    dentro dela, o Django desfaria tudo, inclusive a contagem de tentativas erradas.
    """
    from . import pdf

    erro = None

    with transaction.atomic():
        contrato = Contrato.objects.select_for_update().get(pk=contrato_id)

        if contrato.status not in (Contrato.DADOS, Contrato.AGUARDANDO_PAPEL):
            erro = 'Este contrato não está disponível para assinatura.'
        else:
            registro = (
                contrato.codigos.select_for_update()
                .filter(usado=False).order_by('-criado_em').first()
            )

            if registro is None or registro.expirado:
                erro = 'O código expirou. Peça um novo código.'
            else:
                registro.tentativas += 1
                informado = ''.join(ch for ch in (codigo or '') if ch.isdigit())

                if registro.tentativas > MAX_TENTATIVAS_CODIGO:
                    registro.usado = True
                    registro.save(update_fields=['tentativas', 'usado'])
                    erro = 'Muitas tentativas. Peça um novo código.'
                elif CodigoAssinatura.calcular_hash(contrato.pk, informado) != registro.codigo_hash:
                    registro.save(update_fields=['tentativas'])
                    restantes = MAX_TENTATIVAS_CODIGO - registro.tentativas
                    erro = f'Código incorreto. Você ainda tem {restantes} tentativa(s).'
                else:
                    # O conteúdo mudou desde a última conferência (ex.: o admin alterou um valor)?
                    tipo, modelo = resolver_modelo(contrato)
                    conferido = _assinatura_do_conteudo(
                        modelo, montar_valores(contrato, modelo, tipo, 'impresso'),
                    )

                    if conferido != contrato.previa_hash:
                        registro.usado = True
                        registro.save(update_fields=['tentativas', 'usado'])
                        erro = (
                            'O contrato foi atualizado depois da sua última conferência. '
                            'Confira o contrato de novo e então assine.'
                        )
                    else:
                        _assinar(contrato, modelo, tipo, ip, user_agent, user, pdf)

    if erro:
        raise ErroAssinatura(erro)

    _enviar_copia(contrato)

    return contrato


def _assinar(contrato, modelo, tipo, ip, user_agent, user, pdf):
    """Gera o PDF assinado (contrato + termo), calcula os hashes e grava tudo."""
    agora = timezone.now()
    valores = montar_valores(contrato, modelo, tipo, 'digital', assinado_em=agora)
    corpo_pdf, _ = pdf.preencher(modelo.pdf_bytes, valores)

    hash_conteudo = pdf.hash_pdf(corpo_pdf)
    codigo_verificacao = _agrupar(hash_conteudo[:12].upper())
    c = contrato.dados['contratante']
    tipo_nome = dict(ModeloContrato.TIPOS)[tipo]

    termo = pdf.termo_assinatura({
        'contrato': f'{tipo_nome} {contrato.ano}',
        'aluna': contrato.aluna_nome,
        'nome': c['nome'],
        'cpf': regras.formatar_cpf(c['cpf']),
        'email': c['email'],
        'assinado_em': timezone.localtime(agora).strftime('%d/%m/%Y às %H:%M:%S (horário de Brasília)'),
        'ip': ip or 'não informado',
        'navegador': (user_agent or 'não informado')[:160],
        'metodo': 'Login e senha da conta + código de 6 dígitos enviado por e-mail',
        'codigo': codigo_verificacao,
        'hash': hash_conteudo,
    })
    final = pdf.juntar(corpo_pdf, termo)

    campos_ano = {
        m: valores[m] for m in modelo.nomes_marcadores()
        if regras.categoria_marcador(m) == 'ano' and m in valores
    }
    contrato.dados = {**contrato.dados, 'campos_ano': campos_ano}
    contrato.pdf_assinado = final
    contrato.hash_conteudo = hash_conteudo
    contrato.hash_arquivo = pdf.hash_pdf(final)
    contrato.codigo_verificacao = codigo_verificacao
    contrato.assinado_em = agora
    contrato.assinado_ip = ip or None
    contrato.assinado_user_agent = (user_agent or '')[:300]
    contrato.tipo = tipo
    contrato.modelo = modelo
    contrato.contratante = contrato.contratante or user
    contrato.status = Contrato.ASSINADO_DIGITAL
    contrato.save()

    contrato.codigos.filter(usado=False).update(usado=True)


def _enviar_copia(contrato):
    """Manda uma cópia do contrato assinado por e-mail. Falhar aqui não desfaz a assinatura."""
    email = (contrato.dados or {}).get('contratante', {}).get('email')

    if not email:
        return False

    try:
        mensagem = EmailMessage(
            subject=f'Contrato assinado - {contrato.aluna_nome} ({contrato.ano})',
            body=(
                f'Olá!\n\nSegue em anexo a cópia do contrato de {contrato.aluna_nome} '
                f'({contrato.ano}), assinado eletronicamente.\n\n'
                f'Código de verificação: {contrato.codigo_verificacao}\n\n'
                'Você também pode baixá-lo a qualquer momento no site, em "Contrato".\n\n'
                'BAILAH Corpo e Cia'
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[email],
        )
        mensagem.attach(
            f'contrato-{contrato.ano}-{contrato.pk}.pdf', contrato.pdf_assinado_bytes, 'application/pdf',
        )
        mensagem.send()
        return True
    except Exception:
        logger.exception('Falha ao enviar a cópia do contrato assinado (contrato %s)', contrato.pk)
        return False


# ------------------------------------------------------------ modelos (admin)

def problemas_para_ativar(modelo):
    """Lista de problemas que impedem ativar o modelo (lista vazia = pode ativar)."""
    problemas = []
    nomes = modelo.nomes_marcadores()

    obrigatorios = (
        regras.OBRIGATORIOS_BOLSISTA if modelo.tipo == ModeloContrato.TIPO_BOLSISTA
        else regras.OBRIGATORIOS_PADRAO
    )

    faltando = sorted(obrigatorios - nomes)

    if faltando:
        problemas.append(
            'Faltam marcadores no PDF: ' + ', '.join(f'[[{n}]]' for n in faltando) + '.'
        )

    if modelo.tipo == ModeloContrato.TIPO_PADRAO and nomes & regras.BOLSA:
        problemas.append(
            'O contrato padrão tem marcadores de bolsa (BOLSA_...). Eles só valem no contrato de bolsista.'
        )

    valores = modelo.valores or {}

    for nome in sorted(n for n in nomes if regras.categoria_marcador(n) == 'ano'):
        bruto = valores.get(nome, '')

        if regras.e_dinheiro(nome):
            if regras.parse_dinheiro(bruto) is None:
                problemas.append(f'Informe um valor válido para {nome}.')
        elif not str(bruto).strip():
            problemas.append(f'Preencha o campo {nome}.')

    return problemas


def criar_modelo(arquivo, tipo, nome, ano, user):
    """Analisa o PDF enviado e cria o modelo (inativo). Devolve (modelo, erro, analise)."""
    from . import pdf

    conteudo = arquivo.read()

    if tipo_de_arquivo(conteudo) is None or conteudo[:5] != b'%PDF-':
        return None, 'Envie o contrato em PDF.', None

    if len(conteudo) > TAMANHO_MAXIMO_SCAN:
        return None, 'O PDF é maior que 8 MB.', None

    analise = pdf.analisar_modelo(conteudo)

    if analise.get('erro'):
        return None, analise['erro'], None

    modelo = ModeloContrato.objects.create(
        tipo=tipo,
        nome=nome,
        ano=ano,
        arquivo_pdf=conteudo,
        nome_arquivo=getattr(arquivo, 'name', '')[:200],
        hash_arquivo=hashlib.sha256(conteudo).hexdigest(),
        marcadores=analise['marcadores'],
        criado_por=user,
    )

    return modelo, None, analise


def ativar_modelo(modelo):
    """Ativa este modelo e desativa os outros do mesmo tipo."""
    with transaction.atomic():
        ModeloContrato.objects.filter(tipo=modelo.tipo, ativo=True).exclude(pk=modelo.pk).update(ativo=False)
        modelo.ativo = True
        modelo.save(update_fields=['ativo'])


# -------------------------------------------------------------------- bolsa

def validar_bolsa_post(post, valor_mensalidade, aluna=None):
    """Valida os campos "É bolsista?" do formulário da aluna. Devolve mensagem de erro ou None."""
    if post.get('e_bolsista') != 'on':
        return None

    opcao_id = (post.get('opcao_bolsa') or '').strip()

    if not opcao_id.isdigit():
        return 'Escolha qual é a bolsa da aluna.'

    atual = regras.bolsa_da_aluna(aluna) if aluna else None
    opcoes = OpcaoBolsa.objects.filter(pk=int(opcao_id))

    if not any(o.ativa or (atual and atual.opcao_id == o.pk) for o in opcoes):
        return 'A opção de bolsa escolhida não existe ou está inativa.'

    if not valor_mensalidade or Decimal(valor_mensalidade) <= 0:
        return (
            'Para marcar a aluna como bolsista, informe o valor da mensalidade (o valor '
            'cheio, antes da bolsa). Ele aparece no contrato.'
        )

    return None


def salvar_bolsa_da_aluna(aluna, post):
    """Marca ou desmarca a aluna como bolsista conforme o formulário."""
    antes = regras.bolsa_da_aluna(aluna)

    if post.get('e_bolsista') == 'on':
        opcao = OpcaoBolsa.objects.get(pk=int(post['opcao_bolsa']))
        BolsaAluna.objects.update_or_create(aluna=aluna, defaults={'opcao': opcao})
        mudou = antes is None or antes.opcao_id != opcao.pk
    else:
        BolsaAluna.objects.filter(aluna=aluna).delete()
        mudou = antes is not None

    if mudou:
        # A versão que já foi impressa não vale mais: volta para "dados preenchidos".
        aluna.contratos.filter(status=Contrato.AGUARDANDO_PAPEL).update(
            status=Contrato.DADOS, impresso_em=None,
        )
