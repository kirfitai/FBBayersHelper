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
echo "Starting scheduler in background..."

# Проверяем переменную для запуска планировщика
if [ "$ENABLE_SCHEDULER" = "true" ]; then
  # Запускаем планировщик в фоновом режиме с перенаправлением вывода в лог
  python /app/scheduler.py > /data/scheduler.log 2>&1 &
  SCHEDULER_PID=$!
  echo "Scheduler started with PID: $SCHEDULER_PID"
else
  echo "Scheduler is disabled. Set ENABLE_SCHEDULER=true to enable it."
fi

echo "Starting gunicorn server with debug logging..."

# Запускаем приложение с подробным логированием
exec gunicorn --bind 0.0.0.0:$PORT --workers 1 --log-level debug run:app
