"""Import the approved tank family as 512px RGBA UI sprites and moving hulls.

Requires Pillow. Tracks use a shared 384px width and (.5, .89) bottom-center
anchor. The chassis is separate so its direction never mirrors the aiming gun.
"""
from collections import deque
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

root = Path(__file__).resolve().parents[2]
source = root / 'output/imagegen/tank-upgrades/tank-upgrades.png'
destination = root / 'frontend/public/assets/woodland'
sheet = Image.open(source).convert('RGBA')
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
    cell = sheet.crop((round(index * sheet.width / 3), 0,
                       round((index + 1) * sheet.width / 3), sheet.height))
    main = silhouette(cell.getchannel('A'))
    cell.putalpha(ImageChops.multiply(cell.getchannel('A'), main.filter(ImageFilter.MaxFilter(5))))
    lower = round(sheet.height * .64)
    left, _, right, _ = main.crop((0, lower, cell.width, cell.height)).getbbox()
    bottom = main.getbbox()[3]
    scale = (size * .75) / (right - left)
    anchor_x = (left + right) / 2
    cell = cell.resize((round(cell.width * scale), round(cell.height * scale)), Image.Resampling.LANCZOS)
    sprite = Image.new('RGBA', (size, size))
    sprite.alpha_composite(cell, (round(size * .5 - anchor_x * scale), round(size * .89 - bottom * scale)))
    suffix = '' if index == 0 else f'-lv{index + 1}'
    sprite.save(destination / f'tank{suffix}.png', optimize=True)

    # Preserve the glacis, track skirts, headlights and rear storage. The upper
    # turret is replaced by the high-resolution directional assembly in Phaser.
    mask = Image.new('L', sprite.size)
    ImageDraw.Draw(mask).polygon([(0, 258), (145, 258), (175, 286), (330, 286),
                                 (390, 310), (512, 310), (512, 512), (0, 512)], fill=255)
    hull = sprite.copy()
    hull.putalpha(ImageChops.multiply(hull.getchannel('A'), mask))
    hull = Image.alpha_composite(Image.new('RGBA', sprite.size), hull)
    hull.save(destination / f'tank-hull{suffix}.png', optimize=True)
    print(f'tank{suffix}.png / tank-hull{suffix}.png: {sprite.size}, anchor=(.5, .89)')
