const apiBaseUrlInput = document.getElementById("apiBaseUrl");
const saveSettingsButton = document.getElementById("saveSettingsButton");
const refreshButton = document.getElementById("refreshButton");
const statusLine = document.getElementById("statusLine");
const clientsCount = document.getElementById("clientsCount");
const clientsTableBody = document.getElementById("clientsTableBody");
const activityList = document.getElementById("activityList");
const commandsList = document.getElementById("commandsList");
const screenshotsList = document.getElementById("screenshotsList");
const previewImage = document.getElementById("previewImage");
const previewLabel = document.getElementById("previewLabel");
const previewPlaceholder = document.getElementById("previewPlaceholder");
const previewMeta = document.getElementById("previewMeta");

const API_BASE_STORAGE_KEY = "work-activity-monitor-api-base-url";
let selectedClientId = null;

function getApiBaseUrl() {
    return apiBaseUrlInput.value.replace(/\/+$/, "");
}

function setStatus(text, isError = false) {
    statusLine.textContent = text;
    statusLine.style.color = isError ? "#b04242" : "#657089";
}

function formatDate(value) {
    if (!value) {
        return "n/a";
    }

    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) {
        return value;
    }

    return parsed.toLocaleString("ru-RU");
}

function statusBadge(status) {
    const normalized = status === "online" ? "online" : "offline";
    return `<span class="status-badge status-badge--${normalized}">${normalized}</span>`;
}

function queueBadge(status) {
    return `<span class="queue-badge queue-badge--${status}">${status}</span>`;
}

async function apiFetch(path, options = {}) {
    const response = await fetch(`${getApiBaseUrl()}${path}`, options);
    if (!response.ok) {
        const text = await response.text();
        throw new Error(text.replace(/<[^>]+>/g, " ").trim() || `Request failed: ${response.status}`);
    }
    return response.json();
}

function renderClients(clients) {
    clientsCount.textContent = `${clients.length} записей`;

    if (!clients.length) {
        clientsTableBody.innerHTML = "<tr><td colspan='10'>Нет зарегистрированных клиентов.</td></tr>";
        return;
    }

    clientsTableBody.innerHTML = clients.map((client) => `
        <tr>
            <td>${statusBadge(client.status)}</td>
            <td>${client.user || "-"}</td>
            <td>${client.domain || "-"}</td>
            <td>${client.machine || "-"}</td>
            <td class="mono">${client.ip_address || "-"}</td>
            <td>${client.activity_state || "-"}</td>
            <td>${client.idle_seconds}s</td>
            <td>${formatDate(client.last_active_at)}</td>
            <td>${formatDate(client.last_seen_at)}</td>
            <td>
                <button class="button" onclick="queueScreenshot('${client.client_id}')">Запросить скриншот</button>
            </td>
        </tr>
    `).join("");
}

function renderActivity(items) {
    if (!items.length) {
        activityList.innerHTML = "<li>История активности пока пуста.</li>";
        return;
    }

    activityList.innerHTML = items.map((item) => `
        <li>
            <strong>${item.client_id}</strong>
            Состояние: ${item.activity_state}, idle: ${item.idle_seconds}s
            <br>
            Last active: ${formatDate(item.last_active_at)}
            <br>
            Получено: ${formatDate(item.received_at)}
        </li>
    `).join("");
}

function renderCommands(items) {
    if (!items.length) {
        commandsList.innerHTML = "<li>Команды пока не создавались.</li>";
        return;
    }

    commandsList.innerHTML = items.map((item) => `
        <li>
            <strong>${item.command_type} #${item.id}</strong>
            ${queueBadge(item.status)}
            <br>
            Клиент: ${item.client_id}
            <br>
            Создана: ${formatDate(item.created_at)}
            <br>
            Завершена: ${formatDate(item.completed_at)}
            ${item.error_text ? `<br>Ошибка: ${item.error_text}` : ""}
        </li>
    `).join("");
}

function renderScreenshots(items) {
    if (!items.length) {
        screenshotsList.innerHTML = "<li>Скриншоты пока не загружались.</li>";
        previewImage.style.display = "none";
        previewPlaceholder.style.display = "grid";
        previewLabel.textContent = selectedClientId || "клиент не выбран";
        previewMeta.textContent = "Последний скриншот ещё не появился.";
        return;
    }

    screenshotsList.innerHTML = items.map((item) => `
        <li>
            <strong>${item.client_id}</strong>
            Файл: <a href="${getApiBaseUrl()}${item.url}" target="_blank" rel="noreferrer">${item.file_name}</a>
            <br>
            Загружен: ${formatDate(item.uploaded_at)}
            <br>
            Размер: ${item.byte_size} bytes
        </li>
    `).join("");

    // The latest screenshot is also mirrored into the preview panel for quicker access.
    const latest = items[0];
    previewImage.src = `${getApiBaseUrl()}${latest.url}?ts=${Date.now()}`;
    previewImage.style.display = "block";
    previewPlaceholder.style.display = "none";
    previewLabel.textContent = latest.client_id;
    previewMeta.textContent = `Captured: ${formatDate(latest.captured_at)}. Uploaded: ${formatDate(latest.uploaded_at)}.`;
}

async function queueScreenshot(clientId) {
    selectedClientId = clientId;
    setStatus(`Ставлю команду в очередь для ${clientId}...`);

    try {
        await apiFetch(`/api/v1/dashboard/clients/${clientId}/commands/screenshot`, {
            method: "POST",
        });
        await refreshData();
        setStatus(`Команда на скриншот для ${clientId} поставлена в очередь.`);
    } catch (error) {
        setStatus(error.message, true);
    }
}

async function refreshData() {
    setStatus("Загружаю данные из API...");

    try {
        // Frontend intentionally fetches data in parallel, because all panels are
        // independent and we want the dashboard to feel responsive.
        const [clients, activity, commands, screenshots] = await Promise.all([
            apiFetch("/api/v1/dashboard/clients"),
            apiFetch(selectedClientId ? `/api/v1/dashboard/activity?client_id=${encodeURIComponent(selectedClientId)}&limit=20` : "/api/v1/dashboard/activity?limit=20"),
            apiFetch(selectedClientId ? `/api/v1/dashboard/commands?client_id=${encodeURIComponent(selectedClientId)}&limit=20` : "/api/v1/dashboard/commands?limit=20"),
            apiFetch(selectedClientId ? `/api/v1/dashboard/screenshots?client_id=${encodeURIComponent(selectedClientId)}&limit=12` : "/api/v1/dashboard/screenshots?limit=12"),
        ]);

        renderClients(clients.clients || []);
        renderActivity(activity.items || []);
        renderCommands(commands.items || []);
        renderScreenshots(screenshots.items || []);
        setStatus(`Данные обновлены: ${formatDate(new Date().toISOString())}`);
    } catch (error) {
        setStatus(error.message, true);
    }
}

saveSettingsButton.addEventListener("click", () => {
    localStorage.setItem(API_BASE_STORAGE_KEY, getApiBaseUrl());
    refreshData();
});

refreshButton.addEventListener("click", refreshData);

// Expose the queue action for buttons rendered through template strings.
window.queueScreenshot = queueScreenshot;

const savedUrl = localStorage.getItem(API_BASE_STORAGE_KEY);
if (savedUrl) {
    apiBaseUrlInput.value = savedUrl;
}

refreshData();
setInterval(refreshData, 8000);
