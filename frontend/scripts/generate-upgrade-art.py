"""Original modular SVG equipment layered onto the existing woodland artwork.
Run after generate-art.py. Keeps identical dimensions/origins for animation stability.
"""
from pathlib import Path

assets = Path(__file__).resolve().parents[1] / 'public/assets/woodland'

def equipment(code, level):
    if code == 'infantry':
        parts = ['<path d="M22 31l7-3 10 3v13l-9 4-8-5z" fill="#657c82"/><path d="M19 20q11-9 27 0l-2 6-23-1z" fill="#9cbbb6"/>']
        if level >= 3:
            parts += ['<path d="M18 30l-5 4 4 7 7-4M39 31l8 1 3 8-9 3" fill="#d6d9c1"/><path d="M45 34h16v3H45z" fill="#aabdb6"/><rect x="23" y="42" width="15" height="5" rx="1" fill="#8d7045"/>']
        if level >= 4:
            parts += ['<path d="M20 17l4-9 9 5 10-5 4 10M24 32l7 3 7-3v8l-7 5-7-5z" fill="#e6c66f"/><path d="M24 24h17v4H24z" fill="#80e3d5"/><path d="M53 19l6 2-2 6-6-2z" fill="#e6c66f"/>']
    elif code in ('tank', 'artillery'):
        parts = ['<path d="M21 67l17-7 7 12-18 7zM83 64l18-6 8 12-20 7z" fill="#829b9c"/><path d="M29 79h67v6H29z" fill="#b8c2a9"/>']
        if level >= 3:
            parts += ['<path d="M39 43l22-12 28 8v13L66 64 39 53z" fill="#657e86"/><path d="M69 48l33-13 6 11-36 14z" fill="#b6c7c0"/><path d="M44 42l18-8 19 6-19 9z" fill="#d5dfd3"/>']
        if level >= 4:
            parts += ['<path d="M20 65l17-9 9 13-19 8zM86 59l15-7 9 14-19 9z" fill="#d9bf72"/><path d="M59 33v-13M55 20h8" fill="none" stroke="#e9d291"/><circle cx="59" cy="19" r="4" fill="#8be5d3"/><path d="M101 34l8 9-5 6-8-10z" fill="#e3c474"/>']
    else:
        parts = ['<path d="M18 96l43-18 47 17-43 19z" fill="#778d87"/><path d="M28 94l34-12 34 12-33 12z" fill="#c5cbb1"/>']
        if level >= 3:
            parts += ['<path d="M30 61l12-7 5 34-12 5zM84 54l12 7-5 30-12-6z" fill="#728c91"/><path d="M28 60l12-7 7 9-12 7zM83 53l14 7-10 9-10-8z" fill="#c4d2c9"/>']
        if level >= 4:
            parts += ['<path d="M18 95l11-6 8 9-10 8zM96 89l12 6-10 11-10-8z" fill="#e4c373"/><path d="M41 57l5-8 6 8M78 56l5-8 6 8" fill="#e4c373"/><circle cx="63" cy="81" r="7" fill="#84dacd" stroke="#e7c877"/>']
    return '<g data-equipment-level="%s" stroke="#354638" stroke-width="2" stroke-linejoin="round">%s</g>' % (level, ''.join(parts))

for code in ('infantry', 'tank', 'artillery', 'mg_tower', 'cannon_tower', 'shield_generator'):
    names = [f'infantry-{i}-{f}' for i in range(20) for f in range(4)] if code == 'infantry' else [code]
    for name in names:
        source = (assets / f'{name}.svg').read_text()
        for level in (2, 3, 4):
            (assets / f'{name}-lv{level}.svg').write_text(source.replace('</svg>', equipment(code, level) + '</svg>'))
