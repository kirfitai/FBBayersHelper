from flask import render_template, redirect, url_for, flash, request, jsonify, session
from flask_login import login_user, logout_user, current_user, login_required
from urllib.parse import urlparse
import pyotp
import qrcode
import io
import base64
from app import db  # Используем db из app
from app.auth import bp  # Импортируем bp из auth
from app.auth.forms import LoginForm, RegistrationForm, FacebookAPIForm, FacebookTokenForm, CheckTokenForm, RefreshTokenCampaignsForm, TwoFactorForm
from app.models.user import User
from app.models.token import FacebookToken, FacebookTokenAccount
from app.services.token_checker import TokenChecker

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user is None or not user.check_password(form.password.data):
            flash('Неверное имя пользователя или пароль')
            return redirect(url_for('auth.login'))
        
        # Проверяем, включена ли двухфакторная аутентификация
        if user.is_2fa_enabled:
            # Сохраняем ID пользователя в сессии и перенаправляем на ввод кода 2FA
            session['user_id_2fa'] = user.id
            return redirect(url_for('auth.two_factor'))
        
        login_user(user, remember=form.remember_me.data)
        next_page = request.args.get('next')
        if not next_page or urlparse(next_page).netloc != '':
            next_page = url_for('main.index')
        return redirect(next_page)
    
    return render_template('auth/login.html', title='Вход', form=form)

@bp.route('/two_factor', methods=['GET', 'POST'])
def two_factor():
    # Проверяем, что в сессии есть ID пользователя
    if 'user_id_2fa' not in session:
        return redirect(url_for('auth.login'))
    
    user = User.query.get(session['user_id_2fa'])
    if not user:
        # Если пользователь не найден, удаляем сессию и перенаправляем
        session.pop('user_id_2fa', None)
        return redirect(url_for('auth.login'))
    
    form = TwoFactorForm()
    if form.validate_on_submit():
        # Проверяем введенный код
        totp = pyotp.TOTP(user.totp_secret)
        if totp.verify(form.code.data):
            # Код верный, аутентифицируем пользователя
            login_user(user, remember=True)
            session.pop('user_id_2fa', None)  # Удаляем из сессии ID пользователя
            
            next_page = request.args.get('next')
            if not next_page or urlparse(next_page).netloc != '':
                next_page = url_for('main.index')
            return redirect(next_page)
        else:
            flash('Неверный код аутентификации')
    
    return render_template('auth/two_factor.html', form=form)

@bp.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('auth.login'))

@bp.route('/register', methods=['GET', 'POST'])
@login_required
def register():
    # Проверяем, является ли текущий пользователь администратором
    if not current_user.is_admin:
        flash('Доступ запрещен. Только администраторы могут создавать новых пользователей.')
        return redirect(url_for('main.index'))
    
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(
            username=form.username.data,
            email=form.email.data,
            password=form.password.data
        )
        db.session.add(user)
        db.session.commit()
        flash(f'Пользователь {user.username} успешно создан!')
        return redirect(url_for('admin.users'))
    
    return render_template('auth/register.html', title='Создание пользователя', form=form)

