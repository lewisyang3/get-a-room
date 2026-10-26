import Supercluster, { type PointFeature } from 'supercluster'
import type { Building } from '../api/buildings'
import type { FreeRoomCounts } from './useBuildingAvailability'

export type LocatedBuilding = Building & { latitude: number; longitude: number }

type LngLat = [number, number]

// How close buildings group, in pixels: a little more than a pill's width,
// so pills that would overlap merge instead.
export const CLUSTER_RADIUS = 40

// The last zoom at which buildings group; from 17 every building is shown
// on its own.
export const CLUSTER_MAX_ZOOM = 16

type BuildingProperties = { building_id: number; free: number }
type GroupProperties = { free: number }

/** A building as a point to group. */
type BuildingPoint = PointFeature<BuildingProperties>

export type ClusterIndex = Supercluster<BuildingProperties, GroupProperties>

export type Cluster = {
  lngLat: LngLat
  buildings: number
  free: number
  /** The zoom at which the group splits. */
  expansionZoom: number
}

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
 * them before counts are known. Buildings with none free are left out so
 * they don't swell a group, and so are `leftOut`, e.g. the selected one, so
 * they're always shown on their own. */
export function buildingPoints(
  located: LocatedBuilding[],
  counts: FreeRoomCounts,
  leftOut: ReadonlySet<number>,
): BuildingPoint[] {
  return located.flatMap((building): BuildingPoint[] => {
    if (leftOut.has(building.building_id)) return []
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
}

/** Groups the points at every zoom, summing each group's free rooms. */
export function clusterIndex(points: BuildingPoint[]): ClusterIndex {
  return new Supercluster<BuildingProperties, GroupProperties>({
    radius: CLUSTER_RADIUS,
    maxZoom: CLUSTER_MAX_ZOOM,
    map: ({ free }) => ({ free }),
    reduce: (group, { free }) => {
      group.free += free
    },
  }).load(points)
}

/** The buildings and groups in a box, `[west, south, east, north]`, at a
 * zoom. */
export function groupsOnScreen(
  index: ClusterIndex,
  bbox: [number, number, number, number],
  zoom: number,
): OnScreen {
  const onScreen: OnScreen = { buildingIds: new Set(), clusters: new Map() }
  for (const feature of index.getClusters(bbox, Math.floor(zoom))) {
    const { properties } = feature
    if ('cluster_id' in properties) {
      const id = properties.cluster_id
      onScreen.clusters.set(id, {
        lngLat: feature.geometry.coordinates as LngLat,
        buildings: properties.point_count,
        free: properties.free,
        expansionZoom: index.getClusterExpansionZoom(id),
      })
    } else {
      onScreen.buildingIds.add(properties.building_id)
    }
  }
  return onScreen
}

/** What a group's marker shows: its buildings' total, and a name that says
 * what's grouped and what choosing it does. Before counts are known, it
 * shows no number, which would read as rooms. */
export function clusterContent(
  cluster: Pick<Cluster, 'buildings' | 'free'>,
  counts: FreeRoomCounts,
) {
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
