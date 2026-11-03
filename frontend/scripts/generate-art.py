"""Original woodland game illustrations. Regenerate with python3 scripts/generate-art.py."""
from pathlib import Path
import random

OUT = Path(__file__).resolve().parents[1] / 'public/assets/woodland'
OUT.mkdir(parents=True, exist_ok=True)
COLORS = ['#55a5cc', '#d66552', '#87b65d', '#d4a64b', '#b487cd', '#55bbb0', '#d28caa', '#89a9df', '#cba06b', '#b6c762', '#bd8070', '#88b5a3', '#e6b8df', '#6794e8', '#ed9758', '#83cbd4', '#bca2ed', '#dfcc77', '#c66c94', '#8fbdc9']
DEFS = '''<defs><linearGradient id="stone" x2=".3" y2="1"><stop stop-color="#d9d0a9"/><stop offset="1" stop-color="#8d9278"/></linearGradient><linearGradient id="roof" x2=".4" y2="1"><stop stop-color="#c38b54"/><stop offset="1" stop-color="#79513a"/></linearGradient><linearGradient id="steel" x2=".5" y2="1"><stop stop-color="#e1e7d8"/><stop offset=".5" stop-color="#9eafa8"/><stop offset="1" stop-color="#596f70"/></linearGradient><linearGradient id="leaf" x2=".4" y2="1"><stop stop-color="#9bbd56"/><stop offset="1" stop-color="#427442"/></linearGradient><linearGradient id="wood" x2=".4" y2="1"><stop stop-color="#c69b61"/><stop offset="1" stop-color="#805735"/></linearGradient></defs>'''
def save(name, body, w=128, h=128):
    (OUT / f'{name}.svg').write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">{DEFS}<g stroke="#354638" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">{body}</g></svg>')

def stonework(x, y, width, height):
    s = ''
    for row in range(int(height/12)):
        yy=y+row*12
        s+=f'<path d="M{x+2} {yy}h{width-4}" stroke="#737e68" stroke-width="1" opacity=".6"/>'
        for xx in range(int(x+8+(row%2)*9), int(x+width-4), 19):
            s+=f'<path d="M{xx} {yy}v10" stroke="#737e68" stroke-width="1" opacity=".55"/>'
    return s
for i,c in enumerate(COLORS):
    body=f'''<ellipse cx="66" cy="112" rx="57" ry="12" fill="#324d35" opacity=".23" stroke="none"/>
    <path d="M18 104V47h91v57l-45 12z" fill="url(#stone)"/>{stonework(20,53,87,49)}
    <path d="M25 66V31l39-19 39 19v35z" fill="#b9bd9c"/><path d="M21 33L64 9l44 24-7 9-37-20-38 21z" fill="{c}"/>
    <path d="M48 106V82q16-25 32 0v24z" fill="#544e3e"/><path d="M52 106V84q12-18 24 0v22" fill="url(#wood)"/><path d="M64 80v26M56 86v18M72 86v18" stroke="#745c3e" stroke-width="1.5"/>
    <path d="M9 104V45h27v59l-13 5zM92 104V45h27v59l-13 5z" fill="url(#stone)"/>
    <path d="M7 47V34h8v6h7v-6h8v6h8v8zM90 47V34h8v6h7v-6h8v6h8v8z" fill="#d0cead"/>
    <path d="M17 60h10v17H17zM100 60h10v17h-10zM58 40h12v18H58z" fill="#485b51"/>
    <path d="M56 61h17v19l-8 7-9-7z" fill="{c}"/><path d="M60 68l4 6 5-8" fill="none" stroke="#e9ead4"/>
    <path d="M64 11V-1" stroke="#78674c"/><path d="M65 0h23l-7 6 7 5H65z" fill="{c}"/>
    <path d="M13 96h12M99 90h15M30 84h8M85 74h7" stroke="#dfe0bb" stroke-width="2"/>
    <path d="M7 105l10-3 5 6M104 109l9-6 10 2" stroke="#6c9047" fill="none"/>'''
    save(f'base-{i}',body)
    save(f'banner-{i}',f'<path d="M40 117V13" stroke="#66553b" stroke-width="5"/><path d="M40 16h51l-11 19 11 20H41z" fill="{c}"/><path d="M50 22h29l-8 12 8 12H50" fill="none" stroke="#f1e9bf" stroke-width="2"/><path d="M31 117h19" stroke="#5a573d"/>')
    for f in range(4):
        d = [-3,0,3,0][f]
        body=f'''<ellipse cx="32" cy="58" rx="20" ry="5" fill="#263f32" opacity=".25" stroke="none"/>
        <path d="M24 42l{-d} 12h-9v-5l6-12M36 42l{d} 12h9v-5l-6-12" fill="#655644"/>
        <path d="M20 29q12-9 25 0l-3 19H23z" fill="{c}"/><path d="M25 30h11v16H25" fill="#c0c8ab"/><path d="M22 42h20" stroke="#765c39" stroke-width="4"/>
        <path d="M20 30l-5 13 7 3M42 29l6 12-5 4" fill="url(#steel)"/>
        <path d="M23 21q10-16 21 0v12l-12 7-9-7z" fill="#ddbd8b"/><path d="M20 24q-1-18 13-19 15 1 15 20l-14-2z" fill="url(#steel)"/>
        <path d="M33 7v16M19 24h30" stroke="#526d6d"/><path d="M39 27v3M29 27v3" stroke="#303e38" stroke-width="2"/>
        <g data-weapon="rifle"><path d="M20 35l12 1 5 5-5 5-12-5z" fill="url(#wood)"/><path d="M31 35h22v6H31z" fill="#526a65"/><path d="M48 35h13v4H48z" fill="#303e38"/><path d="M39 41l-2 7h-5l2-7" fill="#455650"/><path d="M48 34v-3h5v3" fill="#303e38"/><path d="M21 32l4 9 8-2M42 30l2 9 8-1" fill="none" stroke="#ddbd8b" stroke-width="5"/></g>
        <path d="M30 5l4-5 4 6" fill="{c}"/>'''
        save(f'infantry-{i}-{f}',body,64,64)
