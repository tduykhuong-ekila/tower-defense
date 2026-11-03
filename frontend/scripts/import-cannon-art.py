"""Import the approved Cannon Tower v2 comparison into aligned RGBA sprites.

Requires Pillow. The full sprites are used by UI/build previews; separate fixed
foundations allow the battlefield gun assembly to turn without moving the base.
"""
from collections import deque
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

root = Path(__file__).resolve().parents[2]
source = root / 'output/imagegen/cannon-tower-upgrades/cannon-tower-upgrades-v2.png'
destination = root / 'frontend/public/assets/woodland'
sheet = Image.open(source).convert('RGBA')
cell_width = sheet.width // 3
size = 512


def silhouette(alpha):
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
    return Image.frombytes('L', alpha.size, bytes(mask))


for index in range(3):
    cell = sheet.crop((index * cell_width, 0, (index + 1) * cell_width, sheet.height))
    main = silhouette(cell.getchannel('A'))
    cell.putalpha(ImageChops.multiply(cell.getchannel('A'), main.filter(ImageFilter.MaxFilter(5))))
    base_top = round(sheet.height * .67)
    left, _, right, _ = main.crop((0, base_top, cell.width, cell.height)).getbbox()
    bottom = main.getbbox()[3]
    contact = main.crop((0, bottom - 8, cell.width, bottom)).getbbox()
    anchor_x = (contact[0] + contact[2]) / 2
    scale = (size * .75) / (right - left)
    cell = cell.resize((round(cell.width * scale), round(cell.height * scale)), Image.Resampling.LANCZOS)
    sprite = Image.new('RGBA', (size, size))
    sprite.alpha_composite(cell, (round(size * .5 - anchor_x * scale), round(size * .89 - bottom * scale)))
    suffix = '' if index == 0 else f'-lv{index + 1}'
    target = destination / f'cannon_tower{suffix}.png'
    sprite.save(target, optimize=True)
    print(f'{target.relative_to(root)}: {sprite.size}, ground anchor=(0.5, 0.89)')

    # Keep the round foundation and the ammunition chest to the left. The
    # turning bearing above the stone drum is supplied by the directional gun.
    mask = Image.new('L', sprite.size)
    chest_top = (265, 278, 294)[index]
    core_top = (298, 320, 330)[index]
    ImageDraw.Draw(mask).polygon([(0, chest_top), (166, chest_top), (166, core_top),
                                 (390, core_top), (432, core_top + 8),
                                 (512, core_top + 8), (512, 512), (0, 512)], fill=255)
    base = sprite.copy()
    base.putalpha(ImageChops.multiply(base.getchannel('A'), mask))
    base = Image.alpha_composite(Image.new('RGBA', sprite.size), base)
    base.save(destination / f'cannon_tower-base{suffix}.png', optimize=True)
