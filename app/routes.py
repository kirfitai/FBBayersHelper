from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, session
from flask_login import current_user, login_required
from app import db
from app.models.user import User
from app.models.setup import Setup, ThresholdEntry, CampaignSetup
from app.models.token import FacebookToken
from app.forms import SetupForm, CampaignSetupForm, CampaignRefreshForm, ThresholdForm
from app.services.fb_api_client import FacebookAdClient
import json

bp = Blueprint('main', __name__)

@bp.route('/')
@bp.route('/index')
def index():
    if not current_user.is_authenticated:
        return redirect(url_for('auth.login'))
    
    setups = Setup.query.filter_by(user_id=current_user.id).all()
    return render_template('index.html', title='Главная', setups=setups)

# Маршруты для управления сетапами

@bp.route('/setups')
@login_required
def setups():
    user_setups = Setup.query.filter_by(user_id=current_user.id).all()
    form = SetupForm()  # Пустая форма для CSRF-токена
    return render_template('setups/index_simple.html', title='Сетапы', setups=user_setups, form=form)

@bp.route('/setups/create', methods=['GET', 'POST'])
@login_required
def create_setup():
    form = SetupForm()
    
    if form.validate_on_submit():
        setup = Setup(
            name=form.name.data,
            user_id=current_user.id,
            check_interval=form.check_interval.data
        )
        db.session.add(setup)
        db.session.commit()
        
        # Добавление порогов
        for threshold_form in form.thresholds.data:
            threshold = ThresholdEntry(
                setup_id=setup.id,
                spend=threshold_form['spend'],
                conversions=threshold_form['conversions']
            )
            db.session.add(threshold)
        
        db.session.commit()
        flash(f'Сетап "{setup.name}" успешно создан')
        return redirect(url_for('main.setups'))
    
    return render_template('setups/create.html', title='Создание сетапа', form=form)

