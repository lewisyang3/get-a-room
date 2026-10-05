export type ApiErrorKind = 'network' | 'not-found' | 'invalid' | 'server'

export class ApiError extends Error {
  readonly kind: ApiErrorKind
  readonly status: number | null

  constructor(kind: ApiErrorKind, message: string, status: number | null) {
    super(message)
    this.name = 'ApiError'
    this.kind = kind
    this.status = status
  }
}

function errorKind(status: number): ApiErrorKind {
  if (status === 404) return 'not-found'
  if (status === 422) return 'invalid'
  return 'server'
}

type FetchJsonOptions<T> = {
  signal?: AbortSignal
  /** Checks the body is the expected shape. */
  isValid: (body: unknown) => body is T
}

/** Fetches and parses a JSON response. Throws an ApiError for a failed
 * request, and rethrows the AbortError when `signal` aborts it. */
export async function fetchJson<T>(
  url: string,
  { signal, isValid }: FetchJsonOptions<T>,
): Promise<T> {
  let response: Response
  try {
    response = await fetch(url, { signal })
  } catch (error) {
    if (signal?.aborted) throw error
    throw new ApiError('network', 'The API could not be reached.', null)
  }

  if (!response.ok) {
    throw new ApiError(
      errorKind(response.status),
      `The API responded with ${response.status}.`,
      response.status,
    )
  }

  let body: unknown
  try {
    body = await response.json()
  } catch (error) {
    if (signal?.aborted) throw error
    throw new ApiError(
      'server',
      'The API returned invalid JSON.',
      response.status,
    )
  }
  if (!isValid(body)) {
    throw new ApiError(
      'server',
      'The API returned an unexpected response.',
      response.status,
    )
  }
  return body
}
