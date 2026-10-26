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

/** Buildings shown on their own, and groups keyed by their lowest
 * building id, which stays the same when the buildings are grouped again.
 * Supercluster's own ids change whenever a building joins or leaves. */
export type Groups = {
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

// All of the world: grouping every building, not just those in view, is
// cheap for one campus, and means panning never reveals a gap.
const WORLD: [number, number, number, number] = [-180, -85, 180, 85]

/** Every building and group at a zoom. */
export function groupsAt(index: ClusterIndex, zoom: number): Groups {
  const groups: Groups = { buildingIds: new Set(), clusters: new Map() }
  for (const feature of index.getClusters(WORLD, Math.floor(zoom))) {
    const { properties } = feature
    if ('cluster_id' in properties) {
      const id = properties.cluster_id
      const key = Math.min(
        ...index
          .getLeaves(id, Infinity)
          .map((leaf) => leaf.properties.building_id),
      )
      groups.clusters.set(key, {
        lngLat: feature.geometry.coordinates as LngLat,
        buildings: properties.point_count,
        free: properties.free,
        expansionZoom: index.getClusterExpansionZoom(id),
      })
    } else {
      groups.buildingIds.add(properties.building_id)
    }
  }
  return groups
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
