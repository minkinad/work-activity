export class ApiError extends Error {
    constructor(message, status = 0) {
        super(message);
        this.name = "ApiError";
        this.status = status;
    }
}

export class ApiClient {
    constructor({ baseUrl, token, timeoutMs = 10_000, fetchImpl = window.fetch.bind(window) }) {
        this.baseUrl = baseUrl;
        this.token = token;
        this.timeoutMs = timeoutMs;
        this.fetchImpl = fetchImpl;
    }

    async request(path, options = {}) {
        const controller = new AbortController();
        const timeout = window.setTimeout(() => controller.abort(), this.timeoutMs);
        const headers = new Headers(options.headers || {});
        headers.set("Authorization", `Bearer ${this.token}`);
        try {
            const response = await this.fetchImpl(`${this.baseUrl}${path}`, {
                ...options,
                headers,
                signal: controller.signal,
                cache: "no-store",
                credentials: "omit",
                referrerPolicy: "no-referrer",
            });
            if (!response.ok) {
                throw await this.toApiError(response);
            }
            return response;
        } catch (error) {
            if (error?.name === "AbortError") {
                throw new ApiError("API не ответил вовремя.");
            }
            throw error;
        } finally {
            window.clearTimeout(timeout);
        }
    }

    async json(path, options) {
        return (await this.request(path, options)).json();
    }

    async blob(path) {
        return (await this.request(path)).blob();
    }

    async toApiError(response) {
        let message = `API вернул ошибку ${response.status}.`;
        try {
            const payload = await response.json();
            message = payload?.error?.message || message;
        } catch {
            // The status-based message is safe for non-JSON responses.
        }
        return new ApiError(message, response.status);
    }
}
