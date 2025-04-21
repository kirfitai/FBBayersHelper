"""
Модуль совместимости для старого кода, ожидающего FacebookAPI
"""

import logging
import traceback
import time
from app.services.fb_api_client import FacebookAdClient, FB_GRAPH_URL
import requests
import json

# Настройка логирования
logger = logging.getLogger(__name__)

class FacebookAPI:
    """
    Класс-обертка для обеспечения обратной совместимости со старым кодом,
    который ожидает класс FacebookAPI
    """
    def __init__(self, access_token, app_id=None, app_secret=None, ad_account_id=None):
        try:
            logger.info(f"[FacebookAPI] Инициализация FacebookAPI с параметрами: access_token={len(access_token) if access_token else 'None'}, app_id={app_id}, app_secret={len(app_secret) if app_secret else 'None'}, ad_account_id={ad_account_id}")
            # Игнорируем ad_account_id, если он передан
            if ad_account_id:
                logger.warning(f"[FacebookAPI] Параметр ad_account_id проигнорирован: {ad_account_id}")
                
            self.client = FacebookAdClient(access_token, app_id, app_secret)
            logger.info("[FacebookAPI] Инициализирована обертка для FacebookAdClient")
        except Exception as e:
            logger.error(f"[FacebookAPI] Ошибка при инициализации: {str(e)}")
            logger.error(traceback.format_exc())
            raise
    
    def get_campaign_stats(self, campaign_id, date_preset='today', timeout=120):
        """
        Получение статистики по кампании
        
        Args:
            campaign_id (str): ID кампании
            date_preset (str): Период (today, yesterday, last_7d, и т.д.)
            timeout (int): Таймаут для запроса в секундах
            
        Returns:
            dict: Данные о расходах и конверсиях
        """
        logger.info(f"[FacebookAPI] Запрос статистики для кампании {campaign_id} за период {date_preset}")
        try:
            # Получаем объявления в кампании
            logger.info(f"[FacebookAPI] Получение объявлений для кампании {campaign_id}")
            ads = self.get_ads_in_campaign(campaign_id, timeout=timeout)
            logger.info(f"[FacebookAPI] Получено {len(ads)} объявлений в кампании {campaign_id}")
            
            total_spend = 0
            total_conversions = 0
            
            # Получаем статистику для каждого объявления
            for ad in ads:
                if not hasattr(ad, 'id') or not ad.id:
                    logger.warning(f"[FacebookAPI] Объявление без ID, пропускаем: {ad}")
                    continue
                    
                try:
                    logger.info(f"[FacebookAPI] Получение статистики для объявления {ad.id}")
                    insights = self.get_ad_insights(ad.id, date_preset=date_preset, timeout=timeout)
                    total_spend += float(insights.get('spend', 0))
                    total_conversions += int(insights.get('conversions', 0))
                    logger.debug(f"[FacebookAPI] Статистика для объявления {ad.id}: расход={insights.get('spend', 0)}, конверсии={insights.get('conversions', 0)}")
                except Exception as ad_error:
                    logger.error(f"[FacebookAPI] Ошибка при получении статистики для объявления {ad.id}: {str(ad_error)}")
                    logger.error(traceback.format_exc())
            
            logger.info(f"[FacebookAPI] Общая статистика кампании {campaign_id}: расход={total_spend}, конверсии={total_conversions}")
            return {
                'campaign_id': campaign_id,
                'spend': total_spend,
                'conversions': total_conversions
            }
        except Exception as e:
            logger.error(f"[FacebookAPI] Ошибка при получении статистики кампании {campaign_id}: {str(e)}")
            logger.error(traceback.format_exc())
            return {
                'campaign_id': campaign_id,
                'spend': 0,
                'conversions': 0
            }
    
    def update_campaign_status(self, campaign_id, status, timeout=120):
        """
        Обновление статуса кампании (ACTIVE, PAUSED)
        
        Args:
            campaign_id (str): ID кампании
            status (str): Новый статус (ACTIVE, PAUSED)
            timeout (int): Таймаут для запроса в секундах
            
        Returns:
            bool: Успешно ли обновлен статус
        """
        logger.info(f"[FacebookAPI] Обновление статуса кампании {campaign_id} на {status}")
        try:
            # Проверяем допустимость статуса
            if status not in ['ACTIVE', 'PAUSED']:
                logger.error(f"[FacebookAPI] Недопустимый статус: {status}")
                return False
                
            url = f"{FB_GRAPH_URL}/{campaign_id}"
            params = {
                'access_token': self.client.access_token,
                'status': status
            }
            
            logger.info(f"[FacebookAPI] Отправка запроса на обновление статуса кампании {campaign_id}")
            response = requests.post(url, params=params, timeout=timeout)
            
            if response.status_code == 200:
                logger.info(f"[FacebookAPI] Статус кампании {campaign_id} успешно обновлен на {status}")
                return True
            else:
                logger.error(f"[FacebookAPI] Ошибка API при обновлении статуса: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            logger.error(f"[FacebookAPI] Ошибка при обновлении статуса кампании {campaign_id}: {str(e)}")
            logger.error(traceback.format_exc())
            return False
    
    def get_ads_in_campaign(self, campaign_id, timeout=120):
        """
        Получение всех объявлений в кампании
        
        Args:
            campaign_id (str): ID кампании
            timeout (int): Таймаут для запроса в секундах
            
        Returns:
            list: Список объектов объявлений
        """
        logger.info(f"[FacebookAPI] Запрос объявлений для кампании {campaign_id}")
        try:
            # Используем метод клиента с поддержкой повторных попыток
            logger.info(f"[FacebookAPI] Вызов client.get_ads_in_campaign для кампании {campaign_id}")
            ads = self.client.get_ads_in_campaign(campaign_id, timeout=timeout)
            
            if ads:
                logger.info(f"[FacebookAPI] Получено {len(ads)} объявлений в кампании {campaign_id}")
                
                # Преобразуем объекты SimpleNamespace в словари для удобства использования
                processed_ads = []
                for ad in ads:
                    if hasattr(ad, 'id'):
                        ad_dict = {
                            'id': ad.id,
                            'name': ad.name if hasattr(ad, 'name') else 'Без имени',
                            'status': ad.status if hasattr(ad, 'status') else 'UNKNOWN',
                            'effective_status': ad.effective_status if hasattr(ad, 'effective_status') else 'UNKNOWN'
                        }
                        processed_ads.append(ad_dict)
                
                # Проверяем наличие необходимых атрибутов и считаем активные объявления
                active_count = sum(1 for ad in processed_ads if ad['effective_status'] == 'ACTIVE')
                logger.info(f"[FacebookAPI] Активных объявлений (effective_status=ACTIVE): {active_count}")
                
                return processed_ads
            else:
                logger.warning(f"[FacebookAPI] Нет объявлений в кампании {campaign_id}")
                
            return []
        except Exception as e:
            logger.error(f"[FacebookAPI] Ошибка при получении объявлений для кампании {campaign_id}: {str(e)}")
            logger.error(traceback.format_exc())
            return []
    
    def get_ad_insights(self, ad_id, date_preset='today', time_range=None, timeout=120):
        """
        Получение статистики по объявлению
        
        Args:
            ad_id (str): ID объявления
            date_preset (str): Предустановленный период
            time_range (dict): Период в формате {'since': 'YYYY-MM-DD', 'until': 'YYYY-MM-DD'}
            timeout (int): Таймаут для запроса в секундах
            
        Returns:
            dict: Данные о расходах и конверсиях
        """
        logger.info(f"[FacebookAPI] Запрос статистики для объявления {ad_id} с date_preset={date_preset}, time_range={time_range}")
        try:
            # Используем метод клиента с поддержкой повторных попыток и передаем параметры
            logger.info(f"[FacebookAPI] Вызов client.get_ad_insights для объявления {ad_id}")
            insights = self.client.get_ad_insights(
                ad_id, 
                date_preset=None if time_range else date_preset,  # Если задан time_range, не используем date_preset
                time_range=time_range,
                timeout=timeout
            )
            
            logger.debug(f"[FacebookAPI] Полученная статистика: {insights}")
            return insights
        except Exception as e:
            logger.error(f"[FacebookAPI] Ошибка при получении статистики для объявления {ad_id}: {str(e)}")
            logger.error(traceback.format_exc())
            return {'ad_id': ad_id, 'spend': 0, 'conversions': 0}
    
    def disable_ad(self, ad_id, timeout=120):
        """
        Отключение объявления
        
        Args:
            ad_id (str): ID объявления
            timeout (int): Таймаут для запроса в секундах
            
        Returns:
            bool: Успешно ли отключено объявление
        """
        logger.info(f"[FacebookAPI] Отключение объявления {ad_id}")
        try:
            url = f"{FB_GRAPH_URL}/{ad_id}"
            params = {
                'access_token': self.client.access_token,
                'status': 'PAUSED'
            }
            
            logger.info(f"[FacebookAPI] Отправка запроса на отключение объявления {ad_id}")
            response = requests.post(url, params=params, timeout=timeout)
            
            if response.status_code == 200:
                logger.info(f"[FacebookAPI] Объявление {ad_id} успешно отключено")
                return True
            else:
                logger.error(f"[FacebookAPI] Ошибка API при отключении объявления: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            logger.error(f"[FacebookAPI] Ошибка при отключении объявления {ad_id}: {str(e)}")
            logger.error(traceback.format_exc())
            return False 