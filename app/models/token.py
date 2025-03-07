from datetime import datetime
from app import db

class FacebookToken(db.Model):
    __tablename__ = 'facebook_tokens'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    name = db.Column(db.String(100), nullable=False)  # Имя/описание токена
    access_token = db.Column(db.String(255), nullable=False)
    app_id = db.Column(db.String(50), nullable=False)
    app_secret = db.Column(db.String(100), nullable=False)
    account_id = db.Column(db.String(50), nullable=False)
    proxy_url = db.Column(db.String(255))  # URL прокси в формате http://username:password@host:port
    is_active = db.Column(db.Boolean, default=True)
    status = db.Column(db.String(20), default='pending')  # pending, valid, invalid
    last_checked = db.Column(db.DateTime)
    error_message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __init__(self, user_id, name, access_token, app_id, app_secret, account_id, proxy_url=None):
        self.user_id = user_id
        self.name = name
        self.access_token = access_token
        self.app_id = app_id
        self.app_secret = app_secret
        self.account_id = account_id
        self.proxy_url = proxy_url
        self.status = 'pending'
    
    def update_status(self, status, error_message=None):
        self.status = status
        self.error_message = error_message
        self.last_checked = datetime.utcnow()
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'access_token': self.access_token,
            'app_id': self.app_id,
            'app_secret': self.app_secret,
            'account_id': self.account_id,
            'proxy_url': self.proxy_url,
            'is_active': self.is_active,
            'status': self.status,
            'last_checked': self.last_checked.strftime('%Y-%m-%d %H:%M:%S') if self.last_checked else None,
            'error_message': self.error_message
        }
    
    def __repr__(self):
        return f'<FacebookToken {self.name} - {self.status}>'