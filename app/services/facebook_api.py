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
        
        # Проверяем, предоставлен ли параметр time_range
        if time_range:
            # Если указан time_range, получаем дату начала и конца для построения URL
            since_date = time_range.get('since')
            until_date = time_range.get('until')
            logger.info(f"Используем кастомный период: {since_date} - {until_date}")
            
            # Создаем временный URL с параметрами для прямого запроса
            url = f'https://graph.facebook.com/v18.0/{ad_id}/insights'
            params = {
                'access_token': self.client.access_token,
                'fields': 'spend,actions',
                'time_range': f'{{"since":"{since_date}","until":"{until_date}"}}',
                'time_increment': 1
            }
            
            try:
                import requests
                import json
                
                response = requests.get(url, params=params, timeout=30)
                if response.status_code == 200:
                    data = response.json()
                    insights = data.get('data', [])
                    
                    if not insights:
                        logger.warning(f"Нет данных для объявления {ad_id} за период {since_date} - {until_date}")
                        return {'ad_id': ad_id, 'spend': 0, 'conversions': 0}
                    
                    # Извлечение данных о расходах и конверсиях
                    spend = float(insights[0].get('spend', 0))
                    conversions = 0
                    
                    actions = insights[0].get('actions', [])
                    for action in actions:
                        if action.get('action_type') in ['offsite_conversion', 'lead', 'purchase']:
                            conversions += int(action.get('value', 0))
                    
                    logger.info(f"Получены данные об объявлении {ad_id}: расход=${spend}, конверсий={conversions}")
                    return {
                        'ad_id': ad_id,
                        'spend': spend,
                        'conversions': conversions
                    }
                else:
                    logger.error(f"Ошибка API при получении данных: {response.status_code} - {response.text}")
            except Exception as e:
                logger.error(f"Ошибка при прямом запросе инсайтов: {str(e)}")
        
        # Если time_range не указан или произошла ошибка, используем стандартный метод
        actual_date_preset = date_preset or 'today'
        logger.info(f"Используем стандартный период: {actual_date_preset}")
        return self.client.get_ad_insights(ad_id, actual_date_preset)
    
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