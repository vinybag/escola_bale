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

    # Salva QR code
    qr_content = gerar_qr_code_image(payload)
    qr_name = f'qr-{ingresso.codigo_unico}.png'
    ingresso.qrcode_image.save(qr_name, qr_content, save=True)

    # Base da arte: imagem do evento ou fundo branco
    if ingresso.evento.imagem_ingresso:
        base = Image.open(ingresso.evento.imagem_ingresso.path).convert("RGB")
    else:
        base = Image.new("RGB", (1200, 1800), "white")

    # QR code redimensionado
    qr_img = Image.open(ingresso.qrcode_image.path).convert("RGB")
    qr_img = qr_img.resize((320, 320))

    draw = ImageDraw.Draw(base)

    try:
        font_titulo = ImageFont.truetype("arial.ttf", 48)
        font_texto = ImageFont.truetype("arial.ttf", 32)
    except Exception:
        font_titulo = ImageFont.load_default()
        font_texto = ImageFont.load_default()

    draw.text((80, 80), ingresso.evento.titulo, fill="black", font=font_titulo)
    draw.text((80, 160), f"Código: {ingresso.codigo_unico}", fill="black", font=font_texto)
    draw.text((80, 210), f"Comprador: {ingresso.pedido.nome_completo}", fill="black", font=font_texto)
    draw.text((80, 260), f"WhatsApp: {ingresso.pedido.whatsapp}", fill="black", font=font_texto)

    # Cola QR code centralizado na parte inferior
    x_qr = (base.width - qr_img.width) // 2
    y_qr = base.height - qr_img.height - 120
    base.paste(qr_img, (x_qr, y_qr))

    output = BytesIO()
    base.save(output, format='PNG')

    final_name = f'ingresso-{slugify(ingresso.evento.titulo)}-{ingresso.codigo_unico}.png'
    ingresso.imagem_ingresso.save(final_name, ContentFile(output.getvalue()), save=True)

    return ingresso


def confirmar_pagamento_pedido(pedido):
    with transaction.atomic():
        pedido.refresh_from_db()

        if pedido.status != 'pago':
            pedido.marcar_como_pago()

        if pedido.ingressos.exists():
            return

        for _ in range(pedido.quantidade):
            ingresso = IngressoEvento.objects.create(
                pedido=pedido,
                evento=pedido.evento,
                nome_participante=pedido.nome_completo,
            )
            gerar_arquivos_ingresso(ingresso)