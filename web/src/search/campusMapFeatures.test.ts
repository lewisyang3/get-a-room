import { describe, expect, it } from 'vitest'
import {
  buildingPoints,
  clusterContent,
  clusterIndex,
  groupsAt,
  type LocatedBuilding,
} from './campusMapFeatures'

const DWINELLE: LocatedBuilding = {
  building_id: 1,
  building_code: 'DWINELLE',
  building_name: 'Dwinelle',
  latitude: 37.8707,
  longitude: -122.2607,
}
const EVANS: LocatedBuilding = {
  building_id: 2,
  building_code: 'EVANS',
  building_name: 'Evans',
  latitude: 37.8736,
  longitude: -122.2577,
}
const BOTH = new Map([
  [1, 6],
  [2, 3],
])

function ids(points: ReturnType<typeof buildingPoints>) {
  return points.map((p) => p.properties.building_id)
}

describe('buildingPoints', () => {
  it('groups only buildings with a room free, with their counts', () => {
    expect(
      buildingPoints([DWINELLE, EVANS], new Map([[1, 6]]), new Set()),
    ).toEqual([
      {
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [-122.2607, 37.8707] },
        properties: { building_id: 1, free: 6 },
      },
    ])
  })

  it("groups every building when counts aren't known", () => {
    expect(
      ids(buildingPoints([DWINELLE, EVANS], 'unknown', new Set())),
    ).toEqual([1, 2])
  })

  it('leaves out the buildings asked to', () => {
    expect(ids(buildingPoints([DWINELLE, EVANS], BOTH, new Set([2])))).toEqual([
      1,
    ])
  })
})

describe('groupsAt', () => {
  const index = clusterIndex(buildingPoints([DWINELLE, EVANS], BOTH, new Set()))

  it('groups nearby buildings when zoomed out, summing their rooms', () => {
    const { buildingIds, clusters } = groupsAt(index, 12.5)

    expect(buildingIds.size).toBe(0)
    expect([...clusters.values()]).toEqual([
      {
        lngLat: [expect.any(Number), expect.any(Number)],
        buildings: 2,
        free: 9,
        expansionZoom: expect.any(Number),
      },
    ])
    expect([...clusters.values()][0].expansionZoom).toBeGreaterThan(12)
  })

  it('keys a group by its lowest building id, whatever else is grouped', () => {
    const far: LocatedBuilding = {
      building_id: 0,
      building_code: 'LHS',
      building_name: 'Lawrence Hall of Science',
      latitude: 37.8793,
      longitude: -122.2465,
    }
    const counts = new Map([...BOTH, [0, 1]])

    for (const leftOut of [new Set<number>(), new Set([0])]) {
      const regrouped = clusterIndex(
        buildingPoints([far, DWINELLE, EVANS], counts, leftOut),
      )
      const { clusters } = groupsAt(regrouped, 12)
      expect([...clusters.keys()]).toEqual([1])
    }
  })

  it('shows each building on its own when zoomed in', () => {
    const { buildingIds, clusters } = groupsAt(index, 16)

    expect([...buildingIds]).toEqual([1, 2])
    expect(clusters.size).toBe(0)
  })
})

describe('clusterContent', () => {
  const cluster = { buildings: 5 }

  it('shows the total free rooms', () => {
    expect(clusterContent({ ...cluster, free: 34 }, new Map())).toEqual({
      text: '34',
      label: '5 buildings, 34 rooms free. Zoom in',
      kind: 'free',
    })
  })

  it('says one room, not one rooms', () => {
    expect(clusterContent({ ...cluster, free: 1 }, new Map()).label).toBe(
      '5 buildings, 1 room free. Zoom in',
    )
  })

  it("shows no number when counts aren't known", () => {
    expect(clusterContent({ ...cluster, free: 0 }, 'unknown')).toEqual({
      text: '',
      label: '5 buildings. Zoom in',
      kind: 'unknown',
    })
  })
})
