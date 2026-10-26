# Accessibility

The page aims for WCAG 2.2 AA on phones and desktops.

- **Keyboard:** every control can be reached with Tab. The segmented controls
  are native radio buttons, so the arrow keys move between options. When Show
  more loads rooms, focus moves to the first new room. When Try again or Show
  all buildings succeeds, focus moves to the results heading.
- **Screen readers:** controls are labelled, filters are grouped under their
  names, and each building's rooms sit under a heading. The results summary
  is a live region, so a changed filter announces the new room count.
- **Map:** each building on the map is a button named with its count, e.g.
  "Evans: 3 rooms free". It's marked pressed when selected, and it's reachable
  with Tab. Buildings with no room free have no button unless selected; one
  that has focus stays until focus moves on. Everything the map does is also
  available without it: the list shows each building's rooms, the Room or
  building search finds a building by name, and Show all buildings clears a
  building chosen on the map.
- **Zoom and small screens:** the page reflows down to 320 CSS px (400% zoom)
  without sideways scrolling. Text follows the browser's font size. Buttons,
  fields and the Directions links have tap targets at least 44px tall.
- **Display settings:** light and dark mode, increased contrast and reduced
  motion are respected. Text colors meet AA contrast in each.

**How it's checked:** `npm test` runs [axe](https://github.com/dequelabs/axe-core)
over the landing page and each search state (loading, results, empty, error,
and the map in both layouts). jsdom can't measure color contrast, so the color
tokens in `src/index.css` are chosen to meet AA. The
layout at each width, the keyboard order and Chrome's accessibility tree are
checked by hand.
