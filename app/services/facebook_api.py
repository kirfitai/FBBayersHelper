"""
Модуль совместимости для старого кода, ожидающего FacebookAPI
"""

import logging
import time
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
            time_range=time_range,
            timeout=60
        )
    
    def update_campaign_status(self, campaign_id, status):
        """
        Обновление статуса кампании (перенаправление в FacebookAdClient)
        """
        return self.client.update_campaign_status(
            campaign_id=campaign_id,
            status=status,
            timeout=60
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
        
        # Максимальное количество попыток
        max_retries = 3
        retry_delay = 5  # секунды между попытками
        current_retry = 0
        
        while current_retry < max_retries:
            try:
                # Увеличиваем таймаут при повторных попытках
                timeout = 60 + (current_retry * 30)  # 60, 90, 120 секунд
                logger.info(f"FacebookAPI: Попытка {current_retry+1}/{max_retries} с таймаутом {timeout} секунд")
                
                # Передаем таймаут в клиент
                ads = self.client.get_ads_in_campaign(campaign_id, timeout=timeout)
                
                # Проверяем, получили ли мы объявления
                if ads is None:
                    logger.error(f"FacebookAPI: Результат вызова get_ads_in_campaign равен None для кампании {campaign_id}")
                    current_retry += 1
                    if current_retry < max_retries:
                        logger.info(f"FacebookAPI: Ожидание {retry_delay} секунд перед следующей попыткой...")
                        time.sleep(retry_delay)
                        continue
                    else:
                        logger.error(f"FacebookAPI: Все попытки исчерпаны, объявления не получены (результат None)")
                        return []
                
                if not ads:
                    logger.warning(f"FacebookAPI: Не получены объявления для кампании {campaign_id} в попытке {current_retry+1}")
                    current_retry += 1
                    if current_retry < max_retries:
                        logger.info(f"FacebookAPI: Ожидание {retry_delay} секунд перед следующей попыткой...")
                        time.sleep(retry_delay)
                        continue
                    else:
                        logger.error(f"FacebookAPI: Все попытки исчерпаны, объявления не получены")
                        return []
                    
                logger.info(f"FacebookAPI: Получено {len(ads)} объявлений для кампании {campaign_id}")
                
                # Выводим типы первых 3-х объявлений для отладки
                for i, ad in enumerate(ads[:3]):
                    logger.info(f"FacebookAPI: Объявление {i+1} - Тип: {type(ad)}, имеет атрибуты: id={hasattr(ad, 'id')}, status={hasattr(ad, 'status')}, name={hasattr(ad, 'name')}")
                
                # Убеждаемся, что объекты объявлений содержат все необходимые атрибуты
                for ad in ads:
                    # Проверяем наличие атрибута status, если его нет - устанавливаем значение по умолчанию
                    if not hasattr(ad, 'status') and hasattr(ad, 'effective_status'):
                        logger.info(f"FacebookAPI: Устанавливаем status из effective_status для объявления {getattr(ad, 'id', 'неизвестный id')}")
                        setattr(ad, 'status', getattr(ad, 'effective_status'))
                    elif not hasattr(ad, 'status'):
                        logger.info(f"FacebookAPI: Устанавливаем status=UNKNOWN для объявления {getattr(ad, 'id', 'неизвестный id')}")
                        setattr(ad, 'status', 'UNKNOWN')
                        
                    # Проверяем наличие атрибута id
                    if not hasattr(ad, 'id') and hasattr(ad, '_data') and 'id' in ad._data:
                        logger.info(f"FacebookAPI: Устанавливаем id из _data для объявления")
                        setattr(ad, 'id', ad._data['id'])
                    
                    # Проверяем наличие атрибута name
                    if not hasattr(ad, 'name') and hasattr(ad, '_data') and 'name' in ad._data:
                        logger.info(f"FacebookAPI: Устанавливаем name из _data для объявления {getattr(ad, 'id', 'неизвестный id')}")
                        setattr(ad, 'name', ad._data['name'])
                        
                # Возвращаем список объявлений
                active_count = sum(1 for ad in ads if getattr(ad, 'status', None) == 'ACTIVE')
                paused_count = sum(1 for ad in ads if getattr(ad, 'status', None) == 'PAUSED')
                logger.info(f"FacebookAPI: Активных объявлений: {active_count}, отключенных: {paused_count}")
                
                return ads
                
            except Exception as e:
                current_retry += 1
                logger.error(f"FacebookAPI: Ошибка при получении объявлений (попытка {current_retry}/{max_retries}): {str(e)}")
                import traceback
                logger.error(f"FacebookAPI: Трассировка ошибки: {traceback.format_exc()}")
                if current_retry < max_retries:
                    logger.info(f"FacebookAPI: Ожидание {retry_delay} секунд перед следующей попыткой...")
                    time.sleep(retry_delay)
                else:
                    logger.error(f"FacebookAPI: Все попытки исчерпаны, ошибка: {str(e)}")
                    return []
    
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
                
                # Увеличиваем таймаут для запроса инсайтов
                response = requests.get(url, params=params, timeout=60)
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
        return self.client.get_ad_insights(ad_id, actual_date_preset, timeout=60)
    
    def disable_ad(self, ad_id):
        """
        Отключение объявления (перенаправление в FacebookAdClient)
        
        Args:
            ad_id (str): ID объявления
            
        Returns:
            bool: Успешность операции
        """
        logger.info(f"FacebookAPI: Отключение объявления {ad_id}")
        return self.client.disable_ad(ad_id, timeout=60) 