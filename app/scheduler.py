import logging
from datetime import datetime, timedelta
from sqlalchemy import and_
from app.extensions import db
from app.models.setup import Setup, CampaignSetup
from app.models.user import User
from app.services.facebook_api import FacebookAPI
from app.models.facebook_token import FacebookToken

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
    Проверяет пороги кампаний и отключает кампании, если они превышены.
    
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
                fb_api = FacebookAPI(
                    access_token=token.access_token,
                    app_id=token.app_id,
                    app_secret=token.app_secret,
                    account_id=token.account_id
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
                
                # Обновляем время последней проверки
                campaign_setup.last_checked = datetime.utcnow()
                db.session.commit()
                
                # Проверяем, превышены ли пороги
                should_disable = False
                
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
                        should_disable = True
                        logger.info(
                            f"Порог превышен для кампании {campaign_setup.campaign_id}: "
                            f"расходы ${spend:.2f}, конверсии {conversion_count}, "
                            f"требуется минимум {required_conversions} конверсий при расходах ${applicable_threshold['spend']}"
                        )
                
                # Если нужно отключить кампанию
                if should_disable:
                    try:
                        # Отключаем кампанию через Facebook API
                        result = fb_api.update_campaign_status(
                            campaign_id=campaign_setup.campaign_id,
                            status='PAUSED'
                        )
                        
                        if result:
                            logger.info(
                                f"Кампания {campaign_setup.campaign_id} успешно приостановлена. "
                                f"Расходы: ${spend:.2f}, конверсии: {conversion_count}, "
                                f"период: {period}"
                            )
                        else:
                            logger.error(f"Не удалось приостановить кампанию {campaign_setup.campaign_id}")
                    except Exception as e:
                        logger.error(f"Ошибка при приостановке кампании {campaign_setup.campaign_id}: {str(e)}")
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