@bp.route('/setup_2fa', methods=['GET', 'POST'])
@login_required
def setup_2fa():
    # Если 2FA уже включена, перенаправляем на страницу настроек
    if current_user.is_2fa_enabled:
        flash('Двухфакторная аутентификация уже настроена')
        return redirect(url_for('main.profile'))
    
    # Генерируем новый секретный ключ, если его нет
    if not current_user.totp_secret:
        secret = pyotp.random_base32()
        current_user.set_totp_secret(secret)
        db.session.commit()
    else:
        secret = current_user.totp_secret
    
    # Создаем URL для QR-кода
    totp = pyotp.TOTP(secret)
    provisioning_url = totp.provisioning_uri(
        name=current_user.email,
        issuer_name="FB Bayers Helper"
    )
    
    # Генерируем QR-код
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(provisioning_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Сохраняем QR-код в памяти и кодируем его в base64
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    qr_code = base64.b64encode(buffer.getvalue()).decode('utf-8')
    
    form = TwoFactorForm()
    if form.validate_on_submit():
        # Проверяем код для подтверждения настройки
        if totp.verify(form.code.data):
            current_user.enable_2fa(True)
            db.session.commit()
            flash('Двухфакторная аутентификация успешно настроена!')
            return redirect(url_for('main.profile'))
        else:
            flash('Неверный код. Попробуйте еще раз.')
    
    return render_template('auth/setup_2fa.html', 
                           qr_code=qr_code, 
                           secret=secret,
                           form=form)

@bp.route('/disable_2fa', methods=['POST'])
@login_required
def disable_2fa():
    current_user.enable_2fa(False)
    db.session.commit()
    flash('Двухфакторная аутентификация отключена')
    return redirect(url_for('main.profile'))

@bp.route('/facebook_api', methods=['GET', 'POST'])
@login_required
def facebook_api():
    form = FacebookAPIForm()
    if form.validate_on_submit():
        current_user.update_fb_credentials(
            form.access_token.data,
            form.app_id.data,
            form.app_secret.data,
            form.account_id.data
        )
        db.session.commit()
        flash('Данные API Facebook успешно обновлены')
        return redirect(url_for('main.index'))
    
    # Предзаполняем форму текущими данными пользователя
    if request.method == 'GET':
        form.access_token.data = current_user.fb_access_token
        form.app_id.data = current_user.fb_app_id
        form.app_secret.data = current_user.fb_app_secret
        form.account_id.data = current_user.fb_account_id
        
    return render_template('auth/facebook_api.html', title='Настройки API Facebook', form=form)

@bp.route('/tokens', methods=['GET'])
@login_required
def tokens():
    tokens = FacebookToken.query.filter_by(user_id=current_user.id).all()
    active_token_id = current_user.active_token_id
    return render_template('auth/tokens.html', tokens=tokens, active_token_id=active_token_id)

@bp.route('/tokens/add', methods=['GET', 'POST'])
@login_required
def add_token():
    form = FacebookTokenForm()
    if form.validate_on_submit():
        token = FacebookToken(
            user_id=current_user.id,
            name=form.name.data,
            access_token=form.access_token.data,
            app_id=form.app_id.data,
            app_secret=form.app_secret.data,
            use_proxy=form.use_proxy.data,
            proxy_url=form.proxy_url.data if form.use_proxy.data else None
        )
        db.session.add(token)
        db.session.commit()
        
        # Проверяем токен и получаем аккаунты
        checker = TokenChecker(token)
        checker.check_and_update_token()
        
        flash('Токен успешно добавлен')
        return redirect(url_for('auth.tokens'))
    
    return render_template('auth/token_form.html', title='Добавить токен', form=form)

@bp.route('/tokens/edit/<int:token_id>', methods=['GET', 'POST'])
@login_required
def edit_token(token_id):
    token = FacebookToken.query.filter_by(id=token_id, user_id=current_user.id).first_or_404()
    form = FacebookTokenForm()
    
    if form.validate_on_submit():
        token.name = form.name.data
        token.access_token = form.access_token.data
        token.app_id = form.app_id.data
        token.app_secret = form.app_secret.data
        token.use_proxy = form.use_proxy.data
        token.proxy_url = form.proxy_url.data if form.use_proxy.data else None
        db.session.commit()
        
        # Проверяем токен и получаем аккаунты
        checker = TokenChecker(token)
        checker.check_and_update_token()
        
        flash('Токен успешно обновлен')
        return redirect(url_for('auth.tokens'))
    
    if request.method == 'GET':
        form.name.data = token.name
        form.access_token.data = token.access_token
        form.app_id.data = token.app_id
        form.app_secret.data = token.app_secret
        form.use_proxy.data = token.use_proxy
        form.proxy_url.data = token.proxy_url
        
    return render_template('auth/token_form.html', title='Редактировать токен', form=form)

@bp.route('/tokens/delete/<int:token_id>', methods=['POST'])
@login_required
def delete_token(token_id):
    token = FacebookToken.query.filter_by(id=token_id, user_id=current_user.id).first_or_404()
    
    # Если удаляем активный токен, сбрасываем active_token_id у пользователя
    if current_user.active_token_id == token.id:
        current_user.active_token_id = None
        db.session.commit()
    
    db.session.delete(token)
    db.session.commit()
    
    flash('Токен успешно удален')
    return redirect(url_for('auth.tokens'))

@bp.route('/tokens/set_active/<int:token_id>', methods=['POST'])
@login_required
def set_active_token(token_id):
    token = FacebookToken.query.filter_by(id=token_id, user_id=current_user.id).first_or_404()
    current_user.active_token_id = token.id
    db.session.commit()
    flash(f'Токен "{token.name}" установлен как активный')
    return redirect(url_for('auth.tokens'))

@bp.route('/tokens/check/<int:token_id>', methods=['GET', 'POST'])
@login_required
def check_token(token_id):
    token = FacebookToken.query.filter_by(id=token_id, user_id=current_user.id).first_or_404()
    form = CheckTokenForm()
    
    if form.validate_on_submit():
        checker = TokenChecker(token)
        result = checker.check_and_update_token()
        if result:
            flash('Токен проверен и обновлен')
        else:
            flash('Ошибка при проверке токена', 'error')
        return redirect(url_for('auth.tokens'))
    
    return render_template('auth/check_token.html', token=token, form=form)

@bp.route('/tokens/refresh_campaigns/<int:token_id>', methods=['GET', 'POST'])
@login_required
def refresh_token_campaigns(token_id):
    token = FacebookToken.query.filter_by(id=token_id, user_id=current_user.id).first_or_404()
    form = RefreshTokenCampaignsForm()
    
    if form.validate_on_submit():
        from app.services.facebook_api import FacebookAPI
        
        try:
            fb_api = FacebookAPI(
                access_token=token.access_token,
                app_id=token.app_id,
                app_secret=token.app_secret,
                account_id=None  # Обновим все аккаунты
            )
            
            # Обновляем кампании для каждого аккаунта
            for account in token.accounts:
                fb_api.account_id = account.account_id
                campaigns = fb_api.get_campaigns()
                
                if campaigns:
                    # Обработка полученных кампаний
                    # Здесь должна быть логика обработки кампаний
                    flash(f'Успешно получено {len(campaigns)} кампаний для аккаунта {account.account_id}')
                else:
                    flash(f'Не удалось получить кампании для аккаунта {account.account_id}', 'error')
                
            return redirect(url_for('auth.tokens'))
            
        except Exception as e:
            flash(f'Ошибка при обновлении кампаний: {str(e)}', 'error')
            return redirect(url_for('auth.tokens'))
    
    return render_template('auth/refresh_campaigns.html', token=token, form=form)