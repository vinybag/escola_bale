from pathlib import Path
from decouple import config
import os
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY
SECRET_KEY = config('SECRET_KEY')
DEBUG = config('DEBUG', default=False, cast=bool)

# ALLOWED_HOSTS corrigido - adicionando o domínio personalizado
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1,web-production-4389a.up.railway.app,bailahcorpoecia.com,www.bailahcorpoecia.com').split(',')

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
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
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

# Asaas
ASAAS_API_KEY = config('ASAAS_API_KEY', default='')
ASAAS_SANDBOX = config('ASAAS_SANDBOX', default='True') == 'True'
ASAAS_BASE_URL = 'https://api.asaas.com/v3'

# Default primary key
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Security settings for production
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = False  # Railway já faz isso
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'

# Configuracao de Email (Gmail)
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = config('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='BAILAH <noreply@bailah.com>')

# CSRF e Security settings
CSRF_TRUSTED_ORIGINS = [
    'https://bailahcorpoecia.com',
    'https://www.bailahcorpoecia.com',
    'https://web-production-4389a.up.railway.app',
]

CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_DOMAIN = '.bailahcorpoecia.com'
SESSION_COOKIE_DOMAIN = '.bailahcorpoecia.com'