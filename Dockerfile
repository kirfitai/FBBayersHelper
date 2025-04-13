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

# Создание директории для данных
RUN mkdir -p /data
RUN chmod 777 /data

# Делаем entrypoint исполняемым
RUN chmod +x /app/entrypoint.sh

# Создание пользователя без привилегий
RUN useradd -m appuser
USER appuser

# Открытие порта для работы приложения
EXPOSE 8080

# Запуск приложения через entrypoint.sh
ENTRYPOINT ["/app/entrypoint.sh"] 