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
            
            # Получение пользователя и его учетных данных
            user = User.query.get(user_id)
            if not user or not user.fb_access_token:
                logger.warning(f"User {user_id} has no Facebook API credentials")
                return
            
            # Инициализация клиента FB API
            fb_client = FacebookAdClient(
                access_token=user.fb_access_token,
                app_id=user.fb_app_id,
                app_secret=user.fb_app_secret,
                ad_account_id=user.fb_account_id
            )
            
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