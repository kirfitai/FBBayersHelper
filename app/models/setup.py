from datetime import datetime
import json
from app.extensions import db

class ThresholdEntry(db.Model):
    __tablename__ = 'threshold_entries'
    
    id = db.Column(db.Integer, primary_key=True)
    setup_id = db.Column(db.Integer, db.ForeignKey('setups.id', ondelete='CASCADE'))
    spend = db.Column(db.Float, nullable=False)
    conversions = db.Column(db.Integer, nullable=False, default=0)
    
    def __repr__(self):
        return f'<Threshold ${self.spend} - {self.conversions}>'

class Setup(db.Model):
    __tablename__ = 'setups'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    check_interval = db.Column(db.Integer, default=30)  # в минутах
    check_period = db.Column(db.String(20), nullable=True, default='today')  # период проверки (today, last2days, last3days, last7days, alltime)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Отношения
    thresholds = db.relationship('ThresholdEntry', backref='setup', lazy='dynamic', 
                                cascade='all, delete-orphan')
    campaigns = db.relationship('CampaignSetup', backref='setup', lazy='dynamic',
                               cascade='all, delete-orphan')

    def __init__(self, name, user_id, check_interval=30, check_period='today'):
        self.name = name
        self.user_id = user_id
        self.check_interval = check_interval
        self.check_period = check_period
    
    def add_threshold(self, spend, conversions):
        threshold = ThresholdEntry(setup_id=self.id, spend=spend, conversions=conversions)
        db.session.add(threshold)
        return threshold
    
    def get_thresholds_as_list(self):
        return [
            {"spend": t.spend, "conversions": t.conversions} 
            for t in self.thresholds.order_by(ThresholdEntry.spend).all()
        ]
    
    def to_json(self):
        return {
            'id': self.id,
            'name': self.name,
            'check_interval': self.check_interval,
            'check_period': self.check_period or 'today',  # Если None, вернуть 'today'
            'is_active': self.is_active,
            'thresholds': self.get_thresholds_as_list()
        }
    
    def __repr__(self):
        return f'<Setup {self.name}>'


class CampaignSetup(db.Model):
    __tablename__ = 'campaign_setups'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    setup_id = db.Column(db.Integer, db.ForeignKey('setups.id', ondelete='CASCADE'))
    campaign_id = db.Column(db.String(50), nullable=False)
    campaign_name = db.Column(db.String(100))
    is_active = db.Column(db.Boolean, default=True)
    last_checked = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __init__(self, user_id, setup_id, campaign_id, campaign_name=None):
        self.user_id = user_id
        self.setup_id = setup_id
        self.campaign_id = campaign_id
        self.campaign_name = campaign_name
    
    def __repr__(self):
        return f'<CampaignSetup {self.campaign_id}>'