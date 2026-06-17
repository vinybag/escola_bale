from io import BytesIO
import qrcode

from PIL import Image, ImageDraw, ImageFont
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils.text import slugify

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
        base = Image.open(ingresso.evento.imagem_ingresso.path).convert("RGB")
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

    try:
        font_titulo = ImageFont.truetype("arial.ttf", 42)
        font_texto = ImageFont.truetype("arial.ttf", 26)
        font_codigo = ImageFont.truetype("arial.ttf", 30)
    except Exception:
        font_titulo = ImageFont.load_default()
        font_texto = ImageFont.load_default()
        font_codigo = ImageFont.load_default()

    y_base = base.height + margem + 25

    draw.text((margem, y_base), ingresso.evento.titulo, fill="black", font=font_titulo)
    draw.text((margem, y_base + 60), f"Código: {ingresso.codigo_unico}", fill="black", font=font_codigo)
    draw.text((margem, y_base + 110), f"Comprador: {ingresso.pedido.nome_completo}", fill="black", font=font_texto)
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
    with transaction.atomic():
        pedido.refresh_from_db()

        if pedido.status != 'pago':
            pedido.marcar_como_pago()
            print(f"[INGRESSO] Pedido {pedido.id} marcado como pago")

        if pedido.ingressos.exists():
            print(f"[INGRESSO] Pedido {pedido.id} já possui ingressos. Garantindo arquivos...")
            garantir_arquivos_ingressos_do_pedido(pedido)
            return pedido.ingressos.all()

        ingressos_criados = []

        for _ in range(pedido.quantidade):
            ingresso = IngressoEvento.objects.create(
                pedido=pedido,
                evento=pedido.evento,
                nome_participante=pedido.nome_completo,
            )
            print(f"[INGRESSO] Criado ingresso {ingresso.codigo_unico}")
            gerar_arquivos_ingresso(ingresso)
            print(f"[INGRESSO] Arquivos gerados para {ingresso.codigo_unico}")
            ingressos_criados.append(ingresso)

        return ingressos_criados