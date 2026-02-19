import requests
from django.conf import settings
from decimal import Decimal
import json

class AsaasAPI:
    
    def __init__(self):
        self.api_key = settings.ASAAS_API_KEY
        self.sandbox = settings.ASAAS_SANDBOX
        
        if self.sandbox:
            self.base_url = "https://sandbox.asaas.com/api/v3"
        else:
            self.base_url = "https://www.asaas.com/api/v3"
        
        print(f"[Asaas] Modo: {'SANDBOX' if self.sandbox else 'PRODUCAO'}")
        print(f"[Asaas] Base URL: {self.base_url}")
        print(f"[Asaas] API Key: {self.api_key[:20]}..." if self.api_key else "[Asaas] API Key não configurada!")
    
    def criar_cobranca_pix(self, valor, descricao, customer_id=None, customer_data=None):
        """
        Cria uma cobrança PIX no Asaas
        """
        # Se não tem customer_id, cria o cliente primeiro
        if not customer_id and customer_data:
            customer = self.criar_cliente(customer_data)
            if customer and 'id' in customer:
                customer_id = customer['id']
            else:
                return {'error': 'Não foi possível criar o cliente'}
        
        url = f"{self.base_url}/payments"
        
        headers = {
            "access_token": self.api_key,
            "Content-Type": "application/json",
        }
        
        payload = {
            "customer": customer_id,
            "billingType": "PIX",
            "value": float(valor),
            "dueDate": self._get_due_date(),
            "description": descricao,
            "externalReference": descricao,  # Para identificar depois
        }
        
        print(f"[Asaas] URL: {url}")
        print(f"[Asaas] Payload: {json.dumps(payload, indent=2)}")
        
        try:
            response = requests.post(url, headers=headers, json=payload)
            
            print(f"[Asaas] Status Code: {response.status_code}")
            print(f"[Asaas] Resposta: {response.text}")
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            print(f"[Asaas] ERRO: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"[Asaas] Status: {e.response.status_code}")
                print(f"[Asaas] Corpo: {e.response.text}")
                
                try:
                    erro_detalhado = e.response.json()
                    return {'error': erro_detalhado}
                except:
                    return {'error': e.response.text}
            return {'error': str(e)}
    
    def criar_cliente(self, customer_data):
        """
        Cria um cliente no Asaas
        customer_data = {
            'name': 'Nome completo',
            'email': 'email@example.com',
            'cpfCnpj': '12345678900'
        }
        """
        url = f"{self.base_url}/customers"
        
        headers = {
            "access_token": self.api_key,
            "Content-Type": "application/json",
        }
        
        print(f"[Asaas] Criando cliente: {customer_data}")
        
        try:
            response = requests.post(url, headers=headers, json=customer_data)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"[Asaas] Erro ao criar cliente: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"[Asaas] Resposta: {e.response.text}")
            return None
    
    def consultar_cobranca(self, payment_id):
        """
        Consulta o status de uma cobrança
        """
        url = f"{self.base_url}/payments/{payment_id}"
        
        headers = {
            "access_token": self.api_key,
        }
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"[Asaas] Erro ao consultar cobrança: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"[Asaas] Resposta: {e.response.text}")
            return None
    
    def obter_qrcode_pix(self, payment_id):
        """
        Obtém o QR Code PIX de uma cobrança
        """
        url = f"{self.base_url}/payments/{payment_id}/pixQrCode"
        
        headers = {
            "access_token": self.api_key,
        }
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"[Asaas] Erro ao obter QR Code: {e}")
            return None
    
    def _get_due_date(self):
        """
        Retorna data de vencimento (hoje)
        """
        from datetime import date
        return date.today().strftime("%Y-%m-%d")