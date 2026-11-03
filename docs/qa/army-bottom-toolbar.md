# Selected-army bottom toolbar

Verified on 2026-11-02 against the local React/Phaser game.

- Clicking a friendly troop automatically replaces the deployment dock with command controls.
- Selecting all three troops updates the summary and preserves direct commands.
- Clicking an enemy target issues the selected-group attack immediately; the server confirmed three troops retargeted.
- The current target is disabled; another active target remains available.
- Retreat is disabled during initial gathering, matching the context menu.
- Clearing selection restores the deployment dock.
- At 390 × 844, the page width remains 390px and the toolbar stays inside the viewport.
- Desktop and mobile screenshots are saved beside this report.

Validation: production build passed; 10 army-control tests passed. The full frontend suite has four failures outside these changes: three star-level markup assertions and one equipment artwork assertion.
