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

let pendingSpinKey = null;

async function spin() {
    if (isSpinning) return;
    isSpinning = true;
    updateSpinButton();

    const idempotencyKey = pendingSpinKey || crypto.randomUUID();

    try {
        const response = await api('/spins', {
            method: 'POST',
            body: JSON.stringify({ idempotency_key: idempotencyKey }),
        });
        const result = await response.json();

        if (response.ok) {
            pendingSpinKey = null;
            await animateWheel(result.segment_id, result.content_item_id);
            showResult(result);
            loadBalances();
        } else {
            alert(result.detail || 'Ошибка');
        }
    } catch (e) {
        console.error('Spin failed:', e);
        pendingSpinKey = idempotencyKey;
        alert('Ошибка соединения. Повторите попытку.');
    } finally {
        isSpinning = false;
        updateSpinButton();
    }
}

function animateWheel(targetSegmentId, targetContentItemId) {
    return new Promise((resolve) => {
        const canvas = document.getElementById('wheel-canvas');
        const ctx = canvas.getContext('2d');
        const segments = wheelData.segments;
        const totalWeight = segments.reduce((sum, s) => sum + s.weight, 0);

        let targetIndex = -1;
        if (targetSegmentId) {
            targetIndex = segments.findIndex(s => s.segment_id === targetSegmentId);
        }
        if (targetIndex === -1 && targetContentItemId) {
            targetIndex = segments.findIndex(s => s.content_item_id === targetContentItemId);
        }
        if (targetIndex === -1) {
            resolve();
            return;
        }

        let targetAngle = 0;
        for (let i = 0; i < targetIndex; i++) {
            targetAngle += (segments[i].weight / totalWeight) * Math.PI * 2;
        }
        targetAngle += (segments[targetIndex].weight / totalWeight) * Math.PI;

        const pointerAngle = -Math.PI / 2;
        const correction = ((-targetAngle % (Math.PI * 2)) + Math.PI * 2) % (Math.PI * 2);

        const totalRotation = Math.PI * 2 * 5 + correction;
        const duration = 4000;
        const startTime = performance.now();
        let currentRotation = 0;

        function animate(currentTime) {
            const elapsed = currentTime - startTime;
            const progress = Math.min(elapsed / duration, 1);
            const eased = 1 - Math.pow(1 - progress, 3);
            currentRotation = totalRotation * eased;

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

async function loadPreviewImage(mediaId, imgElement) {
    try {
        const response = await api(`/media/${mediaId}/preview`);
        if (response.ok) {
            const blob = await response.blob();
            imgElement.src = URL.createObjectURL(blob);
            imgElement.style.display = 'block';
        } else {
            imgElement.style.display = 'none';
        }
    } catch (e) {
        imgElement.style.display = 'none';
    }
}

function showResult(result) {
    document.getElementById('wheel-section').classList.add('hidden');
    document.getElementById('result-section').classList.remove('hidden');
    document.getElementById('result-title').textContent = result.title;
    document.getElementById('result-description').textContent = result.description || '';

    if (result.preview_media_id) {
        loadPreviewImage(result.preview_media_id, document.getElementById('result-image'));
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

        for (const item of data.items) {
            const div = document.createElement('div');
            div.className = 'inventory-item';
            const imgHtml = item.preview_media_id
                ? `<img id="inv-img-${item.inventory_id}" src="" alt="${item.title}" style="display:none">`
                : '';
            div.innerHTML = `${imgHtml}<h4>${item.title}</h4><p>${item.media_type}</p>`;
            grid.appendChild(div);
            if (item.preview_media_id) {
                await loadPreviewImage(item.preview_media_id, div.querySelector('img'));
            }
        }
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

const pendingPurchaseKeys = {};

async function buyPackage(packageId) {
    const idempotencyKey = pendingPurchaseKeys[packageId] || crypto.randomUUID();

    try {
        const response = await api('/spin-purchases', {
            method: 'POST',
            body: JSON.stringify({ package_id: packageId, idempotency_key: idempotencyKey }),
        });
        if (response.ok) {
            pendingPurchaseKeys[packageId] = null;
            alert('Пакет куплен!');
            loadBalances();
        } else {
            const data = await response.json();
            alert(data.detail || 'Ошибка');
        }
    } catch (e) {
        pendingPurchaseKeys[packageId] = idempotencyKey;
        alert('Ошибка соединения. Повторите попытку.');
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
            div.innerHTML = `<h3>${item.title}</h3><p>${item.status} | ${item.media_type}</p>` +
                (item.status === 'draft' ? `<button class="btn btn-secondary" onclick="publishContent(${item.id})">Опубликовать</button>` : '');
            container.appendChild(div);
        });
    } catch (e) {
        console.error('Failed to load admin content:', e);
    }
}

async function publishContent(contentId) {
    try {
        await api(`/admin/content/${contentId}`, {
            method: 'PATCH',
            body: JSON.stringify({ status: 'published' }),
        });
        alert('Опубликовано');
        loadAdminContent();
    } catch (e) {
        alert('Ошибка: ' + (e.message || 'не удалось'));
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
            '<h3 style="margin-top:20px">Сектора активного колеса</h3>' +
            '<div id="wheel-segments"></div>' +
            '<h3>Добавить сектор</h3>' +
            '<select id="segment-content-item"></select>' +
            '<input type="text" id="segment-label" placeholder="Подпись">' +
            '<input type="number" id="segment-weight" placeholder="Вес" value="1" min="1">' +
            '<input type="number" id="segment-position" placeholder="Позиция" value="0">' +
            '<button class="btn btn-primary" onclick="addSegment()">Добавить</button>' +
            '<h3 style="margin-top:20px">Колеса</h3>';

        const wheel = wheels.wheels.find(w => w.status === 'active');
        if (wheel) {
            const resp = await fetch(`/api/v1/wheel`, { headers: { 'Authorization': `Bearer ${token}` } });
            if (resp.ok) {
                const data = await resp.json();
                const segContainer = document.getElementById('wheel-segments');
                segContainer.innerHTML = '';
                data.segments.forEach(seg => {
                    const div = document.createElement('div');
                    div.className = 'admin-card';
                    div.innerHTML = `<p><strong>${seg.label}</p><p>Вес: ${seg.weight} | Позиция: ${seg.content_item_id}</p>`;
                    segContainer.appendChild(div);
                });
            }
        }

        const contentResp = await api('/admin/content');
        const contentData = await contentResp.json();
        const select = document.getElementById('segment-content-item');
        select.innerHTML = '';
        contentData.items.forEach(item => {
            const opt = document.createElement('option');
            opt.value = item.id;
            opt.textContent = item.title;
            select.appendChild(opt);
        });

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

async function addSegment() {
    const content_item_id = parseInt(document.getElementById('segment-content-item').value);
    const label = document.getElementById('segment-label').value;
    const weight = parseInt(document.getElementById('segment-weight').value);
    const position = parseInt(document.getElementById('segment-position').value);

    try {
        const wheelsResponse = await api('/admin/wheels');
        const wheels = await wheelsResponse.json();
        const wheel = wheels.wheels.find(w => w.status === 'active');
        if (!wheel) { alert('Нет активного колеса'); return; }

        await api(`/admin/wheels/${wheel.id}/segments`, {
            method: 'PUT',
            body: JSON.stringify({ segments: [{ content_item_id, label, weight, position }] }),
        });
        alert('Сектор добавлен');
        loadAdminWheel();
    } catch (e) {
        alert('Ошибка');
    }
}

async function loadAdminMedia() {
    try {
        const resp = await api('/admin/media');
        const data = await resp.json();
        const container = document.getElementById('admin-media');
        container.innerHTML = '<h3>Загрузить медиа</h3>' +
            '<select id="media-content-item"></select>' +
            '<select id="media-role"><option value="preview">Превью</option><option value="main">Основное</option></select>' +
            '<input type="file" id="media-file">' +
            '<button class="btn btn-primary" onclick="uploadMedia()">Загрузить</button>' +
            '<h3 style="margin-top:20px">Медиатека</h3>';

        const contentResp = await api('/admin/content');
        const contentData = await contentResp.json();
        const select = document.getElementById('media-content-item');
        select.innerHTML = '';
        contentData.items.forEach(item => {
            const opt = document.createElement('option');
            opt.value = item.id;
            opt.textContent = item.title;
            select.appendChild(opt);
        });

        data.items.forEach(m => {
            const div = document.createElement('div');
            div.className = 'admin-card';
            div.innerHTML = `<p>${m.file_name || 'Без имени'} | ${m.file_type} | ${m.file_size} bytes</p>`;
            container.appendChild(div);
        });
    } catch (e) {
        console.error('Failed to load media:', e);
    }
}

async function uploadMedia() {
    const content_item_id = document.getElementById('media-content-item').value;
    const role = document.getElementById('media-role').value;
    const fileInput = document.getElementById('media-file');
    if (!fileInput.files.length) { alert('Выберите файл'); return; }

    const formData = new FormData();
    formData.append('file', fileInput.files[0]);
    formData.append('content_item_id', content_item_id);
    formData.append('role', role);

    try {
        const response = await fetch('/api/v1/admin/media/upload', {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}` },
            body: formData,
        });
        if (response.ok) {
            alert('Загружено');
            loadAdminMedia();
        } else {
            alert('Ошибка загрузки');
        }
    } catch (e) {
        alert('Ошибка');
    }
}

async function loadAdminWelcomePool() {
    try {
        const resp = await api('/admin/welcome-pool');
        const data = await resp.json();
        const container = document.getElementById('admin-welcome-pool');
        container.innerHTML = '<h3>Приветственный пул</h3><select id="welcome-item-select" multiple size="5"></select>' +
            '<button class="btn btn-primary" onclick="saveWelcomePool()">Сохранить</button>';

        const contentResp = await api('/admin/content');
        const contentData = await contentResp.json();
        const select = document.getElementById('welcome-item-select');
        select.innerHTML = '';
        contentData.items.filter(i => i.status === 'published').forEach(item => {
            const opt = document.createElement('option');
            opt.value = item.id;
            opt.textContent = item.title;
            if (data.items.find(w => w.content_item_id === item.id)) opt.selected = true;
            select.appendChild(opt);
        });
    } catch (e) {
        console.error('Failed to load welcome pool:', e);
    }
}

async function saveWelcomePool() {
    const select = document.getElementById('welcome-item-select');
    const ids = Array.from(select.selectedOptions).map(o => parseInt(o.value));
    try {
        await api('/admin/welcome-pool', {
            method: 'PUT',
            body: JSON.stringify({ content_item_ids: ids }),
        });
        alert('Сохранено');
    } catch (e) {
        alert('Ошибка');
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
    else if (tab === 'media') loadAdminMedia();
    else if (tab === 'welcome') loadAdminWelcomePool();
    else if (tab === 'users') loadAdminUsers();
    else if (tab === 'packages') loadAdminPackages();
}

document.addEventListener('DOMContentLoaded', async () => {
    token = getStoredToken();

    if (token) {
        try {
            const meResponse = await api('/me');
            currentUser = await meResponse.json();
            updateUI();
        } catch (e) {
            logout();
            showLogin();
        }
    } else if (tg?.initData) {
        await auth();
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
