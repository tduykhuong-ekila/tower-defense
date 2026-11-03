"""Deterministic sand shapes, matching frontend rendering/roadShape.ts.

The walking centerline remains the shortest route entirely inside the sand.
Organic bends use only spare width outside the 12px troop anchor allowance.
"""
import math


def natural_road(a, b, key, sand_width):
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy)
    seed = sum(ord(ch) * (i + 1) for i, ch in enumerate(key))
    phase = (seed % 628) / 100
    amplitude = max(0, min(sand_width / 2 - 15, length * .06))
    points = []
    for i in range(33):
        t = i / 32
        bend = amplitude * math.sin(math.pi * t) ** 2 * (
            .72 * math.sin(2 * math.pi * t + phase)
            + .28 * math.sin(math.pi * t + phase * .43)
        )
        points.append((a[0] + dx * t - dy / (length or 1) * bend,
                       a[1] + dy * t + dx / (length or 1) * bend))
    return points
