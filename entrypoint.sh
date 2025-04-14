#!/bin/sh

set -e

# Создаем базу данных, если она еще не существует
python /app/init_db.py

# Запускаем приложение через gunicorn
exec gunicorn --bind 0.0.0.0:$PORT --workers 1 --log-level info run:app
