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
    
    def _parse_fb_error(self, response_text):
        """
        Парсит ошибку Facebook API из JSON ответа
        
        Args:
            response_text: Текст ответа API
            
        Returns:
            str: Понятное сообщение об ошибке
        """
        try:
            data = json.loads(response_text)
            error = data.get('error', {})
            code = error.get('code')
            message = error.get('message')
            sub_code = error.get('error_subcode')
            
            if code == 190:
                return f"Токен доступа недействителен или истек (код 190): {message}"
            elif code == 104:
                return f"Превышено ограничение скорости запросов (код 104): {message}"
            elif code == 200:
                if sub_code == 2341008:
                    return f"Нет доступа к аккаунту (код 200): {message}"
                return f"Недостаточно разрешений (код 200): {message}"
            elif code == 2:
                return f"Ошибка сервиса (код 2): {message}"
            elif code == 100:
                return f"Недопустимый запрос или параметр (код 100): {message}"
            elif code == 1:
                return f"Общая ошибка API (код 1): {message}"
            else:
                return f"Ошибка Facebook API (код {code}): {message}"
        except Exception as e:
            return f"Не удалось распознать ошибку API: {response_text[:200]}"
    
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
        self.logger.info(f"Начало проверки токена {token_obj.id} ({token_obj.name})")
        self.logger.info(f"Токен: {token_obj.access_token[:15]}...")
        
        try:
            # Настройка прокси через переменные окружения, если указан
            if token_obj.use_proxy and token_obj.proxy_url:
                os.environ['http_proxy'] = token_obj.proxy_url
                os.environ['https_proxy'] = token_obj.proxy_url
                # Установка таймаута для соединения
                socket.setdefaulttimeout(30)  # Увеличиваем до 30 секунд
                self.logger.info(f"Используется прокси: {token_obj.proxy_url}")
            
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
                if raw_account_ids:
                    account_ids = [aid.strip() for aid in raw_account_ids.split(',')]
            
            # Проверка на пустой список аккаунтов
            if not account_ids:
                self.logger.warning(f"Для токена {token_obj.id} не указаны ID аккаунтов")
                return ('invalid', "Не указаны ID аккаунтов", None)
            
            self.logger.info(f"Проверка следующих аккаунтов: {account_ids}")
            
            # Проверяем каждый аккаунт
            for account_id in account_ids:
                # Убедимся, что ID аккаунта начинается с 'act_'
                if not account_id.startswith('act_'):
                    account_id = f'act_{account_id}'
                
                self.logger.info(f"Проверка аккаунта {account_id}")
                
                try:
                    # Пробуем сначала прямой запрос к API с увеличенным таймаутом
                    response = requests.get(
                        f'https://graph.facebook.com/v18.0/{account_id}',
                        params={
                            'access_token': token_obj.access_token,
                            'fields': 'name,account_status'
                        },
                        timeout=30  # 30 секунд таймаут
                    )
                    
                    self.logger.info(f"Статус ответа API: {response.status_code}")
                    
                    if response.status_code == 200:
                        account_info = response.json()
                        self.logger.info(f"Получена информация об аккаунте: {account_info}")
                        
                        accounts_data[account_id] = {
                            'name': account_info.get('name', 'Unknown'),
                            'status': account_info.get('account_status')
                        }
                        
                        # Добавляем или обновляем связь с аккаунтом
                        token_obj.add_account(account_id, account_info.get('name'))
                        self.logger.info(f"Аккаунт {account_id} ({account_info.get('name')}) доступен")
                    elif response.status_code == 400 and 'error' in response.json():
                        error_message = self._parse_fb_error(response.text)
                        self.logger.error(f"Ошибка API для аккаунта {account_id}: {error_message}")
                        return ('invalid', error_message, None)
                    else:
                        self.logger.error(f"Ошибка доступа к аккаунту {account_id}: {response.status_code} - {response.text}")
                        error_message = self._parse_fb_error(response.text) if response.text else f"Ошибка API: код {response.status_code}"
                        return ('invalid', error_message, None)
                    
                except requests.exceptions.Timeout:
                    self.logger.error(f"Превышено время ожидания при проверке аккаунта {account_id}")
                    return ('invalid', f"Превышено время ожидания при проверке аккаунта {account_id}. Проверьте соединение или настройки прокси.", None)
                except requests.exceptions.ConnectionError:
                    self.logger.error(f"Ошибка соединения при проверке аккаунта {account_id}")
                    return ('invalid', f"Ошибка соединения при проверке аккаунта {account_id}. Проверьте доступность сети или настройки прокси.", None)
                except Exception as e:
                    self.logger.error(f"Неизвестная ошибка при прямом запросе: {str(e)}")
                    
                    # Пробуем использовать SDK, если прямой запрос не сработал
                    try:
                        self.logger.info(f"Пробуем проверить аккаунт {account_id} через SDK")
                        account = AdAccount(account_id)
                        account_info = account.api_get(fields=['name', 'account_status'])
                        
                        accounts_data[account_id] = {
                            'name': account_info.get('name', 'Unknown'),
                            'status': account_info.get('account_status')
                        }
                        
                        # Добавляем или обновляем связь с аккаунтом
                        token_obj.add_account(account_id, account_info.get('name'))
                        self.logger.info(f"Аккаунт {account_id} ({account_info.get('name')}) доступен через SDK")
                    except FacebookRequestError as fb_error:
                        error_code = fb_error.api_error_code()
                        error_message = fb_error.api_error_message()
                        
                        # Обработка конкретных ошибок API
                        if error_code == 190:  # Недействительный токен доступа
                            self.logger.error(f"Токен доступа недействителен: {error_message}")
                            return ('invalid', f"Токен доступа недействителен: {error_message}", None)
                        else:
                            self.logger.error(f"Ошибка Facebook API [{error_code}]: {error_message}")
                            return ('invalid', f"Ошибка Facebook API: {error_message}", None)
                    except Exception as sdk_error:
                        self.logger.error(f"Ошибка при проверке аккаунта {account_id} через SDK: {str(sdk_error)}")
                        # Если не удалось проверить хотя бы один аккаунт, считаем это ошибкой
                        return ('invalid', f"Ошибка при проверке аккаунта {account_id}: {str(sdk_error)}", None)
            
            # Если запрос успешен, токен валиден
            self.logger.info(f"Токен {token_obj.id} успешно проверен, найдено {len(accounts_data)} аккаунтов")
            return ('valid', None, accounts_data)
            
        except FacebookRequestError as e:
            error_code = e.api_error_code()
            error_message = e.api_error_message()
            
            # Обработка конкретных ошибок API
            if error_code == 190:  # Недействительный токен доступа
                error_message = "Токен доступа недействителен или истек срок его действия"
            elif error_code == 200:  # Ограничение разрешений
                error_message = "Недостаточно разрешений для доступа к рекламным аккаунтам. Требуются разрешения ads_management и ads_read."
            
            self.logger.error(f"Token {token_obj.id} ({token_obj.name}) check failed: {error_message}")
            return ('invalid', error_message, None)
            
        except requests.exceptions.Timeout:
            error_message = "Превышено время ожидания при соединении с Facebook API. Проверьте соединение или настройки прокси."
            self.logger.error(f"Token {token_obj.id} ({token_obj.name}) check failed: {error_message}")
            return ('invalid', error_message, None)
            
        except requests.exceptions.ConnectionError:
            error_message = "Ошибка соединения с Facebook API. Проверьте доступность сети или настройки прокси."
            self.logger.error(f"Token {token_obj.id} ({token_obj.name}) check failed: {error_message}")
            return ('invalid', error_message, None)
            
        except Exception as e:
            error_message = f"Ошибка проверки токена: {str(e)}"
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
        from facebook_business.adobjects.campaign import Campaign
        import requests
        import json
        
        # Отладочный вывод
        self.logger.info(f"fetch_campaigns: token_id={token_obj.id}, account_id={account_id}")
        self.logger.info(f"Token access_token: {token_obj.access_token[:15]}...")
        self.logger.info(f"Token accounts: {token_obj.get_account_ids()}")
        
        results = {}
        
        try:
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
            
            self.logger.info(f"Получение кампаний для аккаунтов: {account_ids}")
            
            # Получаем кампании для каждого аккаунта
            for aid in account_ids:
                try:
                    # Убедимся, что ID аккаунта начинается с 'act_'
                    if not aid.startswith('act_'):
                        aid = f'act_{aid}'
                    
                    self.logger.info(f"Запрос кампаний для аккаунта {aid} с токеном {token_obj.id}")
                    
                    # В первую очередь пробуем прямой запрос к API, так как это более надежный метод
                    try:
                        response = requests.get(
                            f'https://graph.facebook.com/v18.0/{aid}/campaigns',
                            params={
                                'access_token': token_obj.access_token,
                                'fields': 'id,name,status,objective',
                                'limit': 100  # Увеличим лимит для получения большего числа кампаний
                            },
                            timeout=30  # Увеличиваем таймаут до 30 секунд
                        )
                        
                        # Отладочный вывод
                        self.logger.info(f"API response status: {response.status_code}")
                        self.logger.info(f"API response headers: {dict(response.headers)}")
                        
                        if response.status_code == 200:
                            self.logger.info(f"API response text: {response.text[:200]}...")  # Первые 200 символов
                            self.logger.info(f"Успешный прямой запрос к API для аккаунта {aid}")
                            data = response.json()
                            campaigns_data = data.get('data', [])
                            
                            # Создаем список объектов Campaign из полученных данных
                            campaigns = []
                            for campaign_data in campaigns_data:
                                # Фильтруем только активные кампании
                                if campaign_data.get('status') == 'ACTIVE':
                                    campaign = Campaign(campaign_data.get('id'))
                                    # Вручную устанавливаем атрибуты
                                    campaign['id'] = campaign_data.get('id')
                                    campaign['name'] = campaign_data.get('name')
                                    campaign['status'] = campaign_data.get('status')
                                    campaign['objective'] = campaign_data.get('objective')
                                    campaigns.append(campaign)
                            
                            self.logger.info(f"Для аккаунта {aid} найдено {len(campaigns)} активных кампаний из {len(campaigns_data)} через прямой запрос")
                            
                            # Если нет кампаний, создаем тестовую для отладки
                            if not campaigns:
                                self.logger.warning(f"Не найдено активных кампаний для аккаунта {aid}")
                                
                                # ВРЕМЕННО: Создаем тестовую кампанию для отладки интерфейса
                                # Закомментируйте или удалите в production
                                test_campaign = Campaign("123456789123")
                                test_campaign['id'] = "123456789123"
                                test_campaign['name'] = "Тестовая кампания (отладка)"
                                test_campaign['status'] = "ACTIVE"
                                test_campaign['objective'] = "OUTCOME_SALES"
                                campaigns = [test_campaign]
                                self.logger.info(f"Создана тестовая кампания для отладки")
                            
                            # Обновляем счетчик кампаний
                            token_obj.update_campaign_count(aid, len(campaigns))
                            
                            results[aid] = {
                                'success': True,
                                'campaigns': campaigns,
                                'error': None
                            }
                            continue  # Переходим к следующему аккаунту, так как этот успешно обработан
                        else:
                            error_message = self._parse_fb_error(response.text)
                            self.logger.warning(f"Ошибка прямого запроса к API для аккаунта {aid}: {error_message}")
                            self.logger.info(f"API response text: {response.text}")
                            # Продолжаем выполнение и пробуем использовать SDK
                    except Exception as direct_api_error:
                        self.logger.warning(f"Ошибка при прямом запросе к API для аккаунта {aid}: {str(direct_api_error)}")
                        # Продолжаем выполнение и пробуем использовать SDK
                    
                    # Если прямой запрос не удался, пробуем использовать SDK
                    try:
                        # Создаем клиент Facebook API
                        fb_client = FacebookAdClient(token_obj=token_obj)
                        fb_client.set_account(aid)
                        
                        # Получаем ВСЕ кампании и фильтруем на стороне клиента
                        all_campaigns = fb_client.get_campaigns()
                        
                        if all_campaigns is None:
                            all_campaigns = []
                        
                        # Фильтруем только активные на стороне клиента
                        campaigns = []
                        for c in all_campaigns:
                            if hasattr(c, 'status') and c['status'] == 'ACTIVE':
                                campaigns.append(c)
                        
                        self.logger.info(f"Для аккаунта {aid} найдено {len(campaigns)} активных кампаний из {len(all_campaigns)} через SDK")
                        
                        # Если нет кампаний, создаем тестовую для отладки
                        if not campaigns:
                            self.logger.warning(f"Не найдено активных кампаний для аккаунта {aid}")
                            
                            # ВРЕМЕННО: Создаем тестовую кампанию для отладки интерфейса
                            # Закомментируйте или удалите в production
                            test_campaign = Campaign("987654321")
                            test_campaign['id'] = "987654321"
                            test_campaign['name'] = "Тестовая кампания SDK (отладка)"
                            test_campaign['status'] = "ACTIVE"
                            test_campaign['objective'] = "OUTCOME_SALES"
                            campaigns = [test_campaign]
                            self.logger.info(f"Создана тестовая кампания для отладки через SDK")
                        
                        # Обновляем счетчик кампаний
                        token_obj.update_campaign_count(aid, len(campaigns))
                        
                        results[aid] = {
                            'success': True,
                            'campaigns': campaigns,
                            'error': None
                        }
                    except Exception as sdk_error:
                        self.logger.error(f"Ошибка при получении кампаний через SDK для аккаунта {aid}: {str(sdk_error)}")
                        results[aid] = {
                            'success': False,
                            'campaigns': [],
                            'error': str(sdk_error)
                        }
                except Exception as account_error:
                    self.logger.error(f"Ошибка при обработке аккаунта {aid}: {str(account_error)}")
                    results[aid] = {
                        'success': False,
                        'campaigns': [],
                        'error': str(account_error)
                    }
            
            # Итоговый результат
            success_count = sum(1 for result in results.values() if result['success'])
            campaign_count = sum(len(result['campaigns']) for result in results.values() if result['success'])
            self.logger.info(f"Всего получено {campaign_count} кампаний из {len(results)} аккаунтов (успешно: {success_count})")
            
            return results
            
        except Exception as e:
            self.logger.error(f"Ошибка получения кампаний для токена {token_obj.id}: {str(e)}")
            
            # Если был указан конкретный аккаунт, возвращаем ошибку для него
            if account_id:
                return {account_id: {'success': False, 'campaigns': [], 'error': str(e)}}
            
            # Иначе возвращаем пустой результат
            return {}