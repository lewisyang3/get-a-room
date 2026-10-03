import { describe, expect, it } from 'vitest'
import {
  DEFAULT_API_BASE_URL,
  resolveApiBaseUrl,
  resolveTermId,
} from './config'

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

describe('resolveTermId', () => {
  it('parses a positive whole number', () => {
    expect(resolveTermId('12')).toBe(12)
  })

  it('ignores surrounding whitespace', () => {
    expect(resolveTermId(' 3 ')).toBe(3)
  })

  it.each([
    undefined,
    '',
    '   ',
    '0',
    '-1',
    '1.5',
    '1e3',
    'abc',
    '99999999999999999',
  ])('returns null for %j', (value) => {
    expect(resolveTermId(value)).toBeNull()
  })
})
