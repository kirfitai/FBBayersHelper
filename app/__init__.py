from flask import Flask
from config import Config
from app.extensions import db, migrate, login_manager, csrf
import logging
import threading
import time

# Настройка логирования
logger = logging.getLogger(__name__)

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Инициализация расширений с приложением
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    
    # Глобальный словарь для хранения статусов проверки кампаний
    app.check_tasks = {}
    
    with app.app_context():
        # Добавляем глобальную функцию для шаблонов
        @app.template_global()
        def generate_csrf_token():
            from flask_wtf.csrf import generate_csrf
            return generate_csrf()
        
        # Регистрация схем (blueprints)
        from app.auth import bp as auth_bp
        app.register_blueprint(auth_bp, url_prefix='/auth')
        
        from app.routes import bp as main_bp
        app.register_blueprint(main_bp)
        
        # Настраиваем обработчики ошибок
        @app.errorhandler(400)
        def handle_bad_request(e):
            logger.error(f"[FLASK_ERROR] 400 Bad Request: {str(e)}")
            # Проверяем, связана ли ошибка с CSRF
            if 'CSRF' in str(e):
                logger.error(f"[FLASK_ERROR] CSRF token error: {str(e)}")
                from flask import request
                # Подробное логирование запроса
                logger.error(f"[FLASK_ERROR] Request headers: {dict(request.headers)}")
                logger.error(f"[FLASK_ERROR] Request form: {request.form}")
                logger.error(f"[FLASK_ERROR] Request args: {request.args}")
                logger.error(f"[FLASK_ERROR] Request path: {request.path}")
                logger.error(f"[FLASK_ERROR] Request method: {request.method}")
                
                from flask import session
                # Проверяем содержимое сессии (без конфиденциальных данных)
                safe_session = {k: v for k, v in session.items() if not any(sensitive in k.lower() for sensitive in ['token', 'password'])}
                logger.error(f"[FLASK_ERROR] Session data: {safe_session}")
            return 'Bad Request - The browser (or proxy) sent a request that this server could not understand.', 400
        
        @app.errorhandler(401)
        def handle_unauthorized(e):
            logger.error(f"[FLASK_ERROR] 401 Unauthorized: {str(e)}")
            return 'Unauthorized - The server could not verify that you are authorized to access the URL requested.', 401
        
        @app.errorhandler(403)
        def handle_forbidden(e):
            logger.error(f"[FLASK_ERROR] 403 Forbidden: {str(e)}")
            return 'Forbidden - You don\'t have the permission to access the requested resource.', 403
        
        @app.errorhandler(404)
        def handle_not_found(e):
            logger.error(f"[FLASK_ERROR] 404 Not Found: {str(e)}")
            return 'Not Found - The requested URL was not found on the server.', 404
        
        @app.errorhandler(500)
        def handle_server_error(e):
            logger.error(f"[FLASK_ERROR] 500 Internal Server Error: {str(e)}")
            import traceback
            logger.error(f"[FLASK_ERROR] Traceback: {traceback.format_exc()}")
            from flask import request
            logger.error(f"[FLASK_ERROR] Request URL: {request.url}")
            logger.error(f"[FLASK_ERROR] Request method: {request.method}")
            return 'Internal Server Error - The server encountered an internal error and was unable to complete your request.', 500

    # Инициализация фонового планировщика для проверки кампаний
    if not app.debug:
        scheduler_thread = threading.Thread(target=run_scheduler, args=(app,))
        scheduler_thread.daemon = True
        scheduler_thread.start()
        logger.info("Запущен планировщик автоматических проверок кампаний")
    
    return app

def run_scheduler(app):
    """Запускает планировщик для периодических задач"""
    with app.app_context():
        logger.info("Запуск планировщика периодических задач")
        
        while True:
            try:
                # Запускаем проверку кампаний
                from app.scheduler import schedule_campaign_checks
                schedule_campaign_checks()
                
                # Ждем 1 минуту перед следующей проверкой
                time.sleep(60)
            except Exception as e:
                logger.error(f"Ошибка в планировщике задач: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
                time.sleep(60)  # Ждем минуту перед следующей попыткой

# Не импортируйте ничего здесь, чтобы избежать циклических импортов