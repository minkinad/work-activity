export function formatDate(value, locale = "ru-RU") {
    if (!value) {
        return "—";
    }
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? String(value) : parsed.toLocaleString(locale);
}

export function formatDuration(totalSeconds) {
    const seconds = Math.max(0, Number(totalSeconds) || 0);
    if (seconds < 60) {
        return `${seconds} сек`;
    }
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) {
        return `${minutes} мин`;
    }
    return `${Math.floor(minutes / 60)} ч ${minutes % 60} мин`;
}

export function formatBytes(value) {
    const bytes = Math.max(0, Number(value) || 0);
    if (bytes < 1024) {
        return `${bytes} Б`;
    }
    if (bytes < 1024 * 1024) {
        return `${(bytes / 1024).toFixed(1)} КБ`;
    }
    return `${(bytes / 1024 / 1024).toFixed(1)} МБ`;
}
