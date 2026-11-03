# Natural map vegetation

`frontend/src/game/rendering/vegetation.ts` generates deterministic organic clusters throughout battlefieldWorld, including its expanded negative-origin surroundings. The seed incorporates team count and arena layout version. It uses existing tree-0/1/2, bush and rock SVGs, varied scale and horizontal mirroring, irregular cluster radii, spacing rejection and natural clearings. Sparse grass and flowers are painted into the one-time terrain canvas. No perimeter loop or border rows are used.

Generation is capped at 100 clusters of 2–7 candidate decorations, with minimum spacing 44. Trees are denser in the surrounding padding, sparse inside active terrain. All clients with the same map topology/version see the same positions; no Math.random or server collision entities are introduced.

Clearances reserve base areas (200), spawns/rallies (210), build slots (100), passable nodes (105), river banks (95), and roads including quadratic bulge. Projected staging polygons plus margins also reserve gathering and approach space. Sprite canopy size is accounted for by the conservative margins. All six build slots per team remain accessible.

Decorations are created once per map in Phaser and use y depth. They have no input handlers, physics, pathfinding or projectile effects. Camera bounds, minimap, roads, bases, bridges and graph coordinates remain unchanged. Phaser handles camera culling; no particle emitters or per-frame vegetation generation is added.

Unit tests use actual server-generated 2/4/8/20-team map fixtures, compare deterministic layouts, check clearances/uniqueness and expanded-area coverage, and cap density. Browser acceptance compares two clients' actual scenery and captures all four map sizes with tower slot counts and frame samples. Local browser evidence is not a hardware-independent performance guarantee.

Confirmed browser results: 54/57/88/155 decorations for 2/4/8/20 teams, with all 12/24/48/120 tower slots retained. Camera pan/zoom passed on all four sizes, averaging 59.5–60.0 FPS in the local scenery-only sample; p95 frame time was 17.5 ms. See [camera report](qa/team-upgrade-camera.json) and the upgrade implementation QA section for scope.