@bp.route('/setups/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_setup(id):
    setup = Setup.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    form = SetupForm()
    
    if form.validate_on_submit():
        setup.name = form.name.data
        setup.check_interval = form.check_interval.data
        
        # Удаление старых порогов
        for threshold in setup.thresholds:
            db.session.delete(threshold)
        
        # Добавление новых порогов
        for threshold_form in form.thresholds.data:
            threshold = ThresholdEntry(
                setup_id=setup.id,
                spend=threshold_form['spend'],
                conversions=threshold_form['conversions']
            )
            db.session.add(threshold)
        
        db.session.commit()
        flash(f'Сетап "{setup.name}" успешно обновлен')
        return redirect(url_for('main.setups'))
    
    # Предзаполнение формы
    if request.method == 'GET':
        form.name.data = setup.name
        form.check_interval.data = setup.check_interval
        
        # Загрузка порогов
        thresholds = setup.thresholds.order_by(ThresholdEntry.spend).all()
        while len(form.thresholds) > 0:
            form.thresholds.pop_entry()
            
        for threshold in thresholds:
            threshold_form = ThresholdForm()
            threshold_form.spend = threshold.spend
            threshold_form.conversions = threshold.conversions
            form.thresholds.append_entry(
                {'spend': threshold.spend, 'conversions': threshold.conversions}
            )
    
    return render_template('setups/edit.html', title='Редактирование сетапа', form=form, setup=setup)

@bp.route('/setups/<int:id>/delete', methods=['POST'])
@login_required
def delete_setup(id):
    setup = Setup.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    name = setup.name
    db.session.delete(setup)
    db.session.commit()
    flash(f'Сетап "{name}" удален')
    return redirect(url_for('main.setups'))

@bp.route('/setups/<int:id>/toggle', methods=['POST'])
@login_required
def toggle_setup(id):
    setup = Setup.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    setup.is_active = not setup.is_active
    db.session.commit()
    status = 'активирован' if setup.is_active else 'деактивирован'
    flash(f'Сетап "{setup.name}" {status}')
    return redirect(url_for('main.setups'))

# Маршруты для кампаний

@bp.route('/campaigns')
@login_required
def campaigns():
    # Получение сетапов пользователя
    setups = Setup.query.filter_by(user_id=current_user.id).all()
    
    # Получение назначенных кампаний
    campaign_setups = CampaignSetup.query.filter_by(user_id=current_user.id).all()
    
    # Создание пустой формы для CSRF-токена
    form = CampaignRefreshForm()
    
    return render_template('campaigns/index.html', 
                          title='Управление кампаниями',
                          campaign_setups=campaign_setups,
                          form=form)

@bp.route('/campaigns/refresh', methods=['POST'])
@login_required
def refresh_campaigns():
    # Проверка наличия активного токена
    if current_user.active_token_id:
        token = FacebookToken.query.get(current_user.active_token_id)
        if not token or token.status != 'valid':
            flash('Активный токен недействителен. Пожалуйста, выберите другой активный токен.', 'error')
            return redirect(url_for('auth.manage_tokens'))
    elif current_user.fb_access_token and current_user.fb_account_id:
        # Используем стандартные настройки, если нет активного токена
        token = None
    else:
        flash('Необходимо настроить учетные данные Facebook API или выбрать активный токен', 'error')
        return redirect(url_for('auth.manage_tokens'))
    
    try:
        # Инициализация клиента Facebook API
        if token:
            fb_client = FacebookAdClient(token_obj=token)
        else:
            fb_client = FacebookAdClient(
                access_token=current_user.fb_access_token,
                app_id=current_user.fb_app_id,
                app_secret=current_user.fb_app_secret,
                ad_account_id=current_user.fb_account_id
            )
        
        # Получение списка кампаний
        campaigns = fb_client.get_campaigns('ACTIVE')
        
        # Сохранение списка кампаний в сессии
        campaign_list = [{'id': campaign['id'], 'name': campaign['name']} 
                         for campaign in campaigns]
        session['campaigns'] = campaign_list
        
        flash(f'Список кампаний обновлен. Найдено {len(campaign_list)} кампаний')
    except Exception as e:
        flash(f'Ошибка при обновлении кампаний: {str(e)}', 'error')
    
    return redirect(url_for('main.campaigns'))

@bp.route('/campaigns/assign', methods=['GET', 'POST'])
@login_required
def assign_campaign():
    form = CampaignSetupForm()
    
    # Загрузка списка сетапов для селекта
    setups = Setup.query.filter_by(user_id=current_user.id).all()
    form.setup_id.choices = [(setup.id, setup.name) for setup in setups]
    
    # Загрузка списка кампаний из сессии
    campaign_choices = []
    campaigns = session.get('campaigns', [])
    if campaigns:
        campaign_choices = [(c['id'], f"{c['name']} ({c['id']})") for c in campaigns]
    
    form.campaign_ids.choices = campaign_choices
    
    if form.validate_on_submit():
        setup_id = form.setup_id.data
        campaign_id = form.campaign_ids.data
        
        # Проверка, существует ли уже такое назначение
        existing = CampaignSetup.query.filter_by(
            user_id=current_user.id,
            setup_id=setup_id,
            campaign_id=campaign_id
        ).first()
        
        if existing:
            flash('Эта кампания уже назначена на этот сетап', 'error')
        else:
            # Получение имени кампании
            campaign_name = None
            for choice in campaign_choices:
                if choice[0] == campaign_id:
                    campaign_name = choice[1]
                    break
            
            # Создание нового назначения
            campaign_setup = CampaignSetup(
                user_id=current_user.id,
                setup_id=setup_id,
                campaign_id=campaign_id,
                campaign_name=campaign_name
            )
            
            db.session.add(campaign_setup)
            db.session.commit()
            flash('Кампания успешно назначена на сетап')
            return redirect(url_for('main.campaigns'))
    
    return render_template('campaigns/assign.html', 
                          title='Назначение кампании',
                          form=form)

@bp.route('/campaigns/setup/<int:id>/delete', methods=['POST'])
@login_required
def delete_campaign_setup(id):
    campaign_setup = CampaignSetup.query.filter_by(
        id=id, user_id=current_user.id
    ).first_or_404()
    
    db.session.delete(campaign_setup)
    db.session.commit()
    flash('Кампания откреплена от сетапа')
    return redirect(url_for('main.campaigns'))

@bp.route('/campaigns/setup/<int:id>/toggle', methods=['POST'])
@login_required
def toggle_campaign_setup(id):
    campaign_setup = CampaignSetup.query.filter_by(
        id=id, user_id=current_user.id
    ).first_or_404()
    
    campaign_setup.is_active = not campaign_setup.is_active
    db.session.commit()
    
    status = 'активирована' if campaign_setup.is_active else 'деактивирована'
    flash(f'Кампания {status}')
    return redirect(url_for('main.campaigns'))