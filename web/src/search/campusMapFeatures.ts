import type { Building } from '../api/buildings'
import type { FreeRoomCounts } from './useBuildingAvailability'

export type LocatedBuilding = Building & { latitude: number; longitude: number }

type LngLat = [number, number]

/** A building as a point in the map's clustered source. GeoJSON's types
 * aren't installed, so this is the little of them the map uses. */
type BuildingFeature = {
  type: 'Feature'
  geometry: { type: 'Point'; coordinates: LngLat }
  properties: { building_id: number; free: number }
}

export type BuildingFeatures = {
  type: 'FeatureCollection'
  features: BuildingFeature[]
}

/** Sums each group's free rooms, so a group can show them. */
export const CLUSTER_PROPERTIES = { free: ['+', ['get', 'free']] }

/** A feature as `querySourceFeatures` returns it: a building, or a group
 * of them with Mapbox's cluster properties. */
export type SourceFeature = {
  geometry: { type: string; coordinates?: unknown }
  properties: Record<string, unknown> | null
}

export type Cluster = { lngLat: LngLat; buildings: number; free: number }

/** What's on screen: buildings shown on their own, and groups by id. */
export type OnScreen = {
  buildingIds: Set<number>
  clusters: Map<number, Cluster>
}

export function isLocated(building: Building): building is LocatedBuilding {
  return building.latitude !== null && building.longitude !== null
}

export function lngLat(building: LocatedBuilding): LngLat {
  return [building.longitude, building.latitude]
}

/** What a marker shows: its count, and a name that says what the count is. */
export function markerContent(building: Building, counts: FreeRoomCounts) {
  const name = building.building_name
  if (counts === 'unknown') return { text: '', label: name, kind: 'unknown' }
  const free = counts.get(building.building_id) ?? 0
  const rooms = free === 1 ? 'room' : 'rooms'
  return {
    text: String(free),
    label: `${name}: ${free} ${rooms} free`,
    kind: free > 0 ? 'free' : 'none',
  } as const
}

/** The buildings that can be grouped: those with a room free, or all of
 * them before counts are known. The selected building is left out, so it's
 * always shown on its own, and buildings with none free so they don't
 * swell a group. */
export function buildingFeatures(
  located: LocatedBuilding[],
  counts: FreeRoomCounts,
  selectedBuildingId: number | null,
): BuildingFeatures {
  const features = located.flatMap((building): BuildingFeature[] => {
    if (building.building_id === selectedBuildingId) return []
    const free =
      counts === 'unknown' ? 0 : (counts.get(building.building_id) ?? 0)
    if (counts !== 'unknown' && free === 0) return []
    return [
      {
        type: 'Feature',
        geometry: { type: 'Point', coordinates: lngLat(building) },
        properties: { building_id: building.building_id, free },
      },
    ]
  })
  return { type: 'FeatureCollection', features }
}

/** Sorts the source's features into buildings and groups. Mapbox returns a
 * feature once per tile it falls in, so repeats are dropped. */
export function markersOnScreen(features: SourceFeature[]): OnScreen {
  const onScreen: OnScreen = { buildingIds: new Set(), clusters: new Map() }
  for (const { geometry, properties } of features) {
    if (!properties) continue
    if (properties.cluster) {
      const id = Number(properties.cluster_id)
      if (onScreen.clusters.has(id)) continue
      onScreen.clusters.set(id, {
        lngLat: geometry.coordinates as LngLat,
        buildings: Number(properties.point_count),
        free: Number(properties.free),
      })
    } else {
      onScreen.buildingIds.add(Number(properties.building_id))
    }
  }
  return onScreen
}

/** What a group's marker shows: its buildings' total, and a name that says
 * what's grouped and what choosing it does. Before counts are known, it
 * shows no number, which would read as rooms. */
export function clusterContent(cluster: Cluster, counts: FreeRoomCounts) {
  const buildings = `${cluster.buildings} buildings`
  if (counts === 'unknown') {
    return { text: '', label: `${buildings}. Zoom in`, kind: 'unknown' }
  }
  const rooms = cluster.free === 1 ? 'room' : 'rooms'
  return {
    text: String(cluster.free),
    label: `${buildings}, ${cluster.free} ${rooms} free. Zoom in`,
    kind: 'free',
  } as const
}
