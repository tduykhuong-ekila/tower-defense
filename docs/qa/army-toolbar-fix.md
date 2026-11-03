# Selected-unit toolbar layout fix

Cause: the new standalone right-click hint added a third row to a toolbar still constrained to 100px on desktop and 120px on mobile. At 1512px viewport width, the header started 5.2px above the dock and the action form ended 5.2px below it.

Fix: move the hint into the existing composition line; let the selected dock grow from its compact minimum; use intrinsic content rows. On narrow screens the target picker occupies one row, and order buttons plus Execute share the next. The empty toolbar can also grow when touch tools wrap.

Verified in the real BattlePage with the local integration fixture and backend:
- 1512px desktop: dock 104.3px tall, header and form contained, rows do not overlap.
- 390px portrait: dock 168px tall, all visible toolbar controls contained.
- 320px portrait: no controls outside the dock.
- 844x390 landscape: dock 102.3px tall, no controls outside the dock.

Army control tests: 7/7 passed. Build log: army-toolbar-fix-build.txt.
