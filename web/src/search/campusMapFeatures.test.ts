import { describe, expect, it } from 'vitest'
import { clusterFeature, pointFeature } from '../test/mapbox'
import {
  buildingFeatures,
  clusterContent,
  markersOnScreen,
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

function ids(collection: ReturnType<typeof buildingFeatures>) {
  return collection.features.map((f) => f.properties.building_id)
}

describe('buildingFeatures', () => {
  it('groups only buildings with a room free, with their counts', () => {
    const collection = buildingFeatures(
      [DWINELLE, EVANS],
      new Map([[1, 6]]),
      null,
    )

    expect(collection.features).toEqual([
      {
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [-122.2607, 37.8707] },
        properties: { building_id: 1, free: 6 },
      },
    ])
  })

  it("groups every building when counts aren't known", () => {
    expect(ids(buildingFeatures([DWINELLE, EVANS], 'unknown', null))).toEqual([
      1, 2,
    ])
  })

  it('leaves out the selected building', () => {
    const counts = new Map([
      [1, 6],
      [2, 3],
    ])

    expect(ids(buildingFeatures([DWINELLE, EVANS], counts, 2))).toEqual([1])
  })
})

describe('markersOnScreen', () => {
  it('sorts buildings from groups, once each', () => {
    const group = clusterFeature({
      id: 7,
      lngLat: [-122.26, 37.87],
      buildings: 3,
      free: 9,
    })
    const onScreen = markersOnScreen([
      pointFeature(DWINELLE, 6),
      group,
      // Repeated, as in a neighbouring tile.
      pointFeature(DWINELLE, 6),
      group,
    ])

    expect([...onScreen.buildingIds]).toEqual([1])
    expect([...onScreen.clusters]).toEqual([
      [7, { lngLat: [-122.26, 37.87], buildings: 3, free: 9 }],
    ])
  })
})

describe('clusterContent', () => {
  const cluster = { lngLat: [0, 0] as [number, number], buildings: 5 }

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
