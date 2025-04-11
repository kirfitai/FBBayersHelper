from datetime import datetime
import json
from app.extensions import db

class FacebookTokenAccount(db.Model):
    """Модель для отслеживания связи токена с аккаунтами"""
    __tablename__ = 'facebook_token_accounts'
    
    id = db.Column(db.Integer, primary_key=True)
    token_id = db.Column(db.Integer, db.ForeignKey('facebook_tokens.id', ondelete='CASCADE'))
    account_id = db.Column(db.String(50), nullable=False)
    account_name = db.Column(db.String(100))
    is_active = db.Column(db.Boolean, default=True)
    last_checked = db.Column(db.DateTime, default=datetime.utcnow)
    campaign_count = db.Column(db.Integer, default=0)
    
    def __repr__(self):
        return f'<TokenAccount {self.account_id}>'

class FacebookToken(db.Model):
    __tablename__ = 'facebook_tokens'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    name = db.Column(db.String(100), nullable=False)  # Имя/описание токена
    access_token = db.Column(db.String(255), nullable=False)
    app_id = db.Column(db.String(50))  # Теперь необязательное поле
    app_secret = db.Column(db.String(100))  # Теперь необязательное поле
    use_proxy = db.Column(db.Boolean, default=False)  # Флаг использования прокси
    proxy_url = db.Column(db.String(255))  # URL прокси в формате http://username:password@host:port
    is_active = db.Column(db.Boolean, default=True)
    status = db.Column(db.String(20), default='pending')  # pending, valid, invalid
    last_checked = db.Column(db.DateTime)
    error_message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Связь с аккаунтами
    accounts = db.relationship('FacebookTokenAccount', backref='token', 
                              lazy='dynamic', cascade='all, delete-orphan')
    
    def __init__(self, user_id, name, access_token, app_id=None, app_secret=None, use_proxy=False, proxy_url=None):
        self.user_id = user_id
        self.name = name
        self.access_token = access_token
        self.app_id = app_id
        self.app_secret = app_secret
        self.use_proxy = use_proxy
        self.proxy_url = proxy_url if use_proxy else None
        self.status = 'pending'
    
    def add_account(self, account_id, account_name=None):
        """Добавляет аккаунт к токену"""
        existing = FacebookTokenAccount.query.filter_by(
            token_id=self.id, account_id=account_id).first()
            
        if existing:
            existing.last_checked = datetime.utcnow()
            if account_name:
                existing.account_name = account_name
            return existing
            
        account = FacebookTokenAccount(
            token_id=self.id,
            account_id=account_id,
            account_name=account_name
        )
        db.session.add(account)
        return account
    
    def update_campaign_count(self, account_id, count):
        """Обновляет количество кампаний для указанного аккаунта"""
        account = FacebookTokenAccount.query.filter_by(
            token_id=self.id, account_id=account_id).first()
            
        if account:
            account.campaign_count = count
            account.last_checked = datetime.utcnow()
    
    def update_status(self, status, error_message=None):
        """Обновляет статус токена"""
        self.status = status
        self.error_message = error_message
        self.last_checked = datetime.utcnow()
    
    def get_account_ids(self):
        """Возвращает список ID аккаунтов, связанных с токеном"""
        return [account.account_id for account in self.accounts]
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'access_token': self.access_token,
            'app_id': self.app_id,
            'app_secret': self.app_secret,
            'use_proxy': self.use_proxy,
            'proxy_url': self.proxy_url,
            'is_active': self.is_active,
            'status': self.status,
            'accounts': [
                {
                    'id': account.account_id,
                    'name': account.account_name,
                    'campaign_count': account.campaign_count
                } for account in self.accounts
            ],
            'last_checked': self.last_checked.strftime('%Y-%m-%d %H:%M:%S') if self.last_checked else None,
            'error_message': self.error_message
        }
    
    def __repr__(self):
        return f'<FacebookToken {self.name} - {self.status}>'