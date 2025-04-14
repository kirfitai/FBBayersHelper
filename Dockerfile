FROM python:3.11-slim

WORKDIR /app

# Установка системных зависимостей
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Установка зависимостей Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install gunicorn

# Копирование исходного кода приложения
COPY . .

# Установка переменных окружения
ENV PORT=8080
ENV FLASK_APP=run.py
ENV LOG_TO_STDOUT=1
ENV SECRET_KEY=default-dev-key-change-in-production
ENV LC_ALL=C.UTF-8
ENV LANG=C.UTF-8
ENV DATABASE_URL=sqlite:////data/app.db

# Создание директории для данных
RUN mkdir -p /data

# Создание пользователя без привилегий
RUN useradd -m appuser

# Изменение прав на директории
RUN chown -R appuser:appuser /app
RUN chown -R appuser:appuser /data
RUN chmod 755 /app
RUN chmod 755 /data

USER appuser

# Открытие порта для работы приложения
EXPOSE 8080

# Скрипт для инициализации базы данных и запуска приложения
RUN echo '#!/bin/bash\npython -c "from app import db, create_app; app = create_app(); app.app_context().push(); db.create_all()"\nexec gunicorn --bind 0.0.0.0:$PORT run:app' > /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Прямой запуск приложения
ENTRYPOINT ["/app/entrypoint.sh"] 