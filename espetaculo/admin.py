import os
import zipfile
from io import BytesIO

from django.contrib import admin, messages
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.urls import path, reverse
from django.utils.html import format_html, format_html_join

from .models import (
    Espetaculo,
    InscricaoAudicao,
    PedidoIngressoEvento,
    IngressoEvento,
)
from .views import gerar_ingressos_do_pedido

class PedidoIngressoEventoInline(admin.TabularInline):
    model = PedidoIngressoEvento
    extra = 0
    can_delete = False
    fields = (
        'nome_completo',
        'whatsapp',
        'quantidade',
        'valor_total',
        'status',
        'criado_em',
        'ver_pedido',
    )
    readonly_fields = fields
    show_change_link = True
    ordering = ('-criado_em',)

    def ver_pedido(self, obj):
        url = reverse('admin:espetaculo_pedidoingressoevento_change', args=[obj.pk])
        return format_html('<a href="{}">Abrir pedido</a>', url)

    ver_pedido.short_description = 'Detalhes'


@admin.register(Espetaculo)
class EspetaculoAdmin(admin.ModelAdmin):
    list_display = ['titulo', 'tipo', 'publico', 'data_apresentacao', 'venda_aberta', 'ativo']
    list_filter = ['tipo', 'publico', 'ativo', 'audicao_aberta', 'venda_aberta']
    search_fields = ['titulo', 'descricao', 'local']
    inlines = [PedidoIngressoEventoInline]

    fieldsets = (
        ('Informações Básicas', {
            'fields': ('tipo', 'publico', 'titulo', 'subtitulo', 'descricao')
        }),
        ('Data e Local', {
            'fields': ('data_apresentacao', 'local', 'endereco')
        }),
        ('Arquivos', {
            'fields': ('imagem', 'arquivo_divulgacao', 'arquivo_informacoes', 'arquivo_edital')
        }),
        ('Audição', {
            'fields': ('audicao_aberta', 'audicao_data_inicio', 'audicao_data_fim', 'audicao_instrucoes')
        }),
        ('Venda de Ingressos', {
            'fields': ('venda_aberta', 'venda_data_inicio', 'preco_ingresso')
        }),
        ('Controle', {
            'fields': ('ativo',)
        }),
    )


@admin.register(InscricaoAudicao)
class InscricaoAudicaoAdmin(admin.ModelAdmin):
    list_display = ['nome_completo', 'whatsapp', 'idade', 'personagens', 'data_inscricao', 'lida']
    list_filter = ['lida', 'data_inscricao']
    search_fields = ['nome_completo', 'whatsapp']
    list_editable = ['lida']

class IngressoEventoInline(admin.TabularInline):
    model = IngressoEvento
    extra = 0
    can_delete = False
    fields = (
        'codigo_unico',
        'nome_participante',
        'status',
        'criado_em',
        'abrir_ingresso',
    )
    readonly_fields = fields
    show_change_link = True
    ordering = ('criado_em',)

    def abrir_ingresso(self, obj):
        url = reverse('admin:espetaculo_ingressoevento_change', args=[obj.pk])
        return format_html('<a href="{}">Abrir ingresso</a>', url)

    abrir_ingresso.short_description = 'Detalhes'

