const defaultApiBaseUrl = import.meta.env.DEV ? 'http://127.0.0.1:8000' : '/api'

export const API_BASE_URL = String(import.meta.env.VITE_API_BASE_URL || defaultApiBaseUrl).replace(/\/$/, '')

