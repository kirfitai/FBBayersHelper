from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, HiddenField, TextAreaField
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
    is_admin = BooleanField('Администратор')
    submit = SubmitField('Создать пользователя')

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user is not None:
            raise ValidationError('Это имя пользователя уже занято. Пожалуйста, выберите другое.')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user is not None:
            raise ValidationError('Этот email уже используется. Пожалуйста, выберите другой.')

class TwoFactorForm(FlaskForm):
    code = StringField('Код аутентификации', validators=[
        DataRequired(), 
        Length(min=6, max=6, message='Код должен содержать 6 цифр')
    ])
    submit = SubmitField('Подтвердить')

class FacebookAPIForm(FlaskForm):
    access_token = StringField('Токен доступа', validators=[DataRequired()])
    app_id = StringField('App ID', validators=[DataRequired()])
    app_secret = StringField('App Secret', validators=[DataRequired()])
    account_id = StringField('Account ID', validators=[DataRequired()])
    submit = SubmitField('Сохранить')

class FacebookTokenForm(FlaskForm):
    name = StringField('Название токена', validators=[DataRequired()])
    access_token = StringField('Токен доступа', validators=[DataRequired()])
    app_id = StringField('App ID', validators=[Optional()])
    app_secret = StringField('App Secret', validators=[Optional()])
    use_proxy = BooleanField('Использовать прокси')
    proxy_url = StringField('URL прокси (http://user:pass@host:port)', validators=[Optional()])
    account_id = TextAreaField('Account ID(s) (можно несколько через запятую)', validators=[Optional()])
    submit = SubmitField('Сохранить')

class CheckTokenForm(FlaskForm):
    submit = SubmitField('Проверить')

class RefreshTokenCampaignsForm(FlaskForm):
    submit = SubmitField('Обновить кампании')