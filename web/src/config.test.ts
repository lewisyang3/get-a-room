import { describe, expect, it } from 'vitest'
import { DEFAULT_API_BASE_URL, resolveApiBaseUrl } from './config'

describe('resolveApiBaseUrl', () => {
  it('uses the configured URL', () => {
    expect(resolveApiBaseUrl('https://api.example.com')).toBe(
      'https://api.example.com',
    )
  })

  it('removes trailing slashes', () => {
    expect(resolveApiBaseUrl('https://api.example.com//')).toBe(
      'https://api.example.com',
    )
  })

  it.each([undefined, '', '   '])(
    'falls back to the local API when the value is %j',
    (value) => {
      expect(resolveApiBaseUrl(value)).toBe(DEFAULT_API_BASE_URL)
    },
  )
})
