from flask_admin import Admin, AdminIndexView, expose
from flask_admin.contrib.sqla import ModelView
from flask_login import current_user
from flask import redirect, url_for, flash, request, abort
from app import db
from app.models.user import User
from app.models.setup import Setup, CampaignSetup, ThresholdEntry
from app.models.token import FacebookToken, FacebookTokenAccount
from app.models.conversion import Conversion
import pyotp

# Базовый класс для ограничения доступа только администраторам
class AdminRequiredMixin:
    def is_accessible(self):
        return current_user.is_authenticated and current_user.is_admin
    
    def inaccessible_callback(self, name, **kwargs):
        flash('Доступ запрещен. Требуются права администратора.', 'danger')
        return redirect(url_for('auth.login', next=request.url))

# Главная страница админки
class AdminHomeView(AdminRequiredMixin, AdminIndexView):
    @expose('/')
    def index(self):
        stats = {
            'users_count': User.query.count(),
            'conversions_count': Conversion.query.count(),
            'setups_count': Setup.query.count(),
            'tokens_count': FacebookToken.query.count()
        }
        return self.render('admin/index.html', stats=stats)

# Управление пользователями
class UserAdmin(AdminRequiredMixin, ModelView):
    column_list = ('id', 'username', 'email', 'is_admin', 'is_2fa_enabled', 'created_at')
    column_searchable_list = ('username', 'email')
    column_filters = ('is_admin', 'is_2fa_enabled', 'created_at')
    form_columns = ('username', 'email', 'is_admin')
    
    def on_model_change(self, form, model, is_created):
        if is_created:
            # При создании нового пользователя устанавливаем пароль по умолчанию
            model.set_password('password123')  # Временный пароль
            flash(f'Пользователь создан с временным паролем: password123', 'info')
    
    # Добавление действий для сброса пароля и управления 2FA
    @expose('/reset_password/<int:user_id>', methods=['POST'])
    def reset_password(self, user_id):
        user = User.query.get_or_404(user_id)
        new_password = 'password123'  # Или генерировать случайный пароль
        user.set_password(new_password)
        db.session.commit()
        flash(f'Пароль пользователя {user.username} сброшен на: {new_password}', 'success')
        return redirect(url_for('.index_view'))
    
    @expose('/toggle_2fa/<int:user_id>', methods=['POST'])
    def toggle_2fa(self, user_id):
        user = User.query.get_or_404(user_id)
        if user.is_2fa_enabled:
            user.enable_2fa(False)
            flash(f'2FA отключена для пользователя {user.username}', 'success')
        else:
            # Генерируем новый секретный ключ
            secret = pyotp.random_base32()
            user.set_totp_secret(secret)
            user.enable_2fa(True)
            flash(f'2FA включена для пользователя {user.username}. Новый ключ: {secret}', 'success')
        db.session.commit()
        return redirect(url_for('.index_view'))

# Управление конверсиями (только просмотр)
class ConversionAdmin(AdminRequiredMixin, ModelView):
    column_list = ('id', 'ref', 'ref_prefix', 'form_id', 'timestamp', 'ip_address')
    column_searchable_list = ('ref', 'ref_prefix', 'form_id', 'ip_address')
    column_filters = ('ref_prefix', 'form_id', 'date')
    can_create = False
    can_edit = False
    can_delete = True

# Настройка админ-панели
def init_admin(app):
    admin = Admin(
        app, 
        name='FB Bayers Helper Admin', 
        template_mode='bootstrap4',
        index_view=AdminHomeView(name='Панель управления', url='/admin')
    )
    
    # Регистрация моделей
    admin.add_view(UserAdmin(User, db.session, name='Пользователи'))
    admin.add_view(ConversionAdmin(Conversion, db.session, name='Конверсии'))
    
    return admin 