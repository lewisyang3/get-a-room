# Building locations

Berkeley's section pages don't give building coordinates, so they're kept by
hand in [`data/building_locations.csv`](../data/building_locations.csv)
(`name,latitude,longitude`) and applied to the database with:

```bash
python -m ingestion.cli buildings set-locations            # the repo's CSV
python -m ingestion.cli buildings set-locations --file other.csv
```

- Names are matched the way imports key buildings, ignoring case and
  punctuation, so use the building name as it appears in the class schedule's
  locations (`Dwinelle`, `Valley Life Sciences`).
- It's safe to re-run, and imports never change coordinates. Run it again
  after an import adds buildings: it lists covered buildings that still have
  no coordinates (they sort last by distance), and CSV names that matched no
  building.
- An invalid CSV changes nothing and exits 2, naming the line at fault.
- Coordinates come from [OpenStreetMap](https://www.openstreetmap.org/)
  (© OpenStreetMap contributors, ODbL), at each building's centre, to 5
  decimal places (about a metre). For a courtyard or L-shaped building, whose
  centre falls outside it (Anthro/Art Practice Bldg, North Gate, Undergrad
  Academic Bldg), it's the point deepest inside the outline instead. Some schedule names differ from
  OpenStreetMap's: Social Sciences Building is the old Barrows, Anthro/Art
  Practice Bldg is Kroeber, Physics Building is LeConte, Philosophy Hall is
  Moses, Berkeley Art Museum is BAMPFA on Center Street, and UC LAW is the Law
  Building.
- Buildings are added only when the match is clear. After the Fall 2026
  import these are left out, so they sort last by distance and have no pin on
  the map: Graduate Theological Union (two possible buildings), Student Center
  (unclear which), Haas Faculty Wing (not in OpenStreetMap), and 2240 Piedmont
  and 2547 Bowditch (no clear match for the address).

