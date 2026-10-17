const API_BASE = '';
let token = null;
let currentUser = null;
let wheelData = null;
let isSpinning = false;
let currentModelId = null;

const tg = window.Telegram?.WebApp;
if (tg) {
    tg.ready();
    tg.expand();
}

// Извлечение model_id из URL параметров
function getModelIdFromUrl() {
    const urlParams = new URLSearchParams(window.location.search);
    const id = urlParams.get('model_id') || tg?.initDataUnsafe?.start_param;
    return id ? parseInt(id, 10) : null;
}

function getToken() {
    return token;
}

function setToken(newToken) {
    token = newToken;
    localStorage.setItem('user_token', newToken);
}

function getStoredToken() {
    return localStorage.getItem('user_token');
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
    localStorage.removeItem('user_token');
    document.getElementById('main-content').innerHTML = '<p style="text-align:center; padding:30px;">Откройте приложение через бота модели в Telegram</p>';
}

// Загрузка и динамическое применение темы модели
async function applyModelTheme(modelId) {
    if (!modelId) return;
    try {
        const res = await api(`/models/${modelId}/theme`);
        if (!res.ok) return;
        const data = await res.json();

        if (data.name) {
            document.getElementById('model-header-title').textContent = data.name;
        }

        const theme = data.theme || {};
        const root = document.documentElement;

        if (theme.primary_color) {
            root.style.setProperty('--primary-color', theme.primary_color);
            root.style.setProperty('--primary-glow', hexToRgba(theme.primary_color, 0.4));
        }
        if (theme.accent_color || theme.accent) {
            const acc = theme.accent_color || theme.accent;
            root.style.setProperty('--accent-color', acc);
        }
        if (theme.background_color || theme.bg_color) {
            const bg = theme.background_color || theme.bg_color;
            root.style.setProperty('--bg-color', bg);
        }
        if (theme.card_bg) {
            root.style.setProperty('--card-bg', theme.card_bg);
        }
        if (theme.bg_gradient_top) {
            root.style.setProperty('--bg-gradient-top', theme.bg_gradient_top);
        }
        if (theme.bg_gradient_bottom) {
            root.style.setProperty('--bg-gradient-bottom', theme.bg_gradient_bottom);
        }
    } catch (e) {
        console.warn('Could not load model theme, using defaults:', e);
    }
}

function hexToRgba(hex, alpha) {
    let c = hex.replace('#', '');
    if (c.length === 3) c = c.split('').map(x => x + x).join('');
    const num = parseInt(c, 16);
    return `rgba(${(num >> 16) & 255}, ${(num >> 8) & 255}, ${num & 255}, ${alpha})`;
}

async function auth() {
    currentModelId = getModelIdFromUrl();

    if (!tg?.initData) {
        console.log('Not in Telegram webapp, trying stored or demo auth');
        const stored = getStoredToken();
        if (stored) {
            token = stored;
            if (currentModelId) applyModelTheme(currentModelId);
            initNavigation();
            updateUI();
            return;
        }
        document.getElementById('main-content').innerHTML = '<p style="text-align:center; padding:30px;">Пожалуйста, запустите Mini-App внутри Telegram.</p>';
        return;
    }

    try {
        const response = await api('/auth/telegram', {
            method: 'POST',
            body: JSON.stringify({
                init_data: tg.initData,
                model_id: currentModelId,
            }),
        });
        const data = await response.json();
        setToken(data.access_token);
        currentUser = data;

        if (currentModelId) {
            applyModelTheme(currentModelId);
        }

        initNavigation();
        updateUI();
    } catch (e) {
        console.error('Auth failed:', e);
    }
}

function initNavigation() {
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.section').forEach(s => s.classList.add('hidden'));

            btn.classList.add('active');
            const page = btn.getAttribute('data-page');
            const section = document.getElementById(`${page}-section`);
            if (section) {
                section.classList.remove('hidden');
            }

            if (page === 'inventory') loadInventory();
            else if (page === 'shop') loadShop();
            else if (page === 'wheel') loadWheel();
        });
    });

    document.querySelectorAll('.shop-tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.shop-tab-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            const tab = btn.getAttribute('data-shop-tab');
            if (tab === 'spins') {
                document.getElementById('packages-list').classList.remove('hidden');
                document.getElementById('gem-packages-list').classList.add('hidden');
            } else {
                document.getElementById('packages-list').classList.add('hidden');
                document.getElementById('gem-packages-list').classList.remove('hidden');
                loadGemPackages();
            }
        });
    });

    document.getElementById('result-close')?.addEventListener('click', () => {
        document.getElementById('result-section').classList.add('hidden');
        document.getElementById('wheel-section').classList.remove('hidden');
    });

    document.getElementById('spin-btn')?.addEventListener('click', doSpin);
}

function updateUI() {
    loadBalances();
    loadWheel();
}

