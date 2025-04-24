import os
import sys
import logging
from datetime import datetime, timedelta
from sqlalchemy import and_, func, or_
from app.extensions import db
from app.models.setup import Setup, CampaignSetup
from app.models.user import User
from app.services.fb_api_client import FacebookAdClient
from app.models.facebook_token import FacebookToken
from app.models.conversion import Conversion
from app.services.facebook_api import FacebookAPI

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def calculate_date_range_for_period(check_period):
    """
    Рассчитывает диапазон дат на основе периода проверки
    
    Args:
        check_period (str): Период проверки ('today', 'last2days', 'last3days', 'last7days', 'alltime')
        
    Returns:
        dict: Словарь с ключами 'since' и 'until' в формате YYYY-MM-DD
    """
    today = datetime.now().date()
    until_date = today.strftime('%Y-%m-%d')
    
    # Если check_period None, устанавливаем по умолчанию 'today'
    if check_period is None:
        check_period = 'today'
        
    if check_period == 'today':
        since_date = today.strftime('%Y-%m-%d')
    elif check_period == 'last2days':
        since_date = (today - timedelta(days=1)).strftime('%Y-%m-%d')
    elif check_period == 'last3days':
        since_date = (today - timedelta(days=2)).strftime('%Y-%m-%d')
    elif check_period == 'last7days':
        since_date = (today - timedelta(days=6)).strftime('%Y-%m-%d')
    elif check_period == 'alltime':
        # Используем дату, достаточно далеко в прошлом
        since_date = (today - timedelta(days=365)).strftime('%Y-%m-%d')
    else:
        # Если неизвестный период, используем сегодня
        since_date = today.strftime('%Y-%m-%d')
        logger.warning(f"Неизвестный период проверки: {check_period}, используется 'today'")
    
    return {'since': since_date, 'until': until_date}

