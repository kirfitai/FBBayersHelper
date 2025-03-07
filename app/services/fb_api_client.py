import requests
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.adobjects.campaign import Campaign
from facebook_business.adobjects.adset import AdSet
from facebook_business.adobjects.ad import Ad

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
            self.ad_account_id = token_obj.account_id
            self.proxy_url = token_obj.proxy_url
        else:
            self.access_token = access_token
            self.app_id = app_id
            self.app_secret = app_secret
            self.ad_account_id = ad_account_id
            self.proxy_url = None
        
        # Инициализация API с прокси, если указан
        session = requests.Session()
        if self.proxy_url:
            proxy = {
                'http': self.proxy_url,
                'https': self.proxy_url
            }
            session.proxies.update(proxy)
        
        api = FacebookAdsApi.init(
            self.app_id, 
            self.app_secret, 
            self.access_token,
            api_version='v18.0',
            session=session
        )
        
        self.account = AdAccount(self.ad_account_id)
    
    def get_campaigns(self, status_filter=None):
        """
        Получение списка кампаний
        
        Args:
            status_filter (str, optional): Фильтр по статусу (ACTIVE, PAUSED, etc.)
            
        Returns:
            list: Список объектов кампаний
        """
        params = {
            'fields': ['id', 'name', 'status', 'objective']
        }
        
        if status_filter:
            params['filtering'] = [{
                'field': 'status',
                'operator': 'EQUAL',
                'value': status_filter
            }]
            
        return self.account.get_campaigns(params=params)
    
    def get_ads_in_campaign(self, campaign_id):
        """
        Получение всех объявлений в кампании
        
        Args:
            campaign_id (str): ID кампании
            
        Returns:
            list: Список объектов объявлений
        """
        campaign = Campaign(campaign_id)
        return campaign.get_ads(fields=['id', 'name', 'status', 'creative'])
    
    def get_ad_insights(self, ad_id, date_preset='today'):
        """
        Получение статистики по объявлению
        
        Args:
            ad_id (str): ID объявления
            date_preset (str): Временной период ('today', 'yesterday', 'last_7_days', etc.)
            
        Returns:
            dict: Данные о расходах и конверсиях
        """
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
    
    def disable_ad(self, ad_id):
        """
        Отключение объявления
        
        Args:
            ad_id (str): ID объявления
            
        Returns:
            bool: Результат операции
        """
        ad = Ad(ad_id)
        result = ad.api_update(
            params={
                'status': Ad.Status.paused,
            }
        )
        return result