"""Builds the GitHub profile: seasonal SVG cards, a terminal GIF and README.md.

The look comes from the portfolio (github.com/Taz3rr/Portfolio): the same
fonts (Anybody, Instrument Serif, JetBrains Mono), the same four seasons
(Night, Fall, Winter, Spring) and the same procedural trees and weather.

    python scripts/build.py           # the season in season.txt ("auto" = by month)
    python scripts/build.py winter    # switch to a season (saved to season.txt)
    python scripts/build.py auto      # back to following the calendar
    python scripts/build.py --no-gif  # skip the terminal GIF

Needs: pip install fonttools brotli pillow
"""

import base64
import datetime as dt
import html
import io
import math
import re
import sys
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

ROOT = Path(__file__).resolve().parent.parent
ART = ROOT / 'art'
FONTS = ROOT / 'fonts'
ICONS = ROOT / 'icons'
CACHE = ROOT / '.cache'
SEASON_FILE = ROOT / 'season.txt'

USER = 'Taz3rr'
PORTFOLIO = 'https://portfolio-mu-one-3aqkxqrvc0.vercel.app'
W = 1000

# ---------------------------------------------------------------- content

TOOLKIT = [
    ('Languages', 'What I write in', [
        ('Python', 'python'), ('SQL', '#db'), ('JavaScript', 'javascript'),
        ('HTML', 'html5'), ('CSS', 'css'), ('Java', 'openjdk', 'BASIC')]),
    ('Bots & backend', 'What my Discord bots are built on', [
        ('Discord API', 'discord'), ('discord.py', 'python'), ('asyncio', 'python'), ('Pillow', None)]),
    ('Databases', 'Where the data lives', [
        ('SQLite', 'sqlite'), ('MySQL', 'mysql'), ('Oracle SQL', 'oracle')]),
    ('Analytics & BI', 'How I analyse and present it', [
        ('Excel', 'microsoftexcel'), ('Power BI', 'powerbi'), ('Tableau', 'tableau')]),
    ('Dev & deploy', 'How it ships and stays up', [
        ('Linux', 'linux'), ('PM2', 'pm2'), ('Git', 'git'), ('GitHub', 'github'), ('CLI', 'gnubash')]),
    ('AI & agents', 'The agents I build with', [
        ('Claude Code', 'claude'), ('Antigravity', None), ('Hermes', None), ('Qwen', 'qwen')]),
]
SOFT = ['Tournament-day communication', 'Roster & schedule management',
        'Scrim arrangements', 'Clear, timely communication']

JOURNEY_START, JOURNEY_END = dt.date(2024, 6, 1), dt.date(2027, 6, 30)
LANES = [
    dict(org='HSNC University', role='BASc · Data Science & Business Analytics',
         start=dt.date(2024, 6, 1), end=dt.date(2027, 6, 30), expected=True),
    dict(org='Tartarus', role='Esports team manager', start=dt.date(2025, 2, 1), end=dt.date(2025, 7, 31)),
    dict(org='Moba Legends: 5v5', role='Bot developer & moderator', start=dt.date(2025, 9, 1), end=None),
    dict(org='True Rippers', role='Esports manager', start=dt.date(2026, 2, 1), end=dt.date(2026, 7, 31),
         mark=(dt.date(2026, 5, 10), 'MLMS Season 1 champions')),
]

# ---------------------------------------------------------------- seasons
# Colours are the portfolio's tokens (src/styles/base.css, World.css, scenery.js).

SEASONS = {
    'night': dict(label='Night', hint='navy, black and white', dark=True,
                  bg='#04060d', bg2='#0a1330', bg3='#101d45', fg='#e9ecf4', mute='#8a95b3', dim='#4a5576',
                  line='rgba(233,236,244,0.12)', rule='#1a2444', accent='#ffffff', hi='#5b7bd9',
                  fill='#ffffff', on_fill='#0a1330', card='rgba(10,19,48,0.62)', branch='#0d1a3e'),
    'fall': dict(label='Fall', hint='autumn', dark=False,
                 bg='#f6e7ce', bg2='#f1dcb9', bg3='#fbf1df', fg='#3f2a1d', mute='#6b4423', dim='#a8835f',
                 line='rgba(63,42,29,0.18)', rule='#e3cdaa', accent='#c65d32', hi='#c65d32',
                 fill='#9e3f2d', on_fill='#f6e7ce', card='rgba(251,241,223,0.74)', branch='#3f2a1d'),
    'winter': dict(label='Winter', hint='snow', dark=False,
                   bg='#f7fbff', bg2='#e8f3fa', bg3='#ffffff', fg='#2b404c', mute='#4f6a7a', dim='#94adbc',
                   line='rgba(67,93,107,0.18)', rule='#d3e2ec', accent='#4d7590', hi='#4d7590',
                   fill='#435d6b', on_fill='#f7fbff', card='rgba(255,255,255,0.74)', branch='#708fa3'),
    'spring': dict(label='Spring', hint='bloom', dark=False,
                   bg='#fff9ee', bg2='#f3f8ec', bg3='#ffffff', fg='#2e3b2b', mute='#56664f', dim='#a1b199',
                   line='rgba(46,59,43,0.15)', rule='#e1e8d8', accent='#c4547f', hi='#c4547f',
                   fill='#e89ab8', on_fill='#2e3b2b', card='rgba(255,255,255,0.72)', branch='#5f7d4f'),
}
LEAF_COLORS = ['#D99A4E', '#C65D32', '#9E3F2D', '#6B4423', '#E0B05A']
# Dec-Feb winter, Mar-May spring, Jun-Aug night, Sep-Nov fall.
BY_MONTH = ['winter', 'winter', 'spring', 'spring', 'spring', 'night',
            'night', 'night', 'fall', 'fall', 'fall', 'winter']

# ---------------------------------------------------------------- fonts

FACES = {
    'fd': ('Anybody[wdth,wght].ttf', {'wght': 860, 'wdth': 74}),   # display, the hero name
    'fb': ('Anybody[wdth,wght].ttf', {'wght': 430, 'wdth': 86}),   # body
    'fs': ('InstrumentSerif-Italic.ttf', None),                    # serif italic
    'fm': ('JetBrainsMono[wght].ttf', {'wght': 500}),              # mono
}
_font_bytes, _fonts = {}, {}


