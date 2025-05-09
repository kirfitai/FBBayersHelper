from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from app.extensions import db, login_manager

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, index=True)
    email = db.Column(db.String(120), unique=True, index=True)
    password_hash = db.Column(db.String(128))
    fb_access_token = db.Column(db.String(255))
    fb_app_id = db.Column(db.String(50))
    fb_app_secret = db.Column(db.String(100))
    fb_account_id = db.Column(db.String(50))
    active_token_id = db.Column(db.Integer)  # ID активного токена
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Новые поля
    is_admin = db.Column(db.Boolean, default=False)  # Роль администратора
    totp_secret = db.Column(db.String(32))  # Секретный ключ для TOTP (Google Authenticator)
    is_2fa_enabled = db.Column(db.Boolean, default=False)  # Включена ли 2FA
    
    # Отношения
    setups = db.relationship('Setup', backref='owner', lazy='dynamic')
    campaign_setups = db.relationship('CampaignSetup', backref='owner', lazy='dynamic')
    facebook_tokens = db.relationship('FacebookToken', backref='owner', lazy='dynamic')

    def __init__(self, username, email, password, is_admin=False):
        self.username = username
        self.email = email
        self.set_password(password)
        self.is_admin = is_admin

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
        
    def update_fb_credentials(self, access_token, app_id, app_secret, account_id):
        self.fb_access_token = access_token
        self.fb_app_id = app_id
        self.fb_app_secret = app_secret
        self.fb_account_id = account_id
        
    def set_totp_secret(self, secret):
        """Установить секретный ключ для TOTP"""
        self.totp_secret = secret
        
    def enable_2fa(self, enable=True):
        """Включить или выключить 2FA"""
        self.is_2fa_enabled = enable

    def __repr__(self):
        return f'<User {self.username}>'