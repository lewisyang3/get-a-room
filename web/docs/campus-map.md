# Campus map

A map shows each building with how many rooms it has free for the current
search. It needs a Mapbox token (`VITE_MAPBOX_TOKEN`, see
[Configuration](development.md#configuration)), and
search is disabled until one is set.

- **Counts follow the search.** They use the same time, minimum and room or
  building search as the list, at the same minute. Every building keeps its
  count while one is selected. Buildings with no room free are left off the
  map, except a selected one, which shows a faded "0". A plain dot means the
  counts haven't loaded or couldn't be loaded.
- **Groups.** Buildings close enough on screen to overlap merge into one
  pill showing their total free rooms; choosing it zooms in until they
  split. From zoom 17 every building shows on its own. The selected
  building, and one with keyboard focus, are never grouped. While counts are
  unknown, a group is a dot like a building's. Groups are worked out with
  [supercluster](https://github.com/mapbox/supercluster), the library behind
  Mapbox's own clustering, whenever the map stops moving or the counts
  change; the pills are HTML buttons. `CLUSTER_RADIUS` and
  `CLUSTER_MAX_ZOOM` in `src/search/campusMapFeatures.ts` set how eagerly
  buildings group.
- **Choosing a building** on the map filters the results to it. Choosing it
  again, or Show all buildings under the results summary, shows every
  building.
- **Layout.** On wide screens (64rem and up) the map sits beside the
  results and stays in view as they scroll. On narrower screens a List / Map
  switch shows one at a time, and choosing a building goes back to the list.
- **If the map can't load.** Where the browser can't run it (no WebGL), or
  Mapbox can't load it (for example, it rejects the token), a notice says so,
  the switch is left out, and the list fills the page. Typing a building's
  name in the search still finds its rooms. Without any building locations,
  the map is left out with no notice. Mapbox GL loads only when the map is
  shown, in a separate chunk.

The map uses Mapbox's Standard style, with dusk lighting to match the dark
theme. Building locations come from `GET /buildings`, and the
counts from `GET /availability/buildings`.
