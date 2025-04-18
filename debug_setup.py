#!/usr/bin/env python
"""
Скрипт для отладки настроек Setup и проверки кампаний
"""
from app import create_app
from app.models.setup import Setup, ThresholdEntry, CampaignSetup
from app.services.fb_api_client import FacebookAdClient
from app.models.facebook_token import FacebookToken
from app.models.user import User

def check_setup_details():
    """Выводит информацию о настройках Setup"""
    app = create_app()
    with app.app_context():
        setups = Setup.query.all()
        print(f"Найдено {len(setups)} настроек Setup")
        
        for setup in setups:
            print(f"\nSetup ID: {setup.id}")
            print(f"Имя: {setup.name}")
            print(f"Период проверки: {setup.check_period}")
            print(f"Интервал проверки: {setup.check_interval} минут")
            print(f"Активен: {setup.is_active}")
            
            # Получаем пороговые значения
            thresholds = setup.get_thresholds_as_list()
            print(f"Пороги ({len(thresholds)}):")
            for threshold in thresholds:
                print(f"  Расходы: ${threshold['spend']}, Конверсии: {threshold['conversions']}")
            
            # Получаем префиксы REF, если они есть
            if hasattr(setup, 'ref_prefixes'):
                print(f"REF префиксы: {setup.ref_prefixes}")
            else:
                print("REF префиксы: не найдены в модели")
            
            # Получаем связанные кампании
            campaigns = CampaignSetup.query.filter_by(setup_id=setup.id).all()
            print(f"Связанные кампании ({len(campaigns)}):")
            for campaign in campaigns:
                print(f"  ID: {campaign.campaign_id}")
                print(f"  Имя: {campaign.campaign_name}")
                print(f"  Активна: {campaign.is_active}")
                print(f"  Последняя проверка: {campaign.last_checked}")

def check_campaign_status(campaign_id):
    """Проверяет статус кампании через API Facebook"""
    app = create_app()
    with app.app_context():
        # Находим настройку кампании
        campaign_setup = CampaignSetup.query.filter_by(campaign_id=campaign_id).first()
        if not campaign_setup:
            print(f"Кампания {campaign_id} не найдена в базе данных")
            return
        
        # Получаем пользователя и токен
        user = User.query.get(campaign_setup.user_id)
        if not user:
            print(f"Пользователь {campaign_setup.user_id} не найден")
            return
        
        # Получаем активный токен пользователя
        if user.active_token_id:
            token = FacebookToken.query.get(user.active_token_id)
        else:
            token = FacebookToken.query.filter_by(user_id=user.id, is_active=True).first()
            
        if not token:
            print("Активный токен Facebook не найден")
            return
        
        # Инициализируем Facebook API
        fb_api = FacebookAdClient(
            access_token=token.access_token,
            app_id=token.app_id,
            app_secret=token.app_secret
        )
        
        # Получаем статистику кампании за сегодня
        print(f"Получаем статистику для кампании {campaign_id}...")
        today_stats = fb_api.get_campaign_stats(
            campaign_id=campaign_id,
            fields=['campaign_name', 'spend'],
            date_preset='today'
        )
        
        print("\nСтатистика за сегодня:")
        print(f"Расходы: ${today_stats.get('spend', 0)}")
        print(f"Имя кампании: {today_stats.get('campaign_name', 'Н/Д')}")
        
        # Проверяем, какой API-вызов делается для отключения кампании
        print("\nТестовый вызов API для отключения кампании (без реального отключения):")
        import requests
        try:
            # Только формируем URL, но не выполняем запрос
            url = f'https://graph.facebook.com/v18.0/{campaign_id}'
            params = {
                'access_token': token.access_token,
                'status': 'PAUSED'
            }
            print(f"URL: {url}")
            print(f"Параметры: {params}")
        except Exception as e:
            print(f"Ошибка при формировании запроса: {str(e)}")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        campaign_id = sys.argv[1]
        check_campaign_status(campaign_id)
    else:
        check_setup_details() 