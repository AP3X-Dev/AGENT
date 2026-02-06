/**
 * Validation utilities for the application
 */

export function isValidEmail(email: string): boolean {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
    return emailRegex.test(email)
}

export function isValidUrl(url: string): boolean {
    try {
        new URL(url)
        return true
    } catch {
        return false
    }
}

export function isValidPrompt(prompt: string): boolean {
    return prompt.trim().length > 0 && prompt.trim().length <= 1000
}

export function sanitizeInput(input: string): string {
    return input.trim().replace(/[<>]/g, '')
}

export function isValidFileSize(size: number, maxSize: number = 10 * 1024 * 1024): boolean {
    return size > 0 && size <= maxSize
}

export function isValidImageType(type: string): boolean {
    const validTypes = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
    return validTypes.includes(type)
}

export function validateRequired(value: string, fieldName: string): string | null {
    if (!value || value.trim().length === 0) {
        return `${fieldName} is required`
    }
    return null
}

export function validateLength(
    value: string,
    min: number,
    max: number,
    fieldName: string
): string | null {
    if (value.length < min) {
        return `${fieldName} must be at least ${min} characters`
    }
    if (value.length > max) {
        return `${fieldName} must be no more than ${max} characters`
    }
    return null
}
