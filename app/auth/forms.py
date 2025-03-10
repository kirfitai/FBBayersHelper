from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, HiddenField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError, Optional
from app.models.user import User

class LoginForm(FlaskForm):
    username = StringField('Имя пользователя', validators=[DataRequired()])
    password = PasswordField('Пароль', validators=[DataRequired()])
    remember_me = BooleanField('Запомнить меня')
    submit = SubmitField('Войти')

class RegistrationForm(FlaskForm):
    username = StringField('Имя пользователя', validators=[DataRequired(), Length(min=2, max=20)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Пароль', validators=[DataRequired(), Length(min=6)])
    password2 = PasswordField(
        'Повторите пароль', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Зарегистрироваться')

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user is not None:
            raise ValidationError('Это имя пользователя уже занято. Пожалуйста, выберите другое.')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user is not None:
            raise ValidationError('Этот email уже используется. Пожалуйста, выберите другой.')

class FacebookAPIForm(FlaskForm):
    access_token = StringField('Access Token', validators=[DataRequired()])
    app_id = StringField('App ID', validators=[Optional()])
    app_secret = StringField('App Secret', validators=[Optional()])
    account_id = StringField('Account ID (act_XXXXXXXX)', validators=[DataRequired()])
    submit = SubmitField('Сохранить')

class FacebookTokenForm(FlaskForm):
    name = StringField('Название токена', validators=[DataRequired()])
    access_token = StringField('Access Token', validators=[DataRequired()])
    app_id = StringField('App ID', validators=[Optional()])
    app_secret = StringField('App Secret', validators=[Optional()])
    account_id = StringField('ID аккаунтов (через запятую)', validators=[DataRequired()])
    use_proxy = BooleanField('Использовать прокси')
    proxy_url = StringField('Proxy URL (http://username:password@host:port)', validators=[Optional()])
    submit = SubmitField('Добавить токен')

class CheckTokenForm(FlaskForm):
    token_id = HiddenField('Token ID', validators=[DataRequired()])
    submit = SubmitField('Проверить')

class RefreshTokenCampaignsForm(FlaskForm):
    token_id = HiddenField('Token ID', validators=[DataRequired()])
    submit = SubmitField('Обновить кампании')