def font(face):
    """The static instance of a face (TTFont), cached."""
    if face not in _fonts:
        file, axes = FACES[face]
        f = TTFont(FONTS / file)
        if axes:
            f = instancer.instantiateVariableFont(f, axes)
        buf = io.BytesIO()
        f.save(buf)
        _font_bytes[face] = buf.getvalue()
        _fonts[face] = TTFont(io.BytesIO(_font_bytes[face]))
    return _fonts[face]


def measure(face, text, size, ls=0.0):
    f = font(face)
    cmap, hmtx, upm = f.getBestCmap(), f['hmtx'], f['head'].unitsPerEm
    adv = sum(hmtx[cmap.get(ord(c), '.notdef')][0] for c in text)
    return adv * size / upm + ls * size * len(text)


def woff2_base64(face, chars):
    font(face)
    f = TTFont(io.BytesIO(_font_bytes[face]))
    opts = subset.Options()
    opts.flavor = 'woff2'
    opts.layout_features = ['kern']
    opts.name_IDs = ['*']
    opts.hinting = False
    opts.desubroutinize = True
    sub = subset.Subsetter(opts)
    sub.populate(text=''.join(sorted(chars)) + ' ')
    sub.subset(f)
    buf = io.BytesIO()
    f.flavor = 'woff2'
    f.save(buf)
    return base64.b64encode(buf.getvalue()).decode()


_mono_path = []


def mono_ttf_path():
    """The mono instance as a file, for Pillow. Written once per run."""
    if not _mono_path:
        font('fm')
        CACHE.mkdir(exist_ok=True)
        p = CACHE / 'mono.ttf'
        p.write_bytes(_font_bytes['fm'])
        _mono_path.append(p)
    return _mono_path[0]

# ---------------------------------------------------------------- helpers


def rng(seed):
    """mulberry32, the same generator the portfolio seeds its scenery with."""
    state = [seed & 0xFFFFFFFF]

    def imul(a, b):
        return (a * b) & 0xFFFFFFFF

    def r():
        state[0] = (state[0] + 0x6D2B79F5) & 0xFFFFFFFF
        t = state[0]
        t = imul(t ^ (t >> 15), 1 | t)
        t = ((t + imul(t ^ (t >> 7), 61 | t)) & 0xFFFFFFFF) ^ t
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296
    return r


def esc(s):
    return html.escape(s, quote=False)


def f1(n):
    return f'{n:.1f}'.rstrip('0').rstrip('.')


class Doc:
    """One SVG card. Collects the characters each font draws so it can embed
    just those glyphs."""

    def __init__(self, w, h, s):
        self.w, self.h, self.s = w, h, s
        self.defs, self.body, self.css = [], [], []
        self.used = {}

    def text(self, x, y, txt, face, size, fill, ls=0.0, anchor='start', extra=''):
        self.used.setdefault(face, set()).update(txt)
        a = f'x="{f1(x)}" y="{f1(y)}" class="{face}" font-size="{f1(size)}" fill="{fill}"'
        if ls:
            a += f' letter-spacing="{ls * size:.2f}"'
        if anchor != 'start':
            a += f' text-anchor="{anchor}"'
        return f'<text {a}{extra}>{esc(txt)}</text>'

    def render(self, title):
        faces = ''.join(
            f"@font-face{{font-family:'{k}';src:url(data:font/woff2;base64,{woff2_base64(k, v)}) format('woff2')}}"
            f".{k}{{font-family:'{k}'}}"
            for k, v in sorted(self.used.items()))
        css = faces + ''.join(self.css) + (
            '@media (prefers-reduced-motion:reduce){*{animation:none!important}}')
        return (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
                f'viewBox="0 0 {self.w} {self.h}" width="{self.w}" height="{self.h}" role="img" aria-label="{esc(title)}">'
                f'<title>{esc(title)}</title><style>{css}</style><defs>{"".join(self.defs)}</defs>'
                f'{"".join(self.body)}</svg>')


BASE_CSS = (
    '.sw{transform-box:fill-box;transform-origin:center}'
    '@keyframes fall{from{transform:translateY(-40px)}to{transform:translateY(var(--h))}}'
    '@keyframes drift{from{transform:translate(0,-40px)}to{transform:translate(-180px,var(--h))}}'
    '@keyframes sway{0%,100%{transform:translateX(-12px) rotate(-28deg)}50%{transform:translateX(12px) rotate(28deg)}}'
    '@keyframes twinkle{0%,100%{opacity:.12}50%{opacity:1}}'
    '@keyframes spin{to{transform:rotate(360deg)}}'
    '@keyframes pulse{0%,100%{transform:scale(1)}50%{transform:scale(1.22)}}'
    '@keyframes grow{from{transform:scaleX(0)}to{transform:scaleX(1)}}'
    '@keyframes rise{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:none}}'
    '@keyframes treesway{from{transform:rotate(-.7deg)}to{transform:rotate(.7deg)}}'
)


def card_frame(d, rx=22):
    """Sky, grain and border for a card; returns (open, close) wrapping the content."""
    s, w, h = d.s, d.w, d.h
    d.defs.append(f'<clipPath id="card"><rect width="{w}" height="{h}" rx="{rx}"/></clipPath>')
    d.defs.append(
        '<filter id="grain" x="0" y="0" width="100%" height="100%">'
        '<feTurbulence type="fractalNoise" baseFrequency=".9" numOctaves="2" stitchTiles="stitch"/>'
        '<feColorMatrix values="0 0 0 0 .5 0 0 0 0 .5 0 0 0 0 .5 0 0 0 .55 0"/></filter>')
    d.css.append(BASE_CSS + f'svg{{--h:{h + 40}px}}')
    sky = sky_layers(d)
    grain = f'<rect width="{w}" height="{h}" filter="url(#grain)" opacity="{0.07 if s["dark"] else 0.05}"/>'
    border = f'<rect x=".5" y=".5" width="{w - 1}" height="{h - 1}" rx="{rx}" fill="none" stroke="{s["line"]}"/>'
    return f'<g clip-path="url(#card)">{sky}{grain}', f'</g>{border}'