def check_campaign_thresholds(campaign_id, setup_id, check_period='today'):
    """
    Проверяет объявления кампании и отключает те, что не соответствуют требованиям
    
    Args:
        campaign_id (str): ID кампании Facebook
        setup_id (int): ID настроек проверки
        check_period (str, optional): Период за который проверять статистику. 
                                    Доступны: 'today', 'yesterday', 'last2days', 'last3days', 'last7days', 'alltime'.
    
    Returns:
        dict: Результаты проверки
    """
    try:
        # Настраиваем логгер
        logger = logging.getLogger('app')
        logger.info(f"Запуск проверки кампании {campaign_id}, setup_id={setup_id}, period={check_period}")

        # Получаем настройки
        from app.models.setup import Setup
        setup = Setup.query.get(setup_id)
        if not setup:
            logger.error(f"Настройки с ID {setup_id} не найдены")
            return {'error': f'Настройки с ID {setup_id} не найдены'}
        
        logger.info(f"Найдены настройки: {setup.name}")
        
        # Получаем даты для проверки
        date_range = calculate_date_range_for_period(check_period)
        date_from, date_to = date_range['since'], date_range['until']
        logger.info(f"Период проверки: с {date_from} по {date_to}")
        
        # Получаем пороги для проверки
        thresholds = setup.get_thresholds_as_list() if setup.thresholds else []
        logger.info(f"Получены пороги: {thresholds}")
        
        if not thresholds:
            logger.error("Не заданы пороги для проверки")
            return {'error': 'Не заданы пороги для проверки'}
        
        # Используем первый порог из настроек
        threshold = thresholds[0]
        setup_spend = threshold.get('spend', 0)
        setup_conversions = threshold.get('conversions', 0)
        
        logger.info(f"Используем порог: расход >= {setup_spend}, конверсии < {setup_conversions}")
        
        # Подключаемся к Facebook API
        from app.models.user import User
        from app.models.setup import CampaignSetup
        
        # Получаем настройки кампании
        campaign_setup = CampaignSetup.query.filter_by(campaign_id=campaign_id).first()
        if not campaign_setup:
            logger.error(f"Настройки для кампании {campaign_id} не найдены")
            return {'error': f'Настройки для кампании {campaign_id} не найдены'}
        
        # Получаем пользователя
        user = User.query.get(campaign_setup.user_id)
        if not user:
            logger.error(f"Пользователь не найден для campaign_setup.user_id={campaign_setup.user_id}")
            return {'error': f'Пользователь не найден'}
        
        logger.info(f"Проверка кампании для пользователя {user.username} (ID: {user.id})")
        
        # Создаем клиент Facebook API с помощью вспомогательной функции
        fb_client = create_fb_client_for_user(user)
        
        # Проверка подключения к API
        if not fb_client:
            logger.error("Не удалось создать клиент Facebook API")
            return {'error': 'Ошибка подключения к Facebook API'}
        
        # Получаем информацию о кампании
        campaign = fb_client.get_campaign(campaign_id)
        if not campaign:
            logger.error(f"Не удалось получить информацию о кампании {campaign_id}")
            return {'error': 'Не удалось получить информацию о кампании'}
        
        # Получаем объявления для кампании
        logger.info(f"Запрашиваем объявления для кампании {campaign_id}")
        ads = fb_client.get_ads_in_campaign(campaign_id)
        
        if not ads:
            logger.warning(f"Объявления не найдены для кампании {campaign_id}")
            return {'error': 'Объявления не найдены', 'campaign_id': campaign_id}
        
        logger.info(f"Получено {len(ads)} объявлений")
        
        # Получаем конверсии для объявлений
        insights_results = []
        passed_ads = []
        failed_ads = []
        
        total_ads = len(ads)
        ads_disabled = 0
        
        logger.info(f"Начинаем проверку {total_ads} объявлений")
        
        # Проверяем каждое объявление по очереди
        for index, ad in enumerate(ads):
            ad_id = ad.get('id')
            ad_name = ad.get('name')
            ad_status = ad.get('status')
            
            logger.info(f"Проверка объявления {index+1}/{total_ads}: {ad_name} (ID: {ad_id}, статус: {ad_status})")
            
            # Получаем данные о конверсиях для объявления
            logger.info(f"Запрашиваем статистику для объявления {ad_id} с {date_from} по {date_to}")
            insights = fb_client.get_ad_insights(
                ad_id=ad_id,
                date_from=date_from,
                date_to=date_to
            )
            
            # Если данных нет, объявление не имеет статистики
            if not insights:
                logger.info(f"Нет данных о статистике для объявления {ad_id}")
                result = {
                    'ad_id': ad_id,
                    'ad_name': ad_name,
                    'ref': None,
                    'spend': 0,
                    'conversions': 0,
                    'status': ad_status,
                    'passed': True,
                    'reason': 'Нет данных о расходах или конверсиях'
                }
                insights_results.append(result)
                passed_ads.append(result)
                continue
            
            # Извлекаем данные о расходах и конверсиях
            spend = float(insights.get('spend', 0))
            conversions = int(insights.get('conversions', 0))
            ref = insights.get('ref')
            
            logger.info(f"Объявление {ad_id}: расход=${spend:.2f}, конверсии={conversions}")
            
            # Проверяем, соответствует ли объявление требованиям
            passed = True
            reason = None
            
            # Не отключаем объявления, которые уже отключены или в архиве
            if ad_status.lower() not in ['active', 'paused']:
                logger.info(f"Объявление {ad_id} уже имеет статус {ad_status}, пропускаем")
                result = {
                    'ad_id': ad_id,
                    'ad_name': ad_name,
                    'ref': ref,
                    'spend': spend,
                    'conversions': conversions,
                    'status': ad_status,
                    'passed': True,
                    'reason': f'Объявление уже имеет статус {ad_status}'
                }
                insights_results.append(result)
                passed_ads.append(result)
                continue
            
            # Проверяем условия отключения:
            # Если расходы превысили порог И конверсий меньше порога
            if spend >= setup_spend and conversions < setup_conversions:
                passed = False
                reason = f'Расход ${spend:.2f} >= ${setup_spend:.2f} и конверсий {conversions} < {setup_conversions}'
                logger.warning(f"Объявление {ad_id} не соответствует требованиям: {reason}")
                
                # Отключаем объявление только если оно активно
                if ad_status.lower() == 'active':
                    logger.info(f"Отключаем объявление {ad_id}")
                    disable_result = fb_client.disable_ad(ad_id)
                    
                    # Функция disable_ad возвращает True/False, а не словарь
                    if disable_result is True:
                        logger.info(f"Объявление {ad_id} успешно отключено")
                        ads_disabled += 1
                        # Обновляем статус в результате
                        ad_status = 'PAUSED'
                    else:
                        logger.error(f"Ошибка при отключении объявления {ad_id}")
                
            # Формируем результат для объявления
            result = {
                'ad_id': ad_id,
                'ad_name': ad_name,
                'ref': ref,
                'spend': spend,
                'conversions': conversions,
                'status': ad_status,
                'passed': passed,
                'reason': reason
            }
            
            # Добавляем результат в общий список и в соответствующую категорию
            insights_results.append(result)
            if passed:
                passed_ads.append(result)
            else:
                failed_ads.append(result)
        
        # Формируем итоговый результат
        result = {
            'campaign_id': campaign_id,
            'setup_id': setup_id,
            'setup_spend': setup_spend,
            'setup_conversions': setup_conversions,
            'check_period': check_period,
            'date_from': date_from,
            'date_to': date_to,
            'ads_checked': len(ads),
            'ads_disabled': ads_disabled,
            'ads_results': insights_results,
            'passed_ads': passed_ads,
            'failed_ads': failed_ads
        }
        
        logger.info(f"Проверка завершена. Проверено {len(ads)} объявлений, отключено {ads_disabled}")
        
        return result
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        
        # Логируем ошибку
        app_logger = logging.getLogger('app')
        app_logger.error(f"Ошибка при проверке кампании {campaign_id}: {str(e)}")
        app_logger.error(error_trace)
        
        return {'error': str(e)}

