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
  (© OpenStreetMap contributors, ODbL), at each building's centroid, to 5
  decimal places (about a metre). Barrows, Kroeber and LeConte were renamed,
  and their names in the schedule aren't known yet, and Genetics & Plant
  Biology had no OpenStreetMap match, so they're left out until a real import
  shows how the schedule names them.

