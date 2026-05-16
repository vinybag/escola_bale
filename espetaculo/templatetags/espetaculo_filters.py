from django import template

register = template.Library()

@register.filter
def formatar_personagens(valor):
    """Converte a lista de personagens do banco para nomes legíveis"""
    if not valor:
        return "-"
    
    # Dicionário de conversão
    personagens_dict = {
        'thessalia': 'Thessália',
        'zyara': 'Zyara',
        'zyar': 'Zyar',
        'astela_nur': 'Astela Nur',
        'kai_ignus': 'Kai Ignus',
        'eldrick_felicius': 'Eldrick Felicius',
        'florine': 'Florine',
        'odessa': 'Odessa',
        'aurelia': 'Aurélia',
        'cora_del_amour': 'Cora del Amour',
        '3_marias': '3 Marias',
    }
    
    # Tenta converter a string para lista
    try:
        import ast
        lista = ast.literal_eval(valor)
        if isinstance(lista, list):
            nomes = [personagens_dict.get(item, item) for item in lista]
            return ", ".join(nomes)
    except:
        pass
    
    # Se não for lista, tenta limpeza básica
    valor_limpo = valor.replace("['", "").replace("']", "").replace("'", "").split(", ")
    nomes = [personagens_dict.get(v.strip(), v.strip()) for v in valor_limpo]
    return ", ".join(nomes)