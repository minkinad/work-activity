import { ApiClient, ApiError } from "./api-client.js";
import {
    clearDashboardToken,
    loadSessionConfig,
    normalizeApiBaseUrl,
    saveSessionConfig,
    validateDashboardToken,
} from "./config.js";
import { badge } from "./dom.js";
import { formatDate } from "./format.js";
import { renderActivity, renderClients, renderCommands, renderMetrics, renderScreenshots } from "./renderers.js";
import { filterClients, REFRESH_INTERVAL_MS, scopedPath, summarizeClients } from "./state.js";

const elements = {
    settingsForm: document.querySelector("#settingsForm"),
    apiBaseUrl: document.querySelector("#apiBaseUrl"),
    dashboardToken: document.querySelector("#dashboardToken"),
    forgetToken: document.querySelector("#forgetToken"),
    refresh: document.querySelector("#refreshButton"),
    autoRefresh: document.querySelector("#autoRefresh"),
    statusLine: document.querySelector("#statusLine"),
    connectionState: document.querySelector("#connectionState"),
    lastUpdated: document.querySelector("#lastUpdated"),
    metrics: document.querySelector("#metrics"),
    clientSearch: document.querySelector("#clientSearch"),
    clientStatus: document.querySelector("#clientStatus"),
    clientsCount: document.querySelector("#clientsCount"),
    clients: document.querySelector("#clientsTableBody"),
    selectedClient: document.querySelector("#selectedClient"),
    clearSelection: document.querySelector("#clearSelection"),
    activity: document.querySelector("#activityList"),
    commands: document.querySelector("#commandsList"),
    screenshots: document.querySelector("#screenshotsList"),
    previewImage: document.querySelector("#previewImage"),
    previewLabel: document.querySelector("#previewLabel"),
    previewPlaceholder: document.querySelector("#previewPlaceholder"),
    previewMeta: document.querySelector("#previewMeta"),
    clearPreview: document.querySelector("#clearPreview"),
    captureDialog: document.querySelector("#captureDialog"),
    captureTarget: document.querySelector("#captureTarget"),
};

const state = {
    api: null,
    clients: [],
    commands: [],
    selectedClientId: null,
    pendingCaptureClient: null,
    previewObjectUrl: null,
    refreshing: false,
};

function setConnection(value) {
    elements.connectionState.replaceChildren(badge("connection", value));
}

function setStatus(message, { error = false } = {}) {
    elements.statusLine.textContent = message;
    elements.statusLine.dataset.state = error ? "error" : "normal";
}

function setRefreshing(refreshing) {
    state.refreshing = refreshing;
    elements.refresh.disabled = refreshing;
    elements.refresh.textContent = refreshing ? "Обновление…" : "Обновить";
    if (refreshing) {
        setConnection("loading");
    }
}

function applyConfig() {
    const config = {
        apiBaseUrl: normalizeApiBaseUrl(elements.apiBaseUrl.value),
        dashboardToken: validateDashboardToken(elements.dashboardToken.value),
    };
    saveSessionConfig(config);
    elements.apiBaseUrl.value = config.apiBaseUrl;
    state.api = new ApiClient({ baseUrl: config.apiBaseUrl, token: config.dashboardToken });
    return config;
}

function renderClientTable() {
    const visibleClients = filterClients(
        state.clients,
        elements.clientSearch.value,
        elements.clientStatus.value,
    );
    elements.clientsCount.textContent = `${visibleClients.length} из ${state.clients.length}`;
    renderClients(elements.clients, visibleClients, state.selectedClientId, {
        onSelect: selectClient,
        onCapture: requestCaptureConfirmation,
    });
}

function renderSelection() {
    elements.selectedClient.textContent = state.selectedClientId || "Все клиенты";
    elements.clearSelection.hidden = !state.selectedClientId;
}

async function refreshData({ quiet = false } = {}) {
    if (!state.api || state.refreshing || document.hidden) {
        return;
    }
    setRefreshing(true);
    if (!quiet) {
        setStatus("Загружаю актуальные данные…");
    }
    try {
        const [clientsPayload, activityPayload, commandsPayload, screenshotsPayload] = await Promise.all([
            state.api.json("/api/v1/dashboard/clients"),
            state.api.json(scopedPath("activity", state.selectedClientId, 20)),
            state.api.json(scopedPath("commands", state.selectedClientId, 20)),
            state.api.json(scopedPath("screenshots", state.selectedClientId, 12)),
        ]);
        state.clients = clientsPayload.clients || [];
        state.commands = commandsPayload.items || [];
        renderClientTable();
        renderSelection();
        renderMetrics(elements.metrics, summarizeClients(state.clients, state.commands));
        renderActivity(elements.activity, activityPayload.items || []);
        renderCommands(elements.commands, state.commands);
        renderScreenshots(elements.screenshots, screenshotsPayload.items || [], openScreenshot);
        const now = new Date().toISOString();
        elements.lastUpdated.textContent = `Обновлено ${formatDate(now)}`;
        setStatus(state.selectedClientId ? `Показаны данные клиента ${state.selectedClientId}.` : "Данные синхронизированы.");
        setConnection("connected");
    } catch (error) {
        const message = error instanceof ApiError ? error.message : "Не удалось получить данные API.";
        setStatus(message, { error: true });
        setConnection("disconnected");
    } finally {
        setRefreshing(false);
    }
}

