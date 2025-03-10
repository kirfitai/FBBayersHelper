import os
import requests
import logging
import json
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.adobjects.campaign import Campaign
from facebook_business.adobjects.adset import AdSet
from facebook_business.adobjects.ad import Ad

# Настройка логирования
logger = logging.getLogger(__name__)

class FacebookAdClient:
    def __init__(self, access_token=None, app_id=None, app_secret=None, ad_account_id=None, token_obj=None):
        """
        Инициализация клиента Facebook API
        
        Args:
            access_token (str): Access токен Facebook
            app_id (str): ID приложения Facebook
            app_secret (str): Секретный ключ приложения
            ad_account_id (str): ID рекламного аккаунта в формате 'act_XXXXXXXXXX'
            token_obj (FacebookToken): Объект токена (альтернативный способ инициализации)
        """
        if token_obj:
            self.access_token = token_obj.access_token
            self.app_id = token_obj.app_id
            self.app_secret = token_obj.app_secret
            self.proxy_url = token_obj.proxy_url if token_obj.use_proxy else None
            
            # Получаем первый аккаунт из списка, если токен связан с аккаунтами
            account_ids = token_obj.get_account_ids()
            self.ad_account_id = account_ids[0] if account_ids else None
            
            logger.info(f"Инициализация клиента для токена {token_obj.id} ({token_obj.name})")
            logger.info(f"Доступные аккаунты: {account_ids}")
        else:
            self.access_token = access_token
            self.app_id = app_id
            self.app_secret = app_secret
            self.ad_account_id = ad_account_id
            self.proxy_url = None

        # Настройка прокси через переменные окружения
        if self.proxy_url:
            os.environ['http_proxy'] = self.proxy_url
            os.environ['https_proxy'] = self.proxy_url
            logger.info(f"Настроен прокси: {self.proxy_url}")
        
        # Инициализация API без параметра session
        self.api = FacebookAdsApi.init(
            self.app_id, 
            self.app_secret, 
            self.access_token,
            api_version='v18.0'
        )
        
        # Проверка наличия аккаунта
        if self.ad_account_id:
            # Убедимся, что ID аккаунта начинается с 'act_'
            if not self.ad_account_id.startswith('act_'):
                self.ad_account_id = f'act_{self.ad_account_id}'
            
            self.account = AdAccount(self.ad_account_id)
            logger.info(f"Настроен аккаунт по умолчанию: {self.ad_account_id}")
    
    def set_account(self, account_id):
        """
        Устанавливает текущий рекламный аккаунт
        
        Args:
            account_id (str): ID рекламного аккаунта
        """
        # Проверка наличия ID аккаунта
        if not account_id:
            logger.error("Попытка установить пустой ID аккаунта")
            raise ValueError("Не указан ID аккаунта")
            
        # Убедимся, что ID аккаунта начинается с 'act_'
        if not account_id.startswith('act_'):
            account_id = f'act_{account_id}'
            
        self.ad_account_id = account_id
        self.account = AdAccount(self.ad_account_id)
        logger.info(f"Установлен аккаунт: {self.ad_account_id}")
    
    def get_campaigns(self, status_filter=None):
        """
        Получение списка кампаний
        
        Args:
            status_filter (str, optional): Фильтр по статусу (ACTIVE, PAUSED, etc.)
            
        Returns:
            list: Список объектов кампаний
        """
        # Проверка наличия аккаунта
        if not self.ad_account_id:
            logger.error("Попытка получить кампании без указания аккаунта")
            raise ValueError("Не указан ID аккаунта")
            
        try:
            # Получаем ВСЕ кампании без фильтрации по статусу
            params = {
                'fields': ['id', 'name', 'status', 'objective']
            }
            
            logger.info(f"Запрос всех кампаний для аккаунта {self.ad_account_id}")
            campaigns = self.account.get_campaigns(params=params)
            logger.info(f"Получено {len(campaigns)} кампаний через SDK")
            
            # Фильтруем только на клиентской стороне
            if status_filter:
                filtered_campaigns = []
                for c in campaigns:
                    if hasattr(c, 'status') and c['status'] == status_filter:
                        filtered_campaigns.append(c)
                logger.info(f"После фильтрации по статусу {status_filter} осталось {len(filtered_campaigns)} кампаний")
                return filtered_campaigns
                
            return campaigns
        
        except Exception as e:
            logger.warning(f"Ошибка при использовании SDK: {str(e)}")
            logger.info("Попытка получить кампании через прямой запрос к API")
            
            try:
                # Прямой запрос БЕЗ параметра filtering
                api_params = {
                    'access_token': self.access_token,
                    'fields': 'id,name,status,objective'
                }
                
                response = requests.get(
                    f'https://graph.facebook.com/v18.0/{self.ad_account_id}/campaigns',
                    params=api_params
                )
                
                if response.status_code == 200:
                    data = response.json()
                    campaigns_data = data.get('data', [])
                    logger.info(f"Получено {len(campaigns_data)} кампаний через прямой запрос")
                    
                    from facebook_business.adobjects.campaign import Campaign
                    campaigns = []
                    
                    # Фильтруем на клиентской стороне
                    for campaign_data in campaigns_data:
                        if not status_filter or campaign_data.get('status') == status_filter:
                            campaign = Campaign(campaign_data.get('id'))
                            for key, value in campaign_data.items():
                                setattr(campaign, key, value)
                            campaigns.append(campaign)
                    
                    logger.info(f"После фильтрации осталось {len(campaigns)} кампаний")
                    return campaigns
                else:
                    logger.error(f"Ошибка API: {response.status_code} - {response.text}")
                    return []
                    
            except Exception as api_error:
                logger.error(f"Ошибка при прямом запросе: {str(api_error)}")
                return []
    
    def get_ads_in_campaign(self, campaign_id):
        """
        Получение всех объявлений в кампании
        
        Args:
            campaign_id (str): ID кампании
            
        Returns:
            list: Список объектов объявлений
        """
        try:
            campaign = Campaign(campaign_id)
            ads = campaign.get_ads(fields=['id', 'name', 'status', 'creative'])
            logger.info(f"Получено {len(ads)} объявлений для кампании {campaign_id}")
            return ads
        except Exception as e:
            logger.error(f"Ошибка при получении объявлений для кампании {campaign_id}: {str(e)}")
            # В случае ошибки пробуем прямой запрос
            try:
                response = requests.get(
                    f'https://graph.facebook.com/v18.0/{campaign_id}/ads',
                    params={
                        'access_token': self.access_token,
                        'fields': 'id,name,status,creative'
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    ads_data = data.get('data', [])
                    logger.info(f"Получено {len(ads_data)} объявлений через прямой запрос")
                    
                    # Преобразуем в формат, ожидаемый приложением
                    ads = []
                    for ad_data in ads_data:
                        ad = Ad(ad_data.get('id'))
                        for key, value in ad_data.items():
                            setattr(ad, key, value)
                        ads.append(ad)
                    
                    return ads
                else:
                    logger.error(f"Ошибка API: {response.status_code} - {response.text}")
                    return []
            except Exception as api_error:
                logger.error(f"Ошибка при прямом запросе объявлений: {str(api_error)}")
                return []
    
    def get_ad_insights(self, ad_id, date_preset='today'):
        """
        Получение статистики по объявлению
        
        Args:
            ad_id (str): ID объявления
            date_preset (str): Временной период ('today', 'yesterday', 'last_7_days', etc.)
            
        Returns:
            dict: Данные о расходах и конверсиях
        """
        try:
            ad = Ad(ad_id)
            insights = ad.get_insights(
                fields=['ad_id', 'spend', 'actions'],
                params={
                    'date_preset': date_preset,
                    'time_increment': 1
                }
            )
            
            if not insights:
                return {'ad_id': ad_id, 'spend': 0, 'conversions': 0}
            
            # Извлечение данных о конверсиях из результатов
            spend = float(insights[0].get('spend', 0))
            conversions = 0
            
            actions = insights[0].get('actions', [])
            for action in actions:
                if action.get('action_type') in ['offsite_conversion', 'lead', 'purchase']:
                    conversions += int(action.get('value', 0))
            
            return {
                'ad_id': ad_id,
                'spend': spend,
                'conversions': conversions
            }
        except Exception as e:
            logger.error(f"Ошибка при получении статистики для объявления {ad_id}: {str(e)}")
            return {'ad_id': ad_id, 'spend': 0, 'conversions': 0}
    
    def disable_ad(self, ad_id):
        """
        Отключение объявления
        
        Args:
            ad_id (str): ID объявления
            
        Returns:
            bool: Результат операции
        """
        try:
            ad = Ad(ad_id)
            result = ad.api_update(
                params={
                    'status': Ad.Status.paused,
                }
            )
            logger.info(f"Объявление {ad_id} отключено")
            return result
        except Exception as e:
            logger.error(f"Ошибка при отключении объявления {ad_id}: {str(e)}")
            return False