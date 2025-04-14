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
RUN chmod 777 /app
RUN chmod 777 /data

USER appuser

# Открытие порта для работы приложения
EXPOSE 8080

# Скрипт для инициализации базы данных и запуска приложения
RUN echo '#!/bin/bash\n\
echo "Starting database initialization..."\n\
touch /data/app.db\n\
ls -la /data\n\
python -c "from app import db, create_app; from app.models.user import User; print(\"Creating app context...\"); app = create_app(); app.app_context().push(); print(\"Creating database tables...\"); db.create_all(); print(\"Checking for existing users...\"); if User.query.count() == 0: print(\"No users found, creating admin...\"); admin = User(username=\"admin\", email=\"admin@example.com\"); admin.set_password(\"admin\"); db.session.add(admin); db.session.commit(); print(\"Admin user created successfully.\")"\n\
if [ $? -ne 0 ]; then\n\
  echo "Database initialization failed!"\n\
  exit 1\n\
fi\n\
echo "Database initialization completed successfully."\n\
echo "Starting gunicorn server..."\n\
exec gunicorn --bind 0.0.0.0:$PORT --workers 1 --log-level debug run:app' > /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Прямой запуск приложения
ENTRYPOINT ["/app/entrypoint.sh"] 