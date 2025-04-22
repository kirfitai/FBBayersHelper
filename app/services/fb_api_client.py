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

# Создаем улучшенную версию requests.get и requests.post с подробным логированием
def detailed_get(url, params=None, timeout=30, **kwargs):
    """
    Обертка над requests.get с детальным логированием
    """
    log_prefix = "[DETAILED_HTTP]"
    # Логируем запрос
    logger.info(f"{log_prefix} Отправка GET запроса на URL: {url}")
    logger.info(f"{log_prefix} Параметры GET запроса: {json.dumps(params, ensure_ascii=False, indent=2)}")
    
    if 'headers' in kwargs:
        safe_headers = {k: v for k, v in kwargs['headers'].items() if 'token' not in k.lower()}
        logger.info(f"{log_prefix} Заголовки GET запроса: {json.dumps(safe_headers, ensure_ascii=False)}")
    
    start_time = time.time()
    try:
        response = requests.get(url, params=params, timeout=timeout, **kwargs)
        elapsed = time.time() - start_time
        
        # Логируем ответ
        logger.info(f"{log_prefix} GET запрос выполнен за {elapsed:.3f} секунд")
        logger.info(f"{log_prefix} Получен ответ: Статус {response.status_code}")
        
        try:
            if 'application/json' in response.headers.get('Content-Type', ''):
                json_resp = response.json()
                # Упрощенное логирование для больших ответов
                if isinstance(json_resp, dict) and len(str(json_resp)) > 500:
                    logger.info(f"{log_prefix} Получен JSON-ответ (сокращено): {str(json_resp)[:300]}...")
                    if 'error' in json_resp:
                        logger.error(f"{log_prefix} Ошибка в ответе: {json.dumps(json_resp.get('error'), ensure_ascii=False)}")
                else:
                    logger.info(f"{log_prefix} Получен JSON-ответ: {json.dumps(json_resp, ensure_ascii=False)}")
            else:
                logger.info(f"{log_prefix} Получен не-JSON ответ, длина: {len(response.text)} символов")
        except Exception as json_err:
            logger.error(f"{log_prefix} Ошибка при обработке ответа: {str(json_err)}")
            
        return response
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"{log_prefix} Ошибка GET запроса после {elapsed:.3f} секунд: {str(e)}")
        raise

