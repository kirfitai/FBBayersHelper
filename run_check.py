#!/usr/bin/env python
"""
Скрипт для ручного запуска проверки кампаний.
Можно использовать для тестирования и отладки механизма проверки.
"""

import os
import sys
import logging
from datetime import datetime

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

def main():
    logger.info("Запуск ручной проверки кампаний...")
    
    # Импортируем приложение и контекст
    from app import create_app, db
    from app.models.setup import CampaignSetup
    from app.scheduler import check_campaign_thresholds
    
    app = create_app()
    with app.app_context():
        # Получаем все активные назначения кампаний
        campaign_setups = CampaignSetup.query.filter_by(is_active=True).all()
        logger.info(f"Найдено {len(campaign_setups)} активных назначений кампаний")
        
        for cs in campaign_setups:
            logger.info(f"Проверка кампании {cs.campaign_id} (назначение {cs.id})...")
            try:
                result = check_campaign_thresholds(cs.campaign_id)
                if result:
                    logger.info(f"Проверка кампании {cs.campaign_id} завершена успешно")
                else:
                    logger.warning(f"Проверка кампании {cs.campaign_id} завершена с ошибками")
                
                # Обновляем время последней проверки
                cs.last_checked = datetime.utcnow()
                db.session.commit()
            except Exception as e:
                logger.error(f"Ошибка при проверке кампании {cs.campaign_id}: {str(e)}")
    
    logger.info("Проверка кампаний завершена")

if __name__ == "__main__":
    main() 