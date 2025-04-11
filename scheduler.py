import os
import sys
import logging
from datetime import datetime
import time
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from flask import Flask

from app import create_app, db
from app.models.user import User
from app.models.setup import Setup, CampaignSetup
from app.models.token import FacebookToken, FacebookTokenAccount
from app.services.fb_api_client import FacebookAdClient
from app.services.ad_monitor import AdMonitor

app = create_app()
app.app_context().push()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("scheduler.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Настройка планировщика
jobstores = {
    'default': SQLAlchemyJobStore(url=app.config['SQLALCHEMY_DATABASE_URI'])
}

scheduler = BackgroundScheduler(jobstores=jobstores)

def find_suitable_token(user, campaign_id, account_id=None):
    """
    Находит подходящий токен для работы с кампанией
    
    Args:
        user (User): Объект пользователя
        campaign_id (str): ID кампании
        account_id (str, optional): ID рекламного аккаунта
    
    Returns:
        FacebookToken: Объект токена или None, если подходящий токен не найден
    """
    # Если известен ID аккаунта, ищем токены с доступом к нему
    if account_id:
        # Находим все токены пользователя, имеющие доступ к этому аккаунту и имеющие статус 'valid'
        token_accounts = FacebookTokenAccount.query.join(FacebookToken).filter(
            FacebookTokenAccount.account_id == account_id,
            FacebookToken.user_id == user.id,
            FacebookToken.status == 'valid'
        ).all()
        
        # Если нашли подходящие токены, возвращаем первый
        if token_accounts:
            return token_accounts[0].token
    
    # Если аккаунт неизвестен или токены для него не найдены,
    # вернем любой действующий токен пользователя
    valid_token = FacebookToken.query.filter_by(
        user_id=user.id,
        status='valid'
    ).first()
    
    return valid_token

def check_campaign(user_id, campaign_setup_id):
    """
    Проверка кампании по расписанию
    
    Args:
        user_id (int): ID пользователя
        campaign_setup_id (int): ID настройки кампании
    """
    with app.app_context():
        try:
            # Получение настроек кампании
            campaign_setup = CampaignSetup.query.get(campaign_setup_id)
            
            if not campaign_setup or not campaign_setup.is_active:
                logger.warning(f"CampaignSetup {campaign_setup_id} is inactive or deleted")
                return
            
            # Получение сетапа
            setup = Setup.query.get(campaign_setup.setup_id)
            if not setup or not setup.is_active:
                logger.warning(f"Setup {campaign_setup.setup_id} is inactive or deleted")
                return
            
            # Получение пользователя
            user = User.query.get(user_id)
            if not user:
                logger.warning(f"User {user_id} not found")
                return
            
            # Получение ID аккаунта из ID кампании (если возможно)
            # Формат ID кампании в FB обычно: act_123456789_111111
            campaign_id = campaign_setup.campaign_id
            account_id = None
            
            # Проверка, содержит ли ID кампании ID аккаунта
            campaign_parts = campaign_id.split('_')
            if len(campaign_parts) > 1 and campaign_parts[0] == 'act':
                account_id = f"act_{campaign_parts[1]}"
            
            # Находим подходящий токен
            token = find_suitable_token(user, campaign_id, account_id)
            
            # Если не нашли подходящий токен, но есть стандартные настройки
            if not token and user.fb_access_token:
                # Инициализация клиента FB API с стандартными настройками
                fb_client = FacebookAdClient(
                    access_token=user.fb_access_token,
                    app_id=user.fb_app_id,
                    app_secret=user.fb_app_secret,
                    ad_account_id=user.fb_account_id
                )
                logger.info(f"Using default FB credentials for campaign {campaign_id}")
            elif token:
                # Инициализация клиента FB API с токеном
                fb_client = FacebookAdClient(token_obj=token)
                if account_id:
                    fb_client.set_account(account_id)
                logger.info(f"Using token '{token.name}' for campaign {campaign_id}")
            else:
                logger.error(f"No valid token or credentials found for campaign {campaign_id}")
                return
            
            # Инициализация монитора
            monitor = AdMonitor(fb_client)
            
            # Установка пороговых значений из сетапа
            monitor.set_thresholds(setup.get_thresholds_as_list())
            
            # Проверка кампании
            logger.info(f"Checking campaign {campaign_setup.campaign_id} with setup {setup.name}")
            results = monitor.process_campaign(
                campaign_id=campaign_setup.campaign_id,
                date_preset='today',
                auto_disable=True
            )
            
            # Обновление времени последней проверки
            campaign_setup.last_checked = datetime.utcnow()
            db.session.commit()
            
            # Логирование результатов
            ads_checked = len(results)
            ads_disabled = sum(1 for r in results if r.get('disabled', False))
            
            logger.info(f"Campaign {campaign_setup.campaign_id} checked: "
                       f"{ads_checked} ads total, {ads_disabled} ads disabled")
        
        except Exception as e:
            logger.error(f"Error checking campaign {campaign_setup_id}: {str(e)}")


def setup_jobs():
    """Настройка заданий для планировщика"""
    with app.app_context():
        # Очистка всех существующих заданий
        scheduler.remove_all_jobs()
        
        # Получение всех активных назначений кампаний
        campaign_setups = (CampaignSetup.query
                          .join(Setup)
                          .filter(CampaignSetup.is_active == True)
                          .filter(Setup.is_active == True)
                          .all())
        
        for cs in campaign_setups:
            interval = cs.setup.check_interval
            job_id = f"campaign_{cs.id}"
            
            scheduler.add_job(
                check_campaign,
                trigger=IntervalTrigger(minutes=interval),
                args=[cs.user_id, cs.id],
                id=job_id,
                replace_existing=True
            )
            
            logger.info(f"Scheduled job {job_id} for campaign {cs.campaign_id}, "
                       f"interval: {interval} minutes")


def main():
    """Запуск планировщика"""
    logger.info("Starting scheduler for Facebook Ads Monitor")
    
    # Запуск планировщика
    scheduler.start()
    
    # Настройка заданий
    setup_jobs()
    
    # Запуск задачи обновления заданий каждый час
    scheduler.add_job(
        setup_jobs,
        trigger=IntervalTrigger(hours=1),
        id='refresh_jobs',
        replace_existing=True
    )
    
    try:
        # Бесконечный цикл для работы планировщика
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        logger.info("Scheduler stopped")


if __name__ == "__main__":
    main()