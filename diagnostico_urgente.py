from espetaculo.models import (
    Espetaculo, ParticipacaoEspetaculo, IngressoGratuitoAluna,
    Assento, IngressoEvento, PedidoIngressoEvento,
)
from usuarios.models import Aluna

print("\n========== PARTE 1: GRATUIDADE ==========")

eventos = Espetaculo.objects.filter(venda_aberta=True).order_by('data_apresentacao')
print(f"Eventos com venda aberta: {eventos.count()}")
for ev in eventos:
    print(f"  - Evento #{ev.id}: {ev.titulo} | {ev.data_apresentacao}")

for evento in eventos:
    print(f"\n--- Evento #{evento.id} ({evento.titulo} - {evento.data_apresentacao}) ---")

    participacoes = ParticipacaoEspetaculo.objects.filter(espetaculo=evento).select_related('aluna')
    print(f"Total de participações cadastradas: {participacoes.count()}")

    nao_vai_dancar = participacoes.filter(vai_dancar=False)
    print(f"Participações com vai_dancar=False (NÃO contam para gratuidade): {nao_vai_dancar.count()}")
    for p in nao_vai_dancar:
        print(f"    - {p.aluna.nome} (aluna #{p.aluna.id})")

    alunas_inativas = participacoes.filter(aluna__ativa=False)
    print(f"Participações de alunas INATIVAS (não contam para gratuidade): {alunas_inativas.count()}")
    for p in alunas_inativas:
        print(f"    - {p.aluna.nome} (aluna #{p.aluna.id})")

    sem_responsavel_nem_login = participacoes.filter(
        aluna__responsavel__isnull=True,
        aluna__usuario__isnull=True,
    )
    print(f"Alunas SEM responsável E SEM login próprio vinculado (gratuidade impossível de usar): {sem_responsavel_nem_login.count()}")
    for p in sem_responsavel_nem_login:
        print(f"    - {p.aluna.nome} (aluna #{p.aluna.id})")

    ja_usaram = IngressoGratuitoAluna.objects.filter(evento=evento).count()
    print(f"Gratuidades já emitidas para este evento (site + manual): {ja_usaram}")

if eventos.count() == 2:
    ev1, ev2 = eventos[0], eventos[1]
    alunas_ev1 = set(
        ParticipacaoEspetaculo.objects.filter(espetaculo=ev1, vai_dancar=True)
        .values_list('aluna_id', flat=True)
    )
    alunas_ev2 = set(
        ParticipacaoEspetaculo.objects.filter(espetaculo=ev2, vai_dancar=True)
        .values_list('aluna_id', flat=True)
    )

    so_no_ev1 = alunas_ev1 - alunas_ev2
    so_no_ev2 = alunas_ev2 - alunas_ev1

    print(f"\n--- CRUZAMENTO ENTRE OS DOIS DIAS (evento #{ev1.id} vs #{ev2.id}) ---")
    print(f"Alunas com participação SÓ no evento #{ev1.id} ({ev1.titulo}), faltando no #{ev2.id} ({ev2.titulo}): {len(so_no_ev1)}")
    for aluna_id in so_no_ev1:
        a = Aluna.objects.get(pk=aluna_id)
        print(f"    - {a.nome} (aluna #{a.id}) -> SEM gratuidade no dia '{ev2.titulo}'")

    print(f"Alunas com participação SÓ no evento #{ev2.id} ({ev2.titulo}), faltando no #{ev1.id} ({ev1.titulo}): {len(so_no_ev2)}")
    for aluna_id in so_no_ev2:
        a = Aluna.objects.get(pk=aluna_id)
        print(f"    - {a.nome} (aluna #{a.id}) -> SEM gratuidade no dia '{ev1.titulo}'")

print("\n========== PARTE 2: ASSENTOS VENDIDOS PELO ADMIN ==========")

pedidos_manuais = PedidoIngressoEvento.objects.filter(
    external_reference__startswith='ingresso_manual_',
).order_by('-criado_em')

print(f"Total de pedidos gerados manualmente pelo admin: {pedidos_manuais.count()}")

for pedido in pedidos_manuais[:30]:
    print(f"\nPedido #{pedido.id} | {pedido.nome_completo} | evento: {pedido.evento} | status: {pedido.status}")
    print(f"  assentos_ids salvos no pedido: {pedido.assentos_ids}")

    if pedido.assentos_ids:
        assentos_reais = Assento.objects.filter(id__in=pedido.assentos_ids)
        for a in assentos_reais:
            print(f"    -> Assento {a.identificador} | status atual no banco: {a.status}")

    ingressos = pedido.ingressos.all()
    print(f"  ingressos gerados para este pedido: {ingressos.count()}")
    for i in ingressos:
        print(f"    -> Ingresso #{i.id} | assento vinculado: {i.assento} | status ingresso: {i.status}")

print("\n========== FIM DO DIAGNÓSTICO ==========")
