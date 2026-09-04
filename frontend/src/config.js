const LOOPBACK_HOSTS = new Set(["localhost", "127.0.0.1", "[::1]"]);

export const storageKeys = Object.freeze({
    apiBase: "work-activity-monitor-api-base-url",
    dashboardToken: "work-activity-monitor-dashboard-token",
});

export function normalizeApiBaseUrl(value) {
    let url;
    try {
        url = new URL(String(value).trim());
    } catch {
        throw new Error("Укажите корректный API URL.");
    }
    if (url.username || url.password || url.search || url.hash) {
        throw new Error("API URL не должен содержать credentials, query или hash.");
    }
    if (url.protocol !== "https:" && !(url.protocol === "http:" && LOOPBACK_HOSTS.has(url.hostname))) {
        throw new Error("Для удалённого API обязательно используйте HTTPS.");
    }
    return `${url.origin}${url.pathname.replace(/\/+$/, "")}`;
}

export function validateDashboardToken(value) {
    const token = String(value).trim();
    if (token.length < 32) {
        throw new Error("Dashboard token должен содержать минимум 32 символа.");
    }
    return token;
}

export function loadSessionConfig(storage = window.sessionStorage, local = window.localStorage) {
    return {
        apiBaseUrl: local.getItem(storageKeys.apiBase) || "https://127.0.0.1:5000",
        dashboardToken: storage.getItem(storageKeys.dashboardToken) || "",
    };
}

export function saveSessionConfig(config, storage = window.sessionStorage, local = window.localStorage) {
    local.setItem(storageKeys.apiBase, config.apiBaseUrl);
    storage.setItem(storageKeys.dashboardToken, config.dashboardToken);
}

export function clearDashboardToken(storage = window.sessionStorage) {
    storage.removeItem(storageKeys.dashboardToken);
}
