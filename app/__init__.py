from flask import Flask
from config import Config
from app.extensions import db, migrate, login_manager, csrf
import logging

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Настройка логирования
    if not app.debug:
        logging.basicConfig(level=logging.INFO)
        app.logger.setLevel(logging.INFO)
    
    # Инициализация расширений с приложением
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    
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
        
        # Инициализация админ-панели
        try:
            from app.admin import init_admin
            init_admin(app)
            app.logger.info("Админ-панель успешно инициализирована")
        except Exception as e:
            app.logger.error(f"Ошибка при инициализации админ-панели: {str(e)}")
    
    return app

# Не импортируйте ничего здесь, чтобы избежать циклических импортов