async function loadBalances() {
    try {
        const response = await api('/me');
        const data = await response.json();
        document.getElementById('gems-balance').textContent = data.gems ?? 0;
        document.getElementById('spins-balance').textContent = data.spins ?? 0;
    } catch (e) {
        console.error('Failed to load balances:', e);
    }
}

async function loadWheel() {
    try {
        const response = await api('/wheel');
        wheelData = await response.json();
        drawWheel();
        updateSpinButton();
    } catch (e) {
        console.error('Failed to load wheel:', e);
    }
}

function drawWheel() {
    const canvas = document.getElementById('wheel-canvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const width = canvas.width;
    const height = canvas.height;
    const centerX = width / 2;
    const centerY = height / 2;
    const radius = width / 2 - 10;

    ctx.clearRect(0, 0, width, height);

    if (!wheelData || !wheelData.segments || wheelData.segments.length === 0) {
        ctx.fillStyle = '#23253b';
        ctx.beginPath();
        ctx.arc(centerX, centerY, radius, 0, 2 * Math.PI);
        ctx.fill();
        ctx.fillStyle = '#ffffff';
        ctx.font = '14px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('Загрузка колеса...', centerX, centerY);
        return;
    }

    const segments = wheelData.segments;
    const totalSegments = segments.length;
    const anglePerSegment = (2 * Math.PI) / totalSegments;

    const colors = [
        '#e94560', '#533483', '#0f3460', '#ff007f', '#7928ca', '#00f2fe'
    ];

    segments.forEach((seg, i) => {
        const startAngle = i * anglePerSegment;
        const endAngle = startAngle + anglePerSegment;

        ctx.beginPath();
        ctx.moveTo(centerX, centerY);
        ctx.arc(centerX, centerY, radius, startAngle, endAngle);
        ctx.fillStyle = colors[i % colors.length];
        ctx.fill();
        ctx.strokeStyle = 'rgba(255,255,255,0.15)';
        ctx.lineWidth = 1.5;
        ctx.stroke();

        ctx.save();
        ctx.translate(centerX, centerY);
        ctx.rotate(startAngle + anglePerSegment / 2);
        ctx.textAlign = 'right';
        ctx.fillStyle = '#fff';
        ctx.font = 'bold 12px sans-serif';
        ctx.fillText(seg.label || `Prize ${i+1}`, radius - 20, 5);
        ctx.restore();
    });
}

function updateSpinButton() {
    const btn = document.getElementById('spin-btn');
    if (!btn) return;
    btn.disabled = isSpinning;
}

async function doSpin() {
    if (isSpinning) return;
    isSpinning = true;
    updateSpinButton();

    try {
        const idemKey = `spin_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
        const res = await api('/spins', {
            method: 'POST',
            body: JSON.stringify({ idempotency_key: idemKey }),
        });

        if (!res.ok) {
            const err = await res.json();
            alert(err.detail || 'Не удалось выполнить спин');
            isSpinning = false;
            updateSpinButton();
            return;
        }

        const data = await res.json();
        // Анимация и показ результата
        showResult(data);
        loadBalances();
    } catch (e) {
        alert('Ошибка при крутке: ' + e.message);
    } finally {
        isSpinning = false;
        updateSpinButton();
    }
}

function showResult(prize) {
    document.getElementById('wheel-section').classList.add('hidden');
    const resultSec = document.getElementById('result-section');
    resultSec.classList.remove('hidden');

    document.getElementById('result-title').textContent = prize.title || 'Поздравляем!';
    document.getElementById('result-description').textContent = prize.description || 'Вы выиграли эксклюзивную карточку!';
    const imgEl = document.getElementById('result-image');
    if (prize.preview_media_id) {
        imgEl.src = `${API_BASE}/api/v1/media/${prize.preview_media_id}/file`;
        imgEl.classList.remove('hidden');
    } else {
        imgEl.classList.add('hidden');
    }
}

async function loadInventory() {
    const grid = document.getElementById('inventory-grid');
    grid.innerHTML = '<p style="text-align:center; grid-column:span 2;">Загрузка коллекции...</p>';
    try {
        const res = await api('/inventory');
        const data = await res.json();
        const items = data.items || [];
        if (items.length === 0) {
            grid.innerHTML = '<p style="text-align:center; grid-column:span 2; color:var(--text-secondary);">Ваша коллекция пока пуста. Крутите колесо!</p>';
            return;
        }
        grid.innerHTML = items.map(item => `
            <div class="inventory-card">
                ${item.preview_media_id ? `<img src="${API_BASE}/api/v1/media/${item.preview_media_id}/file" alt="Item">` : '<div style="height:100px; display:flex; align-items:center;">🖼️</div>'}
                <h3>${escapeHtml(item.title)}</h3>
            </div>
        `).join('');
    } catch (e) {
        grid.innerHTML = `<p style="grid-column:span 2; color:var(--primary-color);">Ошибка: ${e.message}</p>`;
    }
}

async function loadShop() {
    const list = document.getElementById('packages-list');
    list.innerHTML = '<p style="text-align:center;">Загрузка пакетов...</p>';
    try {
        const res = await api('/spin-packages');
        const data = await res.json();
        const pkgs = data.packages || [];
        if (pkgs.length === 0) {
            list.innerHTML = '<p style="text-align:center; color:var(--text-secondary);">Нет доступных пакетов спинов</p>';
            return;
        }
        list.innerHTML = pkgs.map(p => `
            <div class="package-card">
                <div class="package-info">
                    <h3>${escapeHtml(p.name)}</h3>
                    <p>+${p.spins_count} спинов</p>
                </div>
                <button class="btn btn-primary btn-sm buy-spin-btn" data-id="${p.id}" data-price="${p.price_gems}">
                    ${p.price_gems} 💎
                </button>
            </div>
        `).join('');

        document.querySelectorAll('.buy-spin-btn').forEach(btn => {
            btn.addEventListener('click', async () => {
                const pkgId = parseInt(btn.getAttribute('data-id'), 10);
                await buySpinPackage(pkgId);
            });
        });
    } catch (e) {
        list.innerHTML = `<p style="color:var(--primary-color);">Ошибка: ${e.message}</p>`;
    }
}

async function loadGemPackages() {
    const list = document.getElementById('gem-packages-list');
    list.innerHTML = '<p style="text-align:center;">Загрузка предложений GEMS...</p>';
    try {
        const res = await api('/gem-packages');
        const data = await res.json();
        const pkgs = data.packages || [];
        if (pkgs.length === 0) {
            list.innerHTML = '<p style="text-align:center; color:var(--text-secondary);">Нет доступных предложений GEMS</p>';
            return;
        }
        list.innerHTML = pkgs.map(p => `
            <div class="package-card">
                <div class="package-info">
                    <h3>${escapeHtml(p.name)}</h3>
                    <p>+${p.gems_amount} GEMS</p>
                </div>
                <button class="btn btn-primary btn-sm buy-gem-btn" data-id="${p.id}" data-price="${p.price_stars}">
                    ${p.price_stars} ⭐
                </button>
            </div>
        `).join('');

        document.querySelectorAll('.buy-gem-btn').forEach(btn => {
            btn.addEventListener('click', async () => {
                const pkgId = parseInt(btn.getAttribute('data-id'), 10);
                await buyGemPackage(pkgId);
            });
        });
    } catch (e) {
        list.innerHTML = `<p style="color:var(--primary-color);">Ошибка: ${e.message}</p>`;
    }
}

async function buySpinPackage(pkgId) {
    try {
        const idemKey = `spinpkg_${pkgId}_${Date.now()}`;
        const res = await api('/spin-purchases', {
            method: 'POST',
            body: JSON.stringify({
                package_id: pkgId,
                idempotency_key: idemKey,
            }),
        });
        if (!res.ok) {
            const err = await res.json();
            alert(err.detail || 'Недостаточно GEMS для покупки спинов');
            return;
        }
        alert('Спины успешно добавлены!');
        loadBalances();
    } catch (e) {
        alert('Ошибка при покупке: ' + e.message);
    }
}

async function buyGemPackage(pkgId) {
    try {
        // Создаем ссылку на инвойс через Telegram Stars Payments API
        const res = await api('/gem-purchases/invoice-link', {
            method: 'POST',
            body: JSON.stringify({ package_id: pkgId }),
        });

        if (!res.ok) {
            const err = await res.json();
            alert(err.detail || 'Ошибка создания счёта');
            return;
        }

        const data = await res.json();

        // Если запущено в Telegram — открываем встроенное окно оплаты Telegram Stars
        if (tg?.openInvoice) {
            tg.openInvoice(data.invoice_link, async (status) => {
                if (status === 'paid') {
                    // Завершаем покупку и зачисляем GEMS
                    const compRes = await api('/gem-purchases/complete', {
                        method: 'POST',
                        body: JSON.stringify({
                            package_id: pkgId,
                            idempotency_key: `gem_paid_${Date.now()}`,
                        }),
                    });
                    if (compRes.ok) {
                        alert('Оплата прошла успешно! GEMS начислены.');
                        loadBalances();
                    }
                } else if (status === 'cancelled') {
                    console.log('Payment cancelled');
                } else {
                    alert('Статус платежа: ' + status);
                }
            });
        } else {
            alert(`В тестовом режиме: ссылка на инвойс ${data.invoice_link}`);
        }
    } catch (e) {
        alert('Ошибка: ' + e.message);
    }
}

function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
}

document.addEventListener('DOMContentLoaded', () => {
    auth();
});
