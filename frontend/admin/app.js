const API_BASE = '';
let token = null;
let currentUser = null;

const tg = window.Telegram?.WebApp;
if (tg) {
    tg.ready();
    tg.expand();
}

function getToken() {
    return token;
}

function setToken(newToken) {
    token = newToken;
    localStorage.setItem('admin_token', newToken);
}

function getStoredToken() {
    return localStorage.getItem('admin_token');
}

async function api(endpoint, options = {}) {
    const url = `${API_BASE}/api/v1${endpoint}`;
    const headers = {
        'Content-Type': 'application/json',
        ...options.headers,
    };
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }
    const response = await fetch(url, { ...options, headers });
    if (response.status === 401) {
        logout();
        throw new Error('Unauthorized');
    }
    return response;
}

function logout() {
    token = null;
    localStorage.removeItem('admin_token');
    document.getElementById('main-content').innerHTML = '<p class="loading-text">Откройте приложение через Admin-бота в Telegram.</p>';
}

async function auth() {
    // В тестовой среде или без Telegram подставим сохранённый токен
    const stored = getStoredToken();
    if (stored) {
        token = stored;
        try {
            const meRes = await api('/auth/me');
            if (meRes.ok) {
                currentUser = await meRes.json();
                initTabs();
                loadModels();
                return;
            }
        } catch (e) {
            console.warn('Stored token invalid, re-authenticating...');
        }
    }

    if (!tg?.initData) {
        document.getElementById('main-content').innerHTML = '<p class="loading-text">Пожалуйста, откройте панель через Telegram Admin-бота.</p>';
        return;
    }

    try {
        const response = await api('/auth/telegram', {
            method: 'POST',
            body: JSON.stringify({ init_data: tg.initData }),
        });
        const data = await response.json();
        setToken(data.access_token);
        currentUser = data;

        if (currentUser.role !== 'admin') {
            document.getElementById('main-content').innerHTML = '<p class="loading-text">Доступ запрещен. Требуются права администратора или владельца моделей.</p>';
            return;
        }

        initTabs();
        loadModels();
    } catch (e) {
        console.error('Admin auth failed:', e);
    }
}

function initTabs() {
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

            btn.classList.add('active');
            const tabId = btn.getAttribute('data-tab');
            const tabContent = document.getElementById(`admin-${tabId}`);
            if (tabContent) {
                tabContent.classList.add('active');
            }

            if (tabId === 'models') loadModels();
            else if (tabId === 'dashboard') loadDashboard();
            else if (tabId === 'packages') loadPackages();
        });
    });
}

// ==============================================================================
// Управление моделями
// ==============================================================================

async function loadModels() {
    const listEl = document.getElementById('models-list');
    listEl.innerHTML = '<p class="loading-text">Загрузка моделей...</p>';

    try {
        const res = await api('/admin/models');
        const data = await res.json();
        const models = data.models || [];

        if (models.length === 0) {
            listEl.innerHTML = '<p class="loading-text">У вас пока нет добавленных моделей. Нажмите "+ Добавить модель".</p>';
            return;
        }

        listEl.innerHTML = models.map(m => `
            <div class="item-card">
                <div class="item-info">
                    <div class="item-name">${escapeHtml(m.name)}</div>
                    <div class="item-meta">
                        ${m.bot_token ? '<span class="bot-tag">Бот подключен</span>' : '<span class="no-bot-tag">Бот не подключен</span>'}
                        • ID: ${m.id}
                    </div>
                </div>
                <button class="btn btn-secondary btn-sm edit-model-btn" data-model='${JSON.stringify(m).replace(/'/g, "&apos;")}'>
                    Настроить
                </button>
            </div>
        `).join('');

        document.querySelectorAll('.edit-model-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const model = JSON.parse(btn.getAttribute('data-model'));
                openModelModal(model);
            });
        });
    } catch (e) {
        listEl.innerHTML = `<p class="loading-text" style="color: var(--danger)">Ошибка загрузки: ${e.message}</p>`;
    }
}

function openModelModal(model = null) {
    const modal = document.getElementById('model-modal');
    const modalTitle = document.getElementById('modal-title');
    const idInput = document.getElementById('model-id');
    const nameInput = document.getElementById('model-name');
    const tokenInput = document.getElementById('model-token');
    const themeInput = document.getElementById('model-theme');

    if (model) {
        modalTitle.textContent = 'Редактировать модель';
        idInput.value = model.id;
        nameInput.value = model.name;
        tokenInput.value = model.bot_token || '';
        themeInput.value = model.theme_json || '';
    } else {
        modalTitle.textContent = 'Новая модель';
        idInput.value = '';
        nameInput.value = '';
        tokenInput.value = '';
        themeInput.value = '';
    }

    modal.classList.remove('hidden');
}

function closeModelModal() {
    document.getElementById('model-modal').classList.add('hidden');
}

document.getElementById('add-model-btn')?.addEventListener('click', () => openModelModal(null));
document.getElementById('close-model-modal-btn')?.addEventListener('click', closeModelModal);

document.getElementById('model-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const id = document.getElementById('model-id').value;
    const name = document.getElementById('model-name').value;
    const bot_token = document.getElementById('model-token').value;
    const theme_json = document.getElementById('model-theme').value;

    const payload = {
        name,
        bot_token: bot_token || null,
        theme_json: theme_json || null,
    };

    try {
        if (id) {
            await api(`/admin/models/${id}`, {
                method: 'PATCH',
                body: JSON.stringify(payload),
            });
        } else {
            await api('/admin/models', {
                method: 'POST',
                body: JSON.stringify(payload),
            });
        }
        closeModelModal();
        loadModels();
    } catch (err) {
        alert('Ошибка при сохранении: ' + err.message);
    }
});

async function loadDashboard() {
    const dashEl = document.getElementById('admin-dashboard');
    dashEl.innerHTML = '<p class="loading-text">Загрузка дашборда...</p>';
    try {
        const res = await api('/admin/dashboard');
        const data = await res.json();
        dashEl.innerHTML = `
            <div class="glass-panel" style="padding: 16px;">
                <p>Пользователей: <b>${data.users}</b></p>
                <p>Всего спинов: <b>${data.spins}</b></p>
                <p>Покупок: <b>${data.purchases}</b></p>
            </div>
        `;
    } catch (e) {
        dashEl.innerHTML = `<p class="loading-text" style="color: var(--danger)">Ошибка: ${e.message}</p>`;
    }
}

async function loadPackages() {
    const pkgEl = document.getElementById('admin-packages');
    pkgEl.innerHTML = '<p class="loading-text">Загрузка пакетов...</p>';
    try {
        const res = await api('/admin/spin-packages');
        const data = await res.json();
        pkgEl.innerHTML = `
            <div class="glass-panel" style="padding: 16px;">
                <h3>Пакеты спинов (за GEMS)</h3>
                <div style="margin-top: 10px; display: flex; flex-direction: column; gap: 8px;">
                    ${data.packages.map(p => `
                        <div style="display:flex; justify-content:space-between; padding:8px; border-bottom:1px solid var(--border-glass)">
                            <span>${escapeHtml(p.name)} (${p.spins_count} спинов)</span>
                            <b>${p.price_gems} GEMS</b>
                        </div>
                    `).join('')}
                </div>
            </div>
        `;
    } catch (e) {
        pkgEl.innerHTML = `<p class="loading-text" style="color: var(--danger)">Ошибка: ${e.message}</p>`;
    }
}

function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
}

document.addEventListener('DOMContentLoaded', () => {
    auth();
});
