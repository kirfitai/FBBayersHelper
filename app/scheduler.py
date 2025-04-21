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
    Проверяет объявления в кампании на соответствие пороговым значениям и отключает те,
    которые превышают установленные пороги.
    
    Args:
        campaign_id (str): ID кампании в Facebook
        setup_id (int): ID настройки с пороговыми значениями
        check_period (str): Период проверки ('today', 'last2days', 'last3days', 'last7days', 'alltime')
        
    Returns:
        dict: Словарь с результатами проверки, содержащий:
            - campaign_id: ID кампании
            - setup_id: ID настройки
            - setup_spend: Пороговое значение расхода
            - setup_conversions: Пороговое значение конверсий
            - check_period: Период проверки
            - date_from: Начальная дата периода
            - date_to: Конечная дата периода
            - ads_checked: Количество проверенных объявлений
            - ads_disabled: Количество отключенных объявлений
            - ads_results: Список результатов проверки для каждого объявления
            - error: Информация об ошибке (если есть)
    """
    # Импортируем модели и API
    from app.models.setup import Setup, ThresholdEntry
    from app.services.facebook_api import FacebookAPI
    from app.models.conversion import Conversion
    from sqlalchemy import func
    from datetime import datetime, timedelta
    import logging
    
    logger = logging.getLogger(__name__)
    
    # Получаем настройку с пороговыми значениями
    setup = Setup.query.get(setup_id)
    if not setup:
        error_msg = f"Настройка с ID {setup_id} не найдена"
        logger.error(error_msg)
        return {
            'campaign_id': campaign_id,
            'error': error_msg,
            'ads_checked': 0,
            'ads_disabled': 0,
            'ads_results': []
        }
    
    # Получаем пороговые значения из первого порога
    threshold_values = setup.get_thresholds_as_list()
    if not threshold_values:
        error_msg = f"Для настройки с ID {setup_id} не заданы пороговые значения"
        logger.error(error_msg)
        return {
            'campaign_id': campaign_id,
            'error': error_msg,
            'ads_checked': 0,
            'ads_disabled': 0,
            'ads_results': []
        }
    
    # Берем первый порог из списка
    first_threshold = threshold_values[0]
    threshold_spend = first_threshold['spend']
    threshold_conversions = first_threshold['conversions']
    
    # Инициализируем результаты проверки
    results = {
        'campaign_id': campaign_id,
        'setup_id': setup.id,
        'setup_spend': threshold_spend,
        'setup_conversions': threshold_conversions,
        'check_period': check_period,
        'ads_checked': 0,
        'ads_disabled': 0,
        'ads_results': []
    }
    
    try:
        # Рассчитываем диапазон дат для указанного периода
        date_range = calculate_date_range_for_period(check_period)
        results['date_from'] = date_range['since']
        results['date_to'] = date_range['until']
        
        # Получаем активный токен из базы данных
        token = FacebookToken.query.filter_by(status='valid').first()
        if not token:
            error_msg = "Не найден активный токен Facebook API"
            logger.error(error_msg)
            results['error'] = error_msg
            return results
            
        # Создаем экземпляр API Facebook
        fb_api = FacebookAPI(token.access_token)
        
        # ЭТАП 1: Получаем объявления в кампании
        logger.info(f"ЭТАП 1: Получение списка объявлений для кампании {campaign_id}")
        ads_in_campaign = fb_api.get_ads_in_campaign(campaign_id)
        if not ads_in_campaign:
            results['error'] = f"Не найдены объявления в кампании {campaign_id}"
            return results
        
        # Фильтруем только активные объявления
        active_ads = []
        for ad in ads_in_campaign:
            # Для словарей
            if isinstance(ad, dict):
                if ad.get('effective_status') == 'ACTIVE':
                    active_ads.append(ad)
            # Для объектов
            elif hasattr(ad, 'effective_status') and ad.effective_status == 'ACTIVE':
                active_ads.append(ad)
            elif hasattr(ad, 'status') and ad.status == 'ACTIVE':
                active_ads.append(ad)
        
        logger.info(f"Найдено {len(active_ads)} активных объявлений из {len(ads_in_campaign)}")
        
        # ЭТАП 2: Получаем конверсии и формируем список для работы
        logger.info(f"ЭТАП 2: Получение данных о конверсиях и формирование рабочего списка")
        ads_data = []
        for ad in active_ads:
            # Получаем данные об объявлении в зависимости от формата
            if isinstance(ad, dict):
                ad_id = ad.get('id')
                ad_name = ad.get('name', 'Без имени')
                ad_status = ad.get('effective_status', 'UNKNOWN')
            else:
                ad_id = ad.id if hasattr(ad, 'id') else None
                ad_name = ad.name if hasattr(ad, 'name') else 'Без имени'
                ad_status = ad.effective_status if hasattr(ad, 'effective_status') else (ad.status if hasattr(ad, 'status') else 'UNKNOWN')
            
            # Парсим REF из имени объявления
            ref = None
            if ad_name and '_ref_' in ad_name:
                ref_parts = ad_name.split('_ref_')
                if len(ref_parts) > 1:
                    ref = ref_parts[1].split('_')[0]
            
            # Получаем количество конверсий из нашей базы
            conversions_count = 0
            if ref:
                # Создаем фильтры для запроса конверсий по REF и дате
                filters = [
                    Conversion.ref == ref
                ]
                
                # Добавляем фильтры по датам если не выбран 'alltime'
                if check_period != 'alltime':
                    since_date = datetime.strptime(date_range['since'], '%Y-%m-%d').date()
                    until_date = datetime.strptime(date_range['until'], '%Y-%m-%d').date()
                    
                    filters.append(func.date(Conversion.timestamp) >= since_date)
                    filters.append(func.date(Conversion.timestamp) <= until_date)
                
                # Выполняем запрос с учетом всех фильтров
                conversions_count = Conversion.query.filter(*filters).count()
            
            # Добавляем данные в рабочий список
            ads_data.append({
                'ad_id': ad_id,
                'ad_name': ad_name,
                'ref': ref,
                'conversions': conversions_count,
                'status': ad_status,
                'spend': None,  # Будет заполнено позже
                'passed': None  # Будет заполнено позже
            })
        
        # ЭТАП 3: Сортируем объявления по конверсиям (от большего к меньшему)
        logger.info(f"ЭТАП 3: Сортировка объявлений по количеству конверсий")
        sorted_ads = sorted(ads_data, key=lambda x: x['conversions'], reverse=True)
        
        # ЭТАП 4: Получаем расход для каждого объявления и проверяем условия
        logger.info(f"ЭТАП 4: Получение данных о расходах и проверка условий")
        for ad_data in sorted_ads:
            ad_id = ad_data['ad_id']
            
            # Получаем статистику для объявления за указанный период
            insights = fb_api.get_ad_insights(ad_id, time_range=date_range)
            if not insights:
                logger.warning(f"Нет данных по расходам для объявления {ad_id}")
                ad_data['spend'] = 0
                continue
                
            # Получаем расход из инсайтов
            spend = float(insights.get('spend', 0))
            ad_data['spend'] = spend
            
            # Проверяем соответствие пороговым значениям
            threshold_exceeded = False
            disable_reason = None
            
            # Если расход выше порогового значения И количество конверсий меньше порогового значения
            if spend >= threshold_spend and ad_data['conversions'] < threshold_conversions:
                threshold_exceeded = True
                disable_reason = f"Расход ${spend:.2f} >= ${threshold_spend:.2f} и конверсий {ad_data['conversions']} < {threshold_conversions}"
                
                # Отключаем объявление если порог превышен
                try:
                    fb_api.disable_ad(ad_id)
                    logger.info(f"Объявление {ad_id} отключено: {disable_reason}")
                    results['ads_disabled'] += 1
                except Exception as e:
                    logger.error(f"Ошибка при отключении объявления {ad_id}: {str(e)}")
                    disable_reason += f" (Ошибка отключения: {str(e)})"
            
            # Обновляем статус проверки
            ad_data['passed'] = not threshold_exceeded
            ad_data['reason'] = disable_reason
            
            # Добавляем результат проверки в итоговый список
            ad_result = {
                'ad_id': ad_data['ad_id'],
                'ad_name': ad_data['ad_name'],
                'ref': ad_data['ref'],
                'spend': ad_data['spend'],
                'conversions': ad_data['conversions'],
                'status': ad_data['status'],
                'passed': ad_data['passed'],
                'reason': ad_data['reason']
            }
            
            results['ads_results'].append(ad_result)
            results['ads_checked'] += 1
        
        return results
        
    except Exception as e:
        error_msg = f"Ошибка при проверке кампании {campaign_id}: {str(e)}"
        logger.error(error_msg)
        results['error'] = error_msg
        return results 