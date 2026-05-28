import re
from decimal import Decimal, ROUND_HALF_UP

import requests
from django.conf import settings


class AsaasError(Exception):
    pass


def _base_url():
    return settings.ASAAS_BASE_URL.rstrip('/')


def _api_key():
    api_key = getattr(settings, 'ASAAS_API_KEY', '')
    if not api_key:
        raise AsaasError('ASAAS_API_KEY não configurada.')
    return api_key.strip()


def _headers():
    return {
        'Content-Type': 'application/json',
        'User-Agent': 'bailah-corpo-e-cia',
        'access_token': _api_key(),
    }


def _only_digits(value):
    if not value:
        return ''
    return re.sub(r'\D', '', str(value))


def _parse_response(response):
    try:
        data = response.json()
    except Exception:
        data = {'raw': response.text}

    if not response.ok:
        if isinstance(data, dict) and data.get('errors'):
            first_error = data['errors'][0]
            message = first_error.get('description') or 'Erro no Asaas.'
        else:
            message = f'Erro no Asaas (HTTP {response.status_code}).'
        raise AsaasError(message)

    return data


def _request(method, endpoint, *, params=None, payload=None):
    url = f'{_base_url()}/{endpoint.lstrip("/")}'
    response = requests.request(
        method=method,
        url=url,
        headers=_headers(),
        params=params,
        json=payload,
        timeout=30,
    )
    return _parse_response(response)


def get_responsavel_data(responsavel):
    perfil = getattr(responsavel, 'perfil', None)

    nome = responsavel.get_full_name() or responsavel.username or responsavel.email or f'Responsável {responsavel.pk}'
    email = responsavel.email or ''
    telefone = getattr(perfil, 'telefone', '') if perfil else ''
    cpf_cnpj = ''

    if perfil:
        cpf_cnpj = getattr(perfil, 'cpf', '') or getattr(perfil, 'cpf_cnpj', '') or ''

    return {
        'nome': nome[:100],
        'email': email,
        'telefone': _only_digits(telefone)[:11],
        'cpf_cnpj': _only_digits(cpf_cnpj)[:14],
        'external_reference': f'responsavel:{responsavel.pk}',
    }


def find_customer_by_external_reference(external_reference):
    data = _request('GET', 'customers', params={'externalReference': external_reference})
    customers = data.get('data', [])
    return customers[0] if customers else None


def find_customer_by_cpf_cnpj(cpf_cnpj):
    if not cpf_cnpj:
        return None
    data = _request('GET', 'customers', params={'cpfCnpj': cpf_cnpj})
    customers = data.get('data', [])
    return customers[0] if customers else None


def find_customer_by_email(email):
    if not email:
        return None
    data = _request('GET', 'customers', params={'email': email})
    customers = data.get('data', [])
    return customers[0] if customers else None


def create_customer(responsavel):
    customer_data = get_responsavel_data(responsavel)

    payload = {
        'name': customer_data['nome'],
        'email': customer_data['email'],
        'mobilePhone': customer_data['telefone'],
        'externalReference': customer_data['external_reference'],
    }

    if customer_data['cpf_cnpj']:
        payload['cpfCnpj'] = customer_data['cpf_cnpj']

    payload = {k: v for k, v in payload.items() if v}
    return _request('POST', 'customers', payload=payload)


def get_or_create_customer(responsavel):
    customer_data = get_responsavel_data(responsavel)

    customer = find_customer_by_external_reference(customer_data['external_reference'])
    if customer:
        return customer

    customer = find_customer_by_cpf_cnpj(customer_data['cpf_cnpj'])
    if customer:
        return customer

    customer = find_customer_by_email(customer_data['email'])
    if customer:
        return customer

    return create_customer(responsavel)


def create_payment(
    *,
    customer_id,
    value,
    due_date,
    description,
    external_reference,
    billing_type='PIX',
):
    payload = {
        'customer': customer_id,
        'billingType': billing_type,
        'value': float(Decimal(value).quantize(Decimal('0.01'))),
        'dueDate': str(due_date),
        'description': description[:500],
        'externalReference': str(external_reference)[:255],
    }

    return _request('POST', 'payments', payload=payload)


def calculate_installment_value(total_value, installment_count):
    total_value = Decimal(total_value)
    installment_count = int(installment_count)

    if installment_count <= 0:
        raise AsaasError('Quantidade de parcelas inválida.')

    return (total_value / installment_count).quantize(
        Decimal('0.01'),
        rounding=ROUND_HALF_UP,
    )


def create_installment_payment(
    *,
    customer_id,
    total_value,
    installment_count,
    due_date,
    description,
    external_reference,
    billing_type='PIX',
):
    installment_value = calculate_installment_value(total_value, installment_count)

    payload = {
        'customer': customer_id,
        'billingType': billing_type,
        'installmentCount': int(installment_count),
        'installmentValue': float(installment_value),
        'dueDate': str(due_date),
        'description': description[:500],
        'externalReference': str(external_reference)[:255],
    }

    return _request('POST', 'payments', payload=payload)


def list_installment_payments(installment_id):
    return _request('GET', f'installments/{installment_id}/payments')