import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import logging
from flask import current_app

logger = logging.getLogger(__name__)

class FacebookGraphAPIClient:
    """
    Клиент для работы с Graph API Facebook с расширенной обработкой запросов
    """
    
    def __init__(self, access_token):
        """
        Инициализация клиента
        
        Args:
            access_token (str): Access token для Facebook API
        """
        self.access_token = access_token
        self.session = self._create_retry_session()
    
    def _create_retry_session(self):
        """
        Создание сессии с настройками повторных запросов
        
        Returns:
            requests.Session: Сессия с настройками повторных запросов
        """
        retry_strategy = Retry(
            total=current_app.config.get('HTTP_MAX_RETRIES', 3),
            status_forcelist=[429, 500, 502, 503, 504],
            method_whitelist=["GET", "POST"],
            backoff_factor=current_app.config.get('HTTP_BACKOFF_FACTOR', 0.3)
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session = requests.Session()
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session
    
    def get_paginated_data(self, url, params=None):
        """
        Получение всех данных с поддержкой пагинации
        
        Args:
            url (str): URL для запроса
            params (dict, optional): Параметры запроса
        
        Returns:
            list: Полный список полученных данных
        """
        if params is None:
            params = {}
        
        # Добавляем access_token в параметры, если он не передан
        if 'access_token' not in params:
            params['access_token'] = self.access_token
        
        all_data = []
        current_url = url
        
        try:
            while current_url:
                try:
                    response = self.session.get(
                        current_url, 
                        params=params, 
                        timeout=current_app.config.get('HTTP_REQUEST_TIMEOUT', 30)
                    )
                    
                    response.raise_for_status()
                    data = response.json()
                    
                    # Добавляем текущую страницу данных
                    current_page_data = data.get('data', [])
                    all_data.extend(current_page_data)
                    
                    # Проверяем наличие следующей страницы
                    current_url = data.get('paging', {}).get('next')
                    
                    # Обновляем параметры для следующего запроса
                    params = None
                
                except requests.exceptions.RequestException as req_error:
                    logger.error(f"Ошибка запроса: {str(req_error)}")
                    break
            
            return all_data
        
        except Exception as e:
            logger.error(f"Непредвиденная ошибка при получении данных: {str(e)}")
            return []
    
    def get_campaigns(self, account_id, status_filter=None):
        """
        Получение списка кампаний для конкретного аккаунта
        
        Args:
            account_id (str): ID рекламного аккаунта
            status_filter (str, optional): Фильтр по статусу кампании
        
        Returns:
            list: Список кампаний
        """
        url = f'https://graph.facebook.com/v18.0/{account_id}/campaigns'
        params = {
            'fields': 'id,name,status,objective'
        }
        
        all_campaigns = self.get_paginated_data(url, params)
        
        # Фильтрация кампаний по статусу, если указан
        if status_filter:
            all_campaigns = [
                campaign for campaign in all_campaigns 
                if campaign.get('status') == status_filter
            ]
        
        logger.info(f"Получено кампаний: {len(all_campaigns)}")
        return all_campaigns