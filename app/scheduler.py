import os
import sys
import logging
from datetime import datetime, timedelta
from sqlalchemy import and_, func, or_
from app.extensions import db
from app.models.setup import Setup, CampaignSetup
from app.models.user import User
from app.services.fb_api_client import FacebookAdClient
from app.models.facebook_token import FacebookToken
from app.models.conversion import Conversion

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def calculate_date_range_for_period(check_period):
    """
    Рассчитывает диапазон дат на основе периода проверки
    
    Args:
        check_period (str): Период проверки ('today', 'last2days', 'last3days', 'last7days', 'alltime')
        
    Returns:
        tuple: (since_date, until_date) в формате YYYY-MM-DD
    """
    today = datetime.now().date()
    until_date = today.strftime('%Y-%m-%d')
    
    # Если check_period None, устанавливаем по умолчанию 'today'
    if check_period is None:
        check_period = 'today'
        
    if check_period == 'today':
        since_date = today.strftime('%Y-%m-%d')
    elif check_period == 'last2days':
        since_date = (today - timedelta(days=1)).strftime('%Y-%m-%d')
    elif check_period == 'last3days':
        since_date = (today - timedelta(days=2)).strftime('%Y-%m-%d')
    elif check_period == 'last7days':
        since_date = (today - timedelta(days=6)).strftime('%Y-%m-%d')
    elif check_period == 'alltime':
        # Используем дату, достаточно далеко в прошлом
        since_date = (today - timedelta(days=365)).strftime('%Y-%m-%d')
    else:
        # Если неизвестный период, используем сегодня
        since_date = today.strftime('%Y-%m-%d')
        logger.warning(f"Неизвестный период проверки: {check_period}, используется 'today'")
    
    return since_date, until_date

