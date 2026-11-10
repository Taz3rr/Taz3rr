"""Builds the GitHub profile as one seasonal page (a single SVG) and README.md.

The look comes from the portfolio (github.com/Taz3rr/Portfolio): the same
fonts (Anybody, Instrument Serif, JetBrains Mono), the same four seasons
(Night, Fall, Winter, Spring) and the same procedural trees and weather.

The page, top to bottom: hero, loadout, journey, contributions, terminal.

    python scripts/build.py             # the season in season.txt ("auto" = by month)
    python scripts/build.py winter      # switch to a season (saved to season.txt)
    python scripts/build.py auto        # back to following the calendar
    python scripts/build.py --offline   # use the saved contributions instead of fetching

Needs: pip install fonttools brotli
"""

import base64
import datetime as dt
import html
import io
import json
import math
import re
import sys
import urllib.request
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

ROOT = Path(__file__).resolve().parent.parent
ART = ROOT / 'art'
FONTS = ROOT / 'fonts'
ICONS = ROOT / 'icons'
SEASON_FILE = ROOT / 'season.txt'
CONTRIB_FILE = ART / 'contributions.json'

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
# `ramp` colours the contribution graph, from a quiet day to a busy one.

SEASONS = {
    'night': dict(label='Night', dark=True,
                  bg='#04060d', bg2='#0a1330', bg3='#101d45', fg='#e9ecf4', mute='#8a95b3', dim='#4a5576',
                  line='rgba(233,236,244,0.12)', rule='#1a2444', accent='#ffffff', hi='#5b7bd9',
                  fill='#ffffff', on_fill='#0a1330', card='rgba(10,19,48,0.62)', branch='#0d1a3e',
                  cell='rgba(233,236,244,0.07)', ramp=['#1b3270', '#2f4ea8', '#5b7bd9', '#a9bcf2']),
    'fall': dict(label='Fall', dark=False,
                 bg='#f6e7ce', bg2='#f1dcb9', bg3='#fbf1df', fg='#3f2a1d', mute='#6b4423', dim='#a8835f',
                 line='rgba(63,42,29,0.18)', rule='#e3cdaa', accent='#c65d32', hi='#c65d32',
                 fill='#9e3f2d', on_fill='#f6e7ce', card='rgba(251,241,223,0.74)', branch='#3f2a1d',
                 cell='rgba(63,42,29,0.08)', ramp=['#ecc98f', '#e0b05a', '#d99a4e', '#c65d32']),
    'winter': dict(label='Winter', dark=False,
                   bg='#f7fbff', bg2='#e8f3fa', bg3='#ffffff', fg='#2b404c', mute='#4f6a7a', dim='#94adbc',
                   line='rgba(67,93,107,0.18)', rule='#d3e2ec', accent='#4d7590', hi='#4d7590',
                   fill='#435d6b', on_fill='#f7fbff', card='rgba(255,255,255,0.74)', branch='#708fa3',
                   cell='rgba(67,93,107,0.08)', ramp=['#c9dfec', '#a9c7d8', '#708fa3', '#4d7590']),
    'spring': dict(label='Spring', dark=False,
                   bg='#fff9ee', bg2='#f3f8ec', bg3='#ffffff', fg='#2e3b2b', mute='#56664f', dim='#a1b199',
                   line='rgba(46,59,43,0.15)', rule='#e1e8d8', accent='#c4547f', hi='#c4547f',
                   fill='#e89ab8', on_fill='#2e3b2b', card='rgba(255,255,255,0.72)', branch='#5f7d4f',
                   cell='rgba(46,59,43,0.07)', ramp=['#fbd9e6', '#f5c2d7', '#e89ab8', '#c4547f']),
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
    """The page. Collects the characters each font draws so it can embed just
    those glyphs, plus shared defs and CSS."""

    def __init__(self, s):
        self.s = s
        self.w, self.h = W, 0
        self.defs, self.css = [], []
        self.used = {}

    def text(self, x, y, txt, face, size, fill, ls=0.0, anchor='start', extra=''):
        self.used.setdefault(face, set()).update(txt)
        a = f'x="{f1(x)}" y="{f1(y)}" class="{face}" font-size="{f1(size)}" fill="{fill}"'
        if ls:
            a += f' letter-spacing="{ls * size:.2f}"'
        if anchor != 'start':
            a += f' text-anchor="{anchor}"'
        return f'<text {a}{extra}>{esc(txt)}</text>'

    def spans(self, x, y, segs, face, size):
        """One line of differently coloured runs: [(text, colour), ...]."""
        for t, _ in segs:
            self.used.setdefault(face, set()).update(t)
        runs = ''.join(f'<tspan fill="{c}">{esc(t)}</tspan>' for t, c in segs)
        return f'<text x="{f1(x)}" y="{f1(y)}" class="{face}" font-size="{f1(size)}" xml:space="preserve">{runs}</text>'

    def render(self, title, body):
        faces = ''.join(
            f"@font-face{{font-family:'{k}';src:url(data:font/woff2;base64,{woff2_base64(k, v)}) format('woff2')}}"
            f".{k}{{font-family:'{k}'}}"
            for k, v in sorted(self.used.items()))
        css = faces + ''.join(self.css)
        return (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
                f'viewBox="0 0 {self.w} {self.h}" width="{self.w}" height="{self.h}" role="img" aria-label="{esc(title)}">'
                f'<title>{esc(title)}</title><style>{css}</style><defs>{"".join(self.defs)}</defs>{body}</svg>')


BASE_CSS = (
    '.sw{transform-box:fill-box;transform-origin:center}'
    '@keyframes fall{from{transform:translateY(-40px)}to{transform:translateY(var(--h))}}'
    '@keyframes drift{from{transform:translate(0,-40px)}to{transform:translate(-260px,var(--h))}}'
    '@keyframes sway{0%,100%{transform:translateX(-12px) rotate(-28deg)}50%{transform:translateX(12px) rotate(28deg)}}'
    '@keyframes twinkle{0%,100%{opacity:.12}50%{opacity:1}}'
    '@keyframes pulse{0%,100%{transform:scale(1)}50%{transform:scale(1.22)}}'
    '@keyframes grow{from{transform:scaleX(0)}to{transform:scaleX(1)}}'
    '@keyframes rise{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:none}}'
    '@keyframes treesway{from{transform:rotate(-.7deg)}to{transform:rotate(.7deg)}}'
    '@keyframes blink{50%{opacity:0}}'
    # Without motion everything shows at rest, and the typing covers step aside.
    '@media (prefers-reduced-motion:reduce){*{animation:none!important}.cover{display:none}}'
)


def sky_layers(d):
    key, w, h = d.s['key'], d.w, d.h
    rect = f'<rect width="{w}" height="{h}" fill="url(#%s)"/>'
    if key == 'night':
        d.defs.append(
            '<radialGradient id="sk1" cx=".5" cy="-.04" r=".7" gradientTransform="translate(.5 0) scale(1 .35) translate(-.5 0)">'
            '<stop offset="0" stop-color="#0f2056"/><stop offset="1" stop-color="#0f2056" stop-opacity="0"/></radialGradient>'
            '<radialGradient id="sk2" cx="1" cy="1" r=".6"><stop offset="0" stop-color="#0d1c4a" stop-opacity=".8"/>'
            '<stop offset="1" stop-color="#0d1c4a" stop-opacity="0"/></radialGradient>')
        return f'<rect width="{w}" height="{h}" fill="#04060d"/>' + rect % 'sk1' + rect % 'sk2'
    if key == 'fall':
        d.defs.append(
            '<radialGradient id="sk1" cx=".5" cy=".45" r=".78"><stop offset="0" stop-color="#f6e7ce"/>'
            '<stop offset=".48" stop-color="#f6e7ce"/><stop offset=".68" stop-color="#efd2a4"/>'
            '<stop offset=".86" stop-color="#e2ad6b"/><stop offset="1" stop-color="#d99a4e"/></radialGradient>'
            '<radialGradient id="sk2" cx="0" cy="1" r=".5"><stop offset="0" stop-color="#3f2a1d" stop-opacity=".3"/>'
            '<stop offset="1" stop-color="#3f2a1d" stop-opacity="0"/></radialGradient>')
        return rect % 'sk1' + rect % 'sk2'
    if key == 'winter':
        d.defs.append(
            '<linearGradient id="sk1" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#a9c7d8"/>'
            '<stop offset=".05" stop-color="#c9dfec"/><stop offset=".14" stop-color="#e8f3fa"/>'
            '<stop offset=".25" stop-color="#f7fbff"/><stop offset=".88" stop-color="#f7fbff"/>'
            '<stop offset="1" stop-color="#e8f3fa"/></linearGradient>')
        return rect % 'sk1'
    d.defs.append(
        '<linearGradient id="sk1" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#d7eaf4"/>'
        '<stop offset=".12" stop-color="#fff9ee"/><stop offset=".85" stop-color="#fff9ee"/>'
        '<stop offset="1" stop-color="#ddefd5"/></linearGradient>'
        '<radialGradient id="sk2" cx=".88" cy="0" r=".5" gradientTransform="translate(.88 0) scale(1 .2) translate(-.88 0)">'
        '<stop offset="0" stop-color="#fff1a8" stop-opacity=".6"/><stop offset="1" stop-color="#fff1a8" stop-opacity="0"/></radialGradient>')
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
        return f'<g fill="none" stroke="{s["accent"]}" stroke-width="1.7" stroke-linecap="round">{arms}</g>'
    petals = ''.join(f'<ellipse cx="0" cy="-5.4" rx="4" ry="5.6" transform="rotate({a})"/>' for a in range(0, 360, 72))
    return f'<g fill="#e89ab8">{petals}</g><circle r="2.6" fill="#fff1a8" stroke="#c4547f" stroke-width=".6"/>'


def live_mark(d, x, y, scale=0.62, pulse=True):
    """A season mark at x,y that gently pulses."""
    anim = ' class="sw" style="animation:pulse 2.4s ease-in-out infinite"' if pulse else ''
    return (f'<g transform="translate({f1(x)} {f1(y)}) scale({scale})"><g{anim}>'
            f'{mark(d.s["key"], d.s)}</g></g>')


def weather(d, seed):
    """Falling leaves, snow, drifting petals or twinkling stars down the whole page."""
    key, w, h = d.s['key'], d.w, d.h
    r = rng(seed)
    per_1000 = {'night': 46, 'fall': 18, 'winter': 40, 'spring': 20}[key]
    n = int(per_1000 * h / 1000)
    out = []
    if key == 'night':
        still = []
        for i in range(n):
            x, y = r() * w, r() * h
            sc = 0.15 + r() * 0.3
            dur, delay = 2.5 + r() * 4, r() * 6
            if i % 3:
                still.append(xform(STAR, x, y, 0, sc))
                continue
            out.append(f'<g transform="translate({f1(x)} {f1(y)}) scale({sc:.2f})"><path class="sw" d="{STAR}" fill="#fff" '
                       f'style="animation:twinkle {dur:.1f}s ease-in-out -{delay:.1f}s infinite"/></g>')
        return f'<g><path d="{"".join(still)}" fill="#fff" opacity=".55"/>' + ''.join(out) + '</g>'
    d.defs.append(f'<path id="leaf" d="{LEAF}"/>')
    lo, hi_ = {'fall': (34, 60), 'winter': (22, 40), 'spring': (30, 48)}[key]   # px per second
    for i in range(n):
        x = r() * (w + (260 if key == 'spring' else 0))
        dur = (h + 40) / (lo + r() * (hi_ - lo))
        delay = r() * dur
        sdur, sdelay = 2.6 + r() * 2.4, r() * 4
        if key == 'fall':
            sc = 0.55 + r() * 0.5
            shape = f'<use href="#leaf" fill="{LEAF_COLORS[int(r() * 5)]}" transform="scale({sc:.2f})" opacity=".9"/>'
        elif key == 'winter':
            if r() < 0.7:
                shape = f'<circle r="{1.4 + r() * 2.2:.1f}" fill="#fff" stroke="#a9c7d8" stroke-width=".7"/>'
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


def xform(d, tx, ty, rot=0.0, sc=1.0):
    """Bakes translate(tx ty) rotate(rot) scale(sc) into an absolute M/L/C/Z path,
    so many shapes can share one <path> (far cheaper to redraw every frame)."""
    c, s_ = math.cos(math.radians(rot)) * sc, math.sin(math.radians(rot)) * sc
    out, nums = [], []
    for tk in re.findall(r'[A-Za-z]|-?\d*\.?\d+', d):
        if tk.isalpha():
            out.append(tk)
            continue
        nums.append(float(tk))
        if len(nums) == 2:
            x, y = nums
            nums = []
            out.append(f'{tx + x * c - y * s_:.1f} {ty + x * s_ + y * c:.1f}')
    return ' '.join(out)


def circle_d(cx, cy, r):
    return f'M{cx - r:.1f} {cy:.1f}a{r:.1f} {r:.1f} 0 1 0 {2 * r:.1f} 0a{r:.1f} {r:.1f} 0 1 0 {-2 * r:.1f} 0z'


def bloom_d(x, y, k):
    """Five petals (ellipses 3.4 x 5 around the centre) as one path."""
    out = []
    for a in range(0, 360, 72):
        ra = math.radians(a)
        ex, ey = x + 10 * k * math.sin(ra), y - 10 * k * math.cos(ra)
        rx, ry = 3.4 * k, 5 * k
        out.append(f'M{x:.1f} {y:.1f}A{rx:.1f} {ry:.1f} {a} 1 0 {ex:.1f} {ey:.1f}'
                   f'A{rx:.1f} {ry:.1f} {a} 1 0 {x:.1f} {y:.1f}z')
    return ''.join(out)


def tree_svg(d, seed, transform, origin):
    """The portfolio's tree for the season. Branches are merged by width and
    leaves by colour, so the whole tree is a handful of paths."""
    s, key = d.s, d.s['key']
    branches, tips, joints = make_tree(seed)
    r = rng(seed + 101)
    by_w = {}
    for path, wd, dpt in branches:
        by_w.setdefault(round(wd, 1), []).append(path)
    wood = ''.join(f'<path d="{"".join(ps)}" stroke-width="{w}"/>' for w, ps in sorted(by_w.items(), reverse=True))
    wood = f'<g fill="none" stroke="{s["branch"]}" stroke-linecap="round">{wood}</g>'
    extra = []
    if key == 'winter':
        caps = {}
        for p, wd, dpt in branches:
            if dpt >= 1:
                caps.setdefault(round(wd, 1), []).append(p)
        extra.append('<g fill="none" stroke="#fff" stroke-linecap="round" opacity=".95">' + ''.join(
            f'<path d="{"".join(ps)}" stroke-width="{w * 0.5:.1f}" transform="translate(0 {-w * 0.32:.1f})"/>'
            for w, ps in caps.items()) + '</g>')
        snow = ''.join(circle_d(x, y - 2, 4 + r() * 4) for x, y in tips if r() < 0.5)
        extra.append(f'<path d="{snow}" fill="#fff"/>')
    elif key == 'fall':
        by_c = {}
        for x, y in tips:
            for _ in range(3):
                c = LEAF_COLORS[int(r() * 5)]
                by_c.setdefault(c, []).append(
                    xform(LEAF, x + (r() - .5) * 34, y + (r() - .5) * 30, r() * 360, 1.2 + r() * 0.9))
        extra += [f'<path d="{"".join(ps)}" fill="{c}"/>' for c, ps in by_c.items()]
    elif key == 'spring':
        by_c = {}
        for x, y in tips:
            for _ in range(2):
                c = '#7fb878' if r() < 0.35 else '#a8d5a2'
                by_c.setdefault(c, []).append(xform('M0 0C6 -6 16 -5 20 0 16 5 6 6 0 0z', x + (r() - .5) * 24,
                                                    y + (r() - .5) * 22, r() * 360, 1.1 + r() * 0.6))
        extra += [f'<path d="{"".join(ps)}" fill="{c}"/>' for c, ps in by_c.items()]
        blooms, eyes = {}, []
        for x, y in joints:
            if r() < 0.4:
                c = '#f5c2d7' if r() < 0.6 else '#fff6fa'
                k = 1.3 + r() * 0.8
                blooms.setdefault(c, []).append(bloom_d(x, y, k))
                eyes.append(circle_d(x, y, 1.9 * k))
        extra += [f'<path d="{"".join(ps)}" fill="{c}"/>' for c, ps in blooms.items()]
        extra.append(f'<path d="{"".join(eyes)}" fill="#fff1a8"/>')
    ox, oy = origin
    return (f'<g transform="{transform}"><g style="transform-origin:{ox}px {oy}px;'
            f'animation:treesway 6s ease-in-out infinite alternate">{wood}{"".join(extra)}</g></g>')


def winter_ground(d, height=260):
    """Distant mountains and a snowbank along the bottom of the page."""
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
    return (f'<path d="{ridge(h - height + 90, 90, 120)}" fill="#c9dfec" opacity=".7"/>'
            f'<path d="{ridge(h - height + 150, 60, 90)}" fill="#a9c7d8" opacity=".45"/>'
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
        path = re.search(r' d="([^"]+)"', svg).group(1)
        g = f'<path d="{path}" fill="{color}"/>'
    else:
        d.used.setdefault('fm', set()).add(label[0].upper())
        g = (f'<rect x="1.5" y="1.5" width="21" height="21" rx="5" fill="none" stroke="{color}" stroke-width="2"/>'
             f'<text x="12" y="17" class="fm" font-size="13" fill="{color}" text-anchor="middle">{esc(label[0].upper())}</text>')
    return f'<g transform="translate({f1(x)} {f1(y)}) scale({sc:.4f})">{g}</g>'

# ---------------------------------------------------------------- sections
# Each section draws in its own coordinates (0,0 at its top-left) and returns
# (svg, height). The page stacks them with no gaps.


def header(d, y, title, sub, meta=None):
    """Section heading: big display title, a serif aside, and a mono note on the right."""
    s = d.s
    out = [d.text(48, y, title.upper(), 'fd', 46, s['fg'], ls=0.01)]
    tw = measure('fd', title.upper(), 46, 0.01)
    out.append(d.text(48 + tw + 16, y - 2, sub, 'fs', 21, s['mute']))
    if meta:
        out.append(d.text(d.w - 48, y - 10, meta.upper(), 'fm', 11, s['mute'], ls=0.16, anchor='end'))
    out.append(f'<path d="M48 {y + 22}H{d.w - 48}" stroke="{s["line"]}"/>')
    return ''.join(out)


def sec_hero(d, ctx):
    H = 430
    s, key = d.s, d.s['key']
    b = []
    if key == 'night':
        d.defs.append('<radialGradient id="glow" cx=".86" cy=".32" r=".42"><stop offset="0" stop-color="#5b7bd9" stop-opacity=".34"/>'
                      '<stop offset="1" stop-color="#5b7bd9" stop-opacity="0"/></radialGradient>')
        b.append(f'<rect width="{W}" height="{H}" fill="url(#glow)"/>')
    # The tree is ~840 units tall: at this scale the crown just fits, trunk set in from the edge.
    k = 0.52
    b.append(tree_svg(d, 7, f'translate({W - 70} {H - 1010 * k + 8:.0f}) scale(-{k} {k})', (0, 1010)))

    b.append(d.text(56, 64, 'MUMBAI, INDIA', 'fm', 11, s['fg'], ls=0.16))
    b.append(d.text(56 + measure('fm', 'MUMBAI, INDIA', 11, 0.16) + 14, 64, '19.07° N, 72.87° E', 'fm', 11, s['mute'], ls=0.16))

    # TAZ3R: display capitals with the 3 set in the serif italic, like the portfolio.
    size, x, base = 176, 50, 236
    for i, ch in enumerate('TAZ3R'):
        if ch.isdigit():
            ss = size * 1.12
            g = d.text(x + 4, base, ch, 'fs', ss, s['hi'] if s['dark'] else s['accent'])
            x += measure('fs', ch, ss) + 8
        else:
            g = d.text(x, base, ch, 'fd', size, s['fg'])
            x += measure('fd', ch, size)
        b.append(f'<g style="animation:rise .9s cubic-bezier(.16,1,.3,1) {i * 0.07:.2f}s both">{g}</g>')
    aka = 'ABDUR RAHMAAN'
    aw = measure('fm', aka, 12, 0.18)
    b.append(d.text(x - aw, base + 30, aka, 'fm', 12, s['fg'], ls=0.18))
    b.append(d.text(x - aw - 8, base + 31, 'aka', 'fs', 19, s['mute'], anchor='end'))

    b.append(d.text(56, 318, 'I build Discord bots, and turn data into dashboards.', 'fs', 30, s['fg']))
    b.append(d.text(56, 348, 'DATA SCIENCE & BUSINESS ANALYTICS  ·  PYTHON  ·  SQL  ·  BI', 'fm', 11, s['mute'], ls=0.16))

    status = 'OPEN TO A JOB OR INTERNSHIP  ·  REMOTE  ·  AVAILABLE NOW'
    cw = measure('fm', status, 11, 0.14) + 52
    b.append(f'<rect x="56" y="368" width="{f1(cw)}" height="32" rx="16" fill="{s["card"]}" stroke="{s["line"]}"/>')
    b.append(live_mark(d, 76, 384, 0.55))
    b.append(d.text(94, 388, status, 'fm', 11, s['fg'], ls=0.14))

    tag = f'SEASON · {s["label"].upper()}'
    tw = measure('fm', tag, 11, 0.16) + 46
    b.append(f'<rect x="{f1(W - 40 - tw)}" y="44" width="{f1(tw)}" height="30" rx="15" '
             f'fill="{s["bg2"] if s["dark"] else s["bg3"]}" stroke="{s["line"]}"/>')
    b.append(live_mark(d, W - 40 - tw + 19, 59, 0.5))
    b.append(d.text(W - 40 - tw + 34, 63, tag, 'fm', 11, s['fg'], ls=0.16))
    return ''.join(b), H


def sec_loadout(d, ctx):
    s = d.s
    gap, pw = 16, (W - 96 - 32) / 3
    ph, top = 214, 128
    strip_y = top + 2 * ph + gap + 26
    H = strip_y + 46 + 44
    total = sum(len(g[2]) for g in TOOLKIT) + len(SOFT)
    b = [header(d, 84, 'Loadout', f'{total} tools equipped', meta='grouped by where each fits')]

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
    b.append(d.text(W - 48, H - 20, 'SOFT SKILLS, FROM MANAGING TWO ESPORTS TEAMS', 'fm', 9.5, s['dim'], ls=0.18, anchor='end'))
    return ''.join(b), H


def sec_journey(d, ctx):
    s, today = d.s, ctx['month']
    top, lane_h = 150, 70
    H = top + len(LANES) * lane_h + 84
    X0, X1 = 48, W - 48
    span = (JOURNEY_END - JOURNEY_START).days

    def xd(day):
        return X0 + (min(max(day, JOURNEY_START), JOURNEY_END) - JOURNEY_START).days / span * (X1 - X0)

    b = [header(d, 84, 'Journey', 'one degree, and everything alongside it', meta=f'Jun 2024 — {today:%b %Y}')]
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

    b.append(f'<path d="M{f1(nx)} {top + 6}V{H - 58}" stroke="{s["fg"] if s["dark"] else s["accent"]}" stroke-width="1.5" stroke-dasharray="4 4"/>')
    nl = f'NOW · {today:%b %Y}'.upper()
    nw = measure('fm', nl, 10, 0.16) + 40
    b.append(f'<rect x="{f1(nx - nw / 2)}" y="{top - 22}" width="{f1(nw)}" height="26" rx="13" fill="{s["fill"]}"/>')
    b.append(d.text(nx - nw / 2 + 30, top - 5, nl, 'fm', 10, s['on_fill'], ls=0.16))
    on = dict(s, accent=s['on_fill'])
    b.append(f'<g transform="translate({f1(nx - nw / 2 + 16)} {top - 9}) scale(.46)">'
             f'{mark(s["key"], on if s["key"] in ("night", "winter") else s)}</g>')
    b.append(d.text(X0, H - 18, "MLMS SEASON 1 CHAMPIONS, MAY 2026  ·  INDIA'S FIRST TEAM AT MLBB'S MID SEASON CUP",
                    'fm', 9.5, s['mute'], ls=0.16))
    return ''.join(b), H


def sec_contributions(d, ctx):
    """The last year of GitHub contributions, painted in the season: the busiest
    days become the season's mark (a star, a leaf, a snowflake, a blossom)."""
    s, data = d.s, ctx['contrib']
    if not data:
        H = 200
        return header(d, 84, 'Contributions', 'the graph is on its way') + d.text(
            48, 150, 'COULD NOT READ THE CONTRIBUTION GRAPH ON THIS BUILD.', 'fm', 11, s['mute'], ls=0.16), H

    days = data['days']
    dates = [dt.date.fromisoformat(x['date']) for x in days]
    start = dates[0] - dt.timedelta(days=(dates[0].weekday() + 1) % 7)   # the Sunday the graph starts on
    cols = (dates[-1] - start).days // 7 + 1
    gx, gy = 48 + 36, 158
    pitch = min(16.4, (W - 48 - gx) / cols)
    cell = pitch * 0.8

    total = data['total']
    first, last = dates[0], dates[-1]
    b = [header(d, 84, 'Contributions', f'{total:,} in the last year',
                meta=f'{first:%b %Y} — {last:%b %Y}')]

    for row, name in ((1, 'MON'), (3, 'WED'), (5, 'FRI')):
        b.append(d.text(48, gy + row * pitch + cell - 2, name, 'fm', 9, s['mute'], ls=0.12))

    last_label = -9
    for c in range(cols):
        sat = start + dt.timedelta(days=c * 7 + 6)
        prev = start + dt.timedelta(days=(c - 1) * 7 + 6)
        if (c == 0 or sat.month != prev.month) and c - last_label >= 3 and c < cols - 1:
            b.append(d.text(gx + c * pitch, gy - 12, f'{sat:%b}'.upper(), 'fm', 9.5, s['mute'], ls=0.12))
            last_label = c

    def rrect(x, y, sz, rad=3):
        e = sz - 2 * rad
        return (f'M{x + rad:.1f} {y:.1f}h{e:.1f}a{rad} {rad} 0 0 1 {rad} {rad}v{e:.1f}a{rad} {rad} 0 0 1 {-rad} {rad}'
                f'h{-e:.1f}a{rad} {rad} 0 0 1 {-rad} {-rad}v{-e:.1f}a{rad} {rad} 0 0 1 {rad} {-rad}z')

    by_fill, peaks = {}, []
    for x, day in zip(days, dates):
        c, r = (day - start).days // 7, (day.weekday() + 1) % 7
        cx, cy = gx + c * pitch, gy + r * pitch
        lvl = x['level']
        if lvl >= 4:
            peaks.append(f'<g transform="translate({f1(cx + cell / 2)} {f1(cy + cell / 2)}) scale({cell / 20:.3f})">'
                         f'{mark(s["key"], dict(s, accent=s["ramp"][3] if s["key"] != "night" else "#ffffff"))}</g>')
        else:
            by_fill.setdefault(s['cell'] if lvl == 0 else s['ramp'][lvl - 1], []).append(rrect(cx, cy, cell))
    cells = ''.join(f'<path d="{"".join(ps)}" fill="{c}"/>' for c, ps in by_fill.items()) + ''.join(peaks)
    b.append(f'<g style="animation:rise .9s cubic-bezier(.16,1,.3,1) .2s both">{cells}</g>')

    # Streaks and the busiest day.
    longest = run = 0
    for x in days:
        run = run + 1 if x['count'] > 0 else 0
        longest = max(longest, run)
    tail = days[::-1]
    if tail and tail[0]['count'] == 0:
        tail = tail[1:]   # today may not have one yet
    current = 0
    for x in tail:
        if x['count'] == 0:
            break
        current += 1
    best = max(days, key=lambda x: x['count'])
    bd = dt.date.fromisoformat(best['date'])

    sy = gy + 7 * pitch + 46
    stats = [('TOTAL', f'{total:,}', 'IN A YEAR'),
             ('BEST DAY', str(best['count']), f'{bd:%b} {bd.day}'.upper() if best['count'] else '—'),
             ('LONGEST STREAK', str(longest), 'DAYS' if longest != 1 else 'DAY'),
             ('CURRENT STREAK', str(current), 'DAYS' if current != 1 else 'DAY')]
    for i, (k, v, unit) in enumerate(stats):
        x = 48 + i * 168
        b.append(d.text(x, sy, k, 'fm', 9.5, s['mute'], ls=0.16))
        b.append(d.text(x, sy + 38, v, 'fd', 36, s['fg']))
        b.append(d.text(x + measure('fd', v, 36) + 8, sy + 38, unit, 'fm', 9.5, s['mute'], ls=0.14))

    # Legend: less ... more, ending on the season mark.
    lx = W - 48
    sw = 13
    items = [s['cell']] + s['ramp'][:3]
    b.append(d.text(lx, sy + 34, 'MORE', 'fm', 9, s['mute'], ls=0.14, anchor='end'))
    mx = lx - measure('fm', 'MORE', 9, 0.14) - 16
    b.append(f'<g transform="translate({f1(mx)} {sy + 30}) scale({sw / 20:.3f})">'
             f'{mark(s["key"], dict(s, accent=s["ramp"][3] if s["key"] != "night" else "#ffffff"))}</g>')
    x = mx - 12
    for c in reversed(items):
        x -= sw + 4
        b.append(f'<rect x="{f1(x)}" y="{sy + 24}" width="{sw}" height="{sw}" rx="3" fill="{c}"/>')
    b.append(d.text(x - 8, sy + 34, 'LESS', 'fm', 9, s['mute'], ls=0.14, anchor='end'))
    H = sy + 76
    return ''.join(b), H


def sec_terminal(d, ctx):
    """A terminal that types out who I am, now and what I use. Pure SVG, so it
    takes the season like the rest of the page."""
    s = d.s
    fg, mute = s['fg'], s['mute']
    hi = s['hi'] if s['dark'] else s['accent']
    win = s['bg2'] if s['dark'] else s['bg3']
    size, lh = 16.5, 28
    adv = measure('fm', 'm', size)
    prompt = [('taz3r@mumbai', hi), (':~$ ', mute)]
    pw = adv * len('taz3r@mumbai:~$ ')
    script = [
        ('whoami', [[('Abdur Rahmaan Reshamwala', fg), ('  ·  aka Taz3r  ·  Mumbai, India', mute)]]),
        ('cat now.txt', [
            [('final year, BASc Data Science & Business Analytics · HSNC University', fg)],
            [('building Discord bots for a ~2,500-member community', fg)],
            [('● ', hi), ('open to a job or internship (remote), available immediately', fg)]]),
        ('python -m loadout --top 8', [[('python  sql  discord.py  asyncio  sqlite  power-bi  tableau  linux', fg)]]),
    ]
    rows = sum(1 + len(o) for _, o in script) + 1
    wx, wy, ww = 48, 36, W - 96
    wh = 40 + 22 + rows * lh + 14
    H = wy + wh + 44

    # Timeline (seconds) for one loop.
    t, events = 0.5, []
    for cmd, outs in script:
        p_t = t
        t0 = t + 0.45
        t1 = t0 + len(cmd) * 0.06
        o_t = t1 + 0.35
        events.append((cmd, outs, p_t, t0, t1, o_t))
        t = o_t + len(outs) * 0.14 + 0.8
    final_t = t
    T = final_t + 5.0

    def pc(x):
        return f'{x / T * 100:.2f}'

    def appear(name, at):
        d.css.append(f'@keyframes {name}{{0%,{pc(at)}%{{opacity:0}}{pc(at + 0.02)}%,98%{{opacity:1}}100%{{opacity:0}}}}')
        return f'style="animation:{name} {T:.2f}s linear infinite both"'

    b = [f'<rect x="{wx}" y="{wy}" width="{ww}" height="{wh}" rx="14" fill="{win}" stroke="{s["rule"]}"/>',
         f'<path d="M{wx} {wy + 40}H{wx + ww}" stroke="{s["rule"]}"/>']
    for k, c in enumerate([hi, s['dim'], s['dim']]):
        b.append(f'<circle cx="{wx + 24 + k * 20}" cy="{wy + 20}" r="6" fill="{c}"/>')
    b.append(d.text(W / 2, wy + 25, 'taz3r@mumbai: ~', 'fm', 11.5, mute, anchor='middle'))
    b.append(d.text(wx + ww - 22, wy + 25, f'SEASON · {s["label"].upper()}', 'fm', 10.5, mute, ls=0.1, anchor='end'))

    tx = wx + 26
    y = wy + 40 + 34
    n = 0
    for cmd, outs, p_t, t0, t1, o_t in events:
        n += 1
        cmd_w = adv * len(cmd)
        line = d.spans(tx, y, prompt + [(cmd, fg)], 'fm', size)
        # The cover hides the command and steps right one character at a time; the cursor rides its edge.
        name = f'ty{n}'
        d.css.append(f'@keyframes {name}{{0%,{pc(t0)}%{{transform:translateX(0);animation-timing-function:steps({len(cmd)},end)}}'
                     f'{pc(t1)}%,98%{{transform:translateX({cmd_w:.1f}px)}}100%{{transform:translateX(0)}}}}')
        d.css.append(f'@keyframes cu{n}{{0%,{pc(o_t)}%{{opacity:1}}{pc(o_t + 0.02)}%,100%{{opacity:0}}}}')
        cover = (f'<g class="cover" style="animation:{name} {T:.2f}s infinite both">'
                 f'<rect x="{f1(tx + pw)}" y="{y - 19}" width="{f1(cmd_w + 30)}" height="26" fill="{win}"/>'
                 f'<rect x="{f1(tx + pw + 1)}" y="{y - 16}" width="{f1(adv * 0.9)}" height="21" fill="{hi}" '
                 f'style="animation:cu{n} {T:.2f}s linear infinite both"/></g>')
        b.append(f'<g {appear(f"pl{n}", p_t)}>{line}{cover}</g>')
        y += lh
        for j, o in enumerate(outs):
            b.append(f'<g {appear(f"o{n}x{j}", o_t + j * 0.14)}>{d.spans(tx, y, o, "fm", size)}</g>')
            y += lh
    b.append(f'<g {appear("plast", final_t)}>{d.spans(tx, y, prompt, "fm", size)}'
             f'<rect x="{f1(tx + pw + 1)}" y="{y - 16}" width="{f1(adv * 0.9)}" height="21" fill="{hi}" '
             f'style="animation:blink 1.1s steps(1) infinite"/></g>')
    return ''.join(b), H

# ---------------------------------------------------------------- the page


SECTIONS = [sec_hero, sec_loadout, sec_journey, sec_contributions, sec_terminal]


def page_svg(s, ctx):
    d = Doc(s)
    parts, seams, y = [], [], 0
    for fn in SECTIONS:
        content, h = fn(d, ctx)
        parts.append(f'<svg x="0" y="{f1(y)}" width="{W}" height="{f1(h)}" viewBox="0 0 {W} {f1(h)}">{content}</svg>')
        y += h
        seams.append(y)
    d.h = H = round(y)
    # One page, no gaps: a hairline marks where each section ends.
    parts += [f'<path d="M48 {f1(sy)}H{W - 48}" stroke="{s["line"]}"/>' for sy in seams[:-1]]
    d.css.append(BASE_CSS + f'svg{{--h:{H + 40}px}}')
    d.defs.append(f'<clipPath id="page"><rect width="{W}" height="{H}" rx="22"/></clipPath>')
    # No grain filter: as an <img> the whole page re-renders every animation frame,
    # and a noise filter that size makes the animations crawl.
    body = [f'<g clip-path="url(#page)">', sky_layers(d)]
    if s['key'] == 'winter':
        body.append(winter_ground(d))
    body.append(weather(d, 11))
    body += parts
    body.append('</g>')
    body.append(f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="22" fill="none" stroke="{s["line"]}"/>')
    title = ('Taz3r, aka Abdur Rahmaan Reshamwala: I build Discord bots, and turn data into dashboards. '
             'Loadout, journey, contributions and a terminal, in the ' + s['label'] + ' season.')
    return d.render(title, ''.join(body))

# ---------------------------------------------------------------- contributions data


def fetch_contributions():
    """Reads the public contribution graph. Private work only shows if the profile
    setting 'Private contributions' is on."""
    req = urllib.request.Request(f'https://github.com/users/{USER}/contributions',
                                 headers={'User-Agent': 'taz3r-profile-build'})
    page = urllib.request.urlopen(req, timeout=30).read().decode('utf8', 'replace')
    counts = {}
    for m in re.finditer(r'<tool-tip\b[^>]*\bfor="([^"]+)"[^>]*>([^<]*)</tool-tip>', page):
        n = re.match(r'\s*([\d,]+) contributions?', m.group(2))
        counts[m.group(1)] = int(n.group(1).replace(',', '')) if n else 0
    days = []
    for m in re.finditer(r'<td\b[^>]*\bdata-date="([\d-]+)"[^>]*>', page):
        tag = m.group(0)
        tid = re.search(r'\bid="([^"]+)"', tag)
        lvl = re.search(r'\bdata-level="(\d)"', tag)
        days.append({'date': m.group(1), 'level': int(lvl.group(1)) if lvl else 0,
                     'count': counts.get(tid.group(1), 0) if tid else 0})
    if len(days) < 300:
        raise ValueError(f'expected a year of days, found {len(days)}')
    days.sort(key=lambda x: x['date'])
    tot = re.search(r'([\d,]+)\s+contributions?\s+in the last year', page)
    total = int(tot.group(1).replace(',', '')) if tot else sum(x['count'] for x in days)
    return {'total': total, 'days': days}


def contributions(offline):
    if not offline:
        try:
            data = fetch_contributions()
            ART.mkdir(exist_ok=True)
            CONTRIB_FILE.write_text(json.dumps(data, separators=(',', ':')) + '\n')
            return data
        except Exception as e:
            print(f'warning: could not read contributions ({e}); using the saved ones')
    if CONTRIB_FILE.exists():
        return json.loads(CONTRIB_FILE.read_text())
    return None

# ---------------------------------------------------------------- README


def badge(label, color, logo, ink, href, alt):
    return (f'<a href="{href}"><img src="https://img.shields.io/badge/{label}-{color.lstrip("#")}?style=for-the-badge'
            f'&logo={logo}&logoColor={ink.lstrip("#")}" alt="{alt}" /></a>')


def readme(s):
    key = s['key']
    tools = ', '.join(it[0] for g in TOOLKIT for it in g[2])
    bg, ink = (s['bg2'], s['fg']) if s['dark'] else (s['fill'], s['on_fill'])
    alt = (f'Taz3r, aka Abdur Rahmaan Reshamwala, Mumbai. I build Discord bots, and turn data into dashboards. '
           f'Open to a remote job or internship. Loadout: {tools}. Journey: BASc at HSNC University 2024 to 2027, '
           f'Tartarus 2025, Moba Legends: 5v5 bot developer since 2025, True Rippers 2026 and MLMS Season 1 champions. '
           f'Plus my GitHub contributions for the last year.')
    return f"""<!-- Generated by scripts/build.py. Edit the script, not this file. -->
<div align="center">

<a href="{PORTFOLIO}"><img src="art/{key}/profile.svg" width="100%" alt="{alt}" /></a>

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
    offline = '--offline' in argv
    args = [a for a in argv if not a.startswith('--')]
    choice = (args[0] if args else (SEASON_FILE.read_text().strip() if SEASON_FILE.exists() else 'auto')).lower()
    if choice != 'auto' and choice not in SEASONS:
        sys.exit(f'Unknown season "{choice}". Use auto, {", ".join(SEASONS)}.')
    SEASON_FILE.write_text(choice + '\n')
    today = dt.date.today()
    current = BY_MONTH[today.month - 1] if choice == 'auto' else choice
    # The journey's "now" moves by month; the contributions change daily.
    ctx = {'month': today.replace(day=1), 'contrib': contributions(offline)}

    for key, s in SEASONS.items():
        s = dict(s, key=key)
        folder = ART / key
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'profile.svg').write_text(page_svg(s, ctx), encoding='utf8')

    s = dict(SEASONS[current], key=current)
    (ROOT / 'README.md').write_text(readme(s), encoding='utf8')
    print(f'Built all four seasons; README shows {s["label"]} ({choice}).')


if __name__ == '__main__':
    main(sys.argv[1:])
