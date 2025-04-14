#!/bin/bash

set -e

echo "Starting database initialization..."
touch /data/app.db
ls -la /data

# Запускаем скрипт для инициализации базы данных
python /app/init_db.py

if [ $? -ne 0 ]; then
  echo "Database initialization failed!"
  exit 1
fi

echo "Database initialization completed successfully."
echo "Starting gunicorn server with debug logging..."

# Запускаем приложение с подробным логированием
exec gunicorn --bind 0.0.0.0:$PORT --workers 1 --log-level debug run:app
