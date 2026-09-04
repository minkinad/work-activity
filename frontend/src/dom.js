export function element(tagName, options = {}) {
    const node = document.createElement(tagName);
    if (options.className) {
        node.className = options.className;
    }
    if (options.text !== undefined) {
        node.textContent = String(options.text);
    }
    return node;
}

export function replaceMessage(container, text, { table = false, columns = 1 } = {}) {
    container.replaceChildren();
    if (table) {
        const row = element("tr");
        const cell = element("td", { text });
        cell.colSpan = columns;
        row.append(cell);
        container.append(row);
        return;
    }
    container.append(element("li", { text, className: "empty-message" }));
}

export function badge(kind, value) {
    const allowed = {
        connection: ["connected", "disconnected", "loading"],
        status: ["online", "offline"],
        queue: ["queued", "dispatched", "completed", "failed"],
    };
    const normalized = allowed[kind]?.includes(value) ? value : "unknown";
    const labels = {
        connected: "Подключено",
        disconnected: "Нет связи",
        loading: "Обновление",
        online: "Онлайн",
        offline: "Офлайн",
        queued: "В очереди",
        dispatched: "Выполняется",
        completed: "Готово",
        failed: "Ошибка",
        unknown: "Неизвестно",
    };
    return element("span", {
        className: `badge badge--${normalized}`,
        text: labels[normalized],
    });
}

export function appendField(container, label, value) {
    const title = element("span", { className: "feed__label", text: label });
    container.append(title, document.createTextNode(String(value)));
}