def detailed_post(url, data=None, json=None, params=None, timeout=30, **kwargs):
    """
    Обертка над requests.post с детальным логированием
    """
    log_prefix = "[DETAILED_HTTP]"
    # Логируем запрос
    logger.info(f"{log_prefix} Отправка POST запроса на URL: {url}")
    
    if params:
        logger.info(f"{log_prefix} Параметры URL POST запроса: {json.dumps(params, ensure_ascii=False, indent=2)}")
    
    if data:
        try:
            data_str = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
            logger.info(f"{log_prefix} Данные POST запроса (data): {data_str}")
        except Exception as data_err:
            logger.info(f"{log_prefix} Данные POST запроса (data): {str(data)[:500]}")
    
    if json:
        logger.info(f"{log_prefix} Данные POST запроса (json): {json.dumps(json, ensure_ascii=False, indent=2)}")
    
    if 'headers' in kwargs:
        safe_headers = {k: v for k, v in kwargs['headers'].items() if 'token' not in k.lower()}
        logger.info(f"{log_prefix} Заголовки POST запроса: {safe_headers}")
    
    start_time = time.time()
    try:
        response = requests.post(url, data=data, json=json, params=params, timeout=timeout, **kwargs)
        elapsed = time.time() - start_time
        
        # Логируем ответ
        logger.info(f"{log_prefix} POST запрос выполнен за {elapsed:.3f} секунд")
        logger.info(f"{log_prefix} Получен ответ: Статус {response.status_code}")
        
        try:
            if 'application/json' in response.headers.get('Content-Type', ''):
                json_resp = response.json()
                # Упрощенное логирование для больших ответов
                if isinstance(json_resp, dict) and len(str(json_resp)) > 500:
                    logger.info(f"{log_prefix} Получен JSON-ответ (сокращено): {str(json_resp)[:300]}...")
                    if 'error' in json_resp:
                        logger.error(f"{log_prefix} Ошибка в ответе: {json.dumps(json_resp.get('error'), ensure_ascii=False)}")
                else:
                    logger.info(f"{log_prefix} Получен JSON-ответ: {json.dumps(json_resp, ensure_ascii=False)}")
            else:
                logger.info(f"{log_prefix} Получен не-JSON ответ, длина: {len(response.text)} символов")
        except Exception as json_err:
            logger.error(f"{log_prefix} Ошибка при обработке ответа: {str(json_err)}")
            
        return response
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"{log_prefix} Ошибка POST запроса после {elapsed:.3f} секунд: {str(e)}")
        raise

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
            url = f'{FB_GRAPH_URL}/{self.ad_account_id}/campaigns'
            
            while url and len(all_campaigns) < limit:
                logger.info(f"Запрашиваем страницу: {url}")
                
                response = detailed_get(
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
                    
                    # Формируем URL с параметрами напрямую в адресной строке
                    fields = "id,name,status,effective_status"
                    full_url = f"{FB_GRAPH_URL}/{campaign_id}/ads?fields={fields}&limit=500&access_token={self.access_token}"
                    
                    logger.info(f"[FacebookAdClient] Запрос на URL: {full_url.replace(self.access_token, 'ACCESS_TOKEN_HIDDEN')}")
                    
                    # Отправляем запрос напрямую
                    response = requests.get(full_url, timeout=current_timeout)
                    
                    if response.status_code == 200:
                        ads_data = response.json().get('data', [])
                        
                        if ads_data:
                            logger.info(f"[FacebookAdClient] Получено {len(ads_data)} объявлений")
                            
                            # Логируем первые несколько объявлений для отладки
                            logger.info(f"[FacebookAdClient] Пример данных: {str(ads_data[:2])}")
                            
                            # Создаем объекты для каждого объявления
                            ads = []
                            active_count = 0
                            for ad_data in ads_data:
                                try:
                                    ad = SimpleNamespace()
                                    ad.id = ad_data.get('id')
                                    ad.name = ad_data.get('name')
                                    ad.status = ad_data.get('status', 'UNKNOWN')
                                    ad.effective_status = ad_data.get('effective_status', 'UNKNOWN')
                                    
                                    # Определяем активность объявления по effective_status
                                    # Это более точный показатель фактического статуса объявления
                                    if ad.effective_status == 'ACTIVE':
                                        active_count += 1
                                    
                                    if hasattr(ad, 'id') and ad.id:
                                        ads.append(ad)
                                    else:
                                        logger.warning(f"[FacebookAdClient] Пропущено объявление без ID: {ad_data}")
                                except Exception as ad_error:
                                    logger.error(f"[FacebookAdClient] Ошибка при обработке объявления: {str(ad_error)}")
                            
                            logger.info(f"[FacebookAdClient] Всего активных объявлений (effective_status=ACTIVE): {active_count}")
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
                        # Логируем полный ответ для отладки
                        logger.error(f"[FacebookAdClient] Ответ API с кодом {response.status_code}: {response.text}")
                        
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
            logger.error(traceback.format_exc())
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
                    
                    # Обязательная пауза между запросами для соблюдения лимитов API
                    # Чем больше попыток, тем дольше пауза
                    if current_attempt > 1:
                        pause_time = 2 * current_attempt
                        logger.info(f"[FacebookAdClient] Пауза {pause_time} секунд перед запросом для соблюдения лимитов API")
                        time.sleep(pause_time)
                    
                    # Формируем URL с параметрами напрямую в адресной строке
                    fields_param = ','.join(fields)
                    base_url = f"{FB_GRAPH_URL}/{ad_id}/insights?fields={fields_param}"
                    
                    if time_range:
                        # Преобразуем time_range в JSON строку и экранируем для URL
                        import urllib.parse
                        time_range_json = json.dumps(time_range)
                        time_range_param = urllib.parse.quote(time_range_json)
                        url = f"{base_url}&time_range={time_range_param}&access_token={self.access_token}"
                    else:
                        # Используем date_preset
                        url = f"{base_url}&date_preset={date_preset}&access_token={self.access_token}"
                    
                    logger.info(f"[FacebookAdClient] Запрос на URL: {url.replace(self.access_token, 'ACCESS_TOKEN_HIDDEN')}")
                    
                    # Отправляем запрос напрямую
                    response = requests.get(url, timeout=current_timeout)
                    
                    if response.status_code == 200:
                        data = response.json()
                        insights_data = data.get('data', [])
                        
                        # Логируем ответ для отладки (без конфиденциальной информации)
                        logger.info(f"[FacebookAdClient] Ответ API: {json.dumps(data)[:500]}...")
                        
                        if insights_data and len(insights_data) > 0:
                            # Обрабатываем результаты - берем первый элемент из массива data
                            first_insight = insights_data[0]
                            
                            # Создаем результат с ключевыми полями
                            result = {
                                'ad_id': ad_id,
                                'spend': float(first_insight.get('spend', 0)),
                                'date_start': first_insight.get('date_start'),
                                'date_stop': first_insight.get('date_stop'),
                                'conversions': 0  # По умолчанию ставим 0 конверсий
                            }
                            
                            # Если есть actions, считаем конверсии
                            if 'actions' in first_insight:
                                conversion_types = ['purchase', 'web_in_store_purchase', 'onsite_web_app_purchase']
                                for action in first_insight['actions']:
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
                                
                            # Возвращаем пустой результат с датами из запроса
                            if time_range:
                                return {
                                    'ad_id': ad_id, 
                                    'spend': 0, 
                                    'conversions': 0,
                                    'date_start': time_range.get('since'),
                                    'date_stop': time_range.get('until')
                                }
                            else:
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
            logger.error(traceback.format_exc())
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
        
        # Добавляем небольшую паузу перед отключением
        pause_time = 1
        logger.info(f"Пауза {pause_time} секунд перед запросом на отключение")
        time.sleep(pause_time)
        
        # Формируем URL запроса
        api_url = f"{FB_GRAPH_URL}/{ad_id}"
        params = {
            'status': 'PAUSED',
            'access_token': self.access_token
        }
        
        logger.info(f"Отправка запроса на URL: {api_url} с параметром status=PAUSED")
        
        try:
            # Отправляем POST запрос с параметрами
            response = requests.post(api_url, params=params, timeout=timeout)
            
            # Подробно логируем ответ
            logger.info(f"Статус ответа: {response.status_code}")
            logger.info(f"Тело ответа: {response.text}")
            
            if response.status_code == 200:
                try:
                    response_data = response.json()
                    logger.info(f"Ответ API на отключение: {response_data}")
                    
                    # Проверяем success в ответе
                    if response_data.get('success'):
                        logger.info(f"Объявление {ad_id} успешно отключено (success=true в ответе)")
                        return True
                    else:
                        logger.warning(f"API вернул успешный код, но без success=true: {response_data}")
                        # Если получили код 200, считаем операцию успешной даже без success=true в ответе
                        return True
                except json.JSONDecodeError:
                    logger.warning(f"Не удалось декодировать JSON из ответа: {response.text}")
                    # Если получили код 200, считаем операцию успешной даже при ошибке парсинга JSON
                    return True
            else:
                error_message = response.text
                logger.warning(f"Ошибка API при отключении объявления: {response.status_code} - {error_message}")
                
                # Анализируем ошибку
                try:
                    error_data = response.json()
                    error_code = error_data.get('error', {}).get('code')
                    error_message = error_data.get('error', {}).get('message')
                    
                    # Проверяем код ошибки на превышение лимита
                    if error_code in [17, 4] or (error_message and 'limit' in error_message.lower()):
                        logger.warning(f"Превышен лимит запросов к API: {error_message}")
                        # Делаем паузу и пробуем еще раз
                        time.sleep(10)
                        return self.disable_ad(ad_id, timeout)
                        
                    if error_code == 190:
                        logger.error(f"Ошибка авторизации (недействительный токен): {error_message}")
                    elif error_code == 100:
                        logger.error(f"Объявление не найдено: {error_message}")
                    else:
                        logger.error(f"Ошибка Facebook API (код {error_code}): {error_message}")
                except Exception:
                    logger.error(f"Не удалось распознать ошибку: {error_message}")
                
                return False
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка сети при отключении объявления {ad_id}: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Неожиданная ошибка при отключении объявления {ad_id}: {str(e)}")
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
            response = detailed_get(
                f'{FB_GRAPH_URL}/{campaign_id}/insights',
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
            response = detailed_post(
                f'{FB_GRAPH_URL}/{campaign_id}',
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