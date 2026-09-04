from pathlib import Path
from decouple import config
import os
import dj_database_url



BASE_DIR = Path(__file__).resolve().parent.parent



# SECURITY
SECRET_KEY = config('SECRET_KEY')
DEBUG = config('DEBUG', default=False, cast=bool)



# ALLOWED_HOSTS
ALLOWED_HOSTS = config(
    'ALLOWED_HOSTS',
    default='localhost,127.0.0.1,web-production-4389a.up.railway.app,bailahcorpoecia.com,www.bailahcorpoecia.com'
).split(',')



# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',


    # Apps do projeto
    'core',
    'usuarios',
    'agenda',
    'pagamentos',
    'calendario_avisos',
    'admin_dashboard',
    'espetaculo',


    # Email
    'anymail',
]



MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'csp.middleware.CSPMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django_permissions_policy.PermissionsPolicyMiddleware',
]



ROOT_URLCONF = 'config.urls'



TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]



WSGI_APPLICATION = 'config.wsgi.application'



# Database
DATABASE_URL = config('DATABASE_URL', default=None)


if DATABASE_URL:
    # Produção (Railway com PostgreSQL)
    DATABASES = {
        'default': dj_database_url.parse(DATABASE_URL, conn_max_age=600)
    }
else:
    # Desenvolvimento (SQLite local)
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }



# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]



# Internationalization
LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'America/Sao_Paulo'
USE_I18N = True
USE_TZ = True



# Static files
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'



# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')



# Login/Logout
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'redirecionar_dashboard'
LOGOUT_REDIRECT_URL = 'home'



# Google Calendar
GOOGLE_CALENDAR_CREDENTIALS = BASE_DIR / 'config' / 'credentials' / 'google_calendar.json'
GOOGLE_CALENDAR_ID = config('GOOGLE_CALENDAR_ID', default='')



# Stripe
STRIPE_PUBLIC_KEY = config('STRIPE_PUBLIC_KEY', default='')
STRIPE_SECRET_KEY = config('STRIPE_SECRET_KEY', default='')
STRIPE_WEBHOOK_SECRET = config('STRIPE_WEBHOOK_SECRET', default='')



# Asaas
ASAAS_API_KEY = config('ASAAS_API_KEY', default='')
ASAAS_SANDBOX = config('ASAAS_SANDBOX', default='True') == 'True'
ASAAS_BASE_URL = 'https://api.asaas.com/v3'
ASAAS_WEBHOOK_TOKEN = config('ASAAS_WEBHOOK_TOKEN', default='')



# Default primary key
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'



# Security settings for production
# IMPORTANTE: todas as configuracoes de cookie seguro/dominio ficam
# aqui dentro, pois so fazem sentido em producao (HTTPS + dominio
# proprio). Se ficarem fora deste bloco, o cookie de sessao e o
# cookie de CSRF sao rejeitados pelo navegador em ambiente local
# (HTTP em 127.0.0.1), o que impede o login de funcionar mesmo com
# usuario e senha corretos.
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = False  # Railway já faz isso
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
    CSRF_COOKIE_DOMAIN = '.bailahcorpoecia.com'
    SESSION_COOKIE_DOMAIN = '.bailahcorpoecia.com'

        # HSTS - forca o navegador a SEMPRE usar HTTPS neste dominio
    SECURE_HSTS_SECONDS = 31536000  # 1 ano - ja confirmamos que HTTPS funciona bem
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True



# Permissions-Policy - bloqueia recursos que o site nao usa,
# mas libera camera para o proprio site (usado no leitor de QR Code)
PERMISSIONS_POLICY = {
    "accelerometer": [],
    "camera": ["self"],  # Libera camera apenas para o proprio dominio
    "geolocation": [],
    "gyroscope": [],
    "magnetometer": [],
    "microphone": [],
    "payment": [],
    "usb": [],
}



# Content-Security-Policy - MODO DE TESTE (report-only)
# Nada e bloqueado ainda, so registra no console do navegador o que
# SERIA bloqueado se a policy estivesse ativa de verdade. Depois de
# confirmar que nao aparece nenhum erro navegando pelo site inteiro
# (incluindo o leitor de QR Code), trocamos esta chave para
# CONTENT_SECURITY_POLICY (sem o _REPORT_ONLY) para valer de verdade.
CONTENT_SECURITY_POLICY = {
    'DIRECTIVES': {
        'default-src': ["'self'"],
        'script-src': ["'self'", "'unsafe-inline'"],
        'style-src': ["'self'", "'unsafe-inline'"],
        'img-src': ["'self'", 'data:'],
        'font-src': ["'self'"],
        'connect-src': ["'self'"],
        'frame-src': ["'none'"],
        'object-src': ["'none'"],
        'base-uri': ["'self'"],
        'form-action': ["'self'"],
    },
}



# =========================
# EMAIL - BREVO (API)
# =========================
EMAIL_BACKEND = "anymail.backends.brevo.EmailBackend"


ANYMAIL = {
    "BREVO_API_KEY": config("BREVO_API_KEY", default=""),
}


DEFAULT_FROM_EMAIL = config(
    'DEFAULT_FROM_EMAIL',
    default='BAILAH <naoresponda@bailahcorpoecia.com>'
)


SERVER_EMAIL = DEFAULT_FROM_EMAIL
EMAIL_SUBJECT_PREFIX = '[BAILAH] '



# CSRF e Security settings
CSRF_TRUSTED_ORIGINS = [
    'https://bailahcorpoecia.com',
    'https://www.bailahcorpoecia.com',
    'https://web-production-4389a.up.railway.app',
]


# WhatsApp Business API (Meta)
WHATSAPP_PHONE_NUMBER_ID = os.environ.get('WHATSAPP_PHONE_NUMBER_ID')
WHATSAPP_ACCESS_TOKEN = os.environ.get('WHATSAPP_ACCESS_TOKEN')
WHATSAPP_NUMERO_ESCOLA = os.environ.get('WHATSAPP_NUMERO_ESCOLA')