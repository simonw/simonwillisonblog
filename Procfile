release: python manage.py migrate --noinput
web: bin/start-nginx gunicorn -c gunicorn.conf config.wsgi --enable-stdio-inheritance --log-file -