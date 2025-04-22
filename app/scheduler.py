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

def check_campaign_thresholds(campaign_id, setup_id, check_period='today', progress_callback=None):
    """Проверяет объявления кампании и отключает те, что не соответствуют требованиям
    
    Args:
        campaign_id (str): ID кампании Facebook
        setup_id (int): ID настроек проверки
        check_period (str, optional): Период за который проверять статистику. 
                                    Доступны: 'today', 'last2days', 'last3days', 'last7days', 'alltime'.
        progress_callback (callable, optional): Функция обратного вызова для отображения прогресса.
                                              Принимает параметры: (этап, текущий, всего, сообщение).
    
    Returns:
        dict: Результаты проверки
    """
    try:
        # Настраиваем логгер
        logger = logging.getLogger('app')
        logger.info(f"Запуск проверки кампании {campaign_id}, setup_id={setup_id}, period={check_period}")

        # Сообщаем о начале проверки
        if progress_callback:
            progress_callback('setup', 0, 1, 'Получение настроек кампании...')
            
        # Получаем настройки
        from app.models.setup import Setup
        setup = Setup.query.get(setup_id)
        if not setup:
            logger.error(f"Настройки с ID {setup_id} не найдены")
            return {'error': f'Настройки с ID {setup_id} не найдены'}
        
        logger.info(f"Найдены настройки: {setup.name}")
        
        # Получаем даты для проверки
        date_from, date_to = calculate_date_range_for_period(check_period)
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
        if progress_callback:
            progress_callback('api', 0, 1, 'Подключение к Facebook API...')
            
        from app.services.fb_api_client import FacebookAdClient
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
        
        # Создаем клиент Facebook API
        fb_client = FacebookAdClient(
            access_token=user.fb_access_token,
            ad_account_id=user.fb_ad_account_id
        )
        
        # Получаем объявления для кампании
        if progress_callback:
            progress_callback('ads', 0, 1, 'Получение списка объявлений...')
            
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
        
        if progress_callback:
            progress_callback('insights', 0, total_ads, f'Анализ объявлений (0/{total_ads})...')
        
        logger.info(f"Начинаем проверку {total_ads} объявлений")
        
        # Проверяем каждое объявление по очереди
        for index, ad in enumerate(ads):
            ad_id = ad.get('id')
            ad_name = ad.get('name')
            ad_status = ad.get('status')
            
            logger.info(f"Проверка объявления {index+1}/{total_ads}: {ad_name} (ID: {ad_id}, статус: {ad_status})")
            
            if progress_callback:
                progress_callback('insights', index, total_ads, f'Анализ объявления {index+1}/{total_ads}: {ad_name}')
            
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
                    if progress_callback:
                        progress_callback(
                            'disable', 
                            index, 
                            total_ads, 
                            f'Отключение объявления {ad_name} (ID: {ad_id})'
                        )
                        
                    # Отключаем объявление
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
        
        # Сообщаем о завершении
        if progress_callback:
            progress_callback('complete', total_ads, total_ads, 'Проверка завершена')
        
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
        
        # Сообщаем об ошибке через колбэк
        if progress_callback:
            progress_callback('error', 0, 1, f'Ошибка: {str(e)}')
            
        return {'error': str(e)} 