def sky_layers(d):
    key, w, h = d.s['key'], d.w, d.h
    rect = f'<rect width="{w}" height="{h}" fill="url(#%s)"/>'
    if key == 'night':
        d.defs.append(
            '<radialGradient id="sk1" cx=".5" cy="-.12" r=".75"><stop offset="0" stop-color="#0f2056"/>'
            '<stop offset=".62" stop-color="#0f2056" stop-opacity="0"/></radialGradient>'
            '<radialGradient id="sk2" cx="1" cy="1" r=".6"><stop offset="0" stop-color="#0d1c4a" stop-opacity=".8"/>'
            '<stop offset="1" stop-color="#0d1c4a" stop-opacity="0"/></radialGradient>')
        return f'<rect width="{w}" height="{h}" fill="#04060d"/>' + rect % 'sk1' + rect % 'sk2'
    if key == 'fall':
        d.defs.append(
            '<radialGradient id="sk1" cx=".5" cy=".45" r=".78"><stop offset="0" stop-color="#f6e7ce"/>'
            '<stop offset=".48" stop-color="#f6e7ce"/><stop offset=".68" stop-color="#efd2a4"/>'
            '<stop offset=".86" stop-color="#e2ad6b"/><stop offset="1" stop-color="#d99a4e"/></radialGradient>'
            '<radialGradient id="sk2" cx="0" cy="1" r=".5"><stop offset="0" stop-color="#3f2a1d" stop-opacity=".35"/>'
            '<stop offset="1" stop-color="#3f2a1d" stop-opacity="0"/></radialGradient>')
        return rect % 'sk1' + rect % 'sk2'
    if key == 'winter':
        d.defs.append(
            '<linearGradient id="sk1" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#a9c7d8"/>'
            '<stop offset=".16" stop-color="#c9dfec"/><stop offset=".38" stop-color="#e8f3fa"/>'
            '<stop offset=".6" stop-color="#f7fbff"/><stop offset=".82" stop-color="#f7fbff"/>'
            '<stop offset="1" stop-color="#e8f3fa"/></linearGradient>')
        return rect % 'sk1'
    d.defs.append(
        '<linearGradient id="sk1" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#d7eaf4"/>'
        '<stop offset=".36" stop-color="#fff9ee"/><stop offset=".74" stop-color="#fff9ee"/>'
        '<stop offset="1" stop-color="#ddefd5"/></linearGradient>'
        '<radialGradient id="sk2" cx=".88" cy="0" r=".5"><stop offset="0" stop-color="#fff1a8" stop-opacity=".6"/>'
        '<stop offset="1" stop-color="#fff1a8" stop-opacity="0"/></radialGradient>')
    return rect % 'sk1' + rect % 'sk2'

# ---------------------------------------------------------------- season marks and weather


LEAF = ('M0 -11L2.2 -5.6 6 -7.6 5 -3 10.6 -2.6 7 1 9 4.6 3.6 3.6 1 8 0 4.6 -1 8 -3.6 3.6 -9 4.6 '
        '-7 1 -10.6 -2.6 -5 -3 -6 -7.6 -2.2 -5.6z')
STAR = 'M0 -11C1 -3 3 -1 11 0 3 1 1 3 0 11-1 3-3 1-11 0-3-1-1-3 0-11z'


def mark(key, s):
    """The portfolio's 'live' marker for a season, centred on 0,0 (about 22 units)."""
    if key == 'night':
        return f'<path d="{STAR}" fill="{s["accent"]}"/>'
    if key == 'fall':
        return (f'<g transform="rotate(-8)"><path d="{LEAF}" fill="#b9572e" stroke="#5b3219" stroke-width=".8"/>'
                '<path d="M0 11.5V-8M0 2 6.5 -4.5M0 2 -6.5 -4.5" fill="none" stroke="#5b3219" stroke-width=".7"/></g>')
    if key == 'winter':
        arms = ''.join(f'<path transform="rotate({a})" d="M0 0V-10.5M-3.4 -8.8 0 -5.6 3.4 -8.8"/>'
                       for a in range(0, 360, 60))
        return (f'<g fill="none" stroke="{s["accent"]}" stroke-width="1.7" stroke-linecap="round">{arms}</g>')
    petals = ''.join(f'<ellipse cx="0" cy="-5.4" rx="4" ry="5.6" transform="rotate({a})"/>' for a in range(0, 360, 72))
    return f'<g fill="#e89ab8">{petals}</g><circle r="2.6" fill="#fff1a8" stroke="#c4547f" stroke-width=".6"/>'


def live_mark(d, x, y, scale=0.62, pulse=True):
    """A season mark at x,y that gently pulses."""
    anim = ' class="sw" style="animation:pulse 2.4s ease-in-out infinite"' if pulse else ''
    return (f'<g transform="translate({f1(x)} {f1(y)}) scale({scale})"><g{anim}>'
            f'{mark(d.s["key"], d.s)}</g></g>')


def weather(d, n, seed, top=0):
    """Falling leaves, snow, drifting petals or twinkling stars over the whole card."""
    key, w, h = d.s['key'], d.w, d.h
    r = rng(seed)
    out = []
    if key == 'night':
        for i in range(n):
            x, y = r() * w, top + r() * (h - top)
            sc = 0.15 + r() * 0.3
            dur, delay = 2.5 + r() * 4, r() * 6
            out.append(f'<g transform="translate({f1(x)} {f1(y)}) scale({sc:.2f})"><path class="sw" d="{STAR}" fill="#fff" '
                       f'style="animation:twinkle {dur:.1f}s ease-in-out -{delay:.1f}s infinite"/></g>')
        return '<g>' + ''.join(out) + '</g>'
    d.defs.append(f'<path id="leaf" d="{LEAF}"/>')
    for i in range(n):
        x = r() * (w + (180 if key == 'spring' else 0))
        dur = (9 if key == 'fall' else 13 if key == 'winter' else 11) + r() * 8
        delay = r() * dur
        sdur, sdelay = 2.6 + r() * 2.4, r() * 4
        if key == 'fall':
            sc = 0.55 + r() * 0.5
            shape = f'<use href="#leaf" fill="{LEAF_COLORS[int(r() * 5)]}" transform="scale({sc:.2f})" opacity=".9"/>'
        elif key == 'winter':
            if r() < 0.7:
                rad = 1.4 + r() * 2.2
                shape = f'<circle r="{rad:.1f}" fill="#fff" stroke="#a9c7d8" stroke-width=".7"/>'
            else:
                arms = ''.join(f'<path transform="rotate({a})" d="M0 0V-6M-2 -5 0 -3.2 2 -5"/>' for a in range(0, 360, 60))
                shape = f'<g fill="none" stroke="#a9c7d8" stroke-width="1.1" stroke-linecap="round">{arms}</g>'
        else:
            c = ['#f5c2d7', '#e89ab8', '#fbd9e6'][int(r() * 3)]
            shape = f'<ellipse rx="{3 + r() * 2:.1f}" ry="{1.8 + r():.1f}" fill="{c}"/>'
        anim = 'drift' if key == 'spring' else 'fall'
        out.append(
            f'<g style="animation:{anim} {dur:.1f}s linear -{delay:.1f}s infinite">'
            f'<g transform="translate({f1(x)} 0)"><g class="sw" style="animation:sway {sdur:.1f}s ease-in-out -{sdelay:.1f}s infinite">'
            f'{shape}</g></g></g>')
    return '<g>' + ''.join(out) + '</g>'

