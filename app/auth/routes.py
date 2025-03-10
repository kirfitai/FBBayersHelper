from flask import render_template, redirect, url_for, flash, request, jsonify, session
from flask_login import login_user, logout_user, current_user, login_required
from urllib.parse import urlparse
from app import db  # Используем db из app
from app.auth import bp  # Импортируем bp из auth
from app.auth.forms import LoginForm, RegistrationForm, FacebookAPIForm, FacebookTokenForm, CheckTokenForm, RefreshTokenCampaignsForm
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
        
        login_user(user, remember=form.remember_me.data)
        next_page = request.args.get('next')
        if not next_page or urlparse(next_page).netloc != '':
            next_page = url_for('main.index')
        return redirect(next_page)
    
    return render_template('auth/login.html', title='Вход', form=form)

@bp.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('main.index'))

@bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
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
        flash('Поздравляем, вы зарегистрированы!')
        return redirect(url_for('auth.login'))
    
    return render_template('auth/register.html', title='Регистрация', form=form)

@bp.route('/fb_settings', methods=['GET', 'POST'])
@login_required
def fb_settings():
    form = FacebookAPIForm()
    
    # Предзаполнение формы текущими данными
    if request.method == 'GET':
        if current_user.fb_access_token:
            form.access_token.data = current_user.fb_access_token
        if current_user.fb_app_id:
            form.app_id.data = current_user.fb_app_id
        if current_user.fb_app_secret:
            form.app_secret.data = current_user.fb_app_secret
        if current_user.fb_account_id:
            form.account_id.data = current_user.fb_account_id
    
    if form.validate_on_submit():
        current_user.update_fb_credentials(
            form.access_token.data,
            form.app_id.data,
            form.app_secret.data,
            form.account_id.data
        )
        db.session.commit()
        flash('Настройки Facebook API сохранены')
        return redirect(url_for('main.index'))
    
    return render_template('auth/fb_settings.html', title='Настройки Facebook API', form=form)

@bp.route('/tokens', methods=['GET', 'POST'])
@login_required
def manage_tokens():
    # Ограничение на максимальное количество токенов (10)
    tokens_count = FacebookToken.query.filter_by(user_id=current_user.id).count()
    can_add_token = tokens_count < 10
    
    token_form = FacebookTokenForm()
    check_form = CheckTokenForm()
    refresh_form = RefreshTokenCampaignsForm()
    form = token_form  # Для CSRF-токена
    
    if token_form.validate_on_submit() and can_add_token:
        # Создаем токен без связи с аккаунтами
        token = FacebookToken(
            user_id=current_user.id,
            name=token_form.name.data,
            access_token=token_form.access_token.data,
            app_id=token_form.app_id.data if token_form.app_id.data else None,
            app_secret=token_form.app_secret.data if token_form.app_secret.data else None,
            use_proxy=token_form.use_proxy.data,
            proxy_url=token_form.proxy_url.data if token_form.use_proxy.data and token_form.proxy_url.data else None
        )
        db.session.add(token)
        db.session.commit()
        
        # Разбиваем строку account_id на отдельные аккаунты
        account_ids = [account_id.strip() for account_id in token_form.account_id.data.split(',') if account_id.strip()]
        
        # Добавляем связи с аккаунтами
        for account_id in account_ids:
            # Если ID не начинается с 'act_', добавляем префикс
            if not account_id.startswith('act_'):
                account_id = f'act_{account_id}'
            
            token.add_account(account_id)
        
        db.session.commit()
        
        # Проверка токена и получение данных об аккаунтах
        checker = TokenChecker()
        status, error_message, accounts_data = checker.check_token(token)
        token.update_status(status, error_message)
        db.session.commit()
        
        if status == 'valid':
            # Получаем кампании для всех аккаунтов
            campaigns_result = checker.fetch_campaigns(token)
            
            # Обновляем кампании в сессии
            all_campaigns = []
            for account_id, result in campaigns_result.items():
                if result['success']:
                    # Добавляем аккаунт в имя кампании
                    account_name = next((a.account_name for a in token.accounts if a.account_id == account_id), "Unknown")
                    for campaign in result['campaigns']:
                        campaign['account_id'] = account_id
                        campaign['account_name'] = account_name
                        all_campaigns.append(campaign)
            
            # Обновляем список кампаний в сессии
            if all_campaigns:
                campaign_list = session.get('campaigns', [])
                
                # Добавляем только уникальные кампании
                existing_ids = [c['id'] for c in campaign_list]
                for campaign in all_campaigns:
                    if campaign['id'] not in existing_ids:
                        campaign_data = {
                            'id': campaign['id'],
                            'name': campaign['name'],
                            'account_id': campaign['account_id'],
                            'account_name': campaign['account_name']
                        }
                        campaign_list.append(campaign_data)
                
                session['campaigns'] = campaign_list
            
            flash(f'Токен "{token.name}" добавлен и проверен. Кампании добавлены в список.')
        else:
            flash(f'Токен "{token.name}" добавлен, но не работает: {error_message}', 'danger')
        
        return redirect(url_for('auth.manage_tokens'))
    
    tokens = FacebookToken.query.filter_by(user_id=current_user.id).all()
    
    return render_template('auth/tokens.html', 
                          title='Управление токенами', 
                          token_form=token_form,
                          check_form=check_form,
                          refresh_form=refresh_form,
                          form=form,
                          tokens=tokens,
                          can_add_token=can_add_token)

