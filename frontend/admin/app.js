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
            else if (tabId === 'stats') loadStats();
            else if (tabId === 'content') loadContent();
            else if (tabId === 'wheel') loadWheel();
            else if (tabId === 'media') loadMedia();
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

// ==============================================================================
// Статистика / Аналитика
// ==============================================================================

let statsCharts = [];
let statsModels = [];

function destroyStatsCharts() {
    statsCharts.forEach(c => { try { c.destroy(); } catch (_) {} });
    statsCharts = [];
}

function fmtUsd(v) {
    return '$' + Number(v || 0).toFixed(3).replace(/\.?0+$/, '') ;
}

function renderStatsCharts(daily) {
    destroyStatsCharts();
    const labels = daily.map(d => d.date.slice(5));
    const usdData = daily.map(d => d.revenue_usd);
    const typeLabels = { welcome: 'Welcome', standard: 'Standard', bonus: 'Колесо', media: 'Медиа' };

    const usdCtx = document.getElementById('chart-revenue');
    if (usdCtx) {
        statsCharts.push(new Chart(usdCtx, {
            type: 'line',
            data: {
                labels,
                datasets: [{
                    label: 'Выручка, USD',
                    data: usdData,
                    borderColor: '#ff007f',
                    backgroundColor: 'rgba(255,0,127,0.12)',
                    fill: true,
                    tension: 0.3,
                    pointRadius: 2,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: { x: { ticks: { color: 'rgba(255,255,255,0.55)' } }, y: { ticks: { color: 'rgba(255,255,255,0.55)' }, beginAtZero: true } },
                plugins: { legend: { labels: { color: 'rgba(255,255,255,0.8)' } } },
            },
        }));
    }

    const spinsCtx = document.getElementById('chart-spins');
    if (spinsCtx) {
        const datasets = ['welcome', 'standard', 'bonus', 'media'].map(type => ({
            label: typeLabels[type],
            data: daily.map(d => (d.spins_by_type || {})[type] || 0),
            borderWidth: 1,
        }));
        statsCharts.push(new Chart(spinsCtx, {
            type: 'bar',
            data: { labels, datasets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: { x: { stacked: true, ticks: { color: 'rgba(255,255,255,0.55)' } }, y: { stacked: true, ticks: { color: 'rgba(255,255,255,0.55)' }, beginAtZero: true, precision: 0 } },
                plugins: { legend: { labels: { color: 'rgba(255,255,255,0.8)' } } },
            },
        }));
    }
}

async function loadStats() {
    const el = document.getElementById('admin-stats');
    el.innerHTML = '<p class="loading-text">Загрузка статистики...</p>';
    try {
        const params = new URLSearchParams();
        const period = document.getElementById('stats-period')?.value || 'all';
        const modelSel = document.getElementById('stats-model');
        params.set('period', period);
        if (modelSel && modelSel.value) params.set('model_id', modelSel.value);

        const [statsRes, modelsRes] = await Promise.all([
            api(`/admin/stats?${params.toString()}`),
            api('/admin/models'),
        ]);
        const data = await statsRes.json();
        statsModels = (await modelsRes.json()).models || [];
        const t = data.totals || {};
        const options = `<option value="">Все модели</option>` + statsModels.map(m =>
            `<option value="${m.id}" ${data.model_id === m.id ? 'selected' : ''}>${escapeHtml(m.name)} (#${m.id})</option>`
        ).join('');

        el.innerHTML = `
            <div class="glass-panel stats-panel">
                <div class="stats-controls">
                    <select id="stats-period" class="input">
                        <option value="day" ${period === 'day' ? 'selected' : ''}>Сутки</option>
                        <option value="week" ${period === 'week' ? 'selected' : ''}>Неделя</option>
                        <option value="month" ${period === 'month' ? 'selected' : ''}>Месяц</option>
                        <option value="all" ${period === 'all' ? 'selected' : ''}>Всё время</option>
                    </select>
                    <select id="stats-model" class="input">${options}</select>
                    <button id="stats-refresh" class="btn btn-primary btn-sm">Обновить</button>
                </div>
                <div class="stat-cards">
                    <div class="stat-card"><div class="stat-value">${fmtUsd(t.revenue_usd)}</div><div class="stat-label">Выручка (USD)</div></div>
                    <div class="stat-card"><div class="stat-value">${t.revenue_gems_spent ?? 0}</div><div class="stat-label">GEMS потрачено</div></div>
                    <div class="stat-card"><div class="stat-value">${t.revenue_stars ?? 0} ⭐</div><div class="stat-label">Telegram Stars</div></div>
                    <div class="stat-card"><div class="stat-value">${t.users_total ?? 0} (+${t.users_new ?? 0})</div><div class="stat-label">Пользователи</div></div>
                    <div class="stat-card"><div class="stat-value">${((t.conversion_rate || 0) * 100).toFixed(2)}%</div><div class="stat-label">Конверсия покупок</div></div>
                    <div class="stat-card"><div class="stat-value">${t.purchases_total ?? 0}</div><div class="stat-label">Покупок всего</div></div>
                    <div class="stat-card"><div class="stat-value">${t.spins_total ?? 0}</div><div class="stat-label">Спинов всего</div></div>
                    <div class="stat-card"><div class="stat-value">${t.duplicates ?? 0}</div><div class="stat-label">Дубликаты</div></div>
                </div>
                <div class="stat-breakdown">
                    ${Object.entries(t.spins_by_type || {}).map(([k, v]) => `<span class="no-bot-tag">${k}: ${v}</span>`).join(' ')}
                </div>
            </div>
            <div class="glass-panel stats-panel">
                <h3>Выручка (USD) за 30 дней</h3>
                <div class="chart-wrap"><canvas id="chart-revenue"></canvas></div>
            </div>
            <div class="glass-panel stats-panel">
                <h3>Спины по типам за 30 дней</h3>
                <div class="chart-wrap"><canvas id="chart-spins"></canvas></div>
            </div>
            <div class="glass-panel stats-panel">
                <h3>По моделям</h3>
                <div style="display:flex; flex-direction:column; gap:6px; margin-top:10px;">
                    ${(data.per_model || []).map(m => `
                        <div class="model-stats-row">
                            <span><b>${escapeHtml(m.model_name)}</b></span>
                            <span>${m.spins} спинов • ${m.spin_purchases} покупок • 💎${m.revenue_gems_spent} • ${fmtUsd(m.revenue_usd)}</span>
                        </div>
                    `).join('') || '<p class="loading-text">Нет данных по моделям</p>'}
                </div>
            </div>
        `;

        renderStatsCharts(data.daily || []);

        document.getElementById('stats-refresh').addEventListener('click', () => loadStats());
        document.getElementById('stats-period').addEventListener('change', () => loadStats());
        document.getElementById('stats-model').addEventListener('change', () => loadStats());
    } catch (e) {
        el.innerHTML = `<p class="loading-text" style="color: var(--danger)">Ошибка: ${e.message}</p>`;
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
// Медиа
// ==============================================================================

async function loadMedia() {
    const el = document.getElementById('admin-media');
    el.innerHTML = '<p class="loading-text">Загрузка медиа...</p>';
    try {
        const [mediaRes, contentRes] = await Promise.all([
            api('/admin/media'),
            api('/admin/content'),
        ]);
        const media = await mediaRes.json();
        const content = (await contentRes.json()).items || [];
        const contentOptions = content.map(c => `<option value="${c.id}">${escapeHtml(c.title)} (#${c.id})</option>`).join('');

        el.innerHTML = `
            <div class="glass-panel" style="padding: 16px;">
                <h3>Загрузка медиа</h3>
                <form id="media-upload-form" style="display:flex; flex-direction:column; gap:8px; margin:12px 0;">
                    <select id="media-content" class="input" required>
                        <option value="">Выберите контент</option>${contentOptions}
                    </select>
                    <select id="media-role" class="input">
                        <option value="preview">Preview</option>
                        <option value="main">Main</option>
                    </select>
                    <input type="file" id="media-file" class="input" accept="image/jpeg,image/png,image/webp,video/mp4" required>
                    <button type="submit" class="btn btn-primary btn-sm">Загрузить</button>
                </form>
                <div style="display:flex; flex-direction:column; gap:8px;">
                    ${(media.items || []).map(a => `
                        <div style="display:flex; justify-content:space-between; padding:8px; border-bottom:1px solid var(--border-glass)">
                            <span>#${a.id} ${escapeHtml(a.file_name || '')}</span>
                            <span>${a.file_type} • ${(a.file_size / 1024).toFixed(0)} KB</span>
                        </div>
                    `).join('') || '<p class="loading-text">Нет загруженных медиа</p>'}
                </div>
            </div>
        `;

        document.getElementById('media-upload-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            const contentId = document.getElementById('media-content').value;
            const role = document.getElementById('media-role').value;
            const fileInput = document.getElementById('media-file');
            if (!contentId || !fileInput.files.length) {
                alert('Выберите контент и файл');
                return;
            }
            const formData = new FormData();
            formData.append('file', fileInput.files[0]);
            formData.append('content_item_id', contentId);
            formData.append('role', role);
            const response = await fetch('/api/v1/admin/media/upload', {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` },
                body: formData,
            });
            if (!response.ok) {
                const err = await response.json().catch(() => ({}));
                alert('Ошибка загрузки: ' + (err.detail || response.status));
                return;
            }
            loadMedia();
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
