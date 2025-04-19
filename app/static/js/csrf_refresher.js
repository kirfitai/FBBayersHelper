/**
 * CSRF Token Refresher
 * 
 * Функция периодически обновляет CSRF токены в формах на странице.
 * Обновление происходит:
 * - Каждые 20 минут
 * - При возвращении на страницу после переключения вкладок
 * 
 * Это предотвращает ошибки с устаревшими токенами при долгом использовании страницы.
 */

function refreshCsrfToken() {
    fetch('/api/refresh-csrf')
        .then(response => response.json())
        .then(data => {
            if (data.csrf_token) {
                // Обновляем токен во всех формах
                const csrfFields = document.querySelectorAll('input[name="csrf_token"]');
                csrfFields.forEach(field => {
                    field.value = data.csrf_token;
                });
                console.log('CSRF токен успешно обновлен');
            }
        })
        .catch(error => {
            console.error('Ошибка при обновлении CSRF токена:', error);
        });
}

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', function() {
    // Запускаем обновление токена каждые 20 минут
    setInterval(refreshCsrfToken, 20 * 60 * 1000);
    
    // Также обновляем токен при возвращении на страницу
    document.addEventListener('visibilitychange', function() {
        if (document.visibilityState === 'visible') {
            refreshCsrfToken();
        }
    });
    
    console.log('CSRF refresher инициализирован');
}); 