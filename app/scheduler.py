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

def check_campaign_thresholds(campaign_id, check_period='today', access_token=None):
    """
    Проверяет объявления в кампании по порогам и возвращает список результатов.
    
    Args:
        campaign_id (str): ID кампании Facebook
        check_period (str): Период проверки ('today', 'yesterday', '7days', '14days', '30days')
        access_token (str, optional): Токен доступа Facebook, если None, используется глобальный
        
    Returns:
        dict: Словарь, содержащий информацию о кампании и результаты проверки объявлений
    """
    try:
        # Инициализация API
        fb_api = FacebookAPI(access_token)
        
        # Получение информации о кампании
        campaign_info = fb_api.get_campaign_stats(campaign_id)
        if not campaign_info:
            logging.error(f"Не удалось получить информацию о кампании {campaign_id}")
            return {"error": "Не удалось получить информацию о кампании"}
        
        campaign = {
            "id": campaign_id,
            "name": campaign_info.get("name", "Нет данных"),
            "status": campaign_info.get("status", "Нет данных")
        }
        
        # Получение объявлений в кампании
        ads = fb_api.get_ads_in_campaign(campaign_id)
        if not ads:
            logging.error(f"Не удалось получить объявления для кампании {campaign_id}")
            return {"error": "Не удалось получить объявления для кампании"}
        
        # Определение дат для получения статистики
        today = datetime.datetime.now().date()
        if check_period == 'today':
            since = today.strftime('%Y-%m-%d')
            until = (today + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
        elif check_period == 'yesterday':
            yesterday = today - datetime.timedelta(days=1)
            since = yesterday.strftime('%Y-%m-%d')
            until = today.strftime('%Y-%m-%d')
        elif check_period == '7days':
            since = (today - datetime.timedelta(days=7)).strftime('%Y-%m-%d')
            until = (today + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
        elif check_period == '14days':
            since = (today - datetime.timedelta(days=14)).strftime('%Y-%m-%d')
            until = (today + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
        elif check_period == '30days':
            since = (today - datetime.timedelta(days=30)).strftime('%Y-%m-%d')
            until = (today + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
        else:
            since = today.strftime('%Y-%m-%d')
            until = (today + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
        
        # Пороги для проверки
        spend_threshold = 20  # расход более 20 рублей
        conversion_threshold = 0  # нет конверсий
        
        results = []
        
        # Получение статистики по объявлениям и проверка порогов
        for ad in ads:
            ad_id = ad.get('id')
            ad_name = ad.get('name')
            ad_status = ad.get('status')
            
            # Получение статистики по объявлению за указанный период
            insights = fb_api.get_ad_insights(ad_id, since, until)
            
            if not insights:
                # Если статистика недоступна, пропускаем объявление
                continue
            
            spend = float(insights.get('spend', 0))
            conversions = int(insights.get('actions', {}).get('offsite_conversion.fb_pixel_purchase', 0))
            
            status = "active"
            reason = ""
            
            # Проверка порогов
            if ad_status == 'ACTIVE':
                if spend > spend_threshold and conversions <= conversion_threshold:
                    status = "disabled"
                    reason = f"Расход {spend} руб. без конверсий"
                    # Отключаем объявление
                    fb_api.disable_ad(ad_id)
                elif spend > spend_threshold / 2 and conversions <= conversion_threshold:
                    status = "warning"
                    reason = f"Расход {spend} руб. с низкой конверсией"
            elif ad_status == 'PAUSED':
                status = "disabled"
                reason = "Объявление приостановлено"
            
            results.append({
                "id": ad_id,
                "name": ad_name,
                "status": status,
                "spend": spend,
                "conversions": conversions,
                "reason": reason
            })
        
        return {
            "campaign": campaign,
            "results": results
        }
    
    except Exception as e:
        logging.error(f"Ошибка при проверке кампании {campaign_id}: {str(e)}")
        return {"error": f"Ошибка при проверке кампании: {str(e)}"}

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