# FB Bayers Helper

## GitHub Репозиторий

### Клонирование репозитория
```bash
git clone https://github.com/ваш-логин/FBBayersHelper.git
cd FBBayersHelper
```

### Настройка окружения
```bash
python -m venv venv311
source venv311/bin/activate  # Для Linux/Mac
# или
venv311\Scripts\activate     # Для Windows

pip install -r requirements.txt
```

### Настройка переменных окружения
```bash
cp .env.example .env
# Отредактируйте .env файл, установив необходимые значения
```

## Деплой на Fly.io

Для деплоя приложения на платформу Fly.io необходимо выполнить следующие шаги:

### Предварительные условия
1. Установить [flyctl](https://fly.io/docs/hands-on/install-flyctl/)
2. Авторизоваться в fly.io: `fly auth login`

### Развертывание приложения

1. Создайте объем для хранения данных (если используется SQLite):
```bash
fly volumes create fbbayers_data --size 1
```

2. Настройте секреты и переменные окружения:
```bash
fly secrets set SECRET_KEY=your-very-strong-secret-key
fly secrets set FACEBOOK_APP_ID=your-facebook-app-id
fly secrets set FACEBOOK_APP_SECRET=your-facebook-app-secret
```

3. Разверните приложение:
```bash
fly deploy
```

4. Откройте приложение в браузере:
```bash
fly open
```

### Первоначальная настройка базы данных

После деплоя необходимо инициализировать базу данных:

```bash
fly ssh console
cd /app
python -c "from app import create_app, db; app = create_app(); app.app_context().push(); db.create_all()"
exit
```

### Обновление приложения

Для обновления приложения достаточно выполнить:

```bash
fly deploy
```

### Мониторинг и логи

Для просмотра логов приложения используйте:

```bash
fly logs
```

Для подключения к консоли приложения:

```bash
fly ssh console
```

## Развертывание приложения (Деплой)

Для развертывания приложения используется платформа [fly.io](https://fly.io/). Процесс деплоя настроен с использованием Docker и включает следующие шаги:

### Подготовка к деплою

1. Убедитесь, что все изменения закоммичены и отправлены в репозиторий:
   ```bash
   git add .
   git commit -m "Описание изменений"
   git push origin main
   ```

2. Убедитесь, что у вас установлен [flyctl](https://fly.io/docs/hands-on/install-flyctl/):
   ```bash
   brew install flyctl
   # или для других ОС следуйте инструкциям по ссылке выше
   ```

3. Войдите в свой аккаунт fly.io:
   ```bash
   flyctl auth login
   ```

### Деплой приложения

Для развертывания приложения используйте команду:
```bash
flyctl deploy
```

Эта команда будет:
1. Собирать Docker-образ из Dockerfile
2. Загружать его на платформу fly.io
3. Запускать приложение на основе конфигурации из fly.toml

### Мониторинг и логи

Для просмотра логов запущенного приложения:
```bash
flyctl logs
```

Для мониторинга состояния приложения:
```bash
flyctl status
```

### Настройка переменных окружения

Для изменения переменных окружения:
```bash
flyctl secrets set КЛЮЧ=ЗНАЧЕНИЕ
```

### Важные особенности конфигурации

- База данных хранится в персистентном хранилище, монтируемом по пути `/data`
- Приложение запускается с помощью gunicorn на порту 8080
- Для правильной работы приложения должен быть настроен `SECRET_KEY`
- Для автоматического запуска планировщика используется конфигурация в Dockerfile и entrypoint.sh 