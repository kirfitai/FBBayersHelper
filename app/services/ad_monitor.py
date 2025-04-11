import logging
import pandas as pd
from datetime import datetime

class AdMonitor:
    def __init__(self, fb_client):
        """
        Инициализация монитора объявлений
        
        Args:
            fb_client (FacebookAdClient): Клиент для работы с FB API
        """
        self.fb_client = fb_client
        self.logger = self._setup_logger()
        self.thresholds = []
        
    def _setup_logger(self):
        """Настройка логирования"""
        logger = logging.getLogger('ad_monitor')
        logger.setLevel(logging.INFO)
        
        # Проверяем, есть ли уже обработчики
        if not logger.handlers:
            handler = logging.FileHandler('ad_monitor.log')
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            
        return logger
    
    def set_thresholds(self, thresholds):
        """
        Установка пороговых значений
        
        Args:
            thresholds (list): Список словарей с порогами в формате [{"spend": 10, "conversions": 2}, ...]
        """
        self.thresholds = thresholds
        # Создание DataFrame для удобного поиска пороговых значений
        self.thresholds_df = pd.DataFrame(self.thresholds)
    
    def get_threshold_conversions(self, spend):
        """
        Получение требуемого количества конверсий для данного расхода
        
        Args:
            spend (float): Расход на рекламу
            
        Returns:
            int: Требуемое количество конверсий
        """
        # Проверка, есть ли пороги
        if not hasattr(self, 'thresholds_df') or self.thresholds_df.empty:
            return 0
            
        # Находим максимальный порог, который не превышает текущие затраты
        applicable_thresholds = self.thresholds_df[self.thresholds_df['spend'] <= spend]
        
        if applicable_thresholds.empty:
            return 0
        
        # Берем порог с максимальными затратами
        max_threshold = applicable_thresholds.loc[applicable_thresholds['spend'].idxmax()]
        return max_threshold['conversions']
    
    def check_ad_performance(self, ad_id, date_preset='today'):
        """
        Проверка производительности объявления и принятие решения
        
        Args:
            ad_id (str): ID объявления
            date_preset (str): Период времени
            
        Returns:
            dict: Результат проверки с решением
        """
        # Получение данных о расходах и конверсиях
        ad_data = self.fb_client.get_ad_insights(ad_id, date_preset)
        
        spend = ad_data['spend']
        actual_conversions = ad_data['conversions']
        
        # Определение требуемого количества конверсий
        required_conversions = self.get_threshold_conversions(spend)
        
        # Формирование результата
        result = {
            'ad_id': ad_id,
            'spend': spend,
            'actual_conversions': actual_conversions,
            'required_conversions': required_conversions,
            'datetime': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'should_disable': False
        }
        
        # Проверка необходимости отключения
        if spend > 0 and actual_conversions < required_conversions:
            result['should_disable'] = True
            self.logger.warning(
                f"Ad {ad_id} should be disabled: spent ${spend}, "
                f"has {actual_conversions} conversions, requires {required_conversions}"
            )
        
        return result
    
    def process_campaign(self, campaign_id, date_preset='today', auto_disable=False):
        """
        Обработка всех объявлений в кампании
        
        Args:
            campaign_id (str): ID кампании
            date_preset (str): Период времени
            auto_disable (bool): Автоматически отключать объявления
            
        Returns:
            list: Результаты проверки для всех объявлений
        """
        # Получение всех объявлений в кампании
        ads = self.fb_client.get_ads_in_campaign(campaign_id)
        
        results = []
        for ad in ads:
            result = self.check_ad_performance(ad['id'], date_preset)
            
            # Отключение объявления при необходимости
            if auto_disable and result['should_disable']:
                disable_success = self.fb_client.disable_ad(ad['id'])
                result['disabled'] = disable_success
                
                if disable_success:
                    self.logger.info(f"Ad {ad['id']} has been disabled")
                else:
                    self.logger.error(f"Failed to disable ad {ad['id']}")
            
            results.append(result)
        
        return results