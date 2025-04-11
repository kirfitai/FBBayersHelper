FROM python:3.11-slim

WORKDIR /app

# Установка зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install gunicorn

# Копирование исходного кода приложения
COPY . .

# Создание пользователя без привилегий
RUN useradd -m appuser
USER appuser

# Открытие порта для работы приложения
EXPOSE 8080

# Запуск приложения через gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "run:app"] 