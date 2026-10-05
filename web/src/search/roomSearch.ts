/** What a search for a room or building asks the API for. */
export type RoomSearch = {
  /** Part of a building name. */
  building: string | null
  /** An exact room number. */
  room: string | null
}

/** Trims the text and collapses runs of whitespace to one space. */
export function normalizeSearchText(text: string): string {
  return text.trim().replace(/\s+/g, ' ')
}

// "room 242" and "rm 242" mean the same as "242".
const ROOM_WORDS = new Set(['room', 'rm'])

/** Splits a search like "Dwinelle 242" into a building and a room. A last
 * word with a digit in it is the room number, and anything before it is part
 * of the building name. Without one, the whole text is the building, so
 * "242", "dwin" and "Dwinelle 242" all work. A building name that ends in a
 * number is read as a room, which is a known limit. */
export function parseRoomSearch(text: string): RoomSearch {
  const words = normalizeSearchText(text)
    .split(' ')
    .filter((word) => word !== '' && !ROOM_WORDS.has(word.toLowerCase()))
  const last = words.at(-1)
  if (last === undefined) return { building: null, room: null }
  if (!/\d/.test(last)) return { building: words.join(' '), room: null }
  const building = words.slice(0, -1).join(' ')
  return { building: building || null, room: last }
}
