import requests
import json

def check_account_campaigns(token, account_id):
    """Прямая проверка кампаний через API"""
    if not account_id.startswith('act_'):
        account_id = f'act_{account_id}'
    
    # Получаем информацию об аккаунте
    response = requests.get(
        f'https://graph.facebook.com/v18.0/{account_id}',
        params={
            'access_token': token,
            'fields': 'name,account_status'
        }
    )
    print(f"Проверка аккаунта {account_id}: {response.status_code}")
    print(f"Ответ: {response.text}")
    
    # Получаем кампании
    response = requests.get(
        f'https://graph.facebook.com/v18.0/{account_id}/campaigns',
        params={
            'access_token': token,
            'fields': 'id,name,status,objective'
        }
    )
    print(f"Получение кампаний: {response.status_code}")
    print(f"Ответ: {json.dumps(response.json(), indent=2)}")
    
    # Проверяем по одной кампании из ответа
    data = response.json()
    campaigns = data.get('data', [])
    if campaigns:
        campaign_id = campaigns[0].get('id')
        print(f"Проверка кампании {campaign_id}")
        
        # Получаем объявления в этой кампании
        response = requests.get(
            f'https://graph.facebook.com/v18.0/{campaign_id}/ads',
            params={
                'access_token': token,
                'fields': 'id,name,status'
            }
        )
        print(f"Получение объявлений: {response.status_code}")
        print(f"Ответ: {json.dumps(response.json(), indent=2)}")