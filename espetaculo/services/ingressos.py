from io import BytesIO
import qrcode


from PIL import Image, ImageDraw
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils.text import slugify


from espetaculo.fontes import carregar_fonte
from espetaculo.models import IngressoEvento



def gerar_qr_code_image(conteudo):
    qr = qrcode.QRCode(
        version=1,
        box_size=8,
        border=2,
    )
    qr.add_data(conteudo)
    qr.make(fit=True)


    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    return ContentFile(buffer.getvalue())


def truncar_texto(draw, texto, fonte, largura_maxima):
    if draw.textlength(texto, font=fonte) <= largura_maxima:
        return texto
    while texto and draw.textlength(texto + "...", font=fonte) > largura_maxima:
        texto = texto[:-1]
    return (texto + "...") if texto else "..."



def gerar_arquivos_ingresso(ingresso):
    payload = str(ingresso.codigo_unico)


    if ingresso.qrcode_image:
        ingresso.qrcode_image.delete(save=False)


    if ingresso.imagem_ingresso:
        ingresso.imagem_ingresso.delete(save=False)


    qr_content = gerar_qr_code_image(payload)
    qr_name = f'qr-{ingresso.codigo_unico}.png'
    ingresso.qrcode_image.save(qr_name, qr_content, save=True)


    if ingresso.evento.imagem_ingresso:
        try:
            base = Image.open(ingresso.evento.imagem_ingresso.path).convert("RGB")
        except FileNotFoundError:
            print(f"[INGRESSO] Imagem base do evento não encontrada para o ingresso {ingresso.codigo_unico}. Usando fundo branco.")
            base = Image.new("RGB", (1200, 1400), "white")
    else:
        base = Image.new("RGB", (1200, 1400), "white")


    qr_img = Image.open(ingresso.qrcode_image.path).convert("RGB")
    qr_img = qr_img.resize((280, 280))


    margem = 40
    rodape_altura = 420


    largura_final = base.width + (margem * 2)
    altura_final = base.height + rodape_altura + (margem * 2)


    final = Image.new("RGB", (largura_final, altura_final), "white")
    final.paste(base, (margem, margem))


    draw = ImageDraw.Draw(final)


    font_titulo = carregar_fonte(42, negrito=True)
    font_texto = carregar_fonte(26)
    font_codigo = carregar_fonte(30, negrito=True)


    y_base = base.height + margem + 25


    largura_disponivel_texto = ((largura_final - qr_img.width) // 2) - margem - 10

    comprador_texto = truncar_texto(
        draw,
        f"Comprador: {ingresso.pedido.nome_completo}",
        font_texto,
        largura_disponivel_texto,
    )

    draw.text((margem, y_base), ingresso.evento.titulo, fill="black", font=font_titulo)
    draw.text((margem, y_base + 60), f"Código: {ingresso.codigo_unico}", fill="black", font=font_codigo)
    draw.text((margem, y_base + 110), comprador_texto, fill="black", font=font_texto)
    draw.text((margem, y_base + 150), f"WhatsApp: {ingresso.pedido.whatsapp}", fill="black", font=font_texto)
    draw.text((margem, y_base + 190), f"Status: {ingresso.status.upper()}", fill="black", font=font_texto)


    x_qr = (largura_final - qr_img.width) // 2
    y_qr = base.height + margem + 120
    final.paste(qr_img, (x_qr, y_qr))


    output = BytesIO()
    final.save(output, format='PNG')


    final_name = f'ingresso-{slugify(ingresso.evento.titulo)}-{ingresso.codigo_unico}.png'
    ingresso.imagem_ingresso.save(final_name, ContentFile(output.getvalue()), save=True)


    return ingresso



def regenerar_ingresso(ingresso):
    ingresso.refresh_from_db()
    return gerar_arquivos_ingresso(ingresso)



def regenerar_ingressos_do_pedido(pedido):
    pedido.refresh_from_db()


    for ingresso in pedido.ingressos.all():
        gerar_arquivos_ingresso(ingresso)


    return pedido.ingressos.all()



def garantir_arquivos_ingressos_do_pedido(pedido):
    pedido.refresh_from_db()


    for ingresso in pedido.ingressos.all():
        if not ingresso.qrcode_image or not ingresso.imagem_ingresso:
            gerar_arquivos_ingresso(ingresso)
            print(f"[INGRESSO] Arquivos recriados para {ingresso.codigo_unico}")


    return pedido.ingressos.all()



def confirmar_pagamento_pedido(pedido):
    # Import local para evitar import circular (espetaculo/views.py não
    # importa deste módulo, mas isolar aqui deixa a dependência explícita
    # só onde é usada).
    from espetaculo.views import gerar_ingressos_do_pedido

    with transaction.atomic():
        pedido.refresh_from_db()

        # CORREÇÃO CRÍTICA: nunca "ressuscitar" um pedido que já foi
        # expirado ou cancelado. Antes, um pagamento PIX antigo chegando
        # atrasado (ex.: a pessoa pagou um PIX de um pedido que já tinha
        # sido liberado por abandono) fazia o sistema gerar o ingresso
        # mesmo assim — só que, nesse meio tempo, o assento já podia ter
        # sido vendido para outra pessoa, e a gratuidade já tinha sido
        # devolvida e possivelmente usada de novo por outra família.
        # Agora, nesse caso, o pagamento é apenas registrado no log para
        # conferência manual — ver o comando
        # `diagnosticar_pedidos_ressuscitados`.
        if pedido.status in ('expirado', 'cancelado'):
            print(
                f"[INGRESSO] Pagamento recebido para o pedido {pedido.id}, "
                f"mas ele já está '{pedido.status}' — IGNORADO para não "
                "arriscar vender o mesmo assento duas vezes. Requer "
                "conferência manual."
            )
            return []

        if pedido.status != 'pago':
            pedido.marcar_como_pago()
            print(f"[INGRESSO] Pedido {pedido.id} marcado como pago")

        # CORREÇÃO: usa a mesma função usada em todo o resto do sistema
        # para gerar os ingressos (a mesma do fluxo de compra pelo site e
        # da geração manual pelo admin). Antes, esta função criava
        # ingressos "soltos" — sem vincular a nenhum assento específico e
        # sem marcar o assento como vendido, mesmo em eventos com
        # assentos numerados. Isso deixava o assento preso em
        # "reservado_temporario" para sempre, correndo o risco de ser
        # liberado e vendido de novo para outra pessoa.
        gerar_ingressos_do_pedido(
            pedido,
            assentos_ids=pedido.assentos_ids,
            quantidade_gratuita=pedido.quantidade_gratuita,
        )

        return list(pedido.ingressos.all())