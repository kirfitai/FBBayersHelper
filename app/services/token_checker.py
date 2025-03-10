import logging
import os
import socket
import requests
import json
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.adobjects.campaign import Campaign
from facebook_business.exceptions import FacebookRequestError

logger = logging.getLogger(__name__)

class TokenChecker:
    def __init__(self):
        self.logger = logger
    
    def check_token(self, token_obj):
        """
        Проверяет валидность токена Facebook и получает информацию о связанных аккаунтах
        
        Args:
            token_obj: Объект модели FacebookToken
            
        Returns:
            tuple: (status, error_message, accounts_data)
                status: 'valid' или 'invalid'
                error_message: Сообщение об ошибке или None
                accounts_data: Словарь с данными аккаунтов или None
        """
        try:
            # Настройка прокси через переменные окружения, если указан
            if token_obj.use_proxy and token_obj.proxy_url:
                os.environ['http_proxy'] = token_obj.proxy_url
                os.environ['https_proxy'] = token_obj.proxy_url
                # Установка таймаута для соединения
                socket.setdefaulttimeout(15)
            
            # Инициализация API без параметра session
            api = FacebookAdsApi.init(
                token_obj.app_id or None, 
                token_obj.app_secret or None, 
                token_obj.access_token,
                api_version='v18.0'
            )
            
            accounts_data = {}
            
            # Получаем список ID аккаунтов (может быть несколько через запятую)
            account_ids = [aid.strip() for aid in token_obj.get_account_ids()]
            
            # Если у токена еще нет аккаунтов, берем из полей
            if not account_ids and hasattr(token_obj, 'account_id'):
                raw_account_ids = token_obj.account_id
                account_ids = [aid.strip() for aid in raw_account_ids.split(',')]
            
            # Проверка на пустой список аккаунтов
            if not account_ids:
                return ('invalid', "Не указаны ID аккаунтов", None)
            
            # Проверяем каждый аккаунт
            for account_id in account_ids:
                # Убедимся, что ID аккаунта начинается с 'act_'
                if not account_id.startswith('act_'):
                    account_id = f'act_{account_id}'
                
                try:
                    # Пробуем сначала прямой запрос к API
                    response = requests.get(
                        f'https://graph.facebook.com/v18.0/{account_id}',
                        params={
                            'access_token': token_obj.access_token,
                            'fields': 'name,account_status'
                        }
                    )
                    
                    if response.status_code == 200:
                        account_info = response.json()
                        accounts_data[account_id] = {
                            'name': account_info.get('name', 'Unknown'),
                            'status': account_info.get('account_status')
                        }
                        
                        # Добавляем или обновляем связь с аккаунтом
                        token_obj.add_account(account_id, account_info.get('name'))
                        logger.info(f"Аккаунт {account_id} ({account_info.get('name')}) доступен")
                    else:
                        logger.error(f"Ошибка доступа к аккаунту {account_id}: {response.status_code} - {response.text}")
                        return ('invalid', f"Ошибка доступа к аккаунту {account_id}: {response.text}", None)
                    
                except Exception as e:
                    # Пробуем использовать SDK, если прямой запрос не сработал
                    try:
                        account = AdAccount(account_id)
                        account_info = account.api_get(fields=['name', 'account_status'])
                        
                        accounts_data[account_id] = {
                            'name': account_info.get('name', 'Unknown'),
                            'status': account_info.get('account_status')
                        }
                        
                        # Добавляем или обновляем связь с аккаунтом
                        token_obj.add_account(account_id, account_info.get('name'))
                        logger.info(f"Аккаунт {account_id} ({account_info.get('name')}) доступен через SDK")
                    except Exception as sdk_error:
                        logger.error(f"Ошибка при проверке аккаунта {account_id}: {str(sdk_error)}")
                        # Если не удалось проверить хотя бы один аккаунт, считаем это ошибкой
                        return ('invalid', f"Ошибка при проверке аккаунта {account_id}: {str(sdk_error)}", None)
            
            # Если запрос успешен, токен валиден
            return ('valid', None, accounts_data)
            
        except FacebookRequestError as e:
            error_message = f"Facebook API error: {e.api_error_message()}"
            self.logger.error(f"Token {token_obj.id} ({token_obj.name}) check failed: {error_message}")
            return ('invalid', error_message, None)
            
        except Exception as e:
            error_message = f"Error checking token: {str(e)}"
            self.logger.error(f"Token {token_obj.id} ({token_obj.name}) check failed: {error_message}")
            return ('invalid', error_message, None)
    
    def fetch_campaigns(self, token_obj, account_id=None):
        """
        Получает список кампаний для указанного аккаунта
        
        Args:
            token_obj: Объект модели FacebookToken
            account_id: ID аккаунта (если None, используются все аккаунты токена)
            
        Returns:
            dict: Словарь с результатами по аккаунтам
                {account_id: {'success': bool, 'campaigns': list, 'error': str}}
        """
        from app.services.fb_api_client import FacebookAdClient
        
        results = {}
        
        try:
            # Создаем клиент Facebook API
            fb_client = FacebookAdClient(token_obj=token_obj)
            
            # Определяем список аккаунтов для проверки
            if account_id:
                if not account_id.startswith('act_'):
                    account_id = f'act_{account_id}'
                account_ids = [account_id]
            else:
                account_ids = token_obj.get_account_ids()
            
            # Проверяем, что у нас есть аккаунты для проверки
            if not account_ids:
                self.logger.warning(f"Для токена {token_obj.id} ({token_obj.name}) не найдены связанные аккаунты")
                return {}
            
            # Получаем кампании для каждого аккаунта
            for aid in account_ids:
                try:
                    # Убедимся, что ID аккаунта начинается с 'act_'
                    if not aid.startswith('act_'):
                        aid = f'act_{aid}'
                    
                    # Устанавливаем текущий аккаунт
                    self.logger.info(f"Запрос кампаний для аккаунта {aid} с токеном {token_obj.id}")
                    fb_client.set_account(aid)
                    
                    # Получаем ВСЕ кампании и фильтруем на стороне клиента
                    try:
                        all_campaigns = fb_client.get_campaigns()  # Без фильтра
                        
                        # Фильтруем только активные на стороне клиента
                        campaigns = []
                        for c in all_campaigns:
                            if hasattr(c, 'status') and c['status'] == 'ACTIVE':
                                campaigns.append(c)
                        
                        # Если получили None или пустой список, заменяем на пустой список
                        if not campaigns:
                            campaigns = []
                            self.logger.info(f"Для аккаунта {aid} не найдено активных кампаний (из {len(all_campaigns)} общих)")
                    except Exception as e:
                        self.logger.warning(f"Ошибка при получении кампаний через SDK: {str(e)}")
                        # Если ошибка при использовании SDK, пробуем прямой запрос
                        try:
                            response = requests.get(
                                f'https://graph.facebook.com/v18.0/{aid}/campaigns',
                                params={
                                    'access_token': token_obj.access_token,
                                    'fields': 'id,name,status,objective'
                                    # Без параметра filtering
                                }
                            )
                            
                            if response.status_code == 200:
                                data = response.json()
                                campaigns_data = data.get('data', [])
                                
                                # Преобразуем и фильтруем на стороне клиента
                                campaigns = []
                                for campaign_data in campaigns_data:
                                    if campaign_data.get('status') == 'ACTIVE':
                                        campaign = Campaign(campaign_data.get('id'))
                                        for key, value in campaign_data.items():
                                            setattr(campaign, key, value)
                                        campaigns.append(campaign)
                                
                                self.logger.info(f"Получено {len(campaigns)} активных кампаний из {len(campaigns_data)} через прямой запрос")
                            else:
                                raise Exception(f"API error: {response.status_code} - {response.text}")
                        except Exception as api_error:
                            # Если и этот запрос не сработал, вызываем исключение
                            raise Exception(f"Failed to get campaigns: {str(api_error)}")
                    
                    # Обновляем счетчик кампаний
                    token_obj.update_campaign_count(aid, len(campaigns))
                    
                    self.logger.info(f"Для аккаунта {aid} найдено {len(campaigns)} активных кампаний")
                    results[aid] = {
                        'success': True,
                        'campaigns': campaigns,
                        'error': None
                    }
                    
                except Exception as e:
                    self.logger.error(f"Ошибка при получении кампаний для аккаунта {aid}: {str(e)}")
                    results[aid] = {
                        'success': False,
                        'campaigns': [],
                        'error': str(e)
                    }
            
            return results
            
        except Exception as e:
            self.logger.error(f"Ошибка получения кампаний для токена {token_obj.id}: {str(e)}")
            
            # Если был указан конкретный аккаунт, возвращаем ошибку для него
            if account_id:
                return {account_id: {'success': False, 'campaigns': [], 'error': str(e)}}
            
            # Иначе возвращаем пустой результат
            return {}