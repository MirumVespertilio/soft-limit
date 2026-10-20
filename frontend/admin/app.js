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
            else if (tabId === 'content') loadContent();
            else if (tabId === 'wheel') loadWheel();
            else if (tabId === 'welcome') loadWelcomePool();
            else if (tabId === 'users') loadUsers();
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
    const priceGemsInput = document.getElementById('model-price-gems');
    const priceStarsInput = document.getElementById('model-price-stars');
    const rarityWeightsInput = document.getElementById('model-rarity-weights');

    if (model) {
        modalTitle.textContent = 'Редактировать модель';
        idInput.value = model.id;
        nameInput.value = model.name;
        tokenInput.value = model.bot_token || '';
        themeInput.value = model.theme_json || '';
        priceGemsInput.value = model.media_spin_price_gems ?? 0;
        priceStarsInput.value = model.media_spin_price_stars ?? 0;
        rarityWeightsInput.value = model.rarity_weights_json || '';
    } else {
        modalTitle.textContent = 'Новая модель';
        idInput.value = '';
        nameInput.value = '';
        tokenInput.value = '';
        themeInput.value = '';
        priceGemsInput.value = 0;
        priceStarsInput.value = 0;
        rarityWeightsInput.value = '';
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
    const price_gems = parseInt(document.getElementById('model-price-gems').value, 10) || 0;
    const price_stars = parseInt(document.getElementById('model-price-stars').value, 10) || 0;
    const rarity_weights_json = document.getElementById('model-rarity-weights').value;

    const payload = {
        name,
        bot_token: bot_token || null,
        theme_json: theme_json || null,
        media_spin_price_gems: price_gems,
        media_spin_price_stars: price_stars,
        rarity_weights_json: rarity_weights_json || null,
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

// ==============================================================================
// Контент
// ==============================================================================

async function loadContent() {
    const el = document.getElementById('admin-content');
    el.innerHTML = '<p class="loading-text">Загрузка контента...</p>';
    try {
        const [contentRes, modelsRes] = await Promise.all([
            api('/admin/content'),
            api('/admin/models'),
        ]);
        const content = await contentRes.json();
        const models = (await modelsRes.json()).models || [];
        const modelOptions = models.map(m => `<option value="${m.id}">${escapeHtml(m.name)} (#${m.id})</option>`).join('');
        const items = content.items || [];

        el.innerHTML = `
            <div class="glass-panel" style="padding: 16px;">
                <h3>Контент</h3>
                <form id="content-form" style="display:flex; flex-direction:column; gap:8px; margin:12px 0;">
                    <input type="text" id="content-title" class="input" placeholder="Название" required>
                    <textarea id="content-description" class="input textarea" rows="2" placeholder="Описание"></textarea>
                    <select id="content-model" class="input"><option value="">Без модели</option>${modelOptions}</select>
                    <select id="content-rarity" class="input">
                        <option value="rare">Rare</option>
                        <option value="legendary">Legendary</option>
                        <option value="mythic">Mythic</option>
                        <option value="eternal">Eternal</option>
                    </select>
                    <button type="submit" class="btn btn-primary btn-sm">Добавить контент</button>
                </form>
                <div style="display:flex; flex-direction:column; gap:8px;">
                    ${items.map(c => `
                        <div style="display:flex; justify-content:space-between; padding:8px; border-bottom:1px solid var(--border-glass)">
                            <span>${escapeHtml(c.title)} <span class="no-bot-tag">${c.rarity}</span> ${c.model_id ? `(модель #${c.model_id})` : ''}</span>
                            <span>${c.status}</span>
                        </div>
                    `).join('') || '<p class="loading-text">Нет контента</p>'}
                </div>
            </div>
        `;

        document.getElementById('content-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            const title = document.getElementById('content-title').value;
            const description = document.getElementById('content-description').value;
            const model_id = document.getElementById('content-model').value;
            const rarity = document.getElementById('content-rarity').value;
            await api('/admin/content', {
                method: 'POST',
                body: JSON.stringify({
                    title,
                    description: description || null,
                    media_type: 'photo',
                    model_id: model_id ? parseInt(model_id, 10) : null,
                    rarity,
                }),
            });
            loadContent();
        });
    } catch (e) {
        el.innerHTML = `<p class="loading-text" style="color: var(--danger)">Ошибка: ${e.message}</p>`;
    }
}

// ==============================================================================
// Колесо
// ==============================================================================

async function loadWheel() {
    const el = document.getElementById('admin-wheel');
    el.innerHTML = '<p class="loading-text">Загрузка колёс...</p>';
    try {
        const [wheelsRes, modelsRes] = await Promise.all([
            api('/admin/wheels'),
            api('/admin/models'),
        ]);
        const wheels = (await wheelsRes.json()).wheels || [];
        const models = (await modelsRes.json()).models || [];
        const modelOptions = models.map(m => `<option value="${m.id}">${escapeHtml(m.name)} (#${m.id})</option>`).join('');

        el.innerHTML = `
            <div class="glass-panel" style="padding: 16px;">
                <h3>Колёса</h3>
                <form id="wheel-form" style="display:flex; gap:8px; margin:12px 0; flex-wrap:wrap;">
                    <input type="text" id="wheel-name" class="input" placeholder="Название колеса" required>
                    <select id="wheel-model" class="input"><option value="">Без модели</option>${modelOptions}</select>
                    <button type="submit" class="btn btn-primary btn-sm">Создать</button>
                </form>
                <div style="display:flex; flex-direction:column; gap:8px;">
                    ${wheels.map(w => `<div style="display:flex; justify-content:space-between; padding:8px; border-bottom:1px solid var(--border-glass)"><span>${escapeHtml(w.name)} (#${w.id})${w.model_id ? ` модель #${w.model_id}` : ''}</span><span>${w.status}</span></div>`).join('') || '<p class="loading-text">Нет колёс</p>'}
                </div>
            </div>
        `;

        document.getElementById('wheel-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            const name = document.getElementById('wheel-name').value;
            const model_id = document.getElementById('wheel-model').value;
            await api('/admin/wheels', {
                method: 'POST',
                body: JSON.stringify({ name, model_id: model_id ? parseInt(model_id, 10) : null }),
            });
            loadWheel();
        });
    } catch (e) {
        el.innerHTML = `<p class="loading-text" style="color: var(--danger)">Ошибка: ${e.message}</p>`;
    }
}

// ==============================================================================
// Приветственный пул / Пользователи
// ==============================================================================

async function loadWelcomePool() {
    const el = document.getElementById('admin-welcome');
    el.innerHTML = '<p class="loading-text">Загрузка...</p>';
    try {
        const res = await api('/admin/welcome-pool');
        const data = await res.json();
        el.innerHTML = `
            <div class="glass-panel" style="padding: 16px;">
                <h3>Приветственный пул</h3>
                <div style="display:flex; flex-direction:column; gap:8px; margin-top:10px;">
                    ${(data.items || []).map(i => `<div style="padding:8px; border-bottom:1px solid var(--border-glass)">${escapeHtml(i.title)} (${i.status})</div>`).join('') || '<p class="loading-text">Пусто</p>'}
                </div>
            </div>
        `;
    } catch (e) {
        el.innerHTML = `<p class="loading-text" style="color: var(--danger)">Ошибка: ${e.message}</p>`;
    }
}

async function loadUsers() {
    const el = document.getElementById('admin-users');
    el.innerHTML = '<p class="loading-text">Загрузка пользователей...</p>';
    try {
        const res = await api('/admin/users');
        const data = await res.json();
        el.innerHTML = `
            <div class="glass-panel" style="padding: 16px;">
                <h3>Пользователи</h3>
                <div style="display:flex; flex-direction:column; gap:8px; margin-top:10px;">
                    ${(data.users || []).map(u => `<div style="display:flex; justify-content:space-between; padding:8px; border-bottom:1px solid var(--border-glass)"><span>${escapeHtml(u.username || u.telegram_id)}</span><span>💎${u.gems} 🎰${u.spins}</span></div>`).join('')}
                </div>
            </div>
        `;
    } catch (e) {
        el.innerHTML = `<p class="loading-text" style="color: var(--danger)">Ошибка: ${e.message}</p>`;
    }
}

// ==============================================================================
// Пакеты
// ==============================================================================

async function loadPackages() {
    const pkgEl = document.getElementById('admin-packages');
    pkgEl.innerHTML = '<p class="loading-text">Загрузка пакетов...</p>';
    try {
        const [spinRes, gemRes] = await Promise.all([
            api('/admin/spin-packages'),
            api('/admin/gem-packages'),
        ]);
        const spin = await spinRes.json();
        const gem = await gemRes.json();

        pkgEl.innerHTML = `
            <div class="glass-panel" style="padding: 16px; margin-bottom:12px;">
                <h3>Пакеты спинов (за GEMS)</h3>
                <form id="spin-pkg-form" style="display:flex; gap:8px; margin:10px 0; flex-wrap:wrap;">
                    <input type="text" id="spin-pkg-name" class="input" placeholder="Название" required>
                    <input type="number" id="spin-pkg-count" class="input" placeholder="Спины" required>
                    <input type="number" id="spin-pkg-price" class="input" placeholder="Цена GEMS" required>
                    <button type="submit" class="btn btn-primary btn-sm">Добавить</button>
                </form>
                <div style="display:flex; flex-direction:column; gap:8px;">
                    ${(spin.packages || []).map(p => `<div style="display:flex; justify-content:space-between; padding:8px; border-bottom:1px solid var(--border-glass)"><span>${escapeHtml(p.name)} (${p.spins_count} спинов)</span><b>${p.price_gems} GEMS</b></div>`).join('') || '<p class="loading-text">Нет пакетов</p>'}
                </div>
            </div>
            <div class="glass-panel" style="padding: 16px;">
                <h3>Пакеты GEMS (за Stars)</h3>
                <form id="gem-pkg-form" style="display:flex; gap:8px; margin:10px 0; flex-wrap:wrap;">
                    <input type="text" id="gem-pkg-name" class="input" placeholder="Название" required>
                    <input type="number" id="gem-pkg-amount" class="input" placeholder="GEMS" required>
                    <input type="number" id="gem-pkg-price" class="input" placeholder="Цена Stars" required>
                    <button type="submit" class="btn btn-primary btn-sm">Добавить</button>
                </form>
                <div style="display:flex; flex-direction:column; gap:8px;">
                    ${(gem.packages || []).map(p => `<div style="display:flex; justify-content:space-between; padding:8px; border-bottom:1px solid var(--border-glass)"><span>${escapeHtml(p.name)} (+${p.gems_amount} GEMS)</span><b>${p.price_stars} ⭐</b></div>`).join('') || '<p class="loading-text">Нет пакетов</p>'}
                </div>
            </div>
        `;

        document.getElementById('spin-pkg-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            await api('/admin/spin-packages', {
                method: 'POST',
                body: JSON.stringify({
                    name: document.getElementById('spin-pkg-name').value,
                    spins_count: parseInt(document.getElementById('spin-pkg-count').value, 10),
                    price_gems: parseInt(document.getElementById('spin-pkg-price').value, 10),
                }),
            });
            loadPackages();
        });

        document.getElementById('gem-pkg-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            await api('/admin/gem-packages', {
                method: 'POST',
                body: JSON.stringify({
                    name: document.getElementById('gem-pkg-name').value,
                    gems_amount: parseInt(document.getElementById('gem-pkg-amount').value, 10),
                    price_stars: parseInt(document.getElementById('gem-pkg-price').value, 10),
                }),
            });
            loadPackages();
        });
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
