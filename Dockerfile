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

# Создание пользователя без привилегий
RUN useradd -m appuser
USER appuser

# Открытие порта для работы приложения
EXPOSE 8080

# Запуск приложения через gunicorn
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 run:app 