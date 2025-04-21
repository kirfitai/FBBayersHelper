/**
 * Класс для асинхронной проверки кампаний
 */
class CampaignChecker {
    /**
     * Конструктор
     * @param {string} campaignId - ID кампании для проверки
     * @param {Object} options - Опции для проверки
     * @param {string} options.checkPeriod - Период проверки (today, last2days, last3days, last7days, alltime)
     * @param {Object} options.callbacks - Колбеки для разных этапов проверки
     */
    constructor(campaignId, options = {}) {
        this.campaignId = campaignId;
        this.checkPeriod = options.checkPeriod || 'today';
        this.callbacks = options.callbacks || {};
        this.checkId = null;
        this.pollingInterval = null;
    }

    /**
     * Запускает проверку кампании
     * @returns {Promise} Промис, который резолвится по завершении проверки
     */
    check() {
        this._triggerCallback('onStart');

        return fetch(`/campaigns/check/${this.campaignId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest',
                'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content
            },
            body: JSON.stringify({
                check_period: this.checkPeriod
            })
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`Ошибка при проверке кампании: ${response.status} ${response.statusText}`);
            }
            return response.json();
        })
        .then(data => {
            if (data.status === 'started' && data.check_id) {
                this.checkId = data.check_id;
                this.startPolling();
            } else if (data.status === 'completed' && data.results) {
                this._triggerCallback('onSuccess', data.results);
                this._triggerCallback('onComplete');
            } else {
                throw new Error(data.error || 'Неизвестная ошибка при запуске проверки');
            }
        })
        .catch(error => {
            this.handleError(error);
        });
    }

    /**
     * Запускает периодическую проверку статуса
     */
    startPolling() {
        if (this.pollingInterval) {
            clearInterval(this.pollingInterval);
        }

        this.pollingInterval = setInterval(() => {
            this.pollStatus();
        }, 500);
    }

    /**
     * Проверяет текущий статус проверки
     */
    pollStatus() {
        if (!this.checkId) {
            this.stopPolling();
            return;
        }

        fetch(`/campaigns/check-status/${this.checkId}`)
            .then(response => response.json())
            .then(data => {
                if (data.status === 'completed') {
                    this.stopPolling();
                    this._triggerCallback('onSuccess', data.results);
                    this._triggerCallback('onComplete');
                } else if (data.status === 'error') {
                    this.stopPolling();
                    throw new Error(data.error || 'Ошибка при выполнении проверки');
                }
                // Продолжаем опрос, если статус все еще 'started'
            })
            .catch(error => {
                this.stopPolling();
                this.handleError(error);
            });
    }

    /**
     * Останавливает опрос статуса
     */
    stopPolling() {
        if (this.pollingInterval) {
            clearInterval(this.pollingInterval);
            this.pollingInterval = null;
        }
    }

    /**
     * Обрабатывает ошибки
     * @param {Error} error - Объект ошибки
     */
    handleError(error) {
        console.error('Ошибка при проверке кампании:', error);
        this.stopPolling();
        this._triggerCallback('onError', error);
        this._triggerCallback('onComplete');
    }

    /**
     * Вызывает соответствующий колбек, если он определен
     * @param {string} name - Имя колбека
     * @param {*} data - Данные для передачи в колбек
     * @private
     */
    _triggerCallback(name, data) {
        if (typeof this.callbacks[name] === 'function') {
            this.callbacks[name](data);
        }
    }
}

/**
 * Отображает результаты проверки в таблице
 * @param {Array} results - Массив результатов
 * @param {string} tableSelector - CSS-селектор таблицы
 */
function renderResultsToTable(results, tableSelector) {
    const tbody = document.querySelector(`${tableSelector} tbody`);
    
    if (!tbody || !results || !Array.isArray(results)) {
        return;
    }
    
    // Очищаем таблицу
    tbody.innerHTML = '';
    
    // Группируем результаты по статусу, чтобы отключенные объявления были вверху
    const groupedResults = {
        disabled: [],
        warning: [],
        active: [],
        other: []
    };
    
    results.forEach(result => {
        const status = result.status ? result.status.toLowerCase() : 'other';
        if (groupedResults[status] !== undefined) {
            groupedResults[status].push(result);
        } else {
            groupedResults.other.push(result);
        }
    });
    
    // Добавляем результаты в таблицу в нужном порядке
    ['disabled', 'warning', 'active', 'other'].forEach(status => {
        groupedResults[status].forEach(result => {
            const row = document.createElement('tr');
            
            // Добавляем класс для стилизации
            if (status === 'disabled') {
                row.classList.add('table-danger');
            } else if (status === 'warning') {
                row.classList.add('table-warning');
            } else if (status === 'active') {
                row.classList.add('table-success');
            }
            
            row.innerHTML = `
                <td>${result.ad_id}</td>
                <td>${result.name || '-'}</td>
                <td>${result.status || '-'}</td>
                <td>${result.spend !== undefined ? result.spend : '-'}</td>
                <td>${result.conversions !== undefined ? result.conversions : '-'}</td>
                <td>${result.reason || '-'}</td>
            `;
            
            tbody.appendChild(row);
        });
    });
}