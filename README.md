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