# Woodland asset manifest

All battlefield illustrations are original vector artwork created for this repository. The supplied screenshot guided palette, layering and atmosphere; none of its pixels, map, characters or buildings were extracted. No third-party asset pack was downloaded and no additional attribution or redistribution conditions were introduced.

Source: `frontend/scripts/generate-art.py`. Regenerate with `python3 frontend/scripts/generate-art.py`. Output: `frontend/public/assets/woodland/`. Phaser rasterizes SVG textures when loading; the runtime is a Phaser canvas, not an SVG battlefield or a background poster.

| Files | Count | Use |
|---|---:|---|
| `base-0.svg` … `base-19.svg` | 20 | Team-colored stone keeps, banners and gate details |
| `banner-0.svg` … `banner-19.svg` | 20 | Ownership pennants on defensive structures |
| `infantry-{0..19}-{0..3}.svg` | 80 | Four walking poses for each team color |
| `tank.svg`, `artillery.svg` | 2 | Armored vehicle and long-barrel artillery illustrations |
| `mg_tower.svg`, `cannon_tower.svg`, `shield_generator.svg` | 3 | Distinct defensive silhouettes |
| `tree-0.svg` … `tree-2.svg` | 3 | Overlapping leafy canopies with trunks, shadows and highlights |
| `rock.svg`, `bush.svg`, `crate.svg`, `camp.svg` | 4 | Layered environmental decoration |
| `favicon.svg` | 1 | Original shield app icon, maintained separately |

132 illustrated game textures plus one favicon. Environment texture, roads, water, bridges, ripples, placement markers, HP bars, projectiles and impacts are rendered procedurally in Phaser/Canvas. Infantry idle, attacks, hits, spawning, building and destruction combine these illustrations with transforms/effects. Vehicles currently use transform animation rather than separate directional sprite atlases.

The generator is deterministic. Asset names match backend unit codes so an unlocked technology automatically appears with the correct illustration. Do not rename a unit code merely to change its picture; update the renderer mapping instead.
