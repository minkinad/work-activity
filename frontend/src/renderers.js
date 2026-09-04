import { appendField, badge, element, replaceMessage } from "./dom.js";
import { formatBytes, formatDate, formatDuration } from "./format.js";

export function renderMetrics(container, summary) {
    const labels = {
        total: "Всего клиентов",
        online: "Сейчас онлайн",
        active: "Активны",
        pending: "Команд в работе",
    };
    container.replaceChildren(
        ...Object.entries(labels).map(([key, label]) => {
            const card = element("article", { className: "metric" });
            card.append(
                element("span", { className: "metric__label", text: label }),
                element("strong", { className: "metric__value", text: summary[key] }),
            );
            return card;
        }),
    );
}

export function renderClients(container, clients, selectedClientId, callbacks) {
    container.replaceChildren();
    if (!clients.length) {
        replaceMessage(container, "Клиенты не найдены.", { table: true, columns: 10 });
        return;
    }
    clients.forEach((client) => {
        const row = element("tr", {
            className: client.client_id === selectedClientId ? "is-selected" : "",
        });
        const statusCell = element("td");
        statusCell.append(badge("status", client.status));
        row.append(statusCell);
        [
            client.user || "—",
            client.domain || "—",
            client.machine || "—",
            client.ip_address || "—",
            client.activity_state || "—",
            formatDuration(client.idle_seconds),
            formatDate(client.last_active_at),
            formatDate(client.last_seen_at),
        ].forEach((value, index) => {
            const cell = element("td", { text: value, className: index === 3 ? "mono" : "" });
            row.append(cell);
        });
        const actions = element("td", { className: "table-actions" });
        const details = element("button", { className: "button button--ghost button--small", text: "Детали" });
        details.type = "button";
        details.addEventListener("click", () => callbacks.onSelect(client.client_id));
        const capture = element("button", { className: "button button--small", text: "Снимок" });
        capture.type = "button";
        capture.disabled = client.status !== "online";
        capture.addEventListener("click", () => callbacks.onCapture(client));
        actions.append(details, capture);
        row.append(actions);
        container.append(row);
    });
}

export function renderActivity(container, items) {
    container.replaceChildren();
    if (!items.length) {
        replaceMessage(container, "История активности пока пуста.");
        return;
    }
    items.forEach((item) => {
        const card = element("li");
        card.append(element("strong", { text: item.client_id }));
        appendField(card, "Состояние", `${item.activity_state}, idle ${formatDuration(item.idle_seconds)}`);
        appendField(card, "Активен", formatDate(item.last_active_at));
        appendField(card, "Получено", formatDate(item.received_at));
        container.append(card);
    });
}

export function renderCommands(container, items) {
    container.replaceChildren();
    if (!items.length) {
        replaceMessage(container, "Команды пока не создавались.");
        return;
    }
    items.forEach((item) => {
        const card = element("li");
        const heading = element("div", { className: "feed__heading" });
        heading.append(element("strong", { text: `${item.command_type} #${item.id}` }), badge("queue", item.status));
        card.append(heading);
        appendField(card, "Клиент", item.client_id);
        appendField(card, "Создана", formatDate(item.created_at));
        appendField(card, "Завершена", formatDate(item.completed_at));
        if (item.error_text) {
            appendField(card, "Ошибка", item.error_text);
        }
        container.append(card);
    });
}

export function renderScreenshots(container, items, onOpen) {
    container.replaceChildren();
    if (!items.length) {
        replaceMessage(container, "Скриншоты пока не загружались.");
        return;
    }
    items.forEach((item) => {
        const card = element("li");
        card.append(element("strong", { text: item.client_id }));
        appendField(card, "Загружен", formatDate(item.uploaded_at));
        appendField(card, "Размер", formatBytes(item.byte_size));
        const button = element("button", {
            className: "button button--secondary button--small",
            text: "Открыть защищённый файл",
        });
        button.type = "button";
        button.addEventListener("click", () => onOpen(item));
        card.append(button);
        container.append(card);
    });
}
