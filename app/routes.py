from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, session
from flask_login import current_user, login_required
from app.extensions import db
from app.models.user import User
from app.models.setup import Setup, ThresholdEntry, CampaignSetup
from app.models.token import FacebookToken
from app.forms import SetupForm, CampaignSetupForm, CampaignRefreshForm, ThresholdForm
from app.services.fb_api_client import FacebookAdClient
from app.services.token_checker import TokenChecker
from app.models.conversion import Conversion
import json
import logging
from datetime import datetime
import random
import string

# Настройка логирования
logger = logging.getLogger(__name__)

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
            check_interval=form.check_interval.data,
            check_period=form.check_period.data
        )
        db.session.add(setup)
        db.session.commit()
        
        # Добавление порогов
        for threshold_form in form.thresholds.data:
            # Убедимся, что конверсии не менее 0 (можно установить 0)
            conversions = max(0, threshold_form['conversions'] or 0)
            threshold = ThresholdEntry(
                setup_id=setup.id,
                spend=threshold_form['spend'],
                conversions=conversions
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
        setup.check_period = form.check_period.data
        
        # Удаление старых порогов
        for threshold in setup.thresholds:
            db.session.delete(threshold)
        
        # Добавление новых порогов
        for threshold_form in form.thresholds.data:
            # Убедимся, что конверсии не менее 0 (можно установить 0)
            conversions = max(0, threshold_form['conversions'] or 0)
            threshold = ThresholdEntry(
                setup_id=setup.id,
                spend=threshold_form['spend'],
                conversions=conversions
            )
            db.session.add(threshold)
        
        db.session.commit()
        flash(f'Сетап "{setup.name}" успешно обновлен')
        return redirect(url_for('main.setups'))
    
    # Предзаполнение формы
    if request.method == 'GET':
        form.name.data = setup.name
        form.check_interval.data = setup.check_interval
        form.check_period.data = setup.check_period
        
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
    # Проверка наличия API - проверяем как старые настройки, так и токены
    has_api_configured = False
    
    # Проверка токенов
    valid_tokens = FacebookToken.query.filter_by(
        user_id=current_user.id, 
        status='valid'
    ).count()
    
    if valid_tokens > 0:
        has_api_configured = True
        logger.info(f"Пользователь {current_user.id} имеет {valid_tokens} рабочих токенов")
    
    # Если нет токенов, проверяем старые настройки
    elif current_user.fb_access_token and current_user.fb_account_id:
        has_api_configured = True
        logger.info(f"Пользователь {current_user.id} использует настройки по умолчанию")
    
    # Получение сетапов пользователя
    setups = Setup.query.filter_by(user_id=current_user.id).all()
    
    # Получение назначенных кампаний
    campaign_setups = CampaignSetup.query.filter_by(user_id=current_user.id).all()
    
    # Создание пустой формы для CSRF-токена
    form = CampaignRefreshForm()
    
    return render_template('campaigns/index.html', 
                          title='Управление кампаниями',
                          campaign_setups=campaign_setups,
                          has_api_configured=has_api_configured,
                          form=form)

@bp.route('/campaigns/refresh', methods=['POST'])
@login_required
def refresh_campaigns():
    # Отладочный вывод
    logger.info(f"Пользователь {current_user.id} запустил обновление кампаний")
    
    # Получаем все действующие токены пользователя
    valid_tokens = FacebookToken.query.filter_by(
        user_id=current_user.id, 
        status='valid'
    ).all()
    
    # Отладка токенов
    logger.info(f"Найдено действующих токенов: {len(valid_tokens)}")
    for token in valid_tokens:
        logger.info(f"Токен {token.id} ({token.name}): Аккаунты: {token.get_account_ids()}")
    
    if not valid_tokens:
        logger.warning(f"У пользователя {current_user.id} нет действительных токенов")
        
        # Проверяем, есть ли у пользователя настройки API
        if current_user.fb_access_token and current_user.fb_account_id:
            # Используем стандартные настройки, если нет токенов
            try:
                # Убедимся, что ID аккаунта начинается с 'act_'
                account_id = current_user.fb_account_id
                if not account_id.startswith('act_'):
                    account_id = f'act_{account_id}'
                
                logger.info(f"Пробуем использовать основные настройки API для аккаунта {account_id}")
                
                # Сначала пробуем прямой запрос к API, так как это более надежный метод
                import requests
                import json
                from facebook_business.adobjects.campaign import Campaign
                
                try:
                    response = requests.get(
                        f'https://graph.facebook.com/v18.0/{account_id}/campaigns',
                        params={
                            'access_token': current_user.fb_access_token,
                            'fields': 'id,name,status,objective',
                            'limit': 100
                        },
                        timeout=30  # Увеличиваем таймаут до 30 секунд
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        campaigns_data = data.get('data', [])
                        
                        # Создаем список кампаний для сессии
                        campaign_list = []
                        for campaign_data in campaigns_data:
                            # Фильтруем только активные кампании
                            if campaign_data.get('status') == 'ACTIVE':
                                campaign_list.append({
                                    'id': campaign_data.get('id'),
                                    'name': campaign_data.get('name'),
                                    'account_id': account_id,
                                    'account_name': "Основной аккаунт"
                                })
                        
                        session['campaigns'] = campaign_list
                        
                        logger.info(f"Найдено {len(campaign_list)} кампаний через основные настройки API")
                        flash(f'Список кампаний обновлен. Найдено {len(campaign_list)} кампаний')
                        return redirect(url_for('main.campaigns'))
                    else:
                        logger.error(f"Ошибка API: {response.status_code} - {response.text}")
                        # Продолжаем и пробуем через SDK
                except Exception as direct_api_error:
                    logger.warning(f"Ошибка при прямом запросе к API: {str(direct_api_error)}")
                    # Продолжаем и пробуем через SDK
                
                # Если прямой запрос не сработал, пробуем через SDK
                fb_client = FacebookAdClient(
                    access_token=current_user.fb_access_token,
                    app_id=current_user.fb_app_id,
                    app_secret=current_user.fb_app_secret,
                    ad_account_id=account_id
                )
                
                # Получение списка кампаний
                campaigns = fb_client.get_campaigns('ACTIVE')
                
                # Сохранение списка кампаний в сессии
                campaign_list = []
                for campaign in campaigns:
                    if hasattr(campaign, 'id') and hasattr(campaign, 'name'):
                        campaign_list.append({
                            'id': campaign['id'],
                            'name': campaign['name'],
                            'account_id': account_id,
                            'account_name': "Основной аккаунт"
                        })
                session['campaigns'] = campaign_list
                
                logger.info(f"Найдено {len(campaign_list)} кампаний через основные настройки API")
                flash(f'Список кампаний обновлен. Найдено {len(campaign_list)} кампаний')
                return redirect(url_for('main.campaigns'))
            except Exception as e:
                logger.error(f"Ошибка при обновлении кампаний через основные настройки: {str(e)}")
                flash(f'Ошибка при обновлении кампаний: {str(e)}', 'danger')
                return redirect(url_for('main.campaigns'))
        else:
            logger.warning("Нет ни токенов, ни основных настроек API")
            flash('Необходимо добавить токены Facebook API или настроить учетные данные', 'error')
            return redirect(url_for('auth.manage_tokens'))
    
    # Инициализируем счетчики
    total_campaigns = 0
    success_tokens = 0
    failed_tokens = 0
    
    # Проходимся по всем токенам и собираем кампании
    checker = TokenChecker()
    all_campaigns = []
    
    for token in valid_tokens:
        try:
            logger.info(f"Запрос кампаний для токена {token.id} ({token.name})")
            logger.info(f"Связанные аккаунты: {token.get_account_ids()}")
            
            campaigns_result = checker.fetch_campaigns(token)
            
            has_success = False
            token_campaigns = 0
            
            for account_id, result in campaigns_result.items():
                if result['success']:
                    has_success = True
                    token_campaigns += len(result['campaigns'])
                    logger.info(f"Для аккаунта {account_id} найдено {len(result['campaigns'])} кампаний")
                    
                    # Добавляем аккаунт в имя кампании
                    account_name = next((a.account_name for a in token.accounts if a.account_id == account_id), "Unknown")
                    for campaign in result['campaigns']:
                        # Проверяем, что campaign - объект и имеет нужные атрибуты
                        if hasattr(campaign, 'id') and hasattr(campaign, 'name'):
                            campaign_data = {
                                'id': campaign['id'],
                                'name': campaign['name'],
                                'account_id': account_id,
                                'account_name': account_name
                            }
                            all_campaigns.append(campaign_data)
                        # Обработка объектов класса Campaign из facebook_business SDK
                        elif hasattr(campaign, '_data') and 'id' in campaign._data and 'name' in campaign._data:
                            campaign_data = {
                                'id': campaign._data['id'],
                                'name': campaign._data['name'],
                                'account_id': account_id,
                                'account_name': account_name
                            }
                            all_campaigns.append(campaign_data)
                        elif isinstance(campaign, dict) and 'id' in campaign and 'name' in campaign:
                            campaign_data = {
                                'id': campaign['id'],
                                'name': campaign['name'],
                                'account_id': account_id,
                                'account_name': account_name
                            }
                            all_campaigns.append(campaign_data)
                        else:
                            logger.warning(f"Кампания имеет неожиданный формат: {type(campaign)}, {campaign}")
                else:
                    logger.warning(f"Ошибка получения кампаний для аккаунта {account_id}: {result['error']}")
            
            if has_success:
                success_tokens += 1
                total_campaigns += token_campaigns
                logger.info(f"Токен {token.id} успешно получил {token_campaigns} кампаний")
            else:
                failed_tokens += 1
                logger.warning(f"Токен {token.id} не смог получить кампании")
                
        except Exception as e:
            failed_tokens += 1
            logger.error(f"Ошибка обработки токена {token.id}: {str(e)}")
            continue
    
    # Обновляем список кампаний в сессии
    if all_campaigns:
        # Преобразуем список кампаний для сессии
        campaign_list = []
        for campaign in all_campaigns:
            # Проверяем, что такой кампании еще нет в списке
            if not any(c['id'] == campaign['id'] for c in campaign_list):
                campaign_list.append(campaign)
        
        session['campaigns'] = campaign_list
        
        logger.info(f"Всего найдено {len(campaign_list)} уникальных кампаний через {success_tokens} токенов")
        flash(f'Список кампаний обновлен. Найдено {len(campaign_list)} кампаний через {success_tokens} токенов')
    else:
        logger.warning("Не удалось получить ни одной кампании")
        flash('Не удалось получить кампании через имеющиеся токены', 'warning')
    
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
        for c in campaigns:
            # Добавляем информацию об аккаунте, если есть
            if 'account_name' in c and c['account_name']:
                display_name = f"{c['name']} - {c['account_name']} ({c['id']})"
            else:
                display_name = f"{c['name']} ({c['id']})"
                
            campaign_choices.append((c['id'], display_name))
    
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
            logger.info(f"Кампания {campaign_id} назначена на сетап {setup_id}")
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
    logger.info(f"Кампания {campaign_setup.campaign_id} откреплена от сетапа {campaign_setup.setup_id}")
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
    logger.info(f"Кампания {campaign_setup.campaign_id} {status}")
    flash(f'Кампания {status}')
    return redirect(url_for('main.campaigns'))

@bp.route('/api/conversion/add', methods=['GET', 'POST'])
def add_conversion():
    """API для добавления конверсии через GET или POST запросы"""
    # Получаем данные из GET или POST запроса
    if request.method == 'POST':
        if request.is_json:
            data = request.json
        else:
            data = request.form
    else:  # GET запрос
        data = request.args
    
    # Проверяем наличие обязательных параметров
    ref = data.get('ref')
    form_id = data.get('formid')  # Обратите внимание: параметр называется 'formid', а не 'form_id'
    quid = data.get('quid')
    
    if not ref or not form_id:
        return jsonify({'error': 'Необходимо указать ref и formid'}), 400
    
    # Создаем запись о конверсии
    conversion = Conversion(
        ref=ref,
        form_id=form_id,
        quid=quid,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string if request.user_agent else None
    )
    
    db.session.add(conversion)
    db.session.commit()
    
    # Возвращаем успешный ответ
    return jsonify({
        'success': True, 
        'id': conversion.id,
        'message': 'Конверсия успешно сохранена'
    }), 201

@bp.route('/api/conversions/stats', methods=['GET'])
@login_required
def get_conversion_stats():
    """Получение статистики по конверсиям"""
    try:
        ref_prefix = request.args.get('ref_prefix')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        if start_date:
            try:
                start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            except ValueError:
                return jsonify({'error': 'Неверный формат даты начала (YYYY-MM-DD)'}), 400
        
        if end_date:
            try:
                end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
            except ValueError:
                return jsonify({'error': 'Неверный формат даты окончания (YYYY-MM-DD)'}), 400
        
        if ref_prefix:
            # Статистика по конкретному префиксу
            daily_stats = Conversion.get_daily_stats_by_ref_prefix(ref_prefix, start_date, end_date)
            
            result = {}
            for date, form_id, ref, count in daily_stats:  # Обновляем распаковку, добавляя ref
                date_str = date.strftime('%Y-%m-%d')
                if date_str not in result:
                    result[date_str] = {}
                # Сохраняем count и ref в результате для каждого form_id
                result[date_str][form_id] = {'count': count, 'ref': ref}
            
            return jsonify({
                'ref_prefix': ref_prefix,
                'stats': result
            })
        else:
            # Общая статистика по всем префиксам
            from sqlalchemy import func
            
            query = db.session.query(
                Conversion.ref_prefix,
                func.count(Conversion.id).label('count')
            ).filter(Conversion.ref_prefix != None).group_by(Conversion.ref_prefix)
            
            if start_date:
                query = query.filter(Conversion.date >= start_date)
            if end_date:
                query = query.filter(Conversion.date <= end_date)
                
            stats = query.all()
            
            return jsonify({
                'stats': {prefix: count for prefix, count in stats if prefix}
            })
    except Exception as e:
        logger.error(f"Ошибка при получении статистики конверсий: {str(e)}")
        return jsonify({
            'error': 'Ошибка при получении статистики: ' + str(e),
            'stats': {}
        }), 500

@bp.route('/conversions', methods=['GET'])
@login_required
def conversions_page():
    """Страница с аналитикой конверсий"""
    try:
        # Получаем уникальные ref_prefix
        ref_prefixes = db.session.query(Conversion.ref_prefix).distinct().all()
        ref_prefixes = [r[0] for r in ref_prefixes if r[0]]
        
        return render_template('conversions.html', 
                              title='Конверсии', 
                              ref_prefixes=ref_prefixes)
    except Exception as e:
        logger.error(f"Ошибка при отображении страницы конверсий: {str(e)}")
        flash(f'Произошла ошибка при загрузке страницы конверсий', 'danger')
        return redirect(url_for('main.index'))

@bp.route('/conversions/list', methods=['GET'])
@login_required
def conversions_list():
    """Страница со списком всех конверсий и фильтрацией"""
    try:
        # Получаем параметры для фильтрации и пагинации
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        ref = request.args.get('ref', '')
        ref_prefix = request.args.get('ref_prefix', '')
        form_id = request.args.get('form_id', '')
        quid = request.args.get('quid', '')
        start_date = request.args.get('start_date', '')
        end_date = request.args.get('end_date', '')
        date_range = request.args.get('dateRange', '')
        
        # Строим запрос с фильтрами
        query = Conversion.query
        
        if ref:
            query = query.filter(Conversion.ref.like(f'%{ref}%'))
        
        if ref_prefix:
            query = query.filter(Conversion.ref_prefix == ref_prefix)
        
        if form_id:
            query = query.filter(Conversion.form_id == form_id)
        
        if quid:
            query = query.filter(Conversion.quid.like(f'%{quid}%'))
        
        if start_date:
            try:
                start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
                query = query.filter(Conversion.date >= start_date_obj)
            except ValueError:
                flash('Неверный формат даты начала', 'warning')
        
        if end_date:
            try:
                end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
                query = query.filter(Conversion.date <= end_date_obj)
            except ValueError:
                flash('Неверный формат даты окончания', 'warning')
        
        # Сортировка по времени (сначала новые)
        query = query.order_by(Conversion.timestamp.desc())
        
        # Получаем данные с пагинацией
        try:
            conversions = query.paginate(page=page, per_page=per_page)
        except Exception as e:
            # Обработка ошибки пагинации - возвращаем первую страницу
            logger.error(f"Ошибка при пагинации конверсий: {str(e)}")
            conversions = query.paginate(page=1, per_page=per_page)
            flash('Произошла ошибка при пагинации, показана первая страница', 'warning')
        
        # Обеспечиваем ненулевые значения для шаблонизатора
        if conversions.pages == 0:
            conversions.pages = 1
        
        # Получаем уникальные значения для фильтров
        unique_prefixes = db.session.query(Conversion.ref_prefix).distinct().all()
        unique_form_ids = db.session.query(Conversion.form_id).distinct().all()
        
        return render_template('conversions_list.html',
                              title='Список конверсий',
                              conversions=conversions,
                              ref=ref,
                              ref_prefix=ref_prefix,
                              form_id=form_id,
                              quid=quid,
                              start_date=start_date,
                              end_date=end_date,
                              date_range=date_range,  # Передаем выбранный период в шаблон
                              unique_prefixes=[p[0] for p in unique_prefixes if p[0]],
                              unique_form_ids=[f[0] for f in unique_form_ids if f[0]])
    except Exception as e:
        logger.error(f"Ошибка при отображении списка конверсий: {str(e)}")
        flash(f'Произошла ошибка при загрузке списка конверсий', 'danger')
        return redirect(url_for('main.conversions_page'))

@bp.route('/api/conversions/list', methods=['GET'])
@login_required
def api_conversions_list():
    """API для получения списка конверсий с пагинацией и фильтрацией"""
    # Получаем параметры
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    ref = request.args.get('ref', '')
    ref_prefix = request.args.get('ref_prefix', '')
    form_id = request.args.get('form_id', '')
    quid = request.args.get('quid', '')
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    
    # Строим запрос с фильтрами
    query = Conversion.query
    
    if ref:
        query = query.filter(Conversion.ref.like(f'%{ref}%'))
    
    if ref_prefix:
        query = query.filter(Conversion.ref_prefix == ref_prefix)
    
    if form_id:
        query = query.filter(Conversion.form_id == form_id)
    
    if quid:
        query = query.filter(Conversion.quid.like(f'%{quid}%'))
    
    if start_date:
        try:
            start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
            query = query.filter(Conversion.date >= start_date_obj)
        except ValueError:
            return jsonify({'error': 'Неверный формат даты начала'}), 400
    
    if end_date:
        try:
            end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
            query = query.filter(Conversion.date <= end_date_obj)
        except ValueError:
            return jsonify({'error': 'Неверный формат даты окончания'}), 400
    
    # Сортировка по времени (сначала новые)
    query = query.order_by(Conversion.timestamp.desc())
    
    # Получаем данные с пагинацией
    pagination = query.paginate(page=page, per_page=per_page)
    
    # Формируем результат
    result = {
        'items': [conversion.to_dict() for conversion in pagination.items],
        'total': pagination.total,
        'pages': pagination.pages,
        'page': pagination.page,
        'per_page': pagination.per_page
    }
    
    return jsonify(result)

@bp.route('/add-test-conversion', methods=['GET'])
@login_required
def add_test_conversion():
    """Добавляет тестовую конверсию и возвращает на страницу конверсий"""
    try:
        # Создаем тестовую запись о конверсии со случайными данными
        # Генерируем случайный ref с префиксом
        prefix = random.choice(['abc', 'xyz', 'test', 'promo'])
        suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=5))
        ref = f"{prefix}{suffix}"
        
        # Генерируем случайный form_id
        form_id = f"form_{random.randint(1000, 9999)}"
        
        # Генерируем случайный quid
        quid = f"quid_{random.randint(10000, 99999)}"
        
        # Создаем конверсию
        conversion = Conversion(
            ref=ref,
            form_id=form_id,
            quid=quid,
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string if request.user_agent else None
        )
        
        db.session.add(conversion)
        db.session.commit()
        
        flash(f'Тестовая конверсия успешно добавлена (ID: {conversion.id}, префикс: {conversion.ref_prefix})', 'success')
    except Exception as e:
        logger.error(f"Ошибка при добавлении тестовой конверсии: {str(e)}")
        flash('Произошла ошибка при добавлении тестовой конверсии', 'danger')
    
    # Возвращаемся на страницу списка конверсий
    return redirect(url_for('main.conversions_list'))