@bp.route('/tokens/check/<int:token_id>', methods=['POST'])
@login_required
def check_token(token_id):
    token = FacebookToken.query.filter_by(id=token_id, user_id=current_user.id).first_or_404()
    
    checker = TokenChecker()
    status, error_message, accounts_data = checker.check_token(token)
    token.update_status(status, error_message)
    db.session.commit()
    
    if status == 'valid':
        flash(f'Токен "{token.name}" успешно проверен и работает')
    else:
        flash(f'Токен "{token.name}" не работает: {error_message}', 'danger')
    
    return redirect(url_for('auth.manage_tokens'))

@bp.route('/tokens/refresh/<int:token_id>', methods=['POST'])
@login_required
def refresh_token_campaigns(token_id):
    token = FacebookToken.query.filter_by(id=token_id, user_id=current_user.id).first_or_404()
    
    # Проверяем статус токена
    if token.status != 'valid':
        flash(f'Нельзя получить кампании для неработающего токена. Сначала проверьте его.', 'warning')
        return redirect(url_for('auth.manage_tokens'))
    
    # Получаем кампании для токена
    checker = TokenChecker()
    campaigns_result = checker.fetch_campaigns(token)
    
    # Счетчики для отчета
    total_success = 0
    total_campaigns = 0
    
    # Обновляем кампании в сессии
    all_campaigns = []
    for account_id, result in campaigns_result.items():
        if result['success']:
            total_success += 1
            total_campaigns += len(result['campaigns'])
            
            # Добавляем аккаунт в имя кампании
            account_name = next((a.account_name for a in token.accounts if a.account_id == account_id), "Unknown")
            for campaign in result['campaigns']:
                campaign['account_id'] = account_id
                campaign['account_name'] = account_name
                all_campaigns.append(campaign)
                
    # Обновляем список кампаний в сессии
    if all_campaigns:
        campaign_list = session.get('campaigns', [])
        
        # Добавляем только уникальные кампании
        existing_ids = [c['id'] for c in campaign_list]
        for campaign in all_campaigns:
            if campaign['id'] not in existing_ids:
                campaign_data = {
                    'id': campaign['id'],
                    'name': campaign['name'],
                    'account_id': campaign['account_id'],
                    'account_name': campaign['account_name']
                }
                campaign_list.append(campaign_data)
        
        session['campaigns'] = campaign_list
        
        flash(f'Обновлено {total_success} аккаунтов, добавлено {total_campaigns} кампаний')
    else:
        flash('Не удалось получить кампании или активные кампании отсутствуют', 'warning')
    
    return redirect(url_for('auth.manage_tokens'))

@bp.route('/tokens/delete/<int:token_id>', methods=['POST'])
@login_required
def delete_token(token_id):
    token = FacebookToken.query.filter_by(id=token_id, user_id=current_user.id).first_or_404()
    
    name = token.name
    db.session.delete(token)
    
    # Если удаляемый токен был активным, сбрасываем активный токен
    if current_user.active_token_id == token_id:
        current_user.active_token_id = None
        
    db.session.commit()
    flash(f'Токен "{name}" удален')
    
    return redirect(url_for('auth.manage_tokens'))