for code in ['mg_tower','cannon_tower','shield_generator']:
    top = {
      'mg_tower': '<path d="M30 60V35h68v25z" fill="#8e9c89"/><path d="M27 36V24h12v6h13v-6h12v6h13v-6h12v6h12v12z" fill="url(#stone)"/><path d="M40 28V10h11v20M60 27V9h11v20M80 28V12h11v20" fill="url(#steel)"/><path d="M43 12h5M63 11h5M83 14h5" stroke="#2b3934"/>',
      'cannon_tower': '<path d="M34 60V33h60v27z" fill="url(#wood)"/><ellipse cx="64" cy="36" rx="35" ry="14" fill="#9b9d83"/><path d="M50 34L44 8q20-14 34 1l-1 28z" fill="url(#steel)"/><ellipse cx="61" cy="8" rx="17" ry="8" fill="#33463f"/><ellipse cx="61" cy="8" rx="10" ry="4" fill="#1f302e"/><path d="M49 21l27 2" stroke="#d0d3b8" stroke-width="4"/>',
      'shield_generator': '<ellipse cx="64" cy="56" rx="39" ry="14" fill="#93b1ad"/><path d="M38 53l8-29h36l8 29z" fill="url(#steel)"/><path d="M64 3L49 24l15 20 15-20z" fill="#8bd8de" stroke="#467d85"/><path d="M64 3v41L54 24z" fill="#d5f0dd" stroke="none"/><path d="M36 29l-9 25M92 29l9 25" stroke="#68bac6" stroke-width="5"/>',
    }[code]
    save(code,f'''<ellipse cx="64" cy="112" rx="46" ry="10" fill="#324d35" opacity=".25" stroke="none"/><path d="M24 103l7-46h66l8 46-41 12z" fill="url(#stone)"/>{stonework(33,61,61,39)}<path d="M52 108V88q12-17 24 0v20z" fill="#4a5649"/><path d="M29 59h70v10H29z" fill="#c4c8a5"/>{top}<path d="M52 68h24v17l-12 8-12-8z" fill="#597c80"/><path d="M57 76h14M64 70v14" stroke="#e4dfbb"/><path d="M22 104l7-6M95 108l10-7" stroke="#77924f"/>''')