@admin.register(PedidoIngressoEvento)
class PedidoIngressoEventoAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'nome_completo',
        'tipo_registro',
        'evento',
        'quantidade',
        'valor_total',
        'status',
        'criado_em',
    ]
    list_filter = ['status', 'criado_em', 'evento']
    search_fields = ['nome_completo', 'whatsapp', 'email', 'asaas_payment_id', 'external_reference']
    inlines = [IngressoEventoInline]

    readonly_fields = [
        'evento',
        'nome_completo',
        'email',
        'whatsapp',
        'cpf',
        'quantidade',
        'valor_unitario',
        'valor_total',
        'status',
        'data_pagamento',
        'asaas_payment_id',
        'asaas_customer_id',
        'asaas_status',
        'asaas_invoice_url',
        'codigo_pix',
        'qr_code_pix',
        'external_reference',
        'criado_em',
        'atualizado_em',
        'link_evento',
        'resumo_ingressos',
        'tipo_registro',
        'downloads_ingressos',
        'baixar_todos_zip_link',
    ]

    fieldsets = (
        ('Comprador', {
            'fields': (
                'nome_completo',
                'email',
                'whatsapp',
                'cpf',
                'tipo_registro',
            )
        }),
        ('Evento', {
            'fields': (
                'evento',
                'link_evento',
            )
        }),
        ('Pagamento', {
            'fields': (
                'status',
                'quantidade',
                'valor_unitario',
                'valor_total',
                'data_pagamento',
                'asaas_payment_id',
                'asaas_customer_id',
                'asaas_status',
                'asaas_invoice_url',
                'external_reference',
            )
        }),
        ('PIX', {
            'fields': (
                'codigo_pix',
                'qr_code_pix',
            )
        }),
        ('Ingressos', {
            'fields': (
                'resumo_ingressos',
                'downloads_ingressos',
                'baixar_todos_zip_link',
            )
        }),
        ('Controle', {
            'fields': (
                'criado_em',
                'atualizado_em',
            )
        }),
    )

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                '<int:pedido_id>/baixar-todos-zip/',
                self.admin_site.admin_view(self.baixar_todos_zip_view),
                name='espetaculo_pedidoingressoevento_baixar_todos_zip',
            ),
        ]
        return custom_urls + urls

    def tipo_registro(self, obj):
        texto = f"{obj.nome_completo} {obj.email or ''} {obj.whatsapp or ''}".lower()
        suspeitos = ['teste', 'test', '123', '000', 'fake']
        if any(item in texto for item in suspeitos):
            return 'Possível teste'
        return 'Cliente'

    tipo_registro.short_description = 'Tipo'

    def link_evento(self, obj):
        url = reverse('admin:espetaculo_espetaculo_change', args=[obj.evento.pk])
        return format_html('<a href="{}">{}</a>', url, obj.evento.titulo)

    link_evento.short_description = 'Abrir evento'

    def resumo_ingressos(self, obj):
        ingressos = obj.ingressos.all().order_by('criado_em')
        if not ingressos.exists():
            return 'Nenhum ingresso gerado ainda.'

        links = []
        for ingresso in ingressos:
            url = reverse('admin:espetaculo_ingressoevento_change', args=[ingresso.pk])
            links.append(
                f'<li><a href="{url}">{ingresso.codigo_unico}</a> - {ingresso.get_status_display()}</li>'
            )

        return format_html('<ul>{}</ul>', format_html(''.join(links)))

    resumo_ingressos.short_description = 'Ingressos do pedido'

    def downloads_ingressos(self, obj):
        ingressos = obj.ingressos.all().order_by('criado_em')

        if not ingressos.exists():
            return 'Nenhum ingresso disponível para download.'

        itens = []
        for ingresso in ingressos:
            url_admin = reverse('admin:espetaculo_ingressoevento_change', args=[ingresso.pk])
            url_ver = reverse('espetaculo:ver_imagem_ingresso', args=[ingresso.pk])
            url_baixar = reverse('espetaculo:baixar_ingresso', args=[ingresso.pk])
            url_qr = reverse('espetaculo:baixar_qrcode_ingresso', args=[ingresso.pk])

            itens.append((
                format_html(
                    '<li>'
                    '<strong>{}</strong> - '
                    '<a href="{}" target="_blank">abrir no admin</a> | '
                    '<a href="{}" target="_blank">ver imagem</a> | '
                    '<a href="{}" target="_blank">baixar ingresso</a> | '
                    '<a href="{}" target="_blank">baixar QR</a>'
                    '</li>',
                    ingresso.codigo_unico,
                    url_admin,
                    url_ver,
                    url_baixar,
                    url_qr,
                ),
            ))

        return format_html('<ul>{}</ul>', format_html_join('', '{}', itens))

    downloads_ingressos.short_description = 'Downloads dos ingressos'

    def baixar_todos_zip_link(self, obj):
        if not obj.ingressos.exists():
            return 'Nenhum ingresso para baixar.'

        url = reverse('admin:espetaculo_pedidoingressoevento_baixar_todos_zip', args=[obj.pk])
        return format_html('<a href="{}">Baixar todos em ZIP</a>', url)

    baixar_todos_zip_link.short_description = 'Download em lote'

    def baixar_todos_zip_view(self, request, pedido_id):
        pedido = get_object_or_404(PedidoIngressoEvento, pk=pedido_id)

        ingressos = pedido.ingressos.all().order_by('criado_em')
        if not ingressos.exists():
            raise Http404('Nenhum ingresso encontrado para este pedido.')

        buffer = BytesIO()

        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            total_arquivos = 0

            for ingresso in ingressos:
                ingresso.garantir_arquivos()

                if ingresso.imagem_ingresso and ingresso.imagem_ingresso.name:
                    storage = ingresso.imagem_ingresso.storage
                    nome = ingresso.imagem_ingresso.name
                    if storage.exists(nome):
                        with storage.open(nome, 'rb') as f:
                            zip_file.writestr(
                                f'ingressos/{os.path.basename(nome)}',
                                f.read()
                            )
                            total_arquivos += 1

                if ingresso.qrcode_image and ingresso.qrcode_image.name:
                    storage = ingresso.qrcode_image.storage
                    nome = ingresso.qrcode_image.name
                    if storage.exists(nome):
                        with storage.open(nome, 'rb') as f:
                            zip_file.writestr(
                                f'qrcodes/{os.path.basename(nome)}',
                                f.read()
                            )
                            total_arquivos += 1

        if total_arquivos == 0:
            raise Http404('Nenhum arquivo de ingresso disponível para este pedido.')

        buffer.seek(0)

        nome_zip = f'pedido-{pedido.pk}-ingressos.zip'
        response = HttpResponse(buffer.getvalue(), content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename="{nome_zip}"'
        return response

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return True

    def get_actions(self, request):
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions

    @admin.action(description='Garantir ingressos dos pedidos selecionados')
    def garantir_ingressos(self, request, queryset):
        total_pedidos = 0
        total_ingressos = 0

        for pedido in queryset:
            gerar_ingressos_do_pedido(pedido)
            total_pedidos += 1
            total_ingressos += pedido.ingressos.count()

        self.message_user(
            request,
            f'Ingressos garantidos em {total_pedidos} pedido(s). Total atual de ingressos relacionados: {total_ingressos}.',
            level=messages.SUCCESS,
        )

    @admin.action(description='Regerar arquivos dos ingressos selecionados')
    def regerar_ingressos(self, request, queryset):
        total_pedidos = 0
        total_ingressos = 0

        for pedido in queryset:
            ingressos = pedido.ingressos.all()

            for ingresso in ingressos:
                ingresso.garantir_arquivos(force=True)
                total_ingressos += 1

            total_pedidos += 1

        self.message_user(
            request,
            f'{total_ingressos} ingresso(s) regenerado(s) em {total_pedidos} pedido(s).',
            level=messages.SUCCESS,
        )

    actions = ['garantir_ingressos', 'regerar_ingressos']


@admin.register(IngressoEvento)
class IngressoEventoAdmin(admin.ModelAdmin):
    list_display = [
        'codigo_unico',
        'evento',
        'nome_participante',
        'status',
        'criado_em',
        'baixar_imagem_link',
        'baixar_qrcode_link',
    ]
    list_filter = ['status', 'evento', 'criado_em']
    search_fields = [
        'codigo_unico',
        'nome_participante',
        'pedido__nome_completo',
        'pedido__whatsapp',
        'pedido__email',
    ]

    readonly_fields = [
        'pedido',
        'evento',
        'codigo_unico',
        'nome_participante',
        'status',
        'validado_em',
        'criado_em',
        'link_pedido',
        'link_evento',
        'baixar_imagem_link',
        'baixar_qrcode_link',
        'imagem_atual',
        'qrcode_atual',
    ]

    fieldsets = (
        ('Ingresso', {
            'fields': (
                'codigo_unico',
                'nome_participante',
                'status',
                'validado_em',
                'criado_em',
            )
        }),
        ('Relacionamentos', {
            'fields': (
                'pedido',
                'link_pedido',
                'evento',
                'link_evento',
            )
        }),
        ('Arquivos', {
            'fields': (
                'imagem_atual',
                'qrcode_atual',
                'baixar_imagem_link',
                'baixar_qrcode_link',
            )
        }),
    )

    def link_pedido(self, obj):
        url = reverse('admin:espetaculo_pedidoingressoevento_change', args=[obj.pedido.pk])
        return format_html('<a href="{}">Abrir pedido #{}</a>', url, obj.pedido.pk)

    link_pedido.short_description = 'Pedido'

    def link_evento(self, obj):
        url = reverse('admin:espetaculo_espetaculo_change', args=[obj.evento.pk])
        return format_html('<a href="{}">{}</a>', url, obj.evento.titulo)

    link_evento.short_description = 'Evento'

    def baixar_imagem_link(self, obj):
        if obj.imagem_ingresso:
            url = reverse('espetaculo:baixar_ingresso', args=[obj.pk])
            return format_html('<a href="{}" target="_blank">Baixar ingresso</a>', url)
        return '-'

    baixar_imagem_link.short_description = 'Imagem do ingresso'

    def baixar_qrcode_link(self, obj):
        if obj.qrcode_image:
            url = reverse('espetaculo:baixar_qrcode_ingresso', args=[obj.pk])
            return format_html('<a href="{}" target="_blank">Baixar QR code</a>', url)
        return '-'

    baixar_qrcode_link.short_description = 'QR code'

    def imagem_atual(self, obj):
        if obj.imagem_ingresso:
            url = reverse('espetaculo:ver_imagem_ingresso', args=[obj.pk])
            return format_html('<a href="{}" target="_blank">Ver imagem atual</a>', url)
        return 'Sem imagem'

    imagem_atual.short_description = 'Visualização do ingresso'

    def qrcode_atual(self, obj):
        if obj.qrcode_image:
            return format_html('Arquivo salvo: {}', obj.qrcode_image.name)
        return 'Sem QR code'

    qrcode_atual.short_description = 'Arquivo do QR'

    def has_add_permission(self, request):
        return False