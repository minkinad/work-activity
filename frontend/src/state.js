export const REFRESH_INTERVAL_MS = 15_000;

export function filterClients(clients, query, status) {
    const normalizedQuery = String(query).trim().toLocaleLowerCase("ru-RU");
    return clients.filter((client) => {
        if (status !== "all" && client.status !== status) {
            return false;
        }
        if (!normalizedQuery) {
            return true;
        }
        return [client.user, client.domain, client.machine, client.ip_address, client.client_id]
            .filter(Boolean)
            .some((value) => String(value).toLocaleLowerCase("ru-RU").includes(normalizedQuery));
    });
}

export function summarizeClients(clients, commands) {
    return {
        total: clients.length,
        online: clients.filter((client) => client.status === "online").length,
        active: clients.filter(
            (client) => client.status === "online" && client.activity_state === "active",
        ).length,
        pending: commands.filter((command) => ["queued", "dispatched"].includes(command.status)).length,
    };
}

export function scopedPath(resource, clientId, limit) {
    const params = new URLSearchParams({ limit: String(limit) });
    if (clientId) {
        params.set("client_id", clientId);
    }
    return `/api/v1/dashboard/${resource}?${params}`;
}