for code in ['tank','artillery']:
    barrel='<path d="M57 39l39-25 7 11-37 29z" fill="url(#steel)"/><path d="M95 14l10 10" stroke="#283f38" stroke-width="6"/>' if code=='artillery' else '<path d="M65 49l37-12 4 8-38 14z" fill="url(#steel)"/><path d="M100 37l4 8" stroke="#2c433b" stroke-width="5"/>'
    save(code,f'''<ellipse cx="64" cy="104" rx="53" ry="10" fill="#324d35" opacity=".25" stroke="none"/><path d="M17 67l14-18h64l18 20v24l-20 11H31L17 92z" fill="#475549"/><path d="M20 76h88v15H20z" fill="#7a8065"/>{''.join(f'<circle cx="{x}" cy="86" r="9" fill="#34483e"/><circle cx="{x}" cy="86" r="3" fill="#9b9e7f"/>' for x in [32,53,74,95])}<path d="M23 66l15-24h49l18 24-25 10H41z" fill="#9aa87b"/><path d="M42 45V33l26-9 21 13v20l-22 9-25-10z" fill="#a9b68a"/>{barrel}<path d="M48 36l19-7 15 9-17 8z" fill="#c2c9a2"/><path d="M29 62l15 6M88 63l10-4" stroke="#e0d6a1"/><path d="M54 55l10 4 9-4v10l-10 5-9-5z" fill="#5ba2bc"/>''')
for variant in range(3):
    rng=random.Random(variant+14)
    body='<ellipse cx="64" cy="111" rx="48" ry="10" fill="#2b4a32" stroke="none" opacity=".25"/><path d="M54 110l3-39h14l6 39-12 5z" fill="url(#wood)"/><path d="M63 87l-21-19M66 83l19-20" stroke="#6a623d" stroke-width="7"/>'
    for x,y,r in [(38,64,28),(89,61,27),(63,36,34),(34,43,24),(92,37,23),(64,65,29)]:
        x+=rng.randint(-5,5);y+=rng.randint(-4,4)
        body+=f'<path d="M{x-r} {y}C{x-r-3} {y-r*.6} {x-r*.4} {y-r} {x} {y-r} C{x+r*.6} {y-r-3} {x+r+2} {y-r*.3} {x+r} {y+3} C{x+r} {y+r*.7} {x+r*.3} {y+r} {x-3} {y+r} C{x-r*.7} {y+r} {x-r-3} {y+r*.4} {x-r} {y}Z" fill="url(#leaf)"/><path d="M{x-r+9} {y-5}q8-20 25-18" stroke="#b4c970" stroke-width="5" fill="none" opacity=".6"/>'
    save(f'tree-{variant}',body)
save('rock','<ellipse cx="64" cy="100" rx="41" ry="9" fill="#3c5238" opacity=".2" stroke="none"/><path d="M23 91l9-29 29-13 32 16 13 28-47 12z" fill="#949a7c"/><path d="M32 62l29-13 12 24-14 32-36-14z" fill="#b9bea0"/><path d="M35 67l22-10M78 77l14 9" stroke="#d4d4ac"/>')
save('bush','<ellipse cx="64" cy="104" rx="44" ry="8" fill="#314b32" opacity=".2" stroke="none"/><path d="M19 95q-9-26 16-29 5-31 29-18 29-15 33 19 26 4 14 30-15 15-36 7-24 12-40-1z" fill="url(#leaf)"/><path d="M35 81q6-16 21-14M73 65q13-3 17 12" stroke="#b4c975" stroke-width="4" fill="none"/><circle cx="47" cy="88" r="3" fill="#e3c47b"/><circle cx="82" cy="86" r="3" fill="#e3c47b"/>')
save('crate','<ellipse cx="62" cy="109" rx="42" ry="8" fill="#314b32" opacity=".2" stroke="none"/><path d="M24 57l37-18 40 15v47l-39 12-38-16z" fill="url(#wood)"/><path d="M24 57l38 14 39-17M62 71v42M28 62l29 12v32l-29-13zM68 75l28-11v31l-28 11zM29 64l25 38M94 68l-23 33" fill="none" stroke="#e0ba7c" stroke-width="4"/><path d="M33 55l29-11 29 11-29 10z" fill="#d2aa71"/>')
save('camp','<ellipse cx="67" cy="113" rx="52" ry="10" fill="#314b32" opacity=".2" stroke="none"/><path d="M18 86L64 20l48 68-46 23z" fill="#bd9e64"/><path d="M64 20l2 91-21-9z" fill="#655b3d"/><path d="M13 85l51-71 52 71-10 6-42-58-39 60z" fill="url(#roof)"/><path d="M25 90l-8 22M106 90l10 22" stroke="#786944"/><path d="M36 67l10 4M75 48l12 8M82 67l12 8" stroke="#deb276" stroke-width="3"/>')
print(f'Generated {len(list(OUT.glob("*.svg")))} original SVG assets in {OUT}')
