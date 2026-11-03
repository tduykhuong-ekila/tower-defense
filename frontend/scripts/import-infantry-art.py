"""Split the approved shared infantry concept into three anchored RGBA assets."""
from collections import deque
from pathlib import Path
from PIL import Image, ImageChops, ImageFilter

root = Path(__file__).resolve().parents[2]
sheet = Image.open(root / 'output/imagegen/infantry-upgrades/infantry-upgrades.png').convert('RGBA')
destination = root / 'frontend/public/assets/woodland'
figures = []
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
    bbox = main.getbbox()
    if bbox is None:
        raise ValueError(f'No soldier silhouette found in level {index + 1}')
    cell.putalpha(ImageChops.multiply(cell.getchannel('A'), main.filter(ImageFilter.MaxFilter(3))))
    # The lower silhouette centers the feet; rifle barrels do not affect the anchor.
    foot_bounds = main.crop((0, round(height * .72), width, height)).getbbox()
    if foot_bounds is None:
        raise ValueError(f'No feet found in level {index + 1}')
    anchor_x = (foot_bounds[0] + foot_bounds[2]) / 2
    figures.append((cell.crop(bbox), bbox, anchor_x))

max_extent = max(max(anchor_x - bbox[0], bbox[2] - anchor_x)
                 for _, bbox, anchor_x in figures)
scale = min(420 / max(figure.height for figure, _, _ in figures),
            432 / max(figure.width for figure, _, _ in figures),
            238 / max_extent)
for index, (figure, bbox, anchor_x) in enumerate(figures):
    left, top, right, bottom = bbox
    resized = figure.resize((round(figure.width * scale), round(figure.height * scale)), Image.Resampling.LANCZOS)
    sprite = Image.new('RGBA', (512, 512))
    sprite.alpha_composite(resized, (round(256 - anchor_x * scale + left * scale),
                                     round(512 * .89 - (bottom - top) * scale)))
    path = destination / f'infantry{"" if index == 0 else f"-lv{index + 1}"}.png'
    sprite.save(path, optimize=True)
    print(f'{path.name}: {sprite.size}, RGBA, bottom-center anchor=(.5,.89), bounds={sprite.getbbox()}')