@bp.route('/api/conversion/test', methods=['GET'])
def api_test_conversion():
    """Добавляет тестовую конверсию для проверки функциональности API"""
    # Создаем тестовую запись о конверсии
    conversion = Conversion(
        ref='test123',
        form_id='test_form_id',
        quid='test_quid',
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string if request.user_agent else None
    )
    
    db.session.add(conversion)
    db.session.commit()
    
    return jsonify({
        'success': True, 
        'id': conversion.id,
        'message': 'Тестовая конверсия успешно добавлена'
    }), 201

@bp.route('/conversions/prefix/<string:ref_prefix>', methods=['GET'])
@login_required
def conversions_by_prefix(ref_prefix):
    """Страница с детальной статистикой конверсий по конкретному префиксу"""
    try:
        # Получаем параметры фильтрации
        start_date = request.args.get('start_date', '')
        end_date = request.args.get('end_date', '')
        
        start_date_obj = None
        end_date_obj = None
        
        if start_date:
            try:
                start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
            except ValueError:
                flash('Неверный формат даты начала', 'warning')
        
        if end_date:
            try:
                end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
            except ValueError:
                flash('Неверный формат даты окончания', 'warning')
        
        # Формируем базовый запрос для статистики
        from sqlalchemy import func
        
        # Получаем суммарную статистику по form_id
        summary_query = db.session.query(
            Conversion.form_id,
            func.count(Conversion.id).label('count')
        ).filter(Conversion.ref_prefix == ref_prefix)
        
        if start_date_obj:
            summary_query = summary_query.filter(Conversion.date >= start_date_obj)
        if end_date_obj:
            summary_query = summary_query.filter(Conversion.date <= end_date_obj)
            
        summary_data = summary_query.group_by(Conversion.form_id).order_by(func.count(Conversion.id).desc()).all()
        
        # Общее количество конверсий
        total_conversions = sum(count for _, count in summary_data)
        
        # Подготовка данных для графиков
        form_ids = [form_id for form_id, _ in summary_data]
        counts = [count for _, count in summary_data]
        
        # Получаем статистику по дням
        daily_query = db.session.query(
            Conversion.date,
            func.count(Conversion.id).label('count')
        ).filter(Conversion.ref_prefix == ref_prefix)
        
        if start_date_obj:
            daily_query = daily_query.filter(Conversion.date >= start_date_obj)
        if end_date_obj:
            daily_query = daily_query.filter(Conversion.date <= end_date_obj)
            
        daily_data = daily_query.group_by(Conversion.date).order_by(Conversion.date).all()
        
        # Подготовка данных для графика по дням
        dates = [date.strftime('%d.%m.%Y') for date, _ in daily_data]
        daily_counts = [count for _, count in daily_data]
        
        return render_template('conversions_by_prefix.html',
                            title=f'Конверсии по префиксу {ref_prefix}',
                            ref_prefix=ref_prefix,
                            summary_data=summary_data,
                            total_conversions=total_conversions,
                            form_ids=form_ids,
                            counts=counts,
                            daily_data=daily_data,
                            dates=dates,
                            daily_counts=daily_counts,
                            start_date=start_date,
                            end_date=end_date)
    except Exception as e:
        logger.error(f"Ошибка при отображении статистики по префиксу {ref_prefix}: {str(e)}")
        flash(f'Произошла ошибка при загрузке статистики: {str(e)}', 'danger')
        return redirect(url_for('main.conversions_list', ref_prefix=ref_prefix))