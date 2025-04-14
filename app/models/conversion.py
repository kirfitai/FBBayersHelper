from datetime import datetime
from app.extensions import db

class Conversion(db.Model):
    """Модель для хранения данных о конверсиях"""
    __tablename__ = 'conversions'
    
    id = db.Column(db.Integer, primary_key=True)
    ref = db.Column(db.String(255), index=True)  # Полный ref параметр
    ref_prefix = db.Column(db.String(3), index=True)  # Первые 3 символа ref параметра
    form_id = db.Column(db.String(50), index=True)  # значение ad id из FB
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    date = db.Column(db.Date, index=True)  # Дата конверсии для группировки по дням
    
    # Дополнительные данные о конверсии, можно добавить по необходимости
    ip_address = db.Column(db.String(50))
    user_agent = db.Column(db.Text)
    
    def __init__(self, ref, form_id, timestamp=None, ip_address=None, user_agent=None):
        self.ref = ref
        self.ref_prefix = ref[:3] if ref and len(ref) >= 3 else None
        self.form_id = form_id
        
        if timestamp:
            self.timestamp = timestamp
            self.date = timestamp.date()
        else:
            self.timestamp = datetime.utcnow()
            self.date = self.timestamp.date()
            
        self.ip_address = ip_address
        self.user_agent = user_agent
    
    def to_dict(self):
        return {
            'id': self.id,
            'ref': self.ref,
            'ref_prefix': self.ref_prefix,
            'form_id': self.form_id,
            'timestamp': self.timestamp.isoformat(),
            'date': self.date.isoformat() if self.date else None,
            'ip_address': self.ip_address,
            'user_agent': self.user_agent
        }
    
    @staticmethod
    def get_conversions_by_ref_prefix(ref_prefix, start_date=None, end_date=None):
        """Получение конверсий по префиксу ref"""
        query = Conversion.query.filter_by(ref_prefix=ref_prefix)
        
        if start_date:
            query = query.filter(Conversion.date >= start_date)
        if end_date:
            query = query.filter(Conversion.date <= end_date)
            
        return query.order_by(Conversion.timestamp).all()
    
    @staticmethod
    def get_daily_stats_by_ref_prefix(ref_prefix, start_date=None, end_date=None):
        """Получение статистики по дням для конкретного префикса ref"""
        from sqlalchemy import func
        
        query = db.session.query(
            Conversion.date,
            Conversion.form_id,
            func.count(Conversion.id).label('count')
        ).filter_by(ref_prefix=ref_prefix)
        
        if start_date:
            query = query.filter(Conversion.date >= start_date)
        if end_date:
            query = query.filter(Conversion.date <= end_date)
            
        return query.group_by(Conversion.date, Conversion.form_id).all()
    
    def __repr__(self):
        return f'<Conversion {self.id} ref={self.ref_prefix}>' 