# Section fixtures

Real Fall 2025 section pages from classes.berkeley.edu, used by
`tests/ingestion/test_parse.py`, `test_filter.py` and the pipeline tests. They
are snapshots, so the live pages may have changed since.

| File | Section | Covers | Location | Meetings | Filter result |
|---|---|---|---|---:|---|
| `lec_with_room.html` | ETHSTD 12 LEC 001 | Normal class | Dwinelle 242 | 1 | accepted |
| `dis_with_room.html` | NEU C166 DIS 107 | Normal class; end time shown a minute early | Valley Life Sciences 3030 | 1 | accepted |
| `grp_with_room.html` | ASTRON 98 GRP 001 | Normal class; two days | Campbell Hall 131 | 2 | accepted |
| `lec_three_days.html` | CHEM 122 LEC 001 | Multiple meeting days (Mo, We, Fr) | Evans 35 | 3 | accepted |
| `grp_two_meeting_blocks.html` | COMPSCI 198 GRP 075 | Multiple meeting days, in two blocks with different times | Soda 306 | 2 | accepted |
| `lec_online.html` | EPS 80 LEC 002 | Online class | Internet/Online | 2 | `online` |
| `lec_general_assignment.html` | MECENG 165 LEC 01 | Missing room: not assigned yet | Requested General Assignment | 2 | `general_assignment_requested` |
| `grp_missing_location.html` | COLWRIT 198 GRP 005 | Missing room: no location at all | (none) | 1 | `missing_location` |
| `lec_unparseable_location.html` | PUBPOL 297 LEC 006 | Malformed location: no room number | GTU Student Services Center | 1 | `unparseable_location` |
| `ind_no_meetings.html` | AGRS H195A IND 005 | Independent study: no meetings | (none) | 0 | `section_type_not_room_occupying:IND` |

## Known limit

A section's location comes from its first meeting block that has one. If a
section met in different rooms in different blocks, every meeting would be
put in the first room. None of the 400 Fall 2025 sections sampled for these
fixtures did this: sections with two blocks used the same room in both.

## Adding a fixture

1. Fetch the page once, e.g. `curl -s https://classes.berkeley.edu/content/<slug>`.
   Be polite: one request at a time, a second or more apart.
2. Keep only the `<article class="sf">` element, unchanged, wrapped as:

   ```html
   <!doctype html>
   <html><body>
   <article data-history-node-id="…" class="sf">…</article>
   </body></html>
   ```

3. Add a test for it, and a row to the table above.