def create_fb_client_for_user(user):
    """
    Создаёт клиент Facebook API для пользователя
    
    Args:
        user (User): Объект пользователя
    
    Returns:
        FacebookAdClient: Инициализированный клиент API
    """
    try:
        from app.services.facebook_api import FacebookAPI
        return FacebookAPI(user)
    except ImportError:
        from app.services.fb_api_client import FacebookAdClient
        
        # Получаем действующий токен
        active_token = None
        if user.active_token_id:
            from app.models.facebook_token import FacebookToken
            active_token = FacebookToken.query.get(user.active_token_id)
        
        # Если есть активный токен, используем его
        if active_token and active_token.status == 'valid':
            fb_client = FacebookAdClient(token_obj=active_token)
        else:
            # Иначе используем прямые учетные данные пользователя
            fb_client = FacebookAdClient(
                access_token=user.fb_access_token,
                app_id=user.fb_app_id,
                app_secret=user.fb_app_secret,
                ad_account_id=user.fb_account_id
            )
        
        return fb_client 

def schedule_campaign_checks():
    """
    Запускает проверку всех активных кампаний с учетом настроенных интервалов.
    Эта функция должна быть вызвана периодически (например, раз в минуту).
    """
    try:
        logger = logging.getLogger('app')
        logger.info("Запуск планового обхода кампаний для проверки")
        
        # Импортируем модели
        from app.models.setup import Setup, CampaignSetup
        from datetime import datetime, timedelta
        
        # Получаем все активные кампании, привязанные к активным сетапам
        campaign_setups = (
            CampaignSetup.query
            .join(Setup, CampaignSetup.setup_id == Setup.id)
            .filter(CampaignSetup.is_active == True)
            .filter(Setup.is_active == True)
            .all()
        )
        
        logger.info(f"Найдено {len(campaign_setups)} активных кампаний для проверки")
        
        now = datetime.utcnow()
        campaigns_checked = 0
        
        # Проверяем каждую кампанию
        for cs in campaign_setups:
            # Получаем настройки
            setup = Setup.query.get(cs.setup_id)
            if not setup:
                logger.warning(f"Не найдены настройки для кампании {cs.campaign_id}")
                continue
                
            # Проверяем, прошло ли достаточно времени с момента последней проверки
            interval_minutes = setup.check_interval or 30  # По умолчанию 30 минут
            
            if cs.last_checked:
                next_check_time = cs.last_checked + timedelta(minutes=interval_minutes)
                if now < next_check_time:
                    # Еще не время для проверки
                    continue
            
            # Запускаем проверку кампании
            logger.info(f"Запуск проверки кампании {cs.campaign_id} с интервалом {interval_minutes} минут")
            
            try:
                # Выполняем проверку
                check_period = setup.check_period or 'today'
                result = check_campaign_thresholds(cs.campaign_id, cs.setup_id, check_period)
                
                # Обновляем время последней проверки
                cs.last_checked = now
                
                # Проверяем результат
                if 'error' in result:
                    logger.error(f"Ошибка при проверке кампании {cs.campaign_id}: {result['error']}")
                else:
                    logger.info(f"Проверка кампании {cs.campaign_id} завершена: проверено {result.get('ads_checked', 0)} объявлений, отключено {result.get('ads_disabled', 0)}")
                    campaigns_checked += 1
                
            except Exception as check_error:
                logger.error(f"Ошибка при проверке кампании {cs.campaign_id}: {str(check_error)}")
                # Обновляем время последней проверки даже при ошибке, чтобы избежать повторных ошибок
                cs.last_checked = now
                
        # Сохраняем изменения в базе данных после всех проверок
        from app.extensions import db
        db.session.commit()
        
        logger.info(f"Завершено {campaigns_checked} проверок кампаний")
        
    except Exception as e:
        logger = logging.getLogger('app')
        logger.error(f"Ошибка при выполнении schedule_campaign_checks: {str(e)}")
        
        import traceback
        logger.error(traceback.format_exc()) 