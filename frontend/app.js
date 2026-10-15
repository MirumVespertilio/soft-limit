const API_BASE = '';
let token = null;
let currentUser = null;
let wheelData = null;
let isSpinning = false;

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
    localStorage.setItem('token', newToken);
}

function getStoredToken() {
    return localStorage.getItem('token');
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

async function auth() {
    if (!tg?.initData) {
        console.error('Not in Telegram');
        return;
    }
    const response = await api('/auth/telegram', {
        method: 'POST',
        body: JSON.stringify({ init_data: tg.initData }),
    });
    const data = await response.json();
    setToken(data.access_token);
    currentUser = data;
    updateUI();
}

function logout() {
    token = null;
    localStorage.removeItem('token');
    showLogin();
}

function showLogin() {
    document.getElementById('main-content').innerHTML = '<p>Откройте приложение в Telegram</p>';
}

function updateUI() {
    if (currentUser?.is_admin) {
        document.querySelector('[data-page="admin"]').classList.remove('hidden');
    }
    loadBalances();
    loadWheel();
}

async function loadBalances() {
    try {
        const response = await api('/me');
        const data = await response.json();
        document.getElementById('stars-balance').textContent = data.test_stars;
        document.getElementById('spins-balance').textContent = data.spins;
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
    const ctx = canvas.getContext('2d');
    const centerX = canvas.width / 2;
    const centerY = canvas.height / 2;
    const radius = centerX - 10;

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    if (!wheelData?.segments?.length) {
        ctx.beginPath();
        ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
        ctx.fillStyle = '#0f3460';
        ctx.fill();
        ctx.fillStyle = '#aaa';
        ctx.font = '16px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('Нет данных', centerX, centerY);
        return;
    }

    const segments = wheelData.segments;
    const totalWeight = segments.reduce((sum, s) => sum + s.weight, 0);
    let currentAngle = -Math.PI / 2;

    segments.forEach((seg, i) => {
        const sliceAngle = (seg.weight / totalWeight) * Math.PI * 2;
        const endAngle = currentAngle + sliceAngle;

        ctx.beginPath();
        ctx.moveTo(centerX, centerY);
        ctx.arc(centerX, centerY, radius, currentAngle, endAngle);
        ctx.closePath();
        ctx.fillStyle = i % 2 === 0 ? '#e94560' : '#0f3460';
        ctx.fill();
        ctx.strokeStyle = '#16213e';
        ctx.lineWidth = 2;
        ctx.stroke();

        const midAngle = currentAngle + sliceAngle / 2;
        const textRadius = radius * 0.7;
        const textX = centerX + Math.cos(midAngle) * textRadius;
        const textY = centerY + Math.sin(midAngle) * textRadius;

        ctx.save();
        ctx.translate(textX, textY);
        ctx.rotate(midAngle + Math.PI / 2);
        ctx.fillStyle = '#fff';
        ctx.font = 'bold 12px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(seg.label, 0, 0);
        ctx.restore();

        currentAngle = endAngle;
    });

    ctx.beginPath();
    ctx.arc(centerX, centerY, 20, 0, Math.PI * 2);
    ctx.fillStyle = '#16213e';
    ctx.fill();
    ctx.strokeStyle = '#e94560';
    ctx.lineWidth = 3;
    ctx.stroke();
}

function updateSpinButton() {
    const btn = document.getElementById('spin-btn');
    const spins = parseInt(document.getElementById('spins-balance').textContent) || 0;
    btn.disabled = spins <= 0 || isSpinning;
    btn.textContent = isSpinning ? 'Крутится...' : 'Крутить';
}

async function spin() {
    if (isSpinning) return;
    isSpinning = true;
    updateSpinButton();

    const idempotencyKey = crypto.randomUUID();

    try {
        const response = await api('/spins', {
            method: 'POST',
            body: JSON.stringify({ idempotency_key: idempotencyKey }),
        });
        const result = await response.json();

        if (response.ok) {
            await animateWheel(result.segment_id);
            showResult(result);
            loadBalances();
        } else {
            alert(result.detail || 'Ошибка');
        }
    } catch (e) {
        console.error('Spin failed:', e);
        alert('Ошибка соединения');
    } finally {
        isSpinning = false;
        updateSpinButton();
    }
}

function animateWheel(targetSegmentId) {
    return new Promise((resolve) => {
        const canvas = document.getElementById('wheel-canvas');
        const ctx = canvas.getContext('2d');
        const segments = wheelData.segments;
        const totalWeight = segments.reduce((sum, s) => sum + s.weight, 0);

        const targetIndex = segments.findIndex(s => s.segment_id === targetSegmentId);
        if (targetIndex === -1) {
            resolve();
            return;
        }

        let targetAngle = 0;
        for (let i = 0; i < targetIndex; i++) {
            targetAngle += (segments[i].weight / totalWeight) * Math.PI * 2;
        }
        targetAngle += (segments[targetIndex].weight / totalWeight) * Math.PI;

        const totalRotation = Math.PI * 2 * 5 + targetAngle;
        const duration = 4000;
        const startTime = performance.now();
        let currentRotation = 0;

        function animate(currentTime) {
            const elapsed = currentTime - startTime;
            const progress = Math.min(elapsed / duration, 1);
            const eased = 1 - Math.pow(1 - progress, 3);
            currentRotation = totalRotation * eased;

            ctx.save();
            ctx.translate(canvas.width / 2, canvas.height / 2);
            ctx.rotate(currentRotation);
            ctx.translate(-canvas.width / 2, -canvas.height / 2);
            ctx.restore();

            drawWheelWithRotation(currentRotation);

            if (progress < 1) {
                requestAnimationFrame(animate);
            } else {
                resolve();
            }
        }

        requestAnimationFrame(animate);
    });
}

function drawWheelWithRotation(rotation) {
    const canvas = document.getElementById('wheel-canvas');
    const ctx = canvas.getContext('2d');
    const centerX = canvas.width / 2;
    const centerY = canvas.height / 2;
    const radius = centerX - 10;

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    if (!wheelData?.segments?.length) return;

    const segments = wheelData.segments;
    const totalWeight = segments.reduce((sum, s) => sum + s.weight, 0);
    let currentAngle = -Math.PI / 2 + rotation;

    segments.forEach((seg, i) => {
        const sliceAngle = (seg.weight / totalWeight) * Math.PI * 2;
        const endAngle = currentAngle + sliceAngle;

        ctx.beginPath();
        ctx.moveTo(centerX, centerY);
        ctx.arc(centerX, centerY, radius, currentAngle, endAngle);
        ctx.closePath();
        ctx.fillStyle = i % 2 === 0 ? '#e94560' : '#0f3460';
        ctx.fill();
        ctx.strokeStyle = '#16213e';
        ctx.lineWidth = 2;
        ctx.stroke();

        const midAngle = currentAngle + sliceAngle / 2;
        const textRadius = radius * 0.7;
        const textX = centerX + Math.cos(midAngle) * textRadius;
        const textY = centerY + Math.sin(midAngle) * textRadius;

        ctx.save();
        ctx.translate(textX, textY);
        ctx.rotate(midAngle + Math.PI / 2);
        ctx.fillStyle = '#fff';
        ctx.font = 'bold 12px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(seg.label, 0, 0);
        ctx.restore();

        currentAngle = endAngle;
    });

    ctx.beginPath();
    ctx.arc(centerX, centerY, 20, 0, Math.PI * 2);
    ctx.fillStyle = '#16213e';
    ctx.fill();
    ctx.strokeStyle = '#e94560';
    ctx.lineWidth = 3;
    ctx.stroke();
}

function showResult(result) {
    document.getElementById('wheel-section').classList.add('hidden');
    document.getElementById('result-section').classList.remove('hidden');
    document.getElementById('result-title').textContent = result.title;
    document.getElementById('result-description').textContent = result.description || '';

    if (result.preview_media_id) {
        const img = document.getElementById('result-image');
        img.src = `/api/v1/media/${result.preview_media_id}/preview`;
        img.style.display = 'block';
    } else {
        document.getElementById('result-image').style.display = 'none';
    }
}

function hideResult() {
    document.getElementById('result-section').classList.add('hidden');
    document.getElementById('wheel-section').classList.remove('hidden');
}

async function loadInventory() {
    try {
        const response = await api('/inventory');
        const data = await response.json();
        const grid = document.getElementById('inventory-grid');
        grid.innerHTML = '';

        data.items.forEach(item => {
            const div = document.createElement('div');
            div.className = 'inventory-item';
            div.innerHTML = `
                ${item.preview_media_id ? `<img src="/api/v1/media/${item.preview_media_id}/preview" alt="${item.title}">` : ''}
                <h4>${item.title}</h4>
                <p>${item.media_type}</p>
            `;
            grid.appendChild(div);
        });
    } catch (e) {
        console.error('Failed to load inventory:', e);
    }
}

async function loadShop() {
    try {
        const response = await api('/spin-packages');
        const data = await response.json();
        const list = document.getElementById('packages-list');
        list.innerHTML = '';

        data.packages.forEach(pkg => {
            const div = document.createElement('div');
            div.className = 'package-item';
            div.innerHTML = `
                <div class="package-info">
                    <h3>${pkg.name}</h3>
                    <p>${pkg.spins_count} спинов</p>
                </div>
                <button class="btn btn-primary" onclick="buyPackage(${pkg.id})">${pkg.price_test_stars} ⭐</button>
            `;
            list.appendChild(div);
        });
    } catch (e) {
        console.error('Failed to load shop:', e);
    }
}

async function buyPackage(packageId) {
    const idempotencyKey = crypto.randomUUID();
    try {
        const response = await api('/spin-purchases', {
            method: 'POST',
            body: JSON.stringify({ package_id: packageId, idempotency_key: idempotencyKey }),
        });
        if (response.ok) {
            alert('Пакет куплен!');
            loadBalances();
        } else {
            const data = await response.json();
            alert(data.detail || 'Ошибка');
        }
    } catch (e) {
        alert('Ошибка соединения');
    }
}

async function loadAdminDashboard() {
    try {
        const response = await api('/admin/dashboard');
        const data = await response.json();
        document.getElementById('admin-dashboard').innerHTML = `
            <div class="admin-card">
                <h3>Пользователи</h3>
                <p>${data.users}</p>
            </div>
            <div class="admin-card">
                <h3>Спины</h3>
                <p>${data.spins}</p>
            </div>
            <div class="admin-card">
                <h3>Покупки</h3>
                <p>${data.purchases}</p>
            </div>
        `;
    } catch (e) {
        console.error('Failed to load admin dashboard:', e);
    }
}

async function loadAdminContent() {
    try {
        const response = await api('/admin/content');
        const data = await response.json();
        const container = document.getElementById('admin-content');
        container.innerHTML = '<h3>Создать карточку</h3>' +
            '<input type="text" id="content-title" placeholder="Название">' +
            '<textarea id="content-desc" placeholder="Описание"></textarea>' +
            '<select id="content-type"><option value="photo">Фото</option><option value="video">Видео</option></select>' +
            '<button class="btn btn-primary" onclick="createContent()">Создать</button>' +
            '<h3 style="margin-top:20px">Существующие</h3>';

        data.items.forEach(item => {
            const div = document.createElement('div');
            div.className = 'admin-card';
            div.innerHTML = `<h3>${item.title}</h3><p>${item.status} | ${item.media_type}</p>`;
            container.appendChild(div);
        });
    } catch (e) {
        console.error('Failed to load admin content:', e);
    }
}

async function createContent() {
    const title = document.getElementById('content-title').value;
    const description = document.getElementById('content-desc').value;
    const media_type = document.getElementById('content-type').value;

    try {
        const response = await api('/admin/content', {
            method: 'POST',
            body: JSON.stringify({ title, description, media_type }),
        });
        if (response.ok) {
            alert('Создано!');
            loadAdminContent();
        }
    } catch (e) {
        alert('Ошибка');
    }
}

async function loadAdminWheel() {
    try {
        const wheelsResponse = await api('/admin/wheels');
        const wheels = await wheelsResponse.json();
        const container = document.getElementById('admin-wheel');
        container.innerHTML = '<h3>Создать колесо</h3>' +
            '<input type="text" id="wheel-name" placeholder="Название">' +
            '<button class="btn btn-primary" onclick="createWheel()">Создать</button>' +
            '<h3 style="margin-top:20px">Колеса</h3>';

        wheels.wheels.forEach(w => {
            const div = document.createElement('div');
            div.className = 'admin-card';
            div.innerHTML = `<h3>${w.name}</h3><p>${w.status}</p>`;
            container.appendChild(div);
        });
    } catch (e) {
        console.error('Failed to load admin wheel:', e);
    }
}

async function createWheel() {
    const name = document.getElementById('wheel-name').value;
    try {
        const response = await api('/admin/wheels', {
            method: 'POST',
            body: JSON.stringify({ name }),
        });
        if (response.ok) {
            alert('Создано!');
            loadAdminWheel();
        }
    } catch (e) {
        alert('Ошибка');
    }
}

async function loadAdminUsers() {
    try {
        const response = await api('/admin/users');
        const data = await response.json();
        const container = document.getElementById('admin-users');
        container.innerHTML = '';

        data.users.forEach(u => {
            const div = document.createElement('div');
            div.className = 'admin-card';
            div.innerHTML = `<h3>${u.username || u.telegram_id}</h3>
                <p>⭐ ${u.test_stars} | 🎰 ${u.spins}</p>`;
            container.appendChild(div);
        });
    } catch (e) {
        console.error('Failed to load admin users:', e);
    }
}

async function loadAdminPackages() {
    try {
        const response = await api('/admin/spin-packages');
        const data = await response.json();
        const container = document.getElementById('admin-packages');
        container.innerHTML = '<h3>Создать пакет</h3>' +
            '<input type="text" id="pkg-name" placeholder="Название">' +
            '<input type="number" id="pkg-spins" placeholder="Спины">' +
            '<input type="number" id="pkg-price" placeholder="Цена">' +
            '<button class="btn btn-primary" onclick="createPackage()">Создать</button>' +
            '<h3 style="margin-top:20px">Пакеты</h3>';

        data.packages.forEach(p => {
            const div = document.createElement('div');
            div.className = 'admin-card';
            div.innerHTML = `<h3>${p.name}</h3><p>${p.spins_count} спинов | ${p.price_test_stars} ⭐</p>`;
            container.appendChild(div);
        });
    } catch (e) {
        console.error('Failed to load admin packages:', e);
    }
}

async function createPackage() {
    const name = document.getElementById('pkg-name').value;
    const spins_count = parseInt(document.getElementById('pkg-spins').value);
    const price_test_stars = parseInt(document.getElementById('pkg-price').value);

    try {
        const response = await api('/admin/spin-packages', {
            method: 'POST',
            body: JSON.stringify({ name, spins_count, price_test_stars }),
        });
        if (response.ok) {
            alert('Создано!');
            loadAdminPackages();
        }
    } catch (e) {
        alert('Ошибка');
    }
}

function showPage(page) {
    document.querySelectorAll('.section').forEach(s => s.classList.add('hidden'));
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));

    if (page === 'wheel') {
        document.getElementById('wheel-section').classList.remove('hidden');
        loadWheel();
    } else if (page === 'inventory') {
        document.getElementById('inventory-section').classList.remove('hidden');
        loadInventory();
    } else if (page === 'shop') {
        document.getElementById('shop-section').classList.remove('hidden');
        loadShop();
    } else if (page === 'admin') {
        document.getElementById('admin-section').classList.remove('hidden');
        loadAdminDashboard();
    }

    document.querySelector(`[data-page="${page}"]`).classList.add('active');
}

function showAdminTab(tab) {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

    document.querySelector(`[data-tab="${tab}"]`).classList.add('active');
    document.getElementById(`admin-${tab}`).classList.add('active');

    if (tab === 'dashboard') loadAdminDashboard();
    else if (tab === 'content') loadAdminContent();
    else if (tab === 'wheel') loadAdminWheel();
    else if (tab === 'users') loadAdminUsers();
    else if (tab === 'packages') loadAdminPackages();
}

document.addEventListener('DOMContentLoaded', () => {
    token = getStoredToken();

    if (token) {
        loadBalances();
        loadWheel();
    } else if (tg?.initData) {
        auth();
    } else {
        showLogin();
    }

    document.getElementById('spin-btn')?.addEventListener('click', spin);
    document.getElementById('result-close')?.addEventListener('click', hideResult);

    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.addEventListener('click', () => showPage(btn.dataset.page));
    });

    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => showAdminTab(btn.dataset.tab));
    });
});
