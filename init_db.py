from app import create_app, db
from app.models.user import User
from app.models.setup import Setup, ThresholdEntry, CampaignSetup
from app.models.token import FacebookToken

def init_db():
    """Инициализирует базу данных, создавая все таблицы."""
    print("Initializing database...")
    app = create_app()
    with app.app_context():
        db.create_all()
        print("Database tables created successfully.")
        
        # Проверяем, есть ли уже пользователи в базе
        if User.query.count() == 0:
            # Создаем администратора по умолчанию
            admin = User(username='admin', email='admin@example.com')
            admin.set_password('admin')
            db.session.add(admin)
            db.session.commit()
            print("Default admin user created.")
        else:
            print("Users already exist. Skipping default user creation.")

if __name__ == '__main__':
    init_db() 