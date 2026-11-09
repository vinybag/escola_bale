"""
Interpreta o horário que hoje é escrito à mão na turma (ex.: "Segunda e Quarta
14h-15h") e transforma em dia(s) da semana + hora de início/fim.

É usado uma única vez, na migration que preenche os horários automaticamente.
Quando o texto é ambíguo, a função devolve lista vazia e a turma fica como
"horário pendente" para a escola cadastrar manualmente.
"""
import re
import unicodedata
from datetime import time

_DIAS = [
    (0, r'segunda(?:-?feira)?s?|seg'),
    (1, r'terca(?:-?feira)?s?|ter'),
    (2, r'quarta(?:-?feira)?s?|qua'),
    (3, r'quinta(?:-?feira)?s?|qui'),
    (4, r'sexta(?:-?feira)?s?|sex'),
    (5, r'sabados?|sab'),
    (6, r'domingos?|dom'),
]

# 14h | 14h30 | 14:00 | 14 h  (exige "h" ou ":" para não confundir com outros números)
_HORA = re.compile(r'(?<!\d)(\d{1,2})\s*(?:h|:)\s*(\d{2})?(?!\d)')


def _sem_acento(texto):
    texto = unicodedata.normalize('NFKD', texto or '')
    return ''.join(c for c in texto if not unicodedata.combining(c)).lower()


def dias_no_texto(texto):
    texto = _sem_acento(texto)
    achados = []
    for numero, padrao in _DIAS:
        if re.search(r'\b(?:' + padrao + r')\b', texto):
            achados.append(numero)
    return achados


def intervalo_no_texto(texto):
    """Devolve (inicio, fim) como datetime.time, ou None se não der para ter certeza."""
    horas = _HORA.findall(_sem_acento(texto))
    if len(horas) != 2:
        return None
    pontos = []
    for h, m in horas:
        h = int(h)
        m = int(m) if m else 0
        if not (0 <= h <= 23 and 0 <= m <= 59):
            return None
        pontos.append(time(h, m))
    inicio, fim = pontos
    if fim <= inicio:
        return None
    return inicio, fim


def numero_do_dia(nome_dia):
    """'Segunda' / 'Terça' / 'Sábado' -> 0..6 (ou None)."""
    achados = dias_no_texto(nome_dia)
    return achados[0] if len(achados) == 1 else None


def interpretar_horario(texto_horario, dia_semana_texto):
    """
    Devolve uma lista de (dia_semana_numero, hora_inicio, hora_fim).
    Lista vazia = não foi possível interpretar com segurança.
    """
    intervalo = intervalo_no_texto(texto_horario)
    if intervalo is None:
        return []

    dias = set(dias_no_texto(texto_horario))
    dia_campo = numero_do_dia(dia_semana_texto) if dia_semana_texto else None
    if dia_campo is not None:
        dias.add(dia_campo)
    if not dias:
        return []

    inicio, fim = intervalo
    return [(dia, inicio, fim) for dia in sorted(dias)]
