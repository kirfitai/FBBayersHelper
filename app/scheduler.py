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

def check_campaign_thresholds(campaign_id=None, check_period=None, return_details=False):
    """
    Проверяет пороги для кампаний и отключает объявления, которые не соответствуют
    
    Args:
        campaign_id (str, optional): ID конкретной кампании для проверки
        check_period (str, optional): Период проверки ('today', 'last2days', 'last3days', 'last7days', 'alltime')
        return_details (bool, optional): Возвращать ли детальную информацию о результатах проверки
        
    Returns:
        bool: Результат операции (True - успешно, False - ошибка)
        list: Список результатов проверки объявлений (если return_details=True)
    """
    logger.info(f"Запуск проверки порогов кампаний{'для ID ' + campaign_id if campaign_id else ''}")
    
    try:
        # Получаем все настройки кампаний или конкретную настройку
        from app.models.setup import CampaignSetup, Setup
        from app.models.facebook_token import FacebookToken
        from app.models.conversion import Conversion
        from sqlalchemy import and_, or_
        
        query = CampaignSetup.query.filter_by(is_active=True)
        if campaign_id:
            query = query.filter_by(campaign_id=campaign_id)
            
        campaign_setups = query.all()
        logger.info(f"Найдено {len(campaign_setups)} активных назначений кампаний для проверки")
        
        if not campaign_setups:
            logger.warning(f"Активные назначения кампаний не найдены")
            if return_details:
                return False, []
            return False
            
        ads_results = []  # Для хранения результатов проверки каждого объявления
            
        for campaign_setup in campaign_setups:
            try:
                report_output = []  # Для формирования текстового отчета
                
                report_output.append(f"Начинаем проверку кампании {campaign_setup.campaign_id} ({campaign_setup.campaign_name or 'Без имени'})")
                
                # Получаем сетап и пороги для кампании
                setup = Setup.query.get(campaign_setup.setup_id)
                if not setup:
                    logger.error(f"Сетап {campaign_setup.setup_id} не найден")
                    report_output.append(f"ОШИБКА: Сетап {campaign_setup.setup_id} не найден")
                    continue
                    
                report_output.append(f"Используем период проверки: {check_period or setup.check_period or 'today'}")
                
                # Определяем диапазон дат для периода
                since_date, until_date = calculate_date_range_for_period(check_period or setup.check_period)
                report_output.append(f"Диапазон дат: {since_date} - {until_date}")
                
                # Получаем пороги из сетапа
                thresholds = setup.get_thresholds_as_list()
                if not thresholds:
                    logger.error(f"В сетапе {setup.id} не настроены пороги")
                    report_output.append("ОШИБКА: В сетапе не настроены пороги")
                    continue
                
                # Сортируем пороги по расходам (для удобства)
                thresholds = sorted(thresholds, key=lambda x: x['spend'])
                
                # Выводим пороги
                report_output.append("\nНастроенные пороги:")
                for threshold in thresholds:
                    report_output.append(f"- Расход: ${threshold['spend']}, мин. конверсий: {threshold['conversions']}")
                
                # Получаем API токен пользователя
                token = FacebookToken.query.filter_by(user_id=campaign_setup.user_id, is_active=True).first()
                if not token:
                    logger.error(f"У пользователя {campaign_setup.user_id} нет активного токена API")
                    report_output.append("ОШИБКА: У пользователя нет активного токена API Facebook")
                    continue
                
                # Получаем account_id из первого аккаунта токена
                account_ids = token.get_account_ids()
                if not account_ids:
                    logger.error(f"У токена {token.id} нет связанных аккаунтов")
                    report_output.append("ОШИБКА: У токена нет связанных аккаунтов Facebook")
                    continue
                
                account_id = account_ids[0]
                report_output.append(f"Используем аккаунт {account_id} для проверки кампании")
                
                # Инициализируем Facebook API
                from app.services.facebook_api import FacebookAPI
                fb_api = FacebookAPI(
                    access_token=token.access_token, 
                    app_id=token.app_id,
                    app_secret=token.app_secret,
                    account_id=account_id
                )
                
                # Получаем префиксы для отслеживания конверсий
                ref_prefixes = setup.ref_prefixes.split(',') if hasattr(setup, 'ref_prefixes') and setup.ref_prefixes else []
                ref_prefixes = [prefix.strip() for prefix in ref_prefixes if prefix.strip()]
                
                if ref_prefixes:
                    report_output.append(f"\nПрефиксы REF для отслеживания конверсий: {', '.join(ref_prefixes)}")
                    logger.info(f"Префиксы REF для отслеживания конверсий: {', '.join(ref_prefixes)}")
                else:
                    report_output.append("\nВнимание: префиксы REF не настроены!")
                    logger.warning("Внимание: префиксы REF не настроены!")
                
                # Получаем все объявления в кампании
                report_output.append(f"Получаем объявления для кампании {campaign_setup.campaign_id}")
                ads = None 
                try:
                    logger.info(f"Запрашиваем объявления для кампании {campaign_setup.campaign_id}")
                    ads = fb_api.get_ads_in_campaign(campaign_setup.campaign_id)
                    if ads:
                        logger.info(f"Успешно получено {len(ads)} объявлений")
                        report_output.append(f"Получено {len(ads)} объявлений в кампании")
                    else:
                        logger.warning(f"В кампании {campaign_setup.campaign_id} не найдено объявлений или получен пустой список")
                        report_output.append("В кампании не найдено объявлений")
                        ads = []
                except Exception as ads_error:
                    logger.error(f"Ошибка при получении объявлений: {str(ads_error)}")
                    report_output.append(f"ОШИБКА при получении объявлений: {str(ads_error)}")
                    ads = []
                
                if not ads:
                    report_output.append("Объявления не найдены в кампании")
                    logger.warning(f"В кампании {campaign_setup.campaign_id} не найдено объявлений")
                    # Обновляем время последней проверки, даже если не найдены объявления
                    campaign_setup.last_checked = datetime.utcnow()
                    db.session.commit()
                    continue
                
                report_output.append("\nПРОВЕРКА ОБЪЯВЛЕНИЙ:")
                report_output.append("-" * 80)
                report_output.append(f"{'ID объявления':<20} {'Название':<20} {'Статус':<10} {'Расход':<10} {'Конверсии':<10} {'Требуется':<10} {'Результат':<10}")
                report_output.append("-" * 80)
                
                # Обновляем время последней проверки
                campaign_setup.last_checked = datetime.utcnow()
                db.session.commit()
                
                # Создаем фильтр для поиска конверсий по префиксам
                conversion_filters = []
                for prefix in ref_prefixes:
                    conversion_filters.append(Conversion.ref_prefix == prefix)
                    
                # Преобразуем строковые даты в объекты datetime для фильтрации конверсий
                since_datetime = datetime.strptime(since_date, '%Y-%m-%d').replace(hour=0, minute=0, second=0)
                until_datetime = datetime.strptime(until_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
                
                # Проверяем каждое объявление отдельно
                successful_disabled = 0
                failed_disabled = 0
                skipped_ads = 0
                
                for ad in ads:
                    ad_id = getattr(ad, 'id', None)
                    ad_name = getattr(ad, 'name', 'Неизвестное имя')
                    ad_status = getattr(ad, 'status', 'UNKNOWN')
                    
                    logger.info(f"Проверка объявления: ID={ad_id}, Name={ad_name}, Status={ad_status}")
                    
                    if not ad_id:
                        logger.warning(f"Объявление не имеет ID, пропускаем")
                        continue
                    
                    # Создаем запись о результате проверки объявления
                    ad_result = {
                        'id': ad_id,
                        'name': ad_name,
                        'status': ad_status,
                        'conversions': 0,
                        'disabled': False,
                        'disabled_success': False
                    }
                    
                    # Если объявление уже отключено, пропускаем его
                    if ad_status != 'ACTIVE':
                        report_output.append(f"{ad_id:<20} {ad_name[:20]:<20} {ad_status:<10} -{'':9} -{'':9} -{'':9} Неактивно")
                        skipped_ads += 1
                        ad_result['result'] = "Неактивно"
                        ad_result['spend'] = 0
                        ad_result['required_conversions'] = 0
                        ads_results.append(ad_result)
                        logger.info(f"Объявление {ad_id} не активно, пропускаем")
                        continue
                    
                    # Получаем статистику объявления из Facebook API
                    logger.info(f"Запрашиваем статистику для объявления {ad_id}")
                    ad_stats = fb_api.get_ad_insights(ad_id, date_preset=None, time_range={'since': since_date, 'until': until_date})
                    
                    # Расход на объявление
                    ad_spend = float(ad_stats.get('spend', 0))
                    ad_result['spend'] = ad_spend
                    logger.info(f"Расход по объявлению {ad_id}: ${ad_spend}")
                    
                    # Получаем конверсии для конкретного объявления (по соответствию ID объявления с form_id)
                    ad_conversions = 0
                    try:
                        # Если есть префиксы, получаем конверсии
                        if conversion_filters:
                            # Запрос конверсий, где form_id соответствует ID объявления
                            ad_conversions_query = Conversion.query.filter(
                                and_(
                                    or_(*conversion_filters),
                                    Conversion.form_id == ad_id,  # Соответствие form_id и ID объявления
                                    Conversion.timestamp >= since_datetime,
                                    Conversion.timestamp <= until_datetime
                                )
                            )
                            
                            ad_conversions = ad_conversions_query.count()
                            logger.info(f"Найдено {ad_conversions} конверсий для объявления {ad_id} за период {since_date} - {until_date}")
                    except Exception as e:
                        logger.error(f"Ошибка при получении конверсий для объявления {ad_id}: {str(e)}")
                    
                    ad_result['conversions'] = ad_conversions
                    
                    # Проверяем, превышены ли пороги
                    should_disable = False
                    required_conversions = 0
                    
                    # Сортируем пороги по количеству конверсий (от большего к меньшему)
                    sorted_by_conversions = sorted(thresholds, key=lambda x: x['conversions'], reverse=True)
                    
                    # Определяем максимальное количество конверсий в сетапе
                    max_conversions_threshold = sorted_by_conversions[0]['conversions'] if sorted_by_conversions else 0
                    
                    # НОВАЯ ЛОГИКА:
                    # Если количество конверсий превышает максимальное значение в сетапе,
                    # объявление автоматически проходит проверку
                    if ad_conversions > max_conversions_threshold:
                        should_disable = False
                        required_conversions = max_conversions_threshold
                        ad_result['required_conversions'] = required_conversions
                        logger.info(f"Объявление {ad_id} автоматически прошло проверку: конверсии ({ad_conversions}) превышают максимальное значение в сетапе ({max_conversions_threshold})")
                    else:
                        # Ищем порог, который точно соответствует количеству конверсий
                        exact_match_threshold = None
                        for threshold in thresholds:
                            if threshold['conversions'] == ad_conversions:
                                exact_match_threshold = threshold
                                break
                        
                        # Если нашли точное соответствие, проверяем расход
                        if exact_match_threshold:
                            required_conversions = exact_match_threshold['conversions']
                            ad_result['required_conversions'] = required_conversions
                            
                            # Если расход превышен или равен пороговому, отключаем объявление
                            if ad_spend >= exact_match_threshold['spend']:
                                should_disable = True
                                logger.info(f"Объявление {ad_id} не прошло проверку: расход ${ad_spend} >= ${exact_match_threshold['spend']}, конверсии {ad_conversions} == {required_conversions}")
                            else:
                                should_disable = False
                                logger.info(f"Объявление {ad_id} прошло проверку: расход ${ad_spend} < ${exact_match_threshold['spend']}, конверсии {ad_conversions} == {required_conversions}")
                        else:
                            # Если нет точного соответствия, ищем ближайший нижний порог
                            lower_threshold = None
                            for threshold in sorted(thresholds, key=lambda x: x['conversions']):
                                if threshold['conversions'] < ad_conversions:
                                    lower_threshold = threshold
                                    break
                            
                            if lower_threshold:
                                # Если есть нижний порог и конверсий больше, чем требуется - объявление проходит
                                required_conversions = lower_threshold['conversions']
                                ad_result['required_conversions'] = required_conversions
                                should_disable = False
                                logger.info(f"Объявление {ad_id} прошло проверку: конверсии {ad_conversions} > {required_conversions}")
                            else:
                                # Если конверсий меньше минимального порога, проверяем минимальный порог
                                min_threshold = min(thresholds, key=lambda x: x['conversions'])
                                required_conversions = min_threshold['conversions']
                                ad_result['required_conversions'] = required_conversions
                                
                                # Если расход превышает порог, а конверсий меньше минимального требования, отключаем
                                if ad_spend >= min_threshold['spend'] and ad_conversions < min_threshold['conversions']:
                                    should_disable = True
                                    logger.info(f"Объявление {ad_id} не прошло проверку: расход ${ad_spend} >= ${min_threshold['spend']}, конверсии {ad_conversions} < {min_threshold['conversions']}")
                                else:
                                    should_disable = False
                                    logger.info(f"Объявление {ad_id} прошло проверку: расход ${ad_spend} < ${min_threshold['spend']} или конверсии достаточны")
                    
                    # Выводим информацию о проверке
                    if should_disable:
                        result = "НЕ ПРОШЛО"
                        ad_result['result'] = result
                        ad_result['disabled'] = True
                        
                        logger.info(f"Попытка отключения объявления {ad_id}")
                        # Отключаем объявление через Facebook API
                        disable_result = fb_api.disable_ad(ad_id)
                        if disable_result:
                            successful_disabled += 1
                            ad_result['disabled_success'] = True
                            report_output.append(f"{ad_id:<20} {ad_name[:20]:<20} {ad_status:<10} ${ad_spend:<9.2f} {ad_conversions:<10} {required_conversions:<10} {result}")
                            logger.info(f"Объявление {ad_id} успешно отключено")
                        else:
                            failed_disabled += 1
                            report_output.append(f"{ad_id:<20} {ad_name[:20]:<20} {ad_status:<10} ${ad_spend:<9.2f} {ad_conversions:<10} {required_conversions:<10} {result} (ОШИБКА)")
                            logger.error(f"Не удалось отключить объявление {ad_id}")
                    else:
                        result = "ПРОШЛО"
                        ad_result['result'] = result
                        report_output.append(f"{ad_id:<20} {ad_name[:20]:<20} {ad_status:<10} ${ad_spend:<9.2f} {ad_conversions:<10} {required_conversions:<10} {result}")
                        logger.info(f"Объявление {ad_id} прошло проверку")
                    
                    # Добавляем результат проверки в список
                    ads_results.append(ad_result)
                
                # Выводим итоговую статистику
                report_output.append("-" * 80)
                report_output.append(f"Итоги проверки: Успешно отключено {successful_disabled} объявлений, ошибки при отключении {failed_disabled} объявлений, пропущено {skipped_ads} объявлений")
                report_output.append(f"Проверка завершена с результатом: Успешно")
                
                # Возвращаем пустую строку, если объявления не найдены
                if not ads:
                    report_output.append("Объявления не найдены в кампании")
                
                # Записываем отчет в лог
                logger.info("\n".join(report_output))
                logger.info(f"Итоги проверки кампании {campaign_setup.campaign_id}: Отключено {successful_disabled}, ошибки {failed_disabled}, пропущено {skipped_ads}")
                
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
                        'period': check_period or setup.check_period or 'today',
                        'date_range': f"{since_date} - {until_date}",
                        'ads_results': ads_results  # Добавляем детальную информацию о проверке
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
                import traceback
                logger.error(traceback.format_exc())
                continue
        
        if return_details:
            logger.info(f"Возвращаем детальную информацию о {len(ads_results)} объявлениях")
            return True, ads_results
        return True
                
    except Exception as e:
        logger.error(f"Ошибка при проверке порогов кампаний: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        if return_details:
            return False, []
        return False 