function selectClient(clientId) {
    state.selectedClientId = clientId;
    renderSelection();
    renderClientTable();
    refreshData();
}

function clearSelection() {
    state.selectedClientId = null;
    renderSelection();
    renderClientTable();
    refreshData();
}

function requestCaptureConfirmation(client) {
    state.pendingCaptureClient = client;
    elements.captureTarget.textContent = `${client.user || "Без имени"} · ${client.machine || client.client_id}`;
    elements.captureDialog.returnValue = "cancel";
    elements.captureDialog.showModal();
}

async function queueScreenshot(client) {
    if (!client || !state.api) {
        return;
    }
    setStatus(`Создаю команду для ${client.client_id}…`);
    try {
        await state.api.json(
            `/api/v1/dashboard/clients/${encodeURIComponent(client.client_id)}/commands/screenshot`,
            { method: "POST" },
        );
        state.selectedClientId = client.client_id;
        await refreshData();
        setStatus("Команда создана. Клиент выполнит её при следующем опросе.");
    } catch (error) {
        setStatus(error.message || "Не удалось создать команду.", { error: true });
    }
}

function clearPreview() {
    if (state.previewObjectUrl) {
        URL.revokeObjectURL(state.previewObjectUrl);
        state.previewObjectUrl = null;
    }
    elements.previewImage.removeAttribute("src");
    elements.previewImage.hidden = true;
    elements.previewPlaceholder.hidden = false;
    elements.previewLabel.textContent = "Не открыт";
    elements.previewMeta.textContent = "Файл загружается только по явному действию оператора.";
    elements.clearPreview.hidden = true;
}

async function openScreenshot(item) {
    try {
        setStatus("Загружаю защищённый скриншот…");
        const blob = await state.api.blob(item.url);
        if (blob.type !== "image/png") {
            throw new Error("API вернул файл неподдерживаемого типа.");
        }
        clearPreview();
        state.previewObjectUrl = URL.createObjectURL(blob);
        elements.previewImage.src = state.previewObjectUrl;
        elements.previewImage.hidden = false;
        elements.previewPlaceholder.hidden = true;
        elements.previewLabel.textContent = item.client_id;
        elements.previewMeta.textContent = `Снят ${formatDate(item.captured_at)} · загружен ${formatDate(item.uploaded_at)}`;
        elements.clearPreview.hidden = false;
        setStatus("Скриншот открыт локально в текущей вкладке.");
    } catch (error) {
        setStatus(error.message || "Не удалось открыть скриншот.", { error: true });
    }
}

elements.settingsForm.addEventListener("submit", (event) => {
    event.preventDefault();
    try {
        applyConfig();
        refreshData();
    } catch (error) {
        setStatus(error.message, { error: true });
        setConnection("disconnected");
    }
});

elements.forgetToken.addEventListener("click", () => {
    clearDashboardToken();
    elements.dashboardToken.value = "";
    state.api = null;
    setConnection("disconnected");
    setStatus("Dashboard token удалён из сессии браузера.");
});
elements.refresh.addEventListener("click", () => refreshData());
elements.clientSearch.addEventListener("input", renderClientTable);
elements.clientStatus.addEventListener("change", renderClientTable);
elements.clearSelection.addEventListener("click", clearSelection);
elements.clearPreview.addEventListener("click", clearPreview);
elements.captureDialog.addEventListener("close", () => {
    if (elements.captureDialog.returnValue === "capture") {
        queueScreenshot(state.pendingCaptureClient);
    }
    state.pendingCaptureClient = null;
});
document.addEventListener("visibilitychange", () => {
    if (!document.hidden && elements.autoRefresh.checked) {
        refreshData({ quiet: true });
    }
});
window.addEventListener("beforeunload", clearPreview);
window.setInterval(() => {
    if (elements.autoRefresh.checked) {
        refreshData({ quiet: true });
    }
}, REFRESH_INTERVAL_MS);

const initialConfig = loadSessionConfig();
elements.apiBaseUrl.value = initialConfig.apiBaseUrl;
elements.dashboardToken.value = initialConfig.dashboardToken;
clearPreview();
renderSelection();
renderMetrics(elements.metrics, summarizeClients([], []));
if (initialConfig.dashboardToken) {
    try {
        applyConfig();
        refreshData();
    } catch (error) {
        setStatus(error.message, { error: true });
    }
} else {
    setConnection("disconnected");
    setStatus("Введите API URL и dashboard token, чтобы начать работу.");
}