def check_campaign_thresholds(campaign_id=None, check_period=None):
    """
    Проверяет пороги кампаний и отключает объявления в кампаниях, если пороги превышены.
    Проверка выполняется для каждого объявления отдельно.
    
    Args:
        campaign_id (str, optional): ID кампании для проверки. По умолчанию проверяются все кампании.
        check_period (str, optional): Период проверки ('today', 'last2days', 'last3days', 'last7days', 'alltime').
            По умолчанию используется период из настройки кампании.
    
    Returns:
        bool: True если все проверки выполнены успешно, иначе False
    """
    try:
        # Создаем строку для вывода отчета по проверке
        report_output = []
        report_output.append("=" * 80)
        report_output.append("ОТЧЕТ ПО ПРОВЕРКЕ ОБЪЯВЛЕНИЙ")
        report_output.append("=" * 80)
        
        # Если campaign_id указан, проверяем только эту кампанию
        if campaign_id:
            campaign_setups = CampaignSetup.query.filter(
                CampaignSetup.campaign_id == campaign_id,
                CampaignSetup.is_active == True
            ).all()
            if not campaign_setups:
                logger.warning(f"Кампания {campaign_id} не найдена или не активна")
                return False
        else:
            # Получаем все активные настройки кампаний
            campaign_setups = CampaignSetup.query.filter(
                CampaignSetup.is_active == True
            ).all()
            
        if not campaign_setups:
            logger.info("Нет активных настроек кампаний для проверки")
            return True
            
        # Обработка каждой кампании
        for campaign_setup in campaign_setups:
            try:
                setup = Setup.query.get(campaign_setup.setup_id)
                if not setup or not setup.is_active:
                    logger.info(f"Setup {campaign_setup.setup_id} не активен или не существует")
                    continue
                
                # Используем переданный период проверки или берем из настройки
                period = check_period if check_period is not None else setup.check_period
                # Если период всё еще None, используем 'today'
                if period is None:
                    period = 'today'
                    
                since_date, until_date = calculate_date_range_for_period(period)
                
                # Получаем пороги для настройки
                thresholds = setup.get_thresholds_as_list()
                if not thresholds:
                    logger.info(f"Нет порогов для настройки {setup.id}")
                    continue
                
                report_output.append(f"\nКампания: {campaign_setup.campaign_id} - {campaign_setup.campaign_name or 'Без имени'}")
                report_output.append(f"Период проверки: {period}")
                report_output.append(f"Диапазон дат: {since_date} - {until_date}")
                
                # Выводим информацию о порогах
                report_output.append("\nНастроенные пороги:")
                for i, threshold in enumerate(sorted(thresholds, key=lambda x: x['spend'])):
                    report_output.append(f"  {i+1}. Расход: ${threshold['spend']}, Требуемые конверсии: {threshold['conversions']}")
                
                # Получаем пользователя
                user = User.query.get(campaign_setup.user_id)
                if not user:
                    logger.error(f"Пользователь {campaign_setup.user_id} не найден")
                    continue
                
                # Получаем активный токен пользователя
                if user.active_token_id:
                    token = FacebookToken.query.get(user.active_token_id)
                else:
                    token = FacebookToken.query.filter_by(user_id=user.id, is_active=True).first()
                
                if not token:
                    logger.error(f"Активный токен Facebook не найден для пользователя {user.id}")
                    continue
                
                # Инициализируем Facebook API
                fb_api = FacebookAdClient(
                    access_token=token.access_token,
                    app_id=token.app_id,
                    app_secret=token.app_secret,
                    ad_account_id=token.account_id
                )
                
                # Получаем префиксы для отслеживания конверсий
                ref_prefixes = setup.ref_prefixes.split(',') if hasattr(setup, 'ref_prefixes') and setup.ref_prefixes else []
                ref_prefixes = [prefix.strip() for prefix in ref_prefixes if prefix.strip()]
                
                if ref_prefixes:
                    report_output.append(f"\nПрефиксы REF для отслеживания конверсий: {', '.join(ref_prefixes)}")
                else:
                    report_output.append("\nВнимание: префиксы REF не настроены!")
                
                # Получаем все объявления в кампании
                ads = fb_api.get_ads_in_campaign(campaign_setup.campaign_id)
                
                if not ads:
                    report_output.append("\nВ кампании не найдено объявлений")
                    continue
                
                report_output.append(f"\nНайдено {len(ads)} объявлений в кампании")
                report_output.append("\nПРОВЕРКА ОБЪЯВЛЕНИЙ:")
                report_output.append("-" * 80)
                report_output.append(f"{'ID объявления':<20} {'Название':<20} {'Статус':<10} {'Расход':<10} {'Конверсии':<10} {'Требуется':<10} {'Результат':<10}")
                report_output.append("-" * 80)
                
                # Обновляем время последней проверки
                campaign_setup.last_checked = datetime.utcnow()
                db.session.commit()
                
                # Получаем количество конверсий за период для этой кампании
                campaign_conversions = 0
                try:
                    # Создаем фильтр для поиска конверсий по префиксам
                    conversion_filters = []
                    for prefix in ref_prefixes:
                        conversion_filters.append(Conversion.ref_prefix == prefix)
                    
                    # Если есть префиксы, получаем конверсии
                    if conversion_filters:
                        # Преобразуем строковые даты в объекты datetime
                        since_datetime = datetime.strptime(since_date, '%Y-%m-%d').replace(hour=0, minute=0, second=0)
                        until_datetime = datetime.strptime(until_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
                        
                        # Получаем количество конверсий для кампании
                        campaign_conversions = Conversion.query.filter(
                            and_(
                                or_(*conversion_filters),
                                Conversion.timestamp >= since_datetime,
                                Conversion.timestamp <= until_datetime
                            )
                        ).count()
                        
                except Exception as e:
                    logger.error(f"Ошибка при получении конверсий: {str(e)}")
                
                report_output.append(f"Всего конверсий для кампании: {campaign_conversions}")
                
                # Проверяем каждое объявление отдельно
                successful_disabled = 0
                failed_disabled = 0
                skipped_ads = 0
                
                for ad in ads:
                    ad_id = getattr(ad, 'id', None)
                    ad_name = getattr(ad, 'name', 'Неизвестное имя')
                    ad_status = getattr(ad, 'status', 'UNKNOWN')
                    
                    if not ad_id:
                        continue
                    
                    # Если объявление уже отключено, пропускаем его
                    if ad_status != 'ACTIVE':
                        report_output.append(f"{ad_id:<20} {ad_name[:20]:<20} {ad_status:<10} -{'':9} -{'':9} -{'':9} Неактивно")
                        skipped_ads += 1
                        continue
                    
                    # Получаем статистику объявления
                    ad_stats = fb_api.get_ad_insights(ad_id, date_preset=None, time_range={'since': since_date, 'until': until_date})
                    
                    # Расход на объявление
                    ad_spend = float(ad_stats.get('spend', 0))
                    
                    # Проверяем, превышены ли пороги
                    should_disable = False
                    required_conversions = 0
                    
                    # Сортируем пороги по расходам (по возрастанию)
                    sorted_thresholds = sorted(thresholds, key=lambda x: x['spend'])
                    
                    # Находим подходящий порог для объявления
                    applicable_threshold = None
                    for threshold in sorted_thresholds:
                        if ad_spend >= threshold['spend']:
                            applicable_threshold = threshold
                        else:
                            break
                    
                    # Если нашли подходящий порог, проверяем условие
                    if applicable_threshold:
                        required_conversions = applicable_threshold['conversions']
                        if campaign_conversions < required_conversions:
                            should_disable = True
                    
                    # Выводим информацию о проверке
                    if should_disable:
                        result = "НЕ ПРОШЛО"
                        # Отключаем объявление
                        disable_result = fb_api.disable_ad(ad_id)
                        if disable_result:
                            successful_disabled += 1
                            report_output.append(f"{ad_id:<20} {ad_name[:20]:<20} {ad_status:<10} ${ad_spend:<9.2f} {campaign_conversions:<10} {required_conversions:<10} {result}")
                        else:
                            failed_disabled += 1
                            report_output.append(f"{ad_id:<20} {ad_name[:20]:<20} {ad_status:<10} ${ad_spend:<9.2f} {campaign_conversions:<10} {required_conversions:<10} {result} (ОШИБКА)")
                    else:
                        result = "ПРОШЛО"
                        report_output.append(f"{ad_id:<20} {ad_name[:20]:<20} {ad_status:<10} ${ad_spend:<9.2f} {campaign_conversions:<10} {required_conversions:<10} {result}")
                
                # Выводим итоговую статистику
                report_output.append("-" * 80)
                report_output.append(f"Итоги проверки: Успешно отключено {successful_disabled} объявлений, ошибки при отключении {failed_disabled} объявлений, пропущено {skipped_ads} объявлений")
                report_output.append("=" * 80)
                
                # Записываем отчет в лог
                logger.info("\n".join(report_output))
                
                # Записываем отчет в файл
                try:
                    from pathlib import Path
                    import json
                    
                    log_dir = Path('/data/disable_logs')
                    logger.info(f"Попытка создания директории для логов: {log_dir}")
                    try:
                        log_dir.mkdir(parents=True, exist_ok=True)
                        logger.info(f"Директория {log_dir} успешно создана или уже существует")
                    except Exception as mkdir_error:
                        logger.error(f"Ошибка при создании директории {log_dir}: {str(mkdir_error)}")
                        # Пробуем альтернативную директорию
                        log_dir = Path('/app/static/reports')
                        logger.info(f"Пробуем альтернативную директорию: {log_dir}")
                        log_dir.mkdir(parents=True, exist_ok=True)
                    
                    # Проверяем возможность записи
                    try:
                        test_file = log_dir / "test_write.txt"
                        with open(test_file, 'w') as f:
                            f.write("test")
                        test_file.unlink()  # Удаляем тестовый файл
                        logger.info("Тест записи в директорию логов успешен")
                    except Exception as write_error:
                        logger.error(f"Проблема с правами записи в {log_dir}: {str(write_error)}")
                        # Пробуем использовать временную директорию
                        import tempfile
                        log_dir = Path(tempfile.gettempdir())
                        logger.info(f"Используем временную директорию: {log_dir}")
                    
                    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
                    
                    # Текстовый отчет
                    report_file = log_dir / f"check_report_{campaign_setup.campaign_id}_{timestamp}.txt"
                    logger.info(f"Записываем текстовый отчет в {report_file}")
                    try:
                        with open(report_file, 'w') as f:
                            f.write("\n".join(report_output))
                        logger.info(f"Текстовый отчет успешно записан")
                    except Exception as txt_error:
                        logger.error(f"Ошибка при записи текстового отчета: {str(txt_error)}")
                        
                    # JSON отчет
                    report_json = {
                        'timestamp': datetime.utcnow().isoformat(),
                        'campaign_id': campaign_setup.campaign_id,
                        'campaign_name': campaign_setup.campaign_name,
                        'report_lines': report_output,
                        'successful_disabled': successful_disabled,
                        'failed_disabled': failed_disabled,
                        'skipped_ads': skipped_ads,
                        'total_ads': len(ads),
                        'period': period,
                        'date_range': f"{since_date} - {until_date}"
                    }
                    
                    json_file = log_dir / f"check_report_{campaign_setup.campaign_id}_{timestamp}.json"
                    logger.info(f"Записываем JSON отчет в {json_file}")
                    try:
                        with open(json_file, 'w') as f:
                            json.dump(report_json, f)
                        logger.info(f"JSON отчет успешно записан")
                        
                        # Проверка читаемости JSON-файла
                        with open(json_file, 'r') as f:
                            test_read = json.load(f)
                        logger.info(f"JSON отчет успешно прочитан в тесте")
                    except Exception as json_error:
                        logger.error(f"Ошибка при работе с JSON отчетом: {str(json_error)}")
                        
                    # Логируем все файлы в директории для диагностики
                    try:
                        all_files = list(log_dir.glob('*'))
                        logger.info(f"Все файлы в директории {log_dir}: {[f.name for f in all_files]}")
                    except Exception as ls_error:
                        logger.error(f"Ошибка при просмотре директории: {str(ls_error)}")
                        
                except Exception as e:
                    logger.error(f"Ошибка при сохранении отчета: {str(e)}")
                    import traceback
                    logger.error(traceback.format_exc())
                
            except Exception as e:
                logger.error(f"Ошибка при проверке кампании {campaign_setup.campaign_id}: {str(e)}")
                continue
                
        return True
                
    except Exception as e:
        logger.error(f"Ошибка при проверке порогов кампаний: {str(e)}")
        return False 