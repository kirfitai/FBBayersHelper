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
        
        # Создаем экземпляр API Facebook
        fb_api = FacebookAPI()
        
        # Получаем объявления в кампании
        ads_in_campaign = fb_api.get_ads_in_campaign(campaign_id)
        if not ads_in_campaign:
            results['error'] = f"Не найдены объявления в кампании {campaign_id}"
            return results
            
        # Для каждого объявления в кампании
        for ad in ads_in_campaign:
            ad_id = ad.get('id')
            ad_name = ad.get('name', 'Без имени')
            ad_status = ad.get('status', 'UNKNOWN')
            
            # Получаем только активные объявления
            if ad_status != 'ACTIVE':
                continue
                
            # Получаем статистику для объявления за указанный период
            insights = fb_api.get_ad_insights(ad_id, date_range)
            if not insights:
                logger.warning(f"Нет данных по расходам для объявления {ad_id}")
                continue
                
            # Парсим REF из имени объявления
            ref = None
            if '_ref_' in ad_name:
                ref_parts = ad_name.split('_ref_')
                if len(ref_parts) > 1:
                    ref = ref_parts[1].split('_')[0]
            
            # Получаем расход из инсайтов
            spend = float(insights.get('spend', 0))
            
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
            
            # Проверяем соответствие пороговым значениям
            threshold_exceeded = False
            disable_reason = None
            
            # Если расход выше порогового значения И количество конверсий меньше порогового значения
            if spend >= threshold_spend and conversions_count < threshold_conversions:
                threshold_exceeded = True
                disable_reason = f"Расход ${spend:.2f} >= ${threshold_spend:.2f} и конверсий {conversions_count} < {threshold_conversions}"
                
                # Отключаем объявление если порог превышен
                try:
                    fb_api.disable_ad(ad_id)
                    logger.info(f"Объявление {ad_id} отключено: {disable_reason}")
                    results['ads_disabled'] += 1
                except Exception as e:
                    logger.error(f"Ошибка при отключении объявления {ad_id}: {str(e)}")
                    disable_reason += f" (Ошибка отключения: {str(e)})"
            
            # Добавляем результат проверки в список
            ad_result = {
                'ad_id': ad_id,
                'ad_name': ad_name,
                'ref': ref,
                'spend': spend,
                'conversions': conversions_count,
                'status': ad_status,
                'passed': not threshold_exceeded,
                'reason': disable_reason
            }
            
            results['ads_results'].append(ad_result)
            results['ads_checked'] += 1
        
        return results
        
    except Exception as e:
        error_msg = f"Ошибка при проверке кампании {campaign_id}: {str(e)}"
        logger.error(error_msg)
        results['error'] = error_msg
        return results 