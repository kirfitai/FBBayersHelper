"""
Модуль совместимости для старого кода, ожидающего FacebookAPI
"""

import logging
from app.services.fb_api_client import FacebookAdClient

# Настройка логирования
logger = logging.getLogger(__name__)

class FacebookAPI:
    """
    Класс-обертка для совместимости со старым кодом.
    Перенаправляет все вызовы в FacebookAdClient
    """
    
    def __init__(self, access_token=None, app_id=None, app_secret=None, account_id=None, token_obj=None):
        """
        Инициализация API Facebook
        
        Args:
            access_token (str): Access токен Facebook
            app_id (str): ID приложения Facebook
            app_secret (str): Секретный ключ приложения
            account_id (str): ID рекламного аккаунта
            token_obj (FacebookToken): Объект токена
        """
        logger.info("Инициализация FacebookAPI (обертка для совместимости)")
        self.client = FacebookAdClient(
            access_token=access_token,
            app_id=app_id,
            app_secret=app_secret,
            ad_account_id=account_id,
            token_obj=token_obj
        )
    
    def get_campaign_stats(self, campaign_id, fields=None, date_preset=None, time_range=None):
        """
        Получение статистики для кампании (перенаправление в FacebookAdClient)
        """
        return self.client.get_campaign_stats(
            campaign_id=campaign_id,
            fields=fields,
            date_preset=date_preset,
            time_range=time_range
        )
    
    def update_campaign_status(self, campaign_id, status):
        """
        Обновление статуса кампании (перенаправление в FacebookAdClient)
        """
        return self.client.update_campaign_status(
            campaign_id=campaign_id,
            status=status
        )
        
    def get_ads_in_campaign(self, campaign_id):
        """
        Получение объявлений в кампании (перенаправление в FacebookAdClient)
        
        Args:
            campaign_id (str): ID кампании
            
        Returns:
            list: Список объектов объявлений
        """
        logger.info(f"FacebookAPI: Запрос объявлений для кампании {campaign_id}")
        return self.client.get_ads_in_campaign(campaign_id)
    
    def get_ad_insights(self, ad_id, date_preset=None, time_range=None):
        """
        Получение статистики по объявлению (перенаправление в FacebookAdClient)
        
        Args:
            ad_id (str): ID объявления
            date_preset (str, optional): Предустановленный период ('today', 'yesterday', etc.)
            time_range (dict, optional): Кастомный период времени {'since': 'YYYY-MM-DD', 'until': 'YYYY-MM-DD'}
            
        Returns:
            dict: Данные статистики
        """
        logger.info(f"FacebookAPI: Запрос инсайтов для объявления {ad_id}")
        return self.client.get_ad_insights(ad_id, date_preset, time_range)
    
    def disable_ad(self, ad_id):
        """
        Отключение объявления (перенаправление в FacebookAdClient)
        
        Args:
            ad_id (str): ID объявления
            
        Returns:
            bool: Успешность операции
        """
        logger.info(f"FacebookAPI: Отключение объявления {ad_id}")
        return self.client.disable_ad(ad_id) 