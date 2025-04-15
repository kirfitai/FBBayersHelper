from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, FloatField, BooleanField, SubmitField
from wtforms import FieldList, FormField, SelectField, HiddenField
from wtforms.validators import DataRequired, InputRequired, NumberRange, Optional
from flask import current_app

class ThresholdForm(FlaskForm):
    spend = FloatField('Затраты ($)', validators=[DataRequired(), NumberRange(min=0.01)])
    conversions = IntegerField('Конверсии', validators=[InputRequired(), NumberRange(min=0)])
    
    def validate_conversions(self, field):
        # Принимаем 0 как допустимое значение для конверсий
        if field.data is None:
            field.data = 0
    
    class Meta:
        # Отключение CSRF для вложенных форм
        csrf = False

class SetupForm(FlaskForm):
    name = StringField('Название сетапа', validators=[DataRequired()])
    check_interval = IntegerField('Интервал проверки (мин)', 
                                 validators=[DataRequired(), NumberRange(min=5)],
                                 default=30)
    
    # Динамический список порогов (макс. 15)
    thresholds = FieldList(
        FormField(ThresholdForm),
        min_entries=1,
        max_entries=15
    )
    
    submit = SubmitField('Сохранить')

class CampaignSetupForm(FlaskForm):
    setup_id = SelectField('Выберите сетап', coerce=int, validators=[DataRequired()])
    campaign_ids = SelectField('Выберите кампанию', validators=[DataRequired()])
    submit = SubmitField('Назначить')

class CampaignRefreshForm(FlaskForm):
    submit = SubmitField('Обновить список кампаний')