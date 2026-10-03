export const DEFAULT_API_BASE_URL = 'http://localhost:8000'

/** Returns the API base URL without a trailing slash, so paths can be
 * appended as `${apiBaseUrl}/availability`. Falls back to the local API when
 * the value is unset or blank. */
export function resolveApiBaseUrl(value: string | undefined): string {
  const trimmed = value?.trim()
  return (trimmed || DEFAULT_API_BASE_URL).replace(/\/+$/, '')
}

/** Returns the term to search as a positive integer, or null when the value
 * is unset, blank or not a positive whole number. */
export function resolveTermId(value: string | undefined): number | null {
  const trimmed = value?.trim() ?? ''
  if (!/^\d+$/.test(trimmed)) return null
  const id = Number(trimmed)
  return Number.isSafeInteger(id) && id > 0 ? id : null
}

export const apiBaseUrl = resolveApiBaseUrl(import.meta.env.VITE_API_BASE_URL)

export const termId = resolveTermId(import.meta.env.VITE_TERM_ID)
