export function formatDate(date: Date): string {
    return new Intl.DateTimeFormat('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
    }).format(date)
}

export function formatRelativeTime(date: Date): string {
    const now = new Date()
    const diff = now.getTime() - date.getTime()
    const seconds = Math.floor(diff / 1000)
    const minutes = Math.floor(seconds / 60)
    const hours = Math.floor(minutes / 60)
    const days = Math.floor(hours / 24)

    if (seconds < 60) {
        return 'just now'
    } else if (minutes < 60) {
        return `${minutes}m ago`
    } else if (hours < 24) {
        return `${hours}h ago`
    } else if (days < 7) {
        return `${days}d ago`
    } else {
        return formatDate(date)
    }
}

export function formatFileSize(bytes: number): string {
    const sizes = ['B', 'KB', 'MB', 'GB']
    if (bytes === 0) return '0 B'

    const i = Math.floor(Math.log(bytes) / Math.log(1024))
    const size = bytes / Math.pow(1024, i)

    return `${size.toFixed(1)} ${sizes[i]}`
}

export function truncateText(text: string, maxLength: number): string {
    if (text.length <= maxLength) return text
    return `${text.substring(0, maxLength)}...`
}

export function slugify(text: string): string {
    return text
        .toLowerCase()
        .replace(/[^\w\s-]/g, '')
        .replace(/[\s_-]+/g, '-')
        .replace(/^-+|-+$/g, '')
}

export function generateId(): string {
    return Math.random().toString(36).substring(2) + Date.now().toString(36)
}
