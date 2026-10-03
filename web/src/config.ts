export const DEFAULT_API_BASE_URL = 'http://localhost:8000'

/** Returns the API base URL without a trailing slash, so paths can be
 * appended as `${apiBaseUrl}/availability`. Falls back to the local API when
 * the value is unset or blank. */
export function resolveApiBaseUrl(value: string | undefined): string {
  const trimmed = value?.trim()
  return (trimmed || DEFAULT_API_BASE_URL).replace(/\/+$/, '')
}

export const apiBaseUrl = resolveApiBaseUrl(import.meta.env.VITE_API_BASE_URL)
