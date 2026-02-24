import os
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from django.conf import settings
from datetime import datetime, timedelta
import pytz

SCOPES = ['https://www.googleapis.com/auth/calendar']


def get_calendar_service():
    """Retorna o serviço do Google Calendar autenticado"""
    
    # Tenta ler credenciais da variável de ambiente primeiro (produção)
    creds_json = os.environ.get('GOOGLE_CREDENTIALS')
    
    if creds_json:
        # Produção (Railway) - lê da variável de ambiente
        try:
            creds_dict = json.loads(creds_json)
            credentials = service_account.Credentials.from_service_account_info(
                creds_dict,
                scopes=SCOPES
            )
        except Exception as e:
            print(f"Erro ao carregar credenciais do ambiente: {e}")
            return None
    else:
        # Desenvolvimento (local) - lê do arquivo
        creds_path = settings.GOOGLE_CALENDAR_CREDENTIALS
        
        if not os.path.exists(creds_path):
            print(f"Arquivo de credenciais não encontrado: {creds_path}")
            return None
        
        credentials = service_account.Credentials.from_service_account_file(
            creds_path,
            scopes=SCOPES
        )
    
    try:
        service = build('calendar', 'v3', credentials=credentials)
        return service
    except Exception as e:
        print(f"Erro ao criar serviço do Calendar: {e}")
        return None


def criar_evento_google(agendamento):
    """Cria evento no Google Calendar"""
    
    service = get_calendar_service()
    
    if not service:
        print("Erro: Não foi possível autenticar no Google Calendar")
        return False
    
    fuso = pytz.timezone('America/Sao_Paulo')
    
    inicio = fuso.localize(
        datetime.combine(agendamento.data, agendamento.horario)
    )
    
    fim = inicio + timedelta(hours=1)
    
    evento = {
        'summary': f"Aula experimental – {agendamento.nome_aluna}",
        'description': (
            f"Responsável: {agendamento.nome_responsavel}\n"
            f"Aula: {agendamento.aula.nome}\n"
            f"Telefone: {agendamento.telefone}\n"
            f"E-mail: {agendamento.email}"
        ),
        'start': {
            'dateTime': inicio.isoformat(),
            'timeZone': 'America/Sao_Paulo',
        },
        'end': {
            'dateTime': fim.isoformat(),
            'timeZone': 'America/Sao_Paulo',
        },
    }
    
    try:
        service.events().insert(
            calendarId=settings.GOOGLE_CALENDAR_ID,
            body=evento
        ).execute()
        return True
    except Exception as e:
        print(f"Erro ao criar evento: {e}")
        return False

