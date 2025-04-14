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
ENV DATABASE_URL=sqlite:///app.db

# Создание пользователя без привилегий
RUN useradd -m appuser

# Изменение прав на директорию приложения
RUN chown -R appuser:appuser /app
RUN chmod 755 /app

USER appuser

# Открытие порта для работы приложения
EXPOSE 8080

# Простой пример страницы для проверки работы
RUN echo 'from flask import Flask\napp = Flask(__name__)\n@app.route("/")\ndef hello():\n    return "<h1>FB Bayers Helper</h1><p>Приложение успешно запущено!</p>"\nif __name__ == "__main__":\n    app.run(host="0.0.0.0", port=8080)' > simple_app.py

# Прямой запуск приложения
CMD gunicorn --bind 0.0.0.0:$PORT simple_app:app 