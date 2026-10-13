import { describe, expect, it } from 'vitest'
import { normalizeSearchText, parseRoomSearch } from './roomSearch'

describe('normalizeSearchText', () => {
  it('trims and collapses whitespace', () => {
    expect(normalizeSearchText('  Dwinelle \t  242 ')).toBe('Dwinelle 242')
    expect(normalizeSearchText('   ')).toBe('')
  })
})

describe('parseRoomSearch', () => {
  it.each([
    ['Dwinelle 242', { building: 'Dwinelle', room: '242' }],
    ['242', { building: null, room: '242' }],
    ['dwin', { building: 'dwin', room: null }],
    ['Evans Hall', { building: 'Evans Hall', room: null }],
    ['1229A', { building: null, room: '1229A' }],
    [
      'Valley Life Sciences 2040',
      { building: 'Valley Life Sciences', room: '2040' },
    ],
    ['  dwinelle   b4 ', { building: 'dwinelle', room: 'b4' }],
    ['room 242', { building: null, room: '242' }],
    ['Dwinelle Rm 242', { building: 'Dwinelle', room: '242' }],
    ['', { building: null, room: null }],
    ['  ', { building: null, room: null }],
    ['room', { building: null, room: null }],
  ])('reads %j', (text, expected) => {
    expect(parseRoomSearch(text)).toEqual(expected)
  })
})
