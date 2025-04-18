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
        tuple: (since_date, until_date) в формате YYYY-MM-DD
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
    
    return since_date, until_date

def check_campaign_thresholds(campaign_id=None, check_period=None):
    """
    Проверяет пороги кампаний и отключает объявления в кампаниях, если пороги превышены.
    
    Args:
        campaign_id (str, optional): ID кампании для проверки. По умолчанию проверяются все кампании.
        check_period (str, optional): Период проверки ('today', 'last2days', 'last3days', 'last7days', 'alltime').
            По умолчанию используется период из настройки кампании.
    
    Returns:
        bool: True если все проверки выполнены успешно, иначе False
    """
    try:
        # Если campaign_id указан, проверяем только эту кампанию
        if campaign_id:
            campaign_setups = CampaignSetup.query.filter(
                CampaignSetup.campaign_id == campaign_id,
                CampaignSetup.is_active == True
            ).all()
            if not campaign_setups:
                logger.warning(f"Кампания {campaign_id} не найдена или не активна")
                return False
        else:
            # Получаем все активные настройки кампаний
            campaign_setups = CampaignSetup.query.filter(
                CampaignSetup.is_active == True
            ).all()
            
        if not campaign_setups:
            logger.info("Нет активных настроек кампаний для проверки")
            return True
            
        # Обработка каждой кампании
        for campaign_setup in campaign_setups:
            try:
                setup = Setup.query.get(campaign_setup.setup_id)
                if not setup or not setup.is_active:
                    logger.info(f"Setup {campaign_setup.setup_id} не активен или не существует")
                    continue
                
                # Используем переданный период проверки или берем из настройки
                period = check_period if check_period is not None else setup.check_period
                # Если период всё еще None, используем 'today'
                if period is None:
                    period = 'today'
                    
                since_date, until_date = calculate_date_range_for_period(period)
                
                # Получаем пороги для настройки
                thresholds = setup.get_thresholds_as_list()
                if not thresholds:
                    logger.info(f"Нет порогов для настройки {setup.id}")
                    continue
                
                # Получаем пользователя
                user = User.query.get(campaign_setup.user_id)
                if not user:
                    logger.error(f"Пользователь {campaign_setup.user_id} не найден")
                    continue
                
                # Получаем активный токен пользователя
                if user.active_token_id:
                    token = FacebookToken.query.get(user.active_token_id)
                else:
                    token = FacebookToken.query.filter_by(user_id=user.id, is_active=True).first()
                
                if not token:
                    logger.error(f"Активный токен Facebook не найден для пользователя {user.id}")
                    continue
                
                # Инициализируем Facebook API
                fb_api = FacebookAdClient(
                    access_token=token.access_token,
                    app_id=token.app_id,
                    app_secret=token.app_secret,
                    ad_account_id=token.account_id
                )
                
                # Получаем статистику кампании
                campaign_stats = fb_api.get_campaign_stats(
                    campaign_id=campaign_setup.campaign_id,
                    fields=['campaign_name', 'spend'],
                    date_preset=None,
                    time_range={'since': since_date, 'until': until_date}
                )
                
                if not campaign_stats:
                    logger.warning(f"Не удалось получить статистику для кампании {campaign_setup.campaign_id}")
                    continue
                
                # Получаем расходы
                spend = float(campaign_stats.get('spend', 0))
                
                # Получаем количество конверсий
                conversion_count = 0  # Здесь нужно добавить логику получения конверсий
                
                # Получаем конверсии за указанный период
                try:
                    # Берем префиксы из настройки
                    ref_prefixes = setup.ref_prefixes.split(',') if setup.ref_prefixes else []
                    ref_prefixes = [prefix.strip() for prefix in ref_prefixes if prefix.strip()]
                    
                    # Создаем фильтр для поиска конверсий по префиксам
                    conversion_filters = []
                    for prefix in ref_prefixes:
                        conversion_filters.append(Conversion.ref_prefix == prefix)
                    
                    # Если есть префиксы, получаем конверсии
                    if conversion_filters:
                        # Преобразуем строковые даты в объекты datetime
                        since_datetime = datetime.strptime(since_date, '%Y-%m-%d').replace(hour=0, minute=0, second=0)
                        until_datetime = datetime.strptime(until_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
                        
                        # Получаем количество конверсий
                        conversion_count = Conversion.query.filter(
                            and_(
                                or_(*conversion_filters),
                                Conversion.timestamp >= since_datetime,
                                Conversion.timestamp <= until_datetime
                            )
                        ).count()
                        
                        logger.info(f"Найдено {conversion_count} конверсий для префиксов {ref_prefixes} за период {since_date} - {until_date}")
                except Exception as e:
                    logger.error(f"Ошибка при получении конверсий: {str(e)}")
                
                # Обновляем время последней проверки
                campaign_setup.last_checked = datetime.utcnow()
                db.session.commit()
                
                # Проверяем, превышены ли пороги
                should_disable_ads = False
                
                # Сортируем пороги по расходам (по возрастанию)
                sorted_thresholds = sorted(thresholds, key=lambda x: x['spend'])
                
                # Находим подходящий порог
                applicable_threshold = None
                for threshold in sorted_thresholds:
                    if spend >= threshold['spend']:
                        applicable_threshold = threshold
                    else:
                        break
                
                # Если нашли подходящий порог, проверяем условие
                if applicable_threshold:
                    required_conversions = applicable_threshold['conversions']
                    if conversion_count < required_conversions:
                        should_disable_ads = True
                        logger.info(
                            f"Порог превышен для кампании {campaign_setup.campaign_id}: "
                            f"расходы ${spend:.2f}, конверсии {conversion_count}, "
                            f"требуется минимум {required_conversions} конверсий при расходах ${applicable_threshold['spend']}"
                        )
                
                # Если нужно отключить объявления
                if should_disable_ads:
                    try:
                        # Получаем все объявления в кампании
                        ads = fb_api.get_ads_in_campaign(campaign_setup.campaign_id)
                        
                        if ads:
                            logger.info(f"Найдено {len(ads)} объявлений в кампании {campaign_setup.campaign_id} для отключения")
                            
                            successful_disables = 0
                            failed_disables = 0
                            
                            # Отключаем каждое объявление
                            for ad in ads:
                                if hasattr(ad, 'id') and ad.id:
                                    ad_id = ad.id
                                    ad_name = getattr(ad, 'name', 'Неизвестное имя')
                                    ad_status = getattr(ad, 'status', 'UNKNOWN')
                                    
                                    # Отключаем только активные объявления
                                    if ad_status != 'PAUSED':
                                        status = fb_api.disable_ad(ad_id)
                                        if status:
                                            successful_disables += 1
                                            logger.info(f"Объявление {ad_id} ({ad_name}) успешно отключено")
                                        else:
                                            failed_disables += 1
                                            logger.error(f"Ошибка при отключении объявления {ad_id} ({ad_name})")
                                    else:
                                        logger.info(f"Объявление {ad_id} ({ad_name}) уже отключено, пропускаем")
                                        
                            # Выводим итоговую статистику
                            logger.info(
                                f"Итого по кампании {campaign_setup.campaign_id}: "
                                f"успешно отключено {successful_disables} объявлений, "
                                f"не удалось отключить {failed_disables} объявлений"
                            )
                            
                            # Записываем статистику в файл для последующего анализа
                            import json
                            from pathlib import Path
                            try:
                                log_dir = Path('/data/disable_logs')
                                log_dir.mkdir(exist_ok=True)
                                report = {
                                    'timestamp': datetime.utcnow().isoformat(),
                                    'campaign_id': campaign_setup.campaign_id,
                                    'campaign_name': campaign_stats.get('campaign_name', 'Н/Д'),
                                    'spend': spend,
                                    'conversions': conversion_count,
                                    'threshold': applicable_threshold,
                                    'successful_disables': successful_disables,
                                    'failed_disables': failed_disables
                                }
                                with open(log_dir / f"disable_report_{campaign_setup.campaign_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json", 'w') as f:
                                    json.dump(report, f)
                            except Exception as log_error:
                                logger.error(f"Ошибка при создании отчета: {str(log_error)}")
                        else:
                            logger.warning(f"Не найдено объявлений в кампании {campaign_setup.campaign_id}")
                    except Exception as ad_error:
                        logger.error(f"Ошибка при отключении объявлений: {str(ad_error)}")
                else:
                    logger.info(
                        f"Кампания {campaign_setup.campaign_id} в порядке. "
                        f"Расходы: ${spend:.2f}, конверсии: {conversion_count}, "
                        f"период: {period}"
                    )
            
            except Exception as e:
                logger.error(f"Ошибка при проверке кампании {campaign_setup.campaign_id}: {str(e)}")
                continue
                
        return True
                
    except Exception as e:
        logger.error(f"Ошибка при проверке порогов кампаний: {str(e)}")
        return False 