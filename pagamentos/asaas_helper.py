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
    
    def criar_cobranca_pix(self, valor, descricao, customer_id=None, customer_data=None, external_reference=None):
        """
        Cria uma cobrança PIX no Asaas
        """
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
            "externalReference": external_reference or descricao,
            "postalService": False,
            "notificationDisabled": True,
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
        Cria um cliente no Asaas com notificações desabilitadas
        """
        url = f"{self.base_url}/customers"
        
        headers = {
            "access_token": self.api_key,
            "Content-Type": "application/json",
        }
        
        customer_payload = customer_data.copy()
        customer_payload['notificationDisabled'] = True
        
        print(f"[Asaas] Criando cliente: {customer_payload}")
        
        try:
            response = requests.post(url, headers=headers, json=customer_payload)
            response.raise_for_status()
            cliente = response.json()

            if cliente and 'id' in cliente:
                self.desativar_notificacoes_cliente(cliente['id'])

            return cliente
        except requests.exceptions.RequestException as e:
            print(f"[Asaas] Erro ao criar cliente: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"[Asaas] Resposta: {e.response.text}")
            return None
    
    def listar_notificacoes_cliente(self, customer_id):
        """
        Lista as notificações de um cliente no Asaas
        """
        url = f"{self.base_url}/customers/{customer_id}/notifications"
        
        headers = {
            "access_token": self.api_key,
        }
        
        try:
            response = requests.get(url, headers=headers)
            print(f"[Asaas] Listando notificações do cliente {customer_id}: {response.status_code}")
            print(f"[Asaas] Resposta notificações: {response.text}")
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"[Asaas] Erro ao listar notificações do cliente: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"[Asaas] Resposta: {e.response.text}")
            return None
    
    def desativar_notificacoes_cliente(self, customer_id):
        """
        Desativa todas as notificações do cliente no Asaas
        """
        notificacoes = self.listar_notificacoes_cliente(customer_id)
        if not notificacoes or 'data' not in notificacoes:
            print(f"[Asaas] Nenhuma notificação encontrada para o cliente {customer_id}")
            return False
        
        if not notificacoes['data']:
            print(f"[Asaas] Cliente {customer_id} não possui notificações para desativar")
            return True
        
        url = f"{self.base_url}/notifications/batch"
        
        headers = {
            "access_token": self.api_key,
            "Content-Type": "application/json",
        }
        
        notifications_payload = []
        for notificacao in notificacoes['data']:
            notifications_payload.append({
                "id": notificacao['id'],
                "enabled": False,
                "emailEnabledForProvider": False,
                "smsEnabledForProvider": False,
                "emailEnabledForCustomer": False,
                "smsEnabledForCustomer": False,
                "phoneCallEnabledForCustomer": False,
                "whatsappEnabledForCustomer": False,
            })
        
        payload = {
            "customer": customer_id,
            "notifications": notifications_payload
        }
        
        print(f"[Asaas] Desativando notificações do cliente {customer_id}")
        print(f"[Asaas] Payload batch: {json.dumps(payload, indent=2)}")
        
        try:
            response = requests.post(url, headers=headers, json=payload)
            print(f"[Asaas] Batch status: {response.status_code}")
            print(f"[Asaas] Batch resposta: {response.text}")
            response.raise_for_status()
            print(f"[Asaas] Notificações desativadas com sucesso para {customer_id}")
            return True
        except requests.exceptions.RequestException as e:
            print(f"[Asaas] Erro ao desativar notificações: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"[Asaas] Resposta: {e.response.text}")
            return False
    
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