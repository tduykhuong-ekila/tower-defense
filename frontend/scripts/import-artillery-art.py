"""Split the approved comparison into aligned 512px RGBA artillery UI sprites."""
from collections import deque
from pathlib import Path
from PIL import Image, ImageChops, ImageFilter

root = Path(__file__).resolve().parents[2]
sheet = Image.open(root / 'output/imagegen/artillery-upgrades/artillery-upgrades-v2.png').convert('RGBA')
destination = root / 'frontend/public/assets/woodland'
cells = []
for index in range(3):
    cell = sheet.crop((round(index * sheet.width / 3), 0, round((index + 1) * sheet.width / 3), sheet.height))
    width, height = cell.size
    pixels = bytearray(cell.getchannel('A').point(lambda a: 255 if a >= 128 else 0).tobytes())
    largest = []
    for start in range(len(pixels)):
        if not pixels[start]:
            continue
        pixels[start] = 0
        queue, component = deque([start]), []
        while queue:
            point = queue.popleft()
            component.append(point)
            x, y = point % width, point // width
            for neighbor in (point - 1 if x else -1, point + 1 if x + 1 < width else -1,
                             point - width if y else -1, point + width if y + 1 < height else -1):
                if neighbor >= 0 and pixels[neighbor]:
                    pixels[neighbor] = 0
                    queue.append(neighbor)
        if len(component) > len(largest):
            largest = component
    mask = bytearray(width * height)
    for point in largest:
        mask[point] = 255
    main = Image.frombytes('L', cell.size, bytes(mask))
    cell.putalpha(ImageChops.multiply(cell.getchannel('A'), main.filter(ImageFilter.MaxFilter(5))))
    left, top, right, bottom = cell.getbbox()
    # Align the chassis/feet rather than the elevated muzzle's asymmetric bounds.
    low_left, _, low_right, _ = main.crop((0, round(height * .68), width, height)).getbbox()
    anchor_x = (low_left + low_right) / 2
    cells.append((cell, anchor_x, bottom, max(anchor_x-left, right-anchor_x), bottom-top))

# One shared scale preserves the family proportions; padding fits the longest gun.
scale = min(512 * .44 / max(c[3] for c in cells), 512 * .83 / max(c[4] for c in cells))
for index, (cell, anchor_x, bottom, _, _) in enumerate(cells):
    resized = cell.resize((round(cell.width * scale), round(cell.height * scale)), Image.Resampling.LANCZOS)
    sprite = Image.new('RGBA', (512, 512))
    sprite.alpha_composite(resized, (round(256-anchor_x*scale), round(512*.89-bottom*scale)))
    suffix = '' if index == 0 else f'-lv{index+1}'
    path = destination / f'artillery{suffix}.png'
    sprite.save(path, optimize=True)
    print(f'{path.name}: RGBA {sprite.size}, anchor=(.5,.89), bounds={sprite.getbbox()}')
