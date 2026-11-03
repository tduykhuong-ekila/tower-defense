# Infantry clear defensive towers before the base

Infantry previously marched toward the base and acquired towers only inside
their current weapon range. Grid towers outside that road corridor could survive
while Infantry damaged the base.

Infantry now retain a defensive tower objective belonging to their selected
enemy team. They follow roads toward that tower, using a reachable road node for
legacy impassable foundations. For grid construction, they approach from the
tower's road anchor until the existing footprint range check permits firing.
The approach consumes the normal movement budget; damage, weapon range, HP and
attack cooldown remain unchanged.

An active or disabled surviving tower of the selected team blocks Infantry base
damage. Destroyed and friendly towers do not. After a tower falls, Infantry clear
the next defense and then resume attacking the base. A new tower built during a
base attack also becomes a defensive objective. Existing configured priorities
still decide between nearby troop and tower combat targets.

Approaches and road returns use persisted simulation state and world positions.
Retreat orders interrupt the siege and return Infantry to their road anchor
before continuing toward the rally. Tanks and Artillery retain their movement
and base targeting behavior.

Regression coverage is in `backend/tests/test_infantry_siege.py`: 2/4/8/20-team
arenas, grid towers beyond road range, multiple towers, JSON state reloads,
movement budgets, exact attack ranges, disabled/friendly/destroyed towers,
late construction, road returns, retreat and legacy foundation combat.
The legacy full combat scenario now expects Infantry to attack the surviving
tower before damaging the base.

Verification: 143 tests passed and 5 were skipped across the siege, spawn/tower
realtime, troop movement, grid placement, Infantry cadence, legacy combat,
continuous combat and unlimited tower suites. Ruff passed for every changed
Python file. The spatial-index regression now compares against the existing
tower-footprint distance rule instead of the outdated center-only expectation.

Deploy the updated backend or restart its process to load this change. No
database migration or frontend change is required.