# ---------------------------------------------------------------- tree (a port of the portfolio's lib/tree.js)


def make_tree(seed, depth=7, length=230, width=26, lean=0.12):
    r = rng(seed)
    branches, tips, joints = [], [], []

    def grow(x, y, a, ln, dpt, wd):
        x2, y2 = x + math.cos(a) * ln, y + math.sin(a) * ln
        bend = (r() - 0.5) * ln * 0.35
        cx = (x + x2) / 2 + math.cos(a + math.pi / 2) * bend
        cy = (y + y2) / 2 + math.sin(a + math.pi / 2) * bend
        branches.append((f'M{x:.1f} {y:.1f}Q{cx:.1f} {cy:.1f} {x2:.1f} {y2:.1f}', wd, dpt))
        if dpt <= 2:
            joints.append((x2, y2))
        if dpt == 0:
            tips.append((x2, y2))
            return
        kids = 2 if dpt > 4 else (3 if r() < 0.45 else 2)
        for k in range(kids):
            spread = (k - (kids - 1) / 2) * (0.5 + r() * 0.25)
            pull = -0.08 if dpt < 4 else 0
            grow(x2, y2, a + spread + (r() - 0.5) * 0.3 + pull, ln * (0.68 + r() * 0.12), dpt - 1, max(1, wd * 0.66))

    grow(-6, 1010, -math.pi / 2 + lean, length, depth, width)
    return branches, tips, joints


def tree_svg(d, seed, transform, origin):
    s, key = d.s, d.s['key']
    branches, tips, joints = make_tree(seed)
    r = rng(seed + 101)
    parts = []
    for path, wd, dpt in branches:
        parts.append(f'<path d="{path}" stroke="{s["branch"]}" stroke-width="{wd:.1f}"/>')
    wood = f'<g fill="none" stroke-linecap="round">{"".join(parts)}</g>'
    extra = []
    if key == 'winter':
        caps = [f'<path d="{p}" stroke-width="{wd * 0.5:.1f}" transform="translate(0 {-wd * 0.32:.1f})"/>'
                for p, wd, dpt in branches if dpt >= 1]
        extra.append(f'<g fill="none" stroke="#fff" stroke-linecap="round" opacity=".95">{"".join(caps)}</g>')
        extra += [f'<circle cx="{x:.0f}" cy="{y - 2:.0f}" r="{4 + r() * 4:.1f}" fill="#fff"/>' for x, y in tips if r() < 0.5]
    elif key == 'fall':
        d.defs.append(f'<path id="tleaf" d="{LEAF}"/>')
        for x, y in tips:
            for _ in range(3):
                extra.append(f'<use href="#tleaf" fill="{LEAF_COLORS[int(r() * 5)]}" transform="translate({x + (r() - .5) * 34:.0f} '
                             f'{y + (r() - .5) * 30:.0f}) rotate({r() * 360:.0f}) scale({1.2 + r() * 0.9:.2f})"/>')
    elif key == 'spring':
        d.defs.append('<path id="sleaf" d="M0 0C6 -6 16 -5 20 0 16 5 6 6 0 0z"/>')
        for x, y in tips:
            for _ in range(2):
                c = '#7fb878' if r() < 0.35 else '#a8d5a2'
                extra.append(f'<use href="#sleaf" fill="{c}" transform="translate({x + (r() - .5) * 24:.0f} '
                             f'{y + (r() - .5) * 22:.0f}) rotate({r() * 360:.0f}) scale({1.1 + r() * 0.6:.2f})"/>')
        petals = ''.join(f'<ellipse cx="0" cy="-5" rx="3.4" ry="5" transform="rotate({a})"/>' for a in range(0, 360, 72))
        d.defs.append(f'<g id="bloom">{petals}</g>')
        for x, y in joints:
            if r() < 0.4:
                c = '#f5c2d7' if r() < 0.6 else '#fff6fa'
                extra.append(f'<g transform="translate({x:.0f} {y:.0f}) scale({1.3 + r() * 0.8:.2f})">'
                             f'<use href="#bloom" fill="{c}"/><circle r="1.9" fill="#fff1a8"/></g>')
    ox, oy = origin
    return (f'<g transform="{transform}"><g style="transform-origin:{ox}px {oy}px;'
            f'animation:treesway 6s ease-in-out infinite alternate">{wood}{"".join(extra)}</g></g>')


def winter_ground(d):
    """Distant mountains and a snowbank, as on the portfolio's winter page."""
    w, h = d.w, d.h
    r = rng(5)

    def ridge(base, amp, step):
        pts = [(0, h)]
        x = 0
        while x <= w + step:
            pts.append((x, base - r() * amp))
            x += step * (0.6 + r() * 0.8)
        pts.append((w, h))
        return 'M' + ' '.join(f'{px:.0f} {py:.0f}' for px, py in pts) + 'Z'
    sx = w / 1440
    return (f'<path d="{ridge(h - 70, 90, 120)}" fill="#c9dfec" opacity=".7"/>'
            f'<path d="{ridge(h - 40, 60, 90)}" fill="#a9c7d8" opacity=".45"/>'
            f'<g transform="translate(0 {h - 56}) scale({sx:.4f} .62)">'
            '<path d="M0 90V46c120-26 220-8 340-18s210-30 330-12 240 30 380 10 260-22 390-6v70z" fill="#e8f3fa"/>'
            '<path d="M0 90V58c140-22 240-4 360-14s200-26 320-10 250 26 370 8 250-18 390-4v52z" fill="#fff"/></g>')

