"""Slice the approved concept sheet into game textures (requires Pillow).

Run from any directory. Every level uses a 512px canvas, a 384px-wide
foundation and the game's (.5, .89) ground anchor. Only detached alpha
specks are discarded; artwork and antialiased silhouette edges are kept.
"""
from collections import deque
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter

root = Path(__file__).resolve().parents[2]
source = root / 'output/imagegen/machine-gun-upgrades/machine-gun-tower-upgrades.png'
destination = root / 'frontend/public/assets/woodland'
sheet = Image.open(source).convert('RGBA')
cell_width = sheet.width // 3
size = 512


def silhouette(alpha):
    """Keep the main connected tower and its adjacent antialiasing pixels."""
    width, height = alpha.size
    pixels = bytearray(alpha.point(lambda a: 255 if a >= 128 else 0).tobytes())
    largest = []
    for start in range(len(pixels)):
        if not pixels[start]:
            continue
        pixels[start] = 0
        queue = deque([start])
        component = []
        while queue:
            point = queue.popleft()
            component.append(point)
            x, y = point % width, point // width
            for neighbor in (
                point - 1 if x else -1,
                point + 1 if x + 1 < width else -1,
                point - width if y else -1,
                point + width if y + 1 < height else -1,
            ):
                if neighbor >= 0 and pixels[neighbor]:
                    pixels[neighbor] = 0
                    queue.append(neighbor)
        if len(component) > len(largest):
            largest = component
    mask = bytearray(width * height)
    for point in largest:
        mask[point] = 255
    return Image.frombytes('L', alpha.size, bytes(mask))


for index in range(3):
    cell = sheet.crop((index * cell_width, 0, (index + 1) * cell_width, sheet.height))
    main = silhouette(cell.getchannel('A'))
    cell.putalpha(ImageChops.multiply(cell.getchannel('A'), main.filter(ImageFilter.MaxFilter(5))))
    # Lower part of the sheet contains only the shared foundation.
    base_top = round(sheet.height * .55)
    left, _, right, _ = main.crop((0, base_top, cell.width, cell.height)).getbbox()
    bottom = main.getbbox()[3]
    contact = main.crop((0, bottom - 8, cell.width, bottom)).getbbox()
    anchor_x = (contact[0] + contact[2]) / 2
    scale = (size * .75) / (right - left)
    cell = cell.resize((round(cell.width * scale), round(cell.height * scale)), Image.Resampling.LANCZOS)
    sprite = Image.new('RGBA', (size, size))
    sprite.alpha_composite(cell, (round(size * .5 - anchor_x * scale), round(size * .89 - bottom * scale)))
    suffix = '' if index == 0 else f'-lv{index + 1}'
    target = destination / f'mg_tower{suffix}.png'
    sprite.save(target, optimize=True)
    print(f'{target.relative_to(root)}: {sprite.size}, ground anchor=(0.5, 0.89)')
