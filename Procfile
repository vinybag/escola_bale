release: python manage.py migrate && python init_db.py
web: gunicorn config.wsgi --bind 0.0.0.0:$PORT