# ---------------------------------------------------------------- icons


def icon(name, label, x, y, size, color, d):
    """A 24-unit icon drawn at x,y (top-left), tinted to the season."""
    sc = size / 24
    if name == '#db':
        g = (f'<g fill="none" stroke="{color}" stroke-width="2.2"><ellipse cx="12" cy="5" rx="8" ry="3"/>'
             '<path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/></g>')
    elif name:
        svg = (ICONS / f'{name}.svg').read_text(encoding='utf8')
        g = f'<path d="{re.search(r" d=\"([^\"]+)\"", svg).group(1)}" fill="{color}"/>'
    else:
        d.used.setdefault('fm', set()).add(label[0].upper())
        g = (f'<rect x="1.5" y="1.5" width="21" height="21" rx="5" fill="none" stroke="{color}" stroke-width="2"/>'
             f'<text x="12" y="17" class="fm" font-size="13" fill="{color}" text-anchor="middle">{esc(label[0].upper())}</text>')
    return f'<g transform="translate({f1(x)} {f1(y)}) scale({sc:.4f})">{g}</g>'

# ---------------------------------------------------------------- cards


def header(d, y, title, sub, meta=None, chip=None):
    """Card heading: big display title, a serif aside, and a mono note on the right."""
    s = d.s
    out = [d.text(48, y, title.upper(), 'fd', 46, s['fg'], ls=0.01)]
    tw = measure('fd', title.upper(), 46, 0.01)
    out.append(d.text(48 + tw + 16, y - 2, sub, 'fs', 21, s['mute']))
    x = d.w - 48
    if chip:
        cw = measure('fm', chip, 11, 0.16) + 22
        out.append(f'<rect x="{f1(x - cw)}" y="{y - 27}" width="{f1(cw)}" height="26" rx="13" fill="{s["fill"]}"/>')
        out.append(d.text(x - cw / 2 + 0.9, y - 10, chip, 'fm', 11, s['on_fill'], ls=0.16, anchor='middle'))
        x -= cw + 12
    if meta:
        out.append(d.text(x, y - 10, meta.upper(), 'fm', 11, s['mute'], ls=0.16, anchor='end'))
    out.append(f'<path d="M48 {y + 22}H{d.w - 48}" stroke="{s["line"]}"/>')
    return ''.join(out)


