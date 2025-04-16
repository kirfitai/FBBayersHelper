def check_campaign_thresholds(campaign_setup):
    """
    Проверяет достижение порогов для кампании и отключает ее при необходимости
    
    Args:
        campaign_setup (CampaignSetup): Настройка кампании для проверки
    
    Returns:
        bool: True если кампания была отключена, False в противном случае
    """
    try:
        # Получаем данные о кампании
        setup = campaign_setup.setup
        user = User.query.get(campaign_setup.user_id)
        
        if not user:
            logger.error(f"Пользователь не найден: {campaign_setup.user_id}")
            return False
        
        # Получаем доступ к API
        fb_client = get_fb_client_for_user(user)
        if not fb_client:
            logger.error(f"Не удалось получить FB клиент для пользователя {user.id}")
            return False
            
        # Получаем пороги из сетапа
        thresholds = setup.get_thresholds_as_list()
        if not thresholds:
            logger.info(f"Нет порогов в сетапе {setup.id}")
            return False
        
        # Получаем статистику кампании
        campaign_id = campaign_setup.campaign_id
        campaign_stats = fb_client.get_campaign_stats(campaign_id)
        
        if not campaign_stats:
            logger.warning(f"Не удалось получить статистику для кампании {campaign_id}")
            return False
        
        # Проверяем достижение порогов
        spend = campaign_stats.get('spend', 0)
        conversions = campaign_stats.get('conversions', 0)
        
        # Ищем порог, соответствующий текущему количеству конверсий
        matching_threshold = None
        for threshold in thresholds:
            if threshold['conversions'] == conversions:
                matching_threshold = threshold
                break
        
        if matching_threshold:
            threshold_spend = matching_threshold['spend']
            
            # Проверяем, превышает ли затраты порог для данного количества конверсий
            if float(spend) >= float(threshold_spend):
                # Отключаем кампанию
                logger.info(f"Отключаем кампанию {campaign_id} - затраты {spend}$ при {conversions} конверсиях. "
                           f"Порог: {threshold_spend}$ для {conversions} конверсий")
                
                result = fb_client.pause_campaign(campaign_id)
                
                if result:
                    logger.info(f"Кампания {campaign_id} успешно отключена")
                    
                    # Добавляем запись в историю действий
                    action = CampaignAction(
                        campaign_setup_id=campaign_setup.id,
                        action_type='pause',
                        reason=f"Затраты {spend}$ при {conversions} конверсиях превысили порог {threshold_spend}$"
                    )
                    db.session.add(action)
                    db.session.commit()
                    
                    return True
                else:
                    logger.error(f"Не удалось отключить кампанию {campaign_id}")
            else:
                logger.info(f"Кампания {campaign_id} не превысила порог затрат: "
                           f"{spend}$ при {conversions} конверсиях. Порог: {threshold_spend}$")
        else:
            logger.info(f"Не найден порог для {conversions} конверсий для кампании {campaign_id}")
        
        # Обновляем время последней проверки
        campaign_setup.last_checked = datetime.utcnow()
        db.session.commit()
            
        return False
        
    except Exception as e:
        logger.error(f"Ошибка при проверке порогов для кампании {campaign_setup.campaign_id}: {str(e)}")
        return False 