import logging
import requests
import socket
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.exceptions import FacebookRequestError

logger = logging.getLogger(__name__)

class TokenChecker:
    def __init__(self):
        self.logger = logger
    
    def check_token(self, token_obj):
        """
        Проверяет валидность токена Facebook
        
        Args:
            token_obj: Объект модели FacebookToken
            
        Returns:
            tuple: (status, error_message)
                status: 'valid' или 'invalid'
                error_message: Сообщение об ошибке или None
        """
        try:
            # Настройка сессии с прокси, если указан
            session = requests.Session()
            if token_obj.proxy_url:
                proxy = {
                    'http': token_obj.proxy_url,
                    'https': token_obj.proxy_url
                }
                session.proxies.update(proxy)
                # Установка таймаута для соединения
                socket.setdefaulttimeout(15)
            
            # Инициализация API с пользовательской сессией
            api = FacebookAdsApi.init(
                token_obj.app_id, 
                token_obj.app_secret, 
                token_obj.access_token,
                api_version='v18.0',
                session=session
            )
            
            # Пробуем получить информацию об аккаунте
            account = AdAccount(token_obj.account_id)
            account_info = account.api_get(fields=['name', 'account_status'])
            
            # Если запрос успешен, токен валиден
            return ('valid', None)
            
        except FacebookRequestError as e:
            error_message = f"Facebook API error: {e.api_error_message()}"
            self.logger.error(f"Token {token_obj.id} ({token_obj.name}) check failed: {error_message}")
            return ('invalid', error_message)
            
        except Exception as e:
            error_message = f"Error checking token: {str(e)}"
            self.logger.error(f"Token {token_obj.id} ({token_obj.name}) check failed: {error_message}")
            return ('invalid', error_message)