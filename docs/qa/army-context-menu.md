# Map command popup

In Chỉ huy, left-click a friendly mobile unit to select it; Shift/Ctrl/Command-click adds/removes units. Left-drag selects a group. Space-drag or middle-drag pans. Right-click without dragging opens commands for the current group; right-clicking a unit preserves selection.

The popup lists active enemy bases for attack, retreat to the home rally, and clear selection. Orders use explicit selected unit IDs. Unavailable or already satisfied orders are disabled. Escape and outside clicks close the popup without clearing selection. It clamps to the viewport and renders above the HUD. Retreating the entire army retains the existing confirmation dialog and expands the dock to show it.

Verified manually with local Vite and the running backend on 2026-11-01:
- Real left-drag selected four infantry; right-click opened a four-unit popup.
- Attack changed the selected group's target; server success reported four affected units.
- Escape preserved the four-unit selection.
- Real left-click selected one infantry; right-click on it preserved selection.
- Retreat reported exactly one affected unit, while other units continued attacking.
- Right-click near the bottom-right edge kept the popup within the viewport.
- Outside click closed the popup and preserved selection.
- Popup opened with the dock collapsed.
- Selecting the full army and retreating opened the existing confirmation dialog.

Build passed. Army control tests: 7/7 passed. Full frontend suite: 160/164 passed; failures are three star-level.test.ts artwork expectations and one team-upgrades-vegetation.test.ts artwork assertion, outside the files changed for this feature.

Reproduce: open /tests/fixtures/army-context.html on the Vite development server and click “Tạo trận kiểm thử chỉ huy”. It creates a disposable three-team match and four infantry through the real HTTP API and mounts BattlePage/Phaser. Switch to Chỉ huy, select troops, and right-click the map.
