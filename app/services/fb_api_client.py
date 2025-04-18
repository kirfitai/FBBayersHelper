import os
import requests
import logging
import json
import time
import traceback
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.adobjects.campaign import Campaign
from facebook_business.adobjects.adset import AdSet
from facebook_business.adobjects.ad import Ad
from types import SimpleNamespace

# Определение базового URL для Graph API
FB_GRAPH_URL = 'https://graph.facebook.com/v18.0'

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
    
    def get_campaigns(self, status_filter=None, limit=1000):
        """
        Получение списка кампаний с поддержкой пагинации
        
        Args:
            status_filter (str, optional): Фильтр по статусу (ACTIVE, PAUSED, etc.)
            limit (int): Максимальное количество кампаний для получения
            
        Returns:
            list: Список объектов кампаний
        """
        # Проверка наличия аккаунта
        if not self.ad_account_id:
            logger.error("Попытка получить кампании без указания аккаунта")
            raise ValueError("Не указан ID аккаунта")
        
        all_campaigns = []
        next_url = None
        
        try:
            # Сначала пробуем прямой запрос к API с пагинацией
            api_params = {
                'access_token': self.access_token,
                'fields': 'id,name,status,objective',
                'limit': 100  # Запрашиваем по 100 кампаний за раз
            }
            
            logger.info(f"Прямой запрос кампаний для аккаунта {self.ad_account_id}")
            
            # Выполняем начальный запрос
            url = f'https://graph.facebook.com/v18.0/{self.ad_account_id}/campaigns'
            
            while url and len(all_campaigns) < limit:
                logger.info(f"Запрашиваем страницу: {url}")
                
                response = requests.get(
                    url,
                    params=api_params if next_url is None else {},  # Используем параметры только для первого запроса
                    timeout=30
                )
                
                if response.status_code != 200:
                    logger.warning(f"Ошибка API: {response.status_code} - {response.text}")
                    break
                    
                data = response.json()
                campaigns_data = data.get('data', [])
                logger.info(f"Получено {len(campaigns_data)} кампаний на этой странице")
                
                # Добавляем кампании в общий список
                from facebook_business.adobjects.campaign import Campaign
                
                for campaign_data in campaigns_data:
                    if not status_filter or campaign_data.get('status') == status_filter:
                        campaign = Campaign(campaign_data.get('id'))
                        campaign['id'] = campaign_data.get('id')
                        campaign['name'] = campaign_data.get('name')
                        campaign['status'] = campaign_data.get('status')
                        campaign['objective'] = campaign_data.get('objective')
                        all_campaigns.append(campaign)
                
                # Проверяем, есть ли следующая страница
                paging = data.get('paging', {})
                next_url = paging.get('next')
                
                # Если нет следующей страницы или достигли лимита, выходим из цикла
                if not next_url or len(all_campaigns) >= limit:
                    break
                    
                # Сбрасываем параметры, так как next_url уже содержит все необходимое
                url = next_url
                api_params = None
            
            logger.info(f"Всего получено {len(all_campaigns)} кампаний через прямой запрос")
            
            if all_campaigns:
                return all_campaigns[:limit]  # Возвращаем не более limit записей
        except Exception as api_error:
            logger.warning(f"Ошибка при прямом запросе: {str(api_error)}")
            # Продолжаем выполнение и пробуем использовать SDK
        
        # Если прямой запрос не сработал, пробуем через SDK
        try:
            # Получаем ВСЕ кампании без фильтрации по статусу
            params = {
                'fields': ['id', 'name', 'status', 'objective'],
                'limit': 100
            }
            
            logger.info(f"Запрос кампаний через SDK для аккаунта {self.ad_account_id}")
            campaigns = self.account.get_campaigns(params=params)
            logger.info(f"Получено {len(campaigns)} кампаний через SDK")
            
            # Фильтруем только на клиентской стороне
            if status_filter:
                filtered_campaigns = []
                for c in campaigns:
                    if hasattr(c, 'status') and c['status'] == status_filter:
                        filtered_campaigns.append(c)
                logger.info(f"После фильтрации по статусу {status_filter} осталось {len(filtered_campaigns)} кампаний")
                return filtered_campaigns[:limit]
                
            return campaigns[:limit]
        
        except Exception as e:
            logger.error(f"Ошибка при использовании SDK: {str(e)}")
            
            # Если все методы не сработали, возвращаем пустой список
            logger.warning("Не удалось получить кампании, возвращаем пустой список")
            return []
    
    def get_ads_in_campaign(self, campaign_id, timeout=120):
        """
        Получение объявлений в кампании
        
        Args:
            campaign_id (str): ID кампании
            timeout (int): Таймаут для запроса в секундах
            
        Returns:
            list: Список объявлений в кампании или пустой список при ошибке
        """
        try:
            logger.info(f"[FacebookAdClient] Запрос объявлений для кампании {campaign_id} с таймаутом {timeout} секунд")
            
            # Используем увеличенный таймаут
            max_attempts = 3
            current_attempt = 0
            
            while current_attempt < max_attempts:
                try:
                    current_attempt += 1
                    
                    # Увеличиваем таймаут с каждой попыткой
                    current_timeout = timeout + (current_attempt - 1) * 30
                    logger.info(f"[FacebookAdClient] Попытка {current_attempt}/{max_attempts} с таймаутом {current_timeout}с")
                    
                    url = f"{FB_GRAPH_URL}/{campaign_id}/ads"
                    params = {
                        'access_token': self.access_token,
                        'fields': 'id,name,status,effective_status',
                        'limit': 500  # Увеличенное количество объявлений в одном запросе
                    }
                    
                    response = requests.get(url, params=params, timeout=current_timeout)
                    
                    if response.status_code == 200:
                        ads_data = response.json().get('data', [])
                        
                        if ads_data:
                            logger.info(f"[FacebookAdClient] Получено {len(ads_data)} объявлений")
                            
                            # Создаем объекты для каждого объявления
                            ads = []
                            for ad_data in ads_data:
                                try:
                                    ad = SimpleNamespace()
                                    ad.id = ad_data.get('id')
                                    ad.name = ad_data.get('name')
                                    ad.status = ad_data.get('status') or ad_data.get('effective_status', 'UNKNOWN')
                                    
                                    if hasattr(ad, 'id') and ad.id:
                                        ads.append(ad)
                                    else:
                                        logger.warning(f"[FacebookAdClient] Пропущено объявление без ID: {ad_data}")
                                except Exception as ad_error:
                                    logger.error(f"[FacebookAdClient] Ошибка при обработке объявления: {str(ad_error)}")
                            
                            return ads
                        else:
                            logger.warning(f"[FacebookAdClient] Нет объявлений в ответе API для кампании {campaign_id}")
                            
                            # Пробуем еще раз, если это не последняя попытка
                            if current_attempt < max_attempts:
                                logger.info(f"[FacebookAdClient] Пауза перед следующей попыткой...")
                                time.sleep(2 * current_attempt)
                                continue
                            return []
                    else:
                        # Проверяем код ошибки на превышение лимита
                        try:
                            error_data = response.json().get('error', {})
                            error_code = error_data.get('code')
                            error_subcode = error_data.get('error_subcode')
                            error_message = error_data.get('message', '')
                            
                            # Код 17 - User request limit reached, код 4 - Too many calls
                            if error_code in [17, 4] or 'limit' in error_message.lower():
                                logger.warning(f"[FacebookAdClient] Превышен лимит запросов к API: {error_message}")
                                
                                # Экспоненциальная задержка перед повторной попыткой
                                wait_time = 5 * (2 ** (current_attempt - 1))  # 5, 10, 20 секунд
                                logger.info(f"[FacebookAdClient] Ожидание {wait_time} секунд перед следующей попыткой из-за превышения лимита API")
                                
                                if current_attempt < max_attempts:
                                    time.sleep(wait_time)
                                    continue
                                else:
                                    logger.error("[FacebookAdClient] Превышено количество попыток для обхода ограничения API")
                                    # Возвращаем пустой результат, так как все попытки не удались
                                    return []
                        except Exception as json_error:
                            logger.error(f"[FacebookAdClient] Ошибка при обработке JSON-ответа: {str(json_error)}")
                        
                        logger.error(f"[FacebookAdClient] Ошибка API {response.status_code}: {response.text}")
                        
                        # Пробуем еще раз при определенных ошибках
                        if response.status_code in [500, 502, 503, 504] and current_attempt < max_attempts:
                            logger.info(f"[FacebookAdClient] Пауза перед следующей попыткой...")
                            time.sleep(3 * current_attempt)
                            continue
                            
                        # Для других ошибок прекращаем попытки
                        return []
                        
                except requests.exceptions.RequestException as req_error:
                    logger.error(f"[FacebookAdClient] Ошибка запроса в попытке {current_attempt}: {str(req_error)}")
                    
                    # Пробуем еще раз, если это не последняя попытка
                    if current_attempt < max_attempts:
                        logger.info(f"[FacebookAdClient] Пауза перед следующей попыткой...")
                        time.sleep(3 * current_attempt)
                    else:
                        logger.error(f"[FacebookAdClient] Все попытки израсходованы, не удалось получить объявления")
                        return []
                        
            # Если мы дошли до этого места, значит все попытки не удались
            return []
            
        except Exception as e:
            logger.error(f"[FacebookAdClient] Критическая ошибка при получении объявлений: {str(e)}")
            logger.debug(traceback.format_exc())
            return []
    
    def get_ad_insights(self, ad_id, date_preset='today', time_range=None, fields=None, timeout=120):
        """
        Получение статистики по объявлению
        
        Args:
            ad_id (str): ID объявления
            date_preset (str): Предустановленный период (today, yesterday, last_7d, last_28d, last_30d, last_90d, last_month, this_month)
            time_range (dict): Период в формате {'since': 'YYYY-MM-DD', 'until': 'YYYY-MM-DD'}
            fields (list): Список полей для запроса
            timeout (int): Таймаут для запроса в секундах

        Returns:
            dict: Данные статистики или пустой словарь при ошибке
        """
        try:
            logger.info(f"[FacebookAdClient] Запрос статистики для объявления {ad_id}")
            
            max_attempts = 3
            current_attempt = 0
            
            # Определяем необходимые поля
            if fields is None:
                fields = ['spend']
                
            while current_attempt < max_attempts:
                try:
                    current_attempt += 1
                    current_timeout = timeout + (current_attempt - 1) * 30
                    
                    logger.info(f"[FacebookAdClient] Попытка {current_attempt}/{max_attempts} с таймаутом {current_timeout}с")
                    
                    # Формируем URL и параметры
                    url = f"{FB_GRAPH_URL}/{ad_id}/insights"
                    params = {
                        'access_token': self.access_token,
                        'fields': ','.join(fields)
                    }
                    
                    # Устанавливаем период
                    if time_range:
                        params['time_range'] = json.dumps(time_range)
                    else:
                        params['date_preset'] = date_preset
                        
                    # Делаем GET запрос с увеличенным таймаутом
                    response = requests.get(url, params=params, timeout=current_timeout)
                    
                    if response.status_code == 200:
                        data = response.json()
                        insights_data = data.get('data', [])
                        
                        if insights_data and len(insights_data) > 0:
                            # Обрабатываем результаты
                            result = {'ad_id': ad_id, 'spend': 0, 'conversions': 0}
                            
                            # Извлекаем расходы
                            if 'spend' in insights_data[0]:
                                result['spend'] = float(insights_data[0]['spend'])
                                
                            # Проверяем действия и считаем конверсии если есть
                            if 'actions' in insights_data[0]:
                                conversion_types = ['purchase', 'web_in_store_purchase', 'onsite_web_app_purchase']
                                for action in insights_data[0]['actions']:
                                    if action.get('action_type') in conversion_types:
                                        result['conversions'] += int(action.get('value', 0))
                                        
                            logger.info(f"[FacebookAdClient] Получены данные статистики: {result}")
                            return result
                        else:
                            logger.warning(f"[FacebookAdClient] Нет статистики для объявления {ad_id}")
                            
                            # Пробуем еще раз, если это не последняя попытка
                            if current_attempt < max_attempts:
                                logger.info(f"[FacebookAdClient] Пауза перед следующей попыткой...")
                                time.sleep(1 * current_attempt)
                                continue
                                
                            # Возвращаем пустой результат с нулевыми значениями
                            return {'ad_id': ad_id, 'spend': 0, 'conversions': 0}
                    else:
                        # Проверяем код ошибки на превышение лимита
                        try:
                            error_data = response.json().get('error', {})
                            error_code = error_data.get('code')
                            error_subcode = error_data.get('error_subcode')
                            error_message = error_data.get('message', '')
                            
                            # Код 17 - User request limit reached, код 4 - Too many calls
                            if error_code in [17, 4] or 'limit' in error_message.lower():
                                logger.warning(f"[FacebookAdClient] Превышен лимит запросов к API: {error_message}")
                                
                                # Экспоненциальная задержка перед повторной попыткой
                                wait_time = 5 * (2 ** (current_attempt - 1))  # 5, 10, 20 секунд
                                logger.info(f"[FacebookAdClient] Ожидание {wait_time} секунд перед следующей попыткой из-за превышения лимита API")
                                
                                if current_attempt < max_attempts:
                                    time.sleep(wait_time)
                                    continue
                                else:
                                    logger.error("[FacebookAdClient] Превышено количество попыток для обхода ограничения API")
                                    # Возвращаем пустой результат, так как все попытки не удались
                                    return {'ad_id': ad_id, 'spend': 0, 'conversions': 0}
                        except Exception as json_error:
                            logger.error(f"[FacebookAdClient] Ошибка при обработке JSON-ответа: {str(json_error)}")
                        
                        logger.error(f"[FacebookAdClient] Ошибка API {response.status_code}: {response.text}")
                        
                        # Пробуем еще раз при определенных ошибках
                        if response.status_code in [500, 502, 503, 504] and current_attempt < max_attempts:
                            logger.info(f"[FacebookAdClient] Пауза перед следующей попыткой...")
                            time.sleep(2 * current_attempt)
                            continue
                            
                        # Для других ошибок прекращаем попытки
                        return {'ad_id': ad_id, 'spend': 0, 'conversions': 0}
                        
                except requests.exceptions.RequestException as req_error:
                    logger.error(f"[FacebookAdClient] Ошибка запроса в попытке {current_attempt}: {str(req_error)}")
                    
                    # Пробуем еще раз, если это не последняя попытка
                    if current_attempt < max_attempts:
                        logger.info(f"[FacebookAdClient] Пауза перед следующей попыткой...")
                        time.sleep(2 * current_attempt)
                    else:
                        logger.error(f"[FacebookAdClient] Все попытки израсходованы, не удалось получить статистику")
                        return {'ad_id': ad_id, 'spend': 0, 'conversions': 0}
                        
            # Если мы дошли до этого места, значит все попытки не удались
            return {'ad_id': ad_id, 'spend': 0, 'conversions': 0}
            
        except Exception as e:
            logger.error(f"[FacebookAdClient] Критическая ошибка при получении статистики: {str(e)}")
            logger.debug(traceback.format_exc())
            return {'ad_id': ad_id, 'spend': 0, 'conversions': 0}
    
    def disable_ad(self, ad_id, timeout=60):
        """
        Отключение объявления
        
        Args:
            ad_id (str): ID объявления
            timeout (int): Таймаут для запросов в секундах
            
        Returns:
            bool: Результат операции
        """
        logger.info(f"Попытка отключения объявления {ad_id}")
        
        # Сначала проверяем текущий статус объявления
        try:
            # Получаем информацию о текущем статусе объявления
            ad_info_response = requests.get(
                f'https://graph.facebook.com/v18.0/{ad_id}',
                params={
                    'access_token': self.access_token,
                    'fields': 'status,name'
                },
                timeout=timeout
            )
            
            if ad_info_response.status_code == 200:
                ad_info = ad_info_response.json()
                current_status = ad_info.get('status')
                ad_name = ad_info.get('name', 'Неизвестное имя')
                
                if current_status == 'PAUSED':
                    logger.info(f"Объявление {ad_id} ({ad_name}) уже отключено (статус: {current_status})")
                    return True
                
                logger.info(f"Текущий статус объявления {ad_id} ({ad_name}): {current_status}")
            else:
                logger.warning(f"Не удалось получить информацию об объявлении {ad_id}: {ad_info_response.status_code} - {ad_info_response.text}")
        except Exception as e:
            logger.warning(f"Ошибка при проверке статуса объявления {ad_id}: {str(e)}")
        
        # Пробуем отключить объявление через прямой API запрос
        try:
            response = requests.post(
                f'https://graph.facebook.com/v18.0/{ad_id}',
                params={
                    'access_token': self.access_token,
                    'status': 'PAUSED'
                },
                timeout=timeout
            )
            
            if response.status_code == 200:
                logger.info(f"Объявление {ad_id} отключено через прямой API запрос")
                
                # Проверяем, что объявление действительно отключено
                try:
                    verification_response = requests.get(
                        f'https://graph.facebook.com/v18.0/{ad_id}',
                        params={
                            'access_token': self.access_token,
                            'fields': 'status'
                        },
                        timeout=timeout
                    )
                    
                    if verification_response.status_code == 200:
                        verification_data = verification_response.json()
                        if verification_data.get('status') == 'PAUSED':
                            logger.info(f"Подтверждено отключение объявления {ad_id}")
                            return True
                        else:
                            logger.warning(f"Объявление {ad_id} не было отключено, текущий статус: {verification_data.get('status')}")
                    else:
                        logger.warning(f"Не удалось проверить статус объявления после отключения: {verification_response.status_code}")
                except Exception as ve:
                    logger.warning(f"Ошибка при проверке статуса после отключения: {str(ve)}")
                
                # Если не смогли проверить, но запрос прошел успешно, считаем что объявление отключено
                return True
            else:
                error_message = response.text
                logger.warning(f"Ошибка API при отключении объявления: {response.status_code} - {error_message}")
                
                # Анализируем ошибку
                try:
                    error_data = response.json()
                    error_code = error_data.get('error', {}).get('code')
                    error_message = error_data.get('error', {}).get('message')
                    
                    if error_code == 190:
                        logger.error(f"Ошибка авторизации (недействительный токен): {error_message}")
                    elif error_code == 10:
                        logger.error(f"Превышен лимит запросов API: {error_message}")
                    elif error_code == 100:
                        logger.error(f"Объявление не найдено: {error_message}")
                    else:
                        logger.error(f"Ошибка Facebook API (код {error_code}): {error_message}")
                except Exception:
                    logger.error(f"Не удалось распознать ошибку: {error_message}")
                
                # Продолжаем и пробуем через SDK
        except Exception as api_error:
            logger.warning(f"Ошибка при прямом запросе на отключение: {str(api_error)}")
            # Продолжаем и пробуем через SDK
        
        # Если прямой API запрос не сработал, пробуем через SDK
        try:
            from facebook_business.adobjects.ad import Ad
            
            ad = Ad(ad_id)
            ad.api = self.api  # Устанавливаем API
            
            result = ad.api_update(
                params={
                    'status': 'PAUSED',
                }
            )
            
            if result:
                logger.info(f"Объявление {ad_id} отключено через SDK")
                return True
            else:
                logger.error(f"Не удалось отключить объявление {ad_id} через SDK")
                return False
        except Exception as e:
            logger.error(f"Ошибка при отключении объявления {ad_id} через SDK: {str(e)}")
            
            # Последняя попытка - попробуем использовать низкоуровневый API запрос
            try:
                import urllib.request
                import urllib.parse
                import urllib.error
                
                url = f'https://graph.facebook.com/v18.0/{ad_id}?access_token={self.access_token}&status=PAUSED'
                req = urllib.request.Request(url, method='POST')
                
                try:
                    with urllib.request.urlopen(req, timeout=timeout) as response:
                        response_data = response.read().decode('utf-8')
                        logger.info(f"Объявление {ad_id} отключено через низкоуровневый API запрос: {response_data}")
                        return True
                except urllib.error.HTTPError as e:
                    logger.error(f"Ошибка HTTP при низкоуровневом запросе: {e.code} - {e.reason}")
                except urllib.error.URLError as e:
                    logger.error(f"Ошибка URL при низкоуровневом запросе: {e.reason}")
            except Exception as low_level_error:
                logger.error(f"Ошибка при низкоуровневом запросе: {str(low_level_error)}")
            
            return False
            
    def get_campaign_stats(self, campaign_id, fields=None, date_preset=None, time_range=None, timeout=60):
        """
        Получение статистики для кампании
        
        Args:
            campaign_id (str): ID кампании
            fields (list): Список полей для получения
            date_preset (str): Предустановленный временной диапазон (today, yesterday, last_7_days)
            time_range (dict): Настраиваемый временной диапазон в формате {'since': 'YYYY-MM-DD', 'until': 'YYYY-MM-DD'}
            timeout (int): Таймаут для запросов в секундах
            
        Returns:
            dict: Данные статистики кампании
        """
        if fields is None:
            fields = ['campaign_name', 'spend', 'impressions', 'clicks', 'ctr']
            
        try:
            # Формируем параметры запроса
            params = {
                'access_token': self.access_token,
                'fields': ','.join(fields)
            }
            
            # Добавляем временной диапазон
            if time_range:
                params['time_range'] = json.dumps(time_range)
            elif date_preset:
                params['date_preset'] = date_preset
            else:
                # По умолчанию используем сегодняшний день
                params['date_preset'] = 'today'
                
            # Выполняем прямой запрос к API
            logger.info(f"Запрос статистики для кампании {campaign_id}")
            response = requests.get(
                f'https://graph.facebook.com/v18.0/{campaign_id}/insights',
                params=params,
                timeout=timeout
            )
            
            if response.status_code != 200:
                logger.warning(f"Ошибка API: {response.status_code} - {response.text}")
                # Продолжаем и пробуем через SDK
            else:
                data = response.json()
                insights = data.get('data', [])
                
                if insights:
                    logger.info(f"Получена статистика для кампании {campaign_id} через прямой запрос")
                    return insights[0]  # Возвращаем первый результат
                else:
                    logger.warning(f"Пустой результат для кампании {campaign_id}")
                    return {'campaign_id': campaign_id, 'spend': 0}
                    
        except Exception as api_error:
            logger.warning(f"Ошибка при прямом запросе статистики: {str(api_error)}")
            # Продолжаем и пробуем через SDK
            
        # Если прямой запрос не сработал, пробуем через SDK
        try:
            campaign = Campaign(campaign_id)
            
            # Настраиваем параметры
            sdk_params = {}
            if time_range:
                sdk_params['time_range'] = time_range
            elif date_preset:
                sdk_params['date_preset'] = date_preset
            else:
                sdk_params['date_preset'] = 'today'
                
            insights = campaign.get_insights(
                fields=fields,
                params=sdk_params
            )
            
            if insights:
                logger.info(f"Получена статистика для кампании {campaign_id} через SDK")
                return insights[0]
            else:
                logger.warning(f"Пустой результат для кампании {campaign_id} через SDK")
                return {'campaign_id': campaign_id, 'spend': 0}
                
        except Exception as e:
            logger.error(f"Ошибка при получении статистики для кампании {campaign_id}: {str(e)}")
            return {'campaign_id': campaign_id, 'spend': 0}
            
    def update_campaign_status(self, campaign_id, status, timeout=60):
        """
        Обновление статуса кампании
        
        Args:
            campaign_id (str): ID кампании
            status (str): Новый статус ('ACTIVE', 'PAUSED', 'ARCHIVED')
            timeout (int): Таймаут для запросов в секундах
            
        Returns:
            bool: Результат операции
        """
        try:
            # Сначала пробуем прямой API запрос
            response = requests.post(
                f'https://graph.facebook.com/v18.0/{campaign_id}',
                params={
                    'access_token': self.access_token,
                    'status': status
                },
                timeout=timeout
            )
            
            if response.status_code == 200:
                logger.info(f"Статус кампании {campaign_id} изменен на {status} через прямой API запрос")
                return True
            else:
                logger.warning(f"Ошибка API при изменении статуса кампании: {response.status_code} - {response.text}")
                # Продолжаем и пробуем через SDK
        except Exception as api_error:
            logger.warning(f"Ошибка при прямом запросе на изменение статуса: {str(api_error)}")
            # Продолжаем и пробуем через SDK
        
        # Если прямой API запрос не сработал, пробуем через SDK
        try:
            campaign = Campaign(campaign_id)
            
            # Преобразование статуса в формат SDK если необходимо
            sdk_status = status
            if status == 'ACTIVE':
                sdk_status = Campaign.Status.active
            elif status == 'PAUSED':
                sdk_status = Campaign.Status.paused
            elif status == 'ARCHIVED':
                sdk_status = Campaign.Status.archived
                
            result = campaign.api_update(
                params={
                    'status': sdk_status,
                }
            )
            logger.info(f"Статус кампании {campaign_id} изменен на {status} через SDK")
            return result
        except Exception as e:
            logger.error(f"Ошибка при изменении статуса кампании {campaign_id}: {str(e)}")
            return False