def hero_svg(s, today):
    H = 430
    d = Doc(W, H, s)
    key = s['key']
    open_, close = card_frame(d)
    b = [open_]
    if key == 'winter':
        b.append(winter_ground(d))
    if key == 'night':
        d.defs.append('<radialGradient id="glow" cx=".86" cy=".32" r=".42"><stop offset="0" stop-color="#5b7bd9" stop-opacity=".34"/>'
                      '<stop offset="1" stop-color="#5b7bd9" stop-opacity="0"/></radialGradient>')
        b.append(f'<rect width="{W}" height="{H}" fill="url(#glow)"/>')
    # The tree is ~840 units tall: at this scale the crown just fits, trunk set in from the edge.
    k = 0.52
    b.append(tree_svg(d, 7, f'translate({W - 70} {H - 1010 * k + 8:.0f}) scale(-{k} {k})', (0, 1010)))
    b.append(weather(d, {'night': 80, 'fall': 26, 'winter': 70, 'spring': 30}[key], 11))

    t = []
    # Top line, as on the portfolio hero.
    t.append(d.text(56, 64, 'MUMBAI, INDIA', 'fm', 11, s['fg'], ls=0.16))
    t.append(d.text(56 + measure('fm', 'MUMBAI, INDIA', 11, 0.16) + 14, 64, '19.07° N, 72.87° E', 'fm', 11, s['mute'], ls=0.16))

    # TAZ3R: display capitals with the 3 set in the serif italic, like the portfolio.
    size, x, base = 176, 50, 236
    glyphs = []
    for ch in 'TAZ3R':
        if ch.isdigit():
            ss = size * 1.12
            glyphs.append(d.text(x + 4, base, ch, 'fs', ss, s['hi'] if s['dark'] else s['accent']))
            x += measure('fs', ch, ss) + 8
        else:
            glyphs.append(d.text(x, base, ch, 'fd', size, s['fg']))
            x += measure('fd', ch, size)
    name_end = x
    for i, g in enumerate(glyphs):
        t.append(f'<g style="animation:rise .9s cubic-bezier(.16,1,.3,1) {i * 0.07:.2f}s both">{g}</g>')
    aka = 'ABDUR RAHMAAN'
    aw = measure('fm', aka, 12, 0.18)
    t.append(d.text(name_end - aw, base + 30, aka, 'fm', 12, s['fg'], ls=0.18))
    t.append(d.text(name_end - aw - 8, base + 31, 'aka', 'fs', 19, s['mute'], anchor='end'))

    t.append(d.text(56, 318, 'I build Discord bots, and turn data into dashboards.', 'fs', 30, s['fg']))
    t.append(d.text(56, 348, 'DATA SCIENCE & BUSINESS ANALYTICS  ·  PYTHON  ·  SQL  ·  BI', 'fm', 11, s['mute'], ls=0.16))

    # Status chip with the season's live mark.
    status = 'OPEN TO A FULL-TIME INTERNSHIP  ·  AVAILABLE NOW'
    cw = measure('fm', status, 11, 0.14) + 52
    t.append(f'<rect x="56" y="368" width="{f1(cw)}" height="32" rx="16" fill="{s["card"]}" stroke="{s["line"]}"/>')
    t.append(live_mark(d, 76, 384, 0.55))
    t.append(d.text(94, 388, status, 'fm', 11, s['fg'], ls=0.14))

    # The rotating badge from the portfolio hero.
    cx, cy, rr = 628, 128, 50
    d.defs.append(f'<path id="ring" d="M{cx} {cy}m-{rr} 0a{rr} {rr} 0 1 1 {2 * rr} 0a{rr} {rr} 0 1 1 -{2 * rr} 0"/>')
    ring_txt = 'SCROLL TO GAIN XP · SCROLL TO GAIN XP · '
    d.used.setdefault('fm', set()).update(ring_txt)
    t.append(f'<circle cx="{cx}" cy="{cy}" r="{rr + 16}" fill="{s["card"]}" stroke="{s["line"]}"/>')
    t.append(f'<g style="transform-origin:{cx}px {cy}px;animation:spin 22s linear infinite">'
             f'<text class="fm" font-size="10.4" letter-spacing="2.6" fill="{s["fg"]}">'
             f'<textPath href="#ring" xlink:href="#ring">{esc(ring_txt)}</textPath></text></g>')
    t.append(f'<path d="M{cx} {cy - 14}v28M{cx - 9} {cy + 5}l9 9 9-9" fill="none" stroke="{s["fg"]}" '
             f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>')

    # Season tag, top right.
    tag = f'SEASON · {s["label"].upper()}'
    tw = measure('fm', tag, 11, 0.16) + 46
    t.append(f'<rect x="{f1(W - 40 - tw)}" y="44" width="{f1(tw)}" height="30" rx="15" fill="{s["bg2"] if s["dark"] else s["bg3"]}" stroke="{s["line"]}"/>')
    t.append(live_mark(d, W - 40 - tw + 19, 59, 0.5))
    t.append(d.text(W - 40 - tw + 34, 63, tag, 'fm', 11, s['fg'], ls=0.16))

    b += t
    b.append(close)
    d.body = b
    return d.render('Taz3r, aka Abdur Rahmaan. I build Discord bots, and turn data into dashboards.')


def loadout_svg(s):
    gap, pw = 16, (W - 96 - 32) / 3
    ph, top = 214, 128
    strip_y = top + 2 * ph + gap + 26
    H = strip_y + 46 + 40
    d = Doc(W, H, s)
    open_, close = card_frame(d)
    b = [open_, weather(d, {'night': 60, 'fall': 18, 'winter': 46, 'spring': 22}[s['key']], 23)]
    total = sum(len(g[2]) for g in TOOLKIT) + len(SOFT)
    b.append(header(d, 84, 'Loadout', f'{total} tools equipped', meta='grouped by where each fits', chip='LVL MAX'))

    for i, (name, blurb, items) in enumerate(TOOLKIT):
        col, row = i % 3, i // 3
        x, y = 48 + col * (pw + gap), top + row * (ph + gap)
        g = [f'<rect x="{f1(x)}" y="{y}" width="{f1(pw)}" height="{ph}" rx="16" fill="{s["card"]}" stroke="{s["line"]}"/>']
        g.append(d.text(x + 22, y + 32, f'SLOT 0{i + 1}', 'fm', 10, s['mute'], ls=0.18))
        g.append(d.text(x + pw - 22, y + 32, f'{len(items)} TOOLS', 'fm', 10, s['mute'], ls=0.18, anchor='end'))
        g.append(d.text(x + 22, y + 66, name.upper(), 'fd', 25, s['fg'], ls=0.01))
        g.append(f'<rect x="{f1(x + 22)}" y="{y + 76}" width="30" height="3" rx="1.5" fill="{s["hi"]}"/>')
        g.append(d.text(x + 22, y + 102, blurb, 'fs', 16.5, s['mute']))
        cw = (pw - 44) / 2
        for j, it in enumerate(items):
            label, ic = it[0], it[1]
            ix, iy = x + 22 + (j % 2) * cw, y + 132 + (j // 2) * 28
            g.append(icon(ic, label, ix, iy - 13, 16, s['fg'], d))
            g.append(d.text(ix + 25, iy, label, 'fb', 15, s['fg']))
            if len(it) > 2:
                lw = measure('fb', label, 15)
                g.append(d.text(ix + 25 + lw + 7, iy - 1, it[2], 'fm', 8.5, s['hi'], ls=0.14))
        b.append(f'<g style="animation:rise .8s cubic-bezier(.16,1,.3,1) {0.1 + i * 0.08:.2f}s both">{"".join(g)}</g>')

    # Soft skills: a scrolling strip, from managing two esports teams.
    label = 'OFF THE KEYBOARD'
    lw = measure('fm', label, 11, 0.16) + 30
    seq = '   ·   '.join(x.upper() for x in SOFT) + '   ·   '
    seq_w = measure('fm', seq, 11, 0.2)
    sx = 48 + lw + 14
    d.defs.append(f'<clipPath id="strip"><rect x="{f1(sx)}" y="{strip_y}" width="{f1(W - 48 - sx - 8)}" height="46"/></clipPath>')
    d.css.append(f'@keyframes marquee{{to{{transform:translateX(-{seq_w:.1f}px)}}}}')
    b.append(f'<rect x="48" y="{strip_y}" width="{W - 96}" height="46" rx="12" fill="{s["card"]}" stroke="{s["line"]}"/>')
    b.append(f'<rect x="54" y="{strip_y + 6}" width="{f1(lw)}" height="34" rx="8" fill="{s["fill"]}"/>')
    b.append(d.text(54 + lw / 2 + 0.9, strip_y + 27, label, 'fm', 11, s['on_fill'], ls=0.16, anchor='middle'))
    run = d.text(sx, strip_y + 27, seq * 3, 'fm', 11, s['mute'], ls=0.2)
    b.append(f'<g clip-path="url(#strip)"><g style="animation:marquee 26s linear infinite">{run}</g></g>')
    b.append(d.text(W - 48, H - 18, 'SOFT SKILLS, FROM MANAGING TWO ESPORTS TEAMS', 'fm', 9.5, s['dim'], ls=0.18, anchor='end'))
    b.append(close)
    d.body = b
    names = ', '.join(it[0] for g in TOOLKIT for it in g[2])
    return d.render(f'Loadout: {names}. Soft skills: {", ".join(SOFT)}.')


def journey_svg(s, today):
    top, lane_h = 150, 70
    H = top + len(LANES) * lane_h + 84
    d = Doc(W, H, s)
    X0, X1 = 48, W - 48
    span = (JOURNEY_END - JOURNEY_START).days

    def xd(day):
        return X0 + (min(max(day, JOURNEY_START), JOURNEY_END) - JOURNEY_START).days / span * (X1 - X0)

    open_, close = card_frame(d)
    b = [open_, weather(d, {'night': 50, 'fall': 14, 'winter': 36, 'spring': 16}[s['key']], 37)]
    b.append(header(d, 84, 'Journey', 'one degree, and everything alongside it', meta=f'Jun 2024 — {today:%b %Y}'))

    # Year rules.
    for yr in (2025, 2026, 2027):
        x = xd(dt.date(yr, 1, 1))
        b.append(f'<path d="M{f1(x)} {top + 6}V{H - 58}" stroke="{s["line"]}" stroke-dasharray="2 5"/>')
        b.append(d.text(x, H - 44, str(yr), 'fm', 10, s['mute'], ls=0.16, anchor='middle'))
    b.append(d.text(X0, H - 44, 'JUN 2024', 'fm', 10, s['mute'], ls=0.16))
    b.append(d.text(X1, H - 44, 'JUN 2027', 'fm', 10, s['mute'], ls=0.16, anchor='end'))

    nx = xd(today)
    for i, ln in enumerate(LANES):
        y = top + 30 + i * lane_h
        x0 = xd(ln['start'])
        end = ln['end'] or today
        x1 = xd(min(end, today)) if ln.get('expected') else xd(end)
        lab_w = measure('fb', ln['org'], 17) + 12 + measure('fm', ln['role'].upper(), 9.5, 0.14)
        lx = min(x0, X1 - lab_w)
        g = [d.text(lx, y, ln['org'], 'fb', 17, s['fg'])]
        g.append(d.text(lx + measure('fb', ln['org'], 17) + 12, y - 1, ln['role'].upper(), 'fm', 9.5, s['mute'], ls=0.14))
        by = y + 12
        g.append(f'<rect x="{f1(X0)}" y="{by}" width="{X1 - X0}" height="10" rx="5" fill="{s["line"]}" opacity=".5"/>')
        bar = f'<rect x="{f1(x0)}" y="{by}" width="{f1(max(x1 - x0, 10))}" height="10" rx="5" fill="{s["hi"]}"/>'
        g.append(f'<g style="transform-origin:{f1(x0)}px {by}px;animation:grow 1.4s cubic-bezier(.16,1,.3,1) {0.2 + i * 0.15:.2f}s both">{bar}</g>')
        if ln.get('expected'):
            g.append(f'<path d="M{f1(x1 + 6)} {by + 5}H{f1(xd(ln["end"]) - 4)}" stroke="{s["hi"]}" stroke-width="2.5" '
                     f'stroke-dasharray="3 6" stroke-linecap="round" opacity=".7"/>')
            g.append(d.text(X1, by + 30, 'EXPECTED JUN 2027', 'fm', 9, s['mute'], ls=0.16, anchor='end'))
        if ln['end'] is None:
            g.append(live_mark(d, x1 + 2, by + 5, 0.5))
            g.append(d.text(x1 + 16, by + 9, 'PRESENT', 'fm', 9, s['fg'], ls=0.16))
        if ln.get('mark'):
            day, label = ln['mark']
            mx = xd(day)
            g.append(f'<g transform="translate({f1(mx)} {by + 5}) scale(.62)"><circle r="13" fill="{s["bg"]}" stroke="{s["hi"]}" stroke-width="2"/>'
                     f'<path d="{STAR}" transform="scale(.7)" fill="{s["hi"]}"/></g>')
            g.append(d.text(mx + 10, by + 30, label.upper(), 'fm', 9, s['fg'], ls=0.16, anchor='end'))
        b.append(''.join(g))

    # Now marker.
    b.append(f'<path d="M{f1(nx)} {top + 6}V{H - 58}" stroke="{s["accent"] if not s["dark"] else s["fg"]}" stroke-width="1.5" stroke-dasharray="4 4"/>')
    nl = f'NOW · {today:%b %Y}'.upper()
    nw = measure('fm', nl, 10, 0.16) + 40
    b.append(f'<rect x="{f1(nx - nw / 2)}" y="{top - 22}" width="{f1(nw)}" height="26" rx="13" fill="{s["fill"]}"/>')
    b.append(d.text(nx - nw / 2 + 30, top - 5, nl, 'fm', 10, s['on_fill'], ls=0.16))
    on = dict(s, accent=s['on_fill'])
    b.append(f'<g transform="translate({f1(nx - nw / 2 + 16)} {top - 9}) scale(.46)">{mark(s["key"], on) if s["key"] in ("night", "winter") else mark(s["key"], s)}</g>')

    b.append(d.text(X0, H - 18, "MLMS SEASON 1 CHAMPIONS, MAY 2026  ·  INDIA'S FIRST TEAM AT MLBB'S MID SEASON CUP",
                    'fm', 9.5, s['mute'], ls=0.16))
    b.append(close)
    d.body = b
    return d.render('Journey: BASc at HSNC University (2024–2027); Tartarus esports team manager (2025); '
                    'bot developer and moderator for the Moba Legends: 5v5 Discord (2025–present); '
                    'True Rippers esports manager (2026), MLMS Season 1 champions.')

# ---------------------------------------------------------------- terminal GIF


def terminal_gif(s, out):
    from PIL import Image, ImageDraw, ImageFont

    mono = ImageFont.truetype(str(mono_ttf_path()), 17)
    small = ImageFont.truetype(str(mono_ttf_path()), 12)
    fg, mute, hi = s['fg'], s['mute'], s['hi'] if s['dark'] else s['accent']
    win = s['bg2'] if s['dark'] else s['bg3']
    prompt = [('taz3r@mumbai', hi), (':~$ ', mute)]
    script = [
        ('whoami', [[('Abdur Rahmaan Reshamwala', fg), ('  ·  aka Taz3r  ·  Mumbai, India', mute)]]),
        ('cat now.txt', [
            [('final year, BASc Data Science & Business Analytics · HSNC University', fg)],
            [('building Discord bots for a ~2,500-member community', fg)],
            [('● ', hi), ('open to a full-time internship, available immediately', fg)]]),
        ('python -m loadout --top 8', [[('python  sql  discord.py  asyncio  sqlite  power-bi  tableau  linux', fg)]]),
    ]

    lh, padx, top = 28, 30, 66
    rows = sum(1 + len(o) for _, o in script)
    GW, GH = W, top + rows * lh + 26

    def frame(done, partial=None, cursor=True):
        im = Image.new('RGB', (GW, GH), win)
        dr = ImageDraw.Draw(im)
        dr.rectangle([0, 0, GW - 1, 40], fill=s['bg'] if s['dark'] else s['bg2'])
        dr.line([0, 40, GW, 40], fill=s['rule'])
        dr.rectangle([0, 0, GW - 1, GH - 1], outline=s['rule'])
        for k, c in enumerate([hi, s['dim'], s['rule'] if s['dark'] else s['dim']]):
            dr.ellipse([22 + k * 20, 15, 34 + k * 20, 27], fill=c)
        title = 'taz3r@mumbai: ~'
        dr.text(((GW - small.getlength(title)) / 2, 13), title, font=small, fill=mute)
        tag = f'SEASON · {s["label"].upper()}'
        dr.text((GW - 24 - small.getlength(tag), 13), tag, font=small, fill=mute)
        y = top - 8
        lines = list(done) + ([partial] if partial is not None else [])
        cx = None
        for segs in lines:
            x = padx
            for txt, col in segs:
                dr.text((x, y), txt, font=mono, fill=col)
                x += mono.getlength(txt)
            cx, cy = x, y
            y += lh
        if cursor and cx is not None:
            dr.rectangle([cx + 2, cy + 2, cx + 12, cy + 22], fill=hi)
        return im

    frames, durs = [], []

    def add(im, ms):
        frames.append(im)
        durs.append(ms)

    done = []
    add(frame(done, prompt), 600)
    for cmd, outputs in script:
        for i in range(2, len(cmd) + 2, 2):
            add(frame(done, prompt + [(cmd[:i], fg)]), 55)
        add(frame(done, prompt + [(cmd, fg)], cursor=False), 260)
        done.append(prompt + [(cmd, fg)])
        for o in outputs:
            done.append(o)
            add(frame(done, None, cursor=False), 140)
        for k in range(2):
            add(frame(done, prompt, cursor=True), 380)
            add(frame(done, prompt, cursor=False), 380)
    for k in range(4):
        add(frame(done, prompt, cursor=True), 500)
        add(frame(done, prompt, cursor=False), 500)

    pal = frames[-1].quantize(colors=64, method=Image.Quantize.MEDIANCUT)
    q = [f.quantize(palette=pal, dither=Image.Dither.NONE) for f in frames]
    q[0].save(out, save_all=True, append_images=q[1:], duration=durs, loop=0, optimize=True, disposal=1)

# ---------------------------------------------------------------- README


def badge(label, color, logo, ink, href, alt):
    return (f'<a href="{href}"><img src="https://img.shields.io/badge/{label}-{color.lstrip("#")}?style=for-the-badge'
            f'&logo={logo}&logoColor={ink.lstrip("#")}" alt="{alt}" /></a>')


def readme(s, has_gif):
    key = s['key']
    tools = ', '.join(it[0] for g in TOOLKIT for it in g[2])
    bg, ink = (s['bg2'], s['fg']) if s['dark'] else (s['fill'], s['on_fill'])
    gif = (f'\n<img src="art/terminal.gif" width="100%" alt="Terminal: whoami, what I am doing now, '
           f'and my top tools" />\n') if has_gif else ''
    return f"""<!-- Generated by scripts/build.py. Edit the script, not this file. -->
<div align="center">

<a href="{PORTFOLIO}"><img src="art/{key}/hero.svg" width="100%" alt="Taz3r, aka Abdur Rahmaan. I build Discord bots, and turn data into dashboards. Open to a full-time internship." /></a>
{gif}
<a href="{PORTFOLIO}"><img src="art/{key}/loadout.svg" width="100%" alt="Loadout: {tools}." /></a>

<a href="{PORTFOLIO}/journey"><img src="art/{key}/journey.svg" width="100%" alt="Journey: BASc at HSNC University 2024 to 2027, Tartarus 2025, Moba Legends: 5v5 bot developer since 2025, True Rippers 2026 and MLMS Season 1 champions." /></a>

{badge('Portfolio', bg, 'vercel', ink, PORTFOLIO, 'Portfolio')}
{badge('Discord-taz3rrr', '#5865F2', 'discord', '#ffffff', 'https://discord.com/users/1260149377461256243', 'Discord')}
{badge('LinkedIn', '#0A66C2', 'linkedin', '#ffffff', 'https://www.linkedin.com/in/abdur-rahmaan-reshamwala-780576363', 'LinkedIn')}
{badge('Instagram', '#E4405F', 'instagram', '#ffffff', 'https://www.instagram.com/taz3rrrr/', 'Instagram')}
{badge('Email', bg, 'gmail', ink, 'mailto:reshamwalaabdurrahmaan@gmail.com', 'Email')}

<sub>Discord is the fastest way to reach me. This profile repaints itself with the seasons, like my portfolio. Now showing: <b>{s['label']}</b>.</sub>

</div>
"""

# ---------------------------------------------------------------- main


def main(argv):
    want_gif = '--no-gif' not in argv
    args = [a for a in argv if not a.startswith('--')]
    choice = (args[0] if args else (SEASON_FILE.read_text().strip() if SEASON_FILE.exists() else 'auto')).lower()
    if choice != 'auto' and choice not in SEASONS:
        sys.exit(f'Unknown season "{choice}". Use auto, {", ".join(SEASONS)}.')
    SEASON_FILE.write_text(choice + '\n')
    today = dt.date.today().replace(day=1)  # month precision: rebuilds change once a month
    current = BY_MONTH[today.month - 1] if choice == 'auto' else choice

    for key, s in SEASONS.items():
        s = dict(s, key=key)
        folder = ART / key
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'hero.svg').write_text(hero_svg(s, today), encoding='utf8')
        (folder / 'loadout.svg').write_text(loadout_svg(s), encoding='utf8')
        (folder / 'journey.svg').write_text(journey_svg(s, today), encoding='utf8')

    s = dict(SEASONS[current], key=current)
    gif = ART / 'terminal.gif'
    if want_gif:
        terminal_gif(s, gif)
    (ROOT / 'README.md').write_text(readme(s, gif.exists()), encoding='utf8')
    print(f'Built all four seasons; README shows {s["label"]} ({choice}).')


if __name__ == '__main__':
    main(sys.argv[1:])
