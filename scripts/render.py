# spinning penguin + polar bear on an ice floe, fastfetch style -> assets/terminal.svg
# python render.py                      full build
# python render.py quick 12             every 12th frame only -> previews/quick.svg
# python render.py sheet NAME 0 24 ... just those frames as text in previews/NAME.html
import math, os, sys
from collections import Counter
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))

# ascii grid for the 3d scene
W, H = 74, 34
FS, LH = 11, 13           # scene font size and row pitch
CELL = LH / (FS * 0.6)    # cell height / width
SX, SY = 2, 3             # subsamples per cell
FPS, LOOP = 12, 8.0
NF = round(FPS * LOOP)

# camera + world
EL, DIST, TX, TY, HW = 19, 7.0, -0.05, 0.42, 0.87
HH = HW * H * CELL / W
YT, YW, YB = 0.0, -0.13, -0.6


def unit(v):
    v = np.asarray(v, float)
    return v / np.linalg.norm(v)


LIGHT = unit([-0.55, 0.75, 0.5])
FILL = unit([0.75, 0.15, 0.5])


def ln(x, y, z):
    return np.sqrt(x * x + y * y + z * z)


def sph(p, c, r):
    return ln(p[0] - c[0], p[1] - c[1], p[2] - c[2]) - r


def ell(p, c, r):
    x, y, z = (p[0] - c[0]) / r[0], (p[1] - c[1]) / r[1], (p[2] - c[2]) / r[2]
    k0 = ln(x, y, z)
    k1 = ln(x / r[0], y / r[1], z / r[2])
    return k0 * (k0 - 1) / np.maximum(k1, 1e-6)


def cap(p, a, b, r):
    pa = [p[i] - a[i] for i in range(3)]
    ba = [b[i] - a[i] for i in range(3)]
    h = np.clip(sum(pa[i] * ba[i] for i in range(3)) / sum(v * v for v in ba), 0, 1)
    return ln(*[pa[i] - ba[i] * h for i in range(3)]) - r


def smin(a, b, k):
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0, 1)
    return b + (a - b) * h - k * h * (1 - h)


def roty(p, a):
    c, s = math.cos(a), math.sin(a)
    return np.stack([c * p[0] + s * p[2], p[1], c * p[2] - s * p[0]])


def sstep(a, b, x):
    t = min(max((x - a) / (b - a), 0), 1)
    return t * t * (3 - 2 * t)


# ice floe: convex slab cut by random planes, slightly faceted top
rng = np.random.default_rng(3)
NV = 9
ang = (np.arange(NV) + rng.uniform(-0.3, 0.3, NV)) / NV * 2 * np.pi
rad = rng.uniform(0.66, 0.75, NV)
FV = np.stack([np.cos(ang) * rad, np.sin(ang) * rad], 1)
EDGES = []
for i in range(NV):
    a, b = FV[i], FV[(i + 1) % NV]
    n = np.array([b[1] - a[1], a[0] - b[0]])
    n /= np.linalg.norm(n)
    d = n @ a
    if d < 0:
        n, d = -n, -d
    EDGES.append((n[0], n[1], d))
TOPS = []
for k in range(6):
    b = rng.uniform(0, 2 * np.pi)
    s = math.tan(math.radians(rng.uniform(2, 7)))
    TOPS.append((s * math.cos(b), s * math.sin(b), rng.uniform(0, 0.03)))
SLOPE = math.radians(16)
CS, SN = math.cos(SLOPE), math.sin(SLOPE)


def floe(p):
    x, y, z = p
    d = YB - y
    for nx, nz, e in EDGES:
        d = np.maximum(d, (nx * x + nz * z - e) * CS + (y - YT) * SN)
    for tx, tz, o in TOPS:
        d = np.maximum(d, (y - YT - o + tx * x + tz * z) / math.sqrt(1 + tx * tx + tz * tz))
    return d


def floor_at(x, z):
    return min(YT + o - tx * x - tz * z for tx, tz, o in TOPS)


PPOS, PYAW = (-0.33, 0.1), 0.25
BPOS, BYAW = (0.31, -0.09), -0.2
PP = np.array([[PPOS[0]], [floor_at(*PPOS) - 0.01], [PPOS[1]]])
BP = np.array([[BPOS[0]], [floor_at(*BPOS) - 0.01], [BPOS[1]]])


def flipper(q, s, a):
    x, y, z = q[0] - s * 0.18, q[1] - 0.56, q[2]
    c, sn = math.cos(s * a), math.sin(s * a)
    return ell((c * x + sn * y, c * y - sn * x, z), (0, -0.16, 0), (0.035, 0.18, 0.075))


def penguin(q, wave):
    body = smin(ell(q, (0, 0.27, 0), (0.24, 0.27, 0.21)), ell(q, (0, 0.5, 0.005), (0.18, 0.22, 0.17)), 0.1)
    d = smin(body, sph(q, (0, 0.77, 0.01), 0.16), 0.04)
    d = smin(d, flipper(q, 1, 0.35), 0.03)
    d = smin(d, flipper(q, -1, wave), 0.03)
    beak = ell(q, (0, 0.725, 0.17), (0.07, 0.035, 0.08))
    feet = np.minimum(ell(q, (0.085, 0.025, 0.12), (0.07, 0.025, 0.09)),
                      ell(q, (-0.085, 0.025, 0.12), (0.07, 0.025, 0.09)))
    eyes = np.minimum(sph(q, (0.05, 0.795, 0.145), 0.022), sph(q, (-0.05, 0.795, 0.145), 0.022))
    return d, beak, feet, eyes


def bear(q):
    d = smin(ell(q, (0, 0.3, -0.04), (0.29, 0.29, 0.27)), ell(q, (0, 0.56, 0), (0.21, 0.22, 0.19)), 0.12)
    d = smin(d, sph(q, (0, 0.85, 0.05), 0.165), 0.06)
    d = smin(d, ell(q, (0, 0.8, 0.2), (0.085, 0.072, 0.11)), 0.04)
    for s in (-1, 1):
        d = smin(d, sph(q, (s * 0.125, 0.995, 0.02), 0.06), 0.025)
        d = smin(d, cap(q, (s * 0.17, 0.6, 0.05), (s * 0.14, 0.2, 0.2), 0.065), 0.05)
        d = smin(d, cap(q, (s * 0.17, 0.16, 0.05), (s * 0.21, 0.08, 0.3), 0.085), 0.06)
    nose = ell(q, (0, 0.835, 0.3), (0.036, 0.027, 0.03))
    eyes = np.minimum(sph(q, (0.07, 0.915, 0.175), 0.024), sph(q, (-0.07, 0.915, 0.175), 0.024))
    return d, nose, eyes


def wave(ph):
    # flipper goes up while the penguin faces us
    up = sstep(0.25, 0.8, math.cos(PYAW + 2 * math.pi * ph))
    return 0.35 + up * (1.9 + 0.35 * math.sin(2 * math.pi * 6 * ph))


# bounding spheres so far away points skip the character sdfs
PB = (PP[:, 0] + [0, 0.48, 0], 0.62)
BB = (BP[:, 0] + [0, 0.52, 0], 0.7)


def scene(p, ph, full=False):
    q = roty(p, -2 * math.pi * ph)
    qp = roty(q - PP, -PYAW)
    qb = roty(q - BP, -BYAW)
    if full:
        parts = [floe(q), *penguin(qp, wave(ph)), *bear(qb)]
        return np.minimum.reduce(parts), parts, qp
    d = floe(q)
    for (c, r), fn, lq in ((PB, lambda v: np.minimum.reduce(penguin(v, wave(ph))), qp),
                           (BB, lambda v: np.minimum.reduce(bear(v)), qb)):
        bd = sph(q, c, r)
        near = bd < 0.05
        if near.any():
            bd[near] = fn(lq[:, near])
        d = np.minimum(d, bd)
    return d


def camera():
    el = math.radians(EL)
    tgt = np.array([TX, TY, 0.0])
    pos = tgt + DIST * np.array([0, math.sin(el), math.cos(el)])
    fw = unit(tgt - pos)
    rt = unit(np.cross(fw, [0, 1, 0]))
    return pos, fw, rt, np.cross(rt, fw)


RO, FW, RT, UP = camera()


def rays(nx, ny):
    fx = ((np.arange(nx) + 0.5) / nx - 0.5) * 2 * HW
    fy = (0.5 - (np.arange(ny) + 0.5) / ny) * 2 * HH
    X, Y = np.meshgrid(fx, fy)
    rd = FW[:, None] * DIST + RT[:, None] * X.ravel() + UP[:, None] * Y.ravel()
    return rd / np.linalg.norm(rd, axis=0)


RD = rays(W * SX, H * SY)
RDC = rays(W, H)
BC, BR = np.array([0, 0.3, 0.0]), 1.35


def march(rd, ph):
    n = rd.shape[1]
    oc = RO - BC
    b = rd.T @ oc
    disc = b * b - (oc @ oc - BR * BR)
    alive = disc > 0
    sq = np.sqrt(np.maximum(disc, 0))
    t = np.maximum(-b - sq, 0)
    tfar = -b + sq
    hit = np.zeros(n, bool)
    for _ in range(140):
        idx = np.nonzero(alive)[0]
        if not len(idx):
            break
        d = scene(RO[:, None] + rd[:, idx] * t[idx], ph)
        h = d < 0.0015
        t[idx] += np.where(h, 0, d * 0.85)
        hit[idx[h]] = True
        alive[idx[h | (t[idx] > tfar[idx])]] = False
    return t, hit


def normal(p, ph):
    g = []
    for i in range(3):
        o = np.zeros((3, 1))
        o[i] = 0.002
        g.append(scene(p + o, ph) - scene(p - o, ph))
    g = np.array(g)
    return g / np.maximum(np.linalg.norm(g, axis=0), 1e-9)


def shadow(p, ph):
    res = np.ones(p.shape[1])
    t = np.full(p.shape[1], 0.03)
    for _ in range(22):
        d = scene(p + LIGHT[:, None] * t, ph)
        res = np.minimum(res, 7 * d / t)
        t += np.clip(d, 0.01, 0.12)
    return np.clip(res, 0, 1)


def occl(p, n, ph):
    occ, w = 0, 1.0
    for i in range(1, 5):
        h = 0.035 * i
        occ = occ + (h - scene(p + n * h, ph)) * w
        w *= 0.65
    return np.clip(1 - 2.2 * occ, 0.25, 1)


# materials
ICET, ICES, PDARK, PWHITE, ORANGE, EYE, BEAR, FEET = range(1, 9)
# per material: char ramp dark -> bright, light thresholds for colour, colour classes
MATS = {
    PDARK: ('=+*#%', (0.5,), 'ab'),
    PWHITE: ('*#%@', (0.5,), 'fg'),
    BEAR: ('+*#%@', (0.42,), 'fg'),
    ICET: (' .:', (0.85,), 'kd'),
    ICES: (':|', (2,), 'k'),
    ORANGE: ('+*#%', (0.45, 0.8), 'hij'),
    FEET: ('=*#', (0.45, 0.8), 'hij'),
}
OUTC = {PDARK: 'c', PWHITE: 'f', BEAR: 'g', ICET: 'd', ICES: 'd', ORANGE: 'i', FEET: 'i', EYE: 'a'}
COLORS = {
    'a': '#4a3478', 'b': '#6a4fa3', 'c': '#ab8fdc', 'd': '#9b5de5', 'e': '#c98bff',
    'f': '#dcc8ff', 'g': '#f8f2ff', 'h': '#b8622a', 'i': '#f0883e', 'j': '#ffb27a',
    'k': '#4f2a8a',
}
# shades close enough to swap when it saves a colour switch
SUB = 5   # cost of using a near shade, in bytes
NEAR = {'a': 'b', 'b': 'ac', 'c': 'b', 'd': 'ek', 'e': 'df', 'f': 'eg', 'g': 'f',
        'h': 'i', 'i': 'hj', 'j': 'i', 'k': 'd'}


def look(mat, l, drop=0):
    ramp, th, cl = MATS[mat]
    i = 0
    while i < len(th) and l >= th[i]:
        i += 1
    j = int(round(min(max(l, 0), 1) * (len(ramp) - 1)))
    return ramp[max(0, j - drop)], cl[i]


def shade_hits(p, ph, rd):
    n = normal(p, ph)
    _, parts, qp = scene(p, ph, True)
    m = np.argmin(np.array(parts), axis=0)
    mat = np.choose(m, [ICET, PDARK, ORANGE, FEET, EYE, BEAR, EYE, EYE])
    mat = np.where((mat == ICET) & (n[1] < 0.8), ICES, mat)
    x, y, z = qp
    white = ((z > 0.0) & ((x / 0.165) ** 2 + ((y - 0.34) / 0.35) ** 2 < 1)) | \
            ((z > 0.04) & (((np.abs(x) - 0.058) / 0.056) ** 2 + ((y - 0.79) / 0.066) ** 2 < 1))
    mat = np.where((mat == PDARK) & white, PWHITE, mat)
    dif = np.clip(LIGHT @ n, 0, 1) * shadow(p, ph)
    fil = np.clip(FILL @ n, 0, 1)
    amb = 0.5 + 0.5 * n[1]
    rim = (1 - np.clip(-(rd * n).sum(0), 0, 1)) ** 2.5
    lum = (0.25 * amb + 0.8 * dif + 0.15 * fil) * occl(p, n, ph) + 0.45 * rim
    own = np.where(m == 0, np.where(mat == ICET, 1, 2), np.where(m < 5, 3, 4))
    return mat, lum, own


def hash2(c, r):
    v = math.sin(c * 12.9898 + r * 78.233) * 43758.5453
    return v - math.floor(v)


def water(ph):
    tw = (YW - RO[1]) / RDC[1]
    x = RO[0] + RDC[0] * tw
    z = RO[2] + RDC[2] * tw
    r = np.hypot(x, z)
    a = -2 * math.pi * ph
    qx, qz = math.cos(a) * x + math.sin(a) * z, math.cos(a) * z - math.sin(a) * x
    de = np.max([nx * qx + nz * qz - e - (YT - YW) * math.tan(SLOPE) for nx, nz, e in EDGES], axis=0)
    # rings move out twice per loop
    ring = np.cos(2 * math.pi * (de * 6.0 - 2 * ph))
    out = []
    for k in range(H * W):
        rr, cc = divmod(k, W)
        h = hash2(cc, rr)
        fade = min(max((1.5 - r[k]) / 0.5, 0), 1)
        if de[k] < 0.05:
            out.append(('~', 'e'))
        elif ring[k] > 0.72 and h < fade:
            out.append(('~' if r[k] < 1.15 else '-', 'k'))
        elif ring[k] > 0.1 and h < 0.2 * fade:
            out.append(('.', 'k'))
        else:
            out.append((' ', None))
    return out


def edge_char(gx, gy, ice):
    a = math.degrees(math.atan2(gy, gx))
    if -15 <= a <= 15:
        return '|' if ice else '('
    if a >= 165 or a <= -165:
        return '|' if ice else ')'
    if 15 < a < 60 or -165 < a < -120:
        return '/'
    if 120 < a < 165 or -60 < a < -15:
        return '\\'
    return '_' if a > 0 else '-'


def grad(cv):
    p = np.pad(cv, 1)
    gx = 2 * (p[1:-1, 2:] - p[1:-1, :-2]) + p[:-2, 2:] - p[:-2, :-2] + p[2:, 2:] - p[2:, :-2]
    gy = 2 * (p[2:, 1:-1] - p[:-2, 1:-1]) + p[2:, :-2] - p[:-2, :-2] + p[2:, 2:] - p[:-2, 2:]
    return gx / 2, gy / (2 * CELL)


def cells(a):
    return a.reshape(H, SY, W, SX).transpose(0, 2, 1, 3).reshape(H, W, SX * SY)


def render(ph):
    S = SX * SY
    t, hit = march(RD, ph)
    tw = np.where(RD[1] < 0, (YW - RO[1]) / np.minimum(RD[1], -1e-9), np.inf)
    obj = hit & (t < tw)
    n = RD.shape[1]
    mat, lum, oid = np.zeros(n, int), np.zeros(n), np.zeros(n, int)
    idx = np.nonzero(obj)[0]
    if len(idx):
        p = RO[:, None] + RD[:, idx] * t[idx]
        mat[idx], lum[idx], oid[idx] = shade_hits(p, ph, RD[:, idx])
    # outline: subsamples on a silhouette (animal vs anything behind, ice vs empty, ice top vs side)
    G = oid.reshape(H * SY, W * SX)
    Z = np.where(obj, t, 99).reshape(H * SY, W * SX)
    E = np.zeros(G.shape, bool)
    for sh in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        nb, nz = np.roll(G, sh, (0, 1)), np.roll(Z, sh, (0, 1))
        E |= (G >= 3) & (nb != G) & (nz > Z + 0.08)
        if sh != (-1, 0):
            # no outline along the waterline, the foam does that
            E |= (G >= 1) & (G <= 2) & (nb == 0)
        E |= (G == 1) & (nb == 2)
    mat, lum, oid, E = cells(mat), cells(lum), cells(G), cells(E)
    cov = {k: (oid == k).mean(-1) for k in (1, 2, 3, 4)}
    gr = {3: grad(cov[3]), 4: grad(cov[4]), 1: grad(cov[1]), 0: grad(cov[1] + cov[2])}
    wat = water(ph)
    grid = []
    for r in range(H):
        row = []
        for c in range(W):
            ms, ls, os_, es = mat[r, c], lum[r, c], oid[r, c], E[r, c]
            nobj = (ms > 0).sum()
            if (ms == EYE).sum() >= 2:
                row.append((' ', None))
                continue
            if (ms == ORANGE).sum() >= 2:
                m = ORANGE
            elif (ms == FEET).sum() >= 3:
                m = FEET
            elif nobj >= 2 or es.any():
                vals, cnt = np.unique(ms[ms > 0], return_counts=True)
                m = vals[np.argmax(cnt)]
            else:
                row.append(wat[r * W + c])
                continue
            l = float(ls[ms == m].mean())
            if es.any():
                ow = np.bincount(os_[es], minlength=5)
                k = 4 if ow[4] else 3 if ow[3] else 1
                if k == 1 and ((os_ == 0).any() or not (os_ == 2).any()):
                    k = 0
                gx, gy = gr[k][0][r, c], gr[k][1][r, c]
                if abs(gx) + abs(gy) > 0.05:
                    ch = edge_char(gx, gy, k < 3)
                    if m == ORANGE:
                        row.append(('>' if ch == ')' else '<' if ch == '(' else look(m, l)[0], 'i'))
                        continue
                    em = ms[(os_ == k) if k else (os_ == 1) | (os_ == 2)]
                    em = em[em > 0]
                    vals, cnt = np.unique(em, return_counts=True)
                    row.append((ch, OUTC[vals[np.argmax(cnt)]] if len(vals) else 'e'))
                    continue
            ch, cl = look(m, l, (S - nobj + 1) // 2 if nobj < S else 0)
            row.append((ch, cl if ch != ' ' else None))
        grid.append(row)
    return grid


def smooth(row, cost):
    # pick colours per row so there are fewer switches, allowing a cell to take a near shade
    idx = [i for i, (ch, cl) in enumerate(row) if cl]
    if not idx:
        return row
    opts = [[row[i][1]] + list(NEAR.get(row[i][1], '')) for i in idx]
    best = {o: (cost(o) + (0 if o == opts[0][0] else SUB), [o]) for o in opts[0]}
    for j in range(1, len(idx)):
        nxt = {}
        for o in opts[j]:
            pen = 0 if o == opts[j][0] else SUB
            cands = [(v + (0 if p == o else cost(o)) + pen, path) for p, (v, path) in best.items()]
            v, path = min(cands, key=lambda x: x[0])
            nxt[o] = (v, path + [o])
        best = nxt
    path = min(best.values(), key=lambda x: x[0])[1]
    out = list(row)
    for i, o in zip(idx, path):
        out[i] = (row[i][0], o)
    return out


def esc(s):
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def sheet(name, frames):
    out = ['<html><body style="background:#120c1f;margin:8px;display:grid;'
           'grid-template-columns:repeat(2,auto);gap:6px 14px;justify-content:start">']
    for f in frames:
        g = [smooth(row, lambda o: 0 if o == 'e' else 20) for row in render(f / NF)]
        rows = []
        for row in g:
            rows.append(''.join(esc(ch) if cl is None else f'<span style="color:{COLORS[cl]}">{esc(ch)}</span>'
                                for ch, cl in row))
        out.append(f'<div><div style="color:#75659a;font:11px Consolas">frame {f}</div>'
                   f'<pre style="font:{FS}px/{LH}px Consolas;margin:0;border:1px solid #2e2245">'
                   + '\n'.join(rows) + '</pre></div>')
    out.append('</body></html>')
    with open(os.path.join(HERE, 'previews', name + '.html'), 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(out))


# svg layout
SW = 960
FONT = "ui-monospace,SFMono-Regular,Menlo,Consolas,'Liberation Mono','DejaVu Sans Mono',monospace"
SCX, SCY = 24, 76                     # scene origin
FH = H * LH + 24                      # frame pitch in the stack
GX, CW = 24, 7.8                      # grid for the prompt lines
PX = 545                              # info panel x
BY = SCY + H * LH + 32                # last prompt baseline
SH = BY + 24
HOST = 'ШАТУН'

# purple everything
BG, BAR, LINE = '#120c1f', '#1b1230', '#2e2245'

LOGO = [a + b + c + d + e for a, b, c, d, e in zip(
    ['██╗     ', '██║     ', '██║     ', '██║     ', '███████╗', '╚══════╝'],
    ['████████╗', '╚══██╔══╝', '   ██║   ', '   ██║   ', '   ██║   ', '   ╚═╝   '],
    ['██╗  ██╗', '██║  ██║', '███████║', '██╔══██║', '██║  ██║', '╚═╝  ╚═╝'],
    ['      ', '      ', '█████╗', '╚════╝', '      ', '      '],
    [' █████╗ ', '██╔══██╗', '███████║', '██╔══██║', '██║  ██║', '╚═╝  ╚═╝'])]
# double line pieces and the sides they connect to
BOX = {'═': 'lr', '║': 'ud', '╗': 'ld', '╔': 'rd', '╝': 'lu', '╚': 'ru'}

INFO = [('OS', 'Arch Linux x86_64 (btw)'),
        ('Host', 'a laptop that sounds like a jet engine'),
        ('Kernel', 'whatever pacman -Syu gave me today'),
        ('Uptime', 'since 2022, no reboots'),
        ('Packages', 'too many (pacman)'),
        ('Editor', 'vim'),
        ('Langs', 'Assembly, C, C++, PHP, Python, Rust, Java'),
        ('Pets', '1 penguin, 1 polar bear'),
        ('Bio', ';')]
SWATCH = ['#2e1a4f', '#4b2a80', '#6a3bb5', '#8a4fe0', '#a66cff', '#bf8fff', '#d8b8ff', '#f1e6ff']

# snow: x, start phase, speed (falls per loop), char
srng = np.random.default_rng(11)
FLAKES = [(srng.uniform(0, 1), srng.uniform(0, 1), int(srng.choice([1, 1, 2])), str(srng.choice(list(".*'+.*"))))
          for _ in range(20)]


def num(v):
    return f'{v:.2f}'.rstrip('0').rstrip('.')


def runs(row, tags):
    out, cur, buf, gap = [], None, '', ''

    def flush():
        if buf:
            o, c = tags[cur]
            out.append(o + buf + c)

    for ch, cl in row:
        if ch == ' ':
            gap += ' '
            continue
        if cl != cur:
            flush()
            out.append(gap)
            cur, buf = cl, esc(ch)
        else:
            buf += gap + esc(ch)
        gap = ''
    flush()
    return ''.join(out)


def gtext(col, y, segs):
    # every char gets its own x so the font width never shifts the typed text
    s = ''.join(t for t, _ in segs)
    xs = ' '.join(num(GX + (col + i) * CW) for i in range(len(s)))
    body = ''.join(esc(t) if c is None else f'<tspan class="{c}">{esc(t)}</tspan>' for t, c in segs)
    return f'<text x="{xs}" y="{y}">{body}</text>'


def prompt(cmd=''):
    return [('lth-a', 'ku'), ('@' + HOST, None), (' ~', 'cy'), (' $ ', 'dm')] + ([(cmd, 'wh')] if cmd else [])


def logo_svg(x0, y0, cw=8.4, ch=14.5):
    rects, segs, g = [], [], 1.7
    for r, line in enumerate(LOGO):
        c = 0
        while c < len(line):
            if line[c] == '█':
                e = c
                while e < len(line) and line[e] == '█':
                    e += 1
                rects.append(f'<rect x="{num(x0 + c * cw)}" y="{num(y0 + r * ch)}" '
                             f'width="{num((e - c) * cw)}" height="{num(ch + 0.5)}"/>')
                c = e
                continue
            k = BOX.get(line[c])
            if k:
                cx, cy = x0 + (c + 0.5) * cw, y0 + (r + 0.5) * ch
                lx, rx, uy, dy = x0 + c * cw, x0 + (c + 1) * cw, y0 + r * ch, y0 + (r + 1) * ch
                if k == 'lr':
                    segs += [(lx, cy - g, rx, cy - g), (lx, cy + g, rx, cy + g)]
                elif k == 'ud':
                    segs += [(cx - g, uy, cx - g, dy), (cx + g, uy, cx + g, dy)]
                else:
                    hx = lx if 'l' in k else rx
                    vy = uy if 'u' in k else dy
                    sx = 1 if 'l' in k else -1
                    sy = 1 if 'u' in k else -1
                    for o in (-1, 1):
                        segs.append((hx, cy + o * g * sy, cx + o * g * sx, cy + o * g * sy, cx + o * g * sx, vy))
            c += 1
    path = ''.join('M' + num(s[0]) + ' ' + num(s[1]) + ''.join(
        'L' + num(s[i]) + ' ' + num(s[i + 1]) for i in range(2, len(s), 2)) for s in segs)
    w, h = len(LOGO[0]) * cw, 6 * ch
    svg = (f'<clipPath id="lc">{"".join(rects)}</clipPath>'
           f'<linearGradient id="lg" gradientUnits="userSpaceOnUse" x1="{x0}" y1="0" x2="{num(x0 + w)}" y2="0">'
           f'<stop offset="0" stop-color="#7b2ff7"/><stop offset=".6" stop-color="#b56cff"/>'
           f'<stop offset="1" stop-color="#f0b8ff"/></linearGradient>'
           f'<linearGradient id="hl"><stop offset="0" stop-color="#fff" stop-opacity="0"/>'
           f'<stop offset=".5" stop-color="#fff" stop-opacity=".55"/><stop offset="1" stop-color="#fff" stop-opacity="0"/>'
           f'</linearGradient>'
           f'<path d="{path}" fill="none" stroke="url(#lg)" stroke-opacity=".55" stroke-width="1.2"/>'
           f'<g clip-path="url(#lc)"><rect x="{x0}" y="{y0}" width="{num(w)}" height="{num(h + 1)}" fill="url(#lg)"/>'
           f'<polygon class="sh" points="{num(x0 - 70)},{y0} {num(x0 - 20)},{y0} {num(x0 - 50)},{num(y0 + h + 1)} '
           f'{num(x0 - 100)},{num(y0 + h + 1)}" fill="url(#hl)"/></g>')
    return svg, w, h


def build(ids=range(NF), path=os.path.join(HERE, '..', 'assets', 'terminal.svg')):
    frames = []
    for f in ids:
        frames.append(render(f / NF))
        print(f'\rframe {f + 1}/{NF}', end='', file=sys.stderr)
    print(file=sys.stderr)

    # most used colour is the default fill, the next two get the short <a> and bare <tspan> wrappers
    def colour_tags(frs):
        cnt = Counter(cl for g in frs for row in g for ch, cl in row if cl)
        top = [k for k, _ in cnt.most_common()]
        tags = {k: (f'<tspan class="{k}">', '</tspan>') for k in top}
        tags[top[0]] = ('', '')
        if len(top) > 1:
            tags[top[1]] = ('<a>', '</a>')
        if len(top) > 2:
            tags[top[2]] = ('<tspan>', '</tspan>')
        return top, tags

    top, tags = colour_tags(frames)
    for _ in range(2):
        frames = [[smooth(row, lambda o: len(tags[o][0]) + len(tags[o][1])) for row in g] for g in frames]
        top, tags = colour_tags(frames)
    stack = []
    for k, g in enumerate(frames):
        rows = ''.join(f'<text y="{LH - 2 + r * LH}">{s}</text>'
                       for r, s in enumerate(runs(row, tags) for row in g) if s)
        stack.append(f'<g transform="translate({SCX} {SCY + k * FH})">{rows}</g>')

    nf = len(frames)
    css = [f'text{{font-family:{FONT};font-size:13px;fill:#e2d9f3;white-space:pre}}',
           f'.sc text{{font-size:{FS}px;fill:{COLORS[top[0]]}}}',
           f'.sc a{{fill:{COLORS[top[1]]}}}.sc tspan{{fill:{COLORS[top[2]]}}}',
           ''.join(f'.sc .{k}{{fill:{COLORS[k]}}}' for k in top[3:]),
           '.ku{fill:#b07cff;font-weight:700}.cy{fill:#e0a8ff}.dm{fill:#75659a}.wh{fill:#f8f2ff}'
           '.tt{fill:#9d8cbf}.cu{fill:#e2d9f3}',
           f'.fr{{animation:fr {num(LOOP)}s steps({nf}) infinite}}',
           f'@keyframes fr{{to{{transform:translateY(-{nf * FH}px)}}}}']

    # snow drifts down on its own, one row per step, same loop as the scene
    fall = (H + 2) * LH
    snow = []
    for i, (fx, f0, k, ch) in enumerate(FLAKES):
        dur = LOOP / k
        snow.append(f'<text class="s{k}" x="{num(SCX + fx * W * FS * 0.58)}" y="{SCY - LH}" '
                    f'style="animation-delay:-{num(f0 * dur)}s">{esc(ch)}</text>')
    for k in (1, 2):
        css.append(f'.s{k}{{fill:#e0ccff;animation:s{k} {num(LOOP / k)}s steps({H + 2}) infinite}}'
                   f'@keyframes s{k}{{to{{transform:translate(-{18 * k}px,{fall}px)}}}}')

    css += ['.bl{animation:bl 1s step-end infinite}@keyframes bl{0%{opacity:1}50%{opacity:0}100%{opacity:0}}',
            '.sh{animation:sh 7s ease-in-out infinite}'
            '@keyframes sh{0%{transform:translateX(0)}40%{transform:translateX(450px)}100%{transform:translateX(450px)}}']

    pre = len(''.join(t for t, _ in prompt()))
    bot = [gtext(0, BY, prompt()),
           f'<rect class="cu bl" x="{num(GX + pre * CW + 0.5)}" y="{BY - 11}" width="{num(CW - 1)}" height="14"/>']

    # info panel, vertically centred on the scene
    ph = 6 * 14.5 + 34 + 40 + len(INFO) * 20 + 10
    top_y = SCY + (H * LH - ph) // 2
    lg, lw, lh = logo_svg(PX, top_y)
    iy = top_y + lh + 34
    info = [f'<text x="{PX}" y="{iy}"><tspan class="ku">lth-a</tspan>@<tspan class="ku">{HOST}</tspan></text>',
            f'<text x="{PX}" y="{iy + 20}">{"-" * (6 + len(HOST))}</text>']
    for i, (k, v) in enumerate(INFO):
        info.append(f'<text x="{PX}" y="{iy + 40 + i * 20}"><tspan class="ku">{k}:</tspan> {esc(v)}</text>')
    sy = iy + 40 + len(INFO) * 20 - 6
    info += [f'<rect x="{num(PX + i * 3 * CW)}" y="{sy}" width="{num(3 * CW + 0.3)}" height="15" fill="{c}"/>'
             for i, c in enumerate(SWATCH)]

    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{SW}" height="{SH}" viewBox="0 0 {SW} {SH}" '
           f'xml:space="preserve" role="img" aria-label="lth-a running fastfetch on arch, a penguin and a polar bear on an ice floe">'
           f'<style>{"".join(css)}</style>'
           f'<rect x=".5" y=".5" width="{SW - 1}" height="{SH - 1}" rx="12" fill="{BG}"/>'
           f'<path d="M.5 34V12.5A12 12 0 0 1 12.5 .5H947.5A12 12 0 0 1 959.5 12.5V34Z" fill="{BAR}"/>'
           f'<path d="M.5 34.5H959.5" stroke="{LINE}"/>'
           f'<circle cx="20" cy="17" r="6" fill="#ff5f57"/><circle cx="40" cy="17" r="6" fill="#febc2e"/>'
           f'<circle cx="60" cy="17" r="6" fill="#28c840"/>'
           f'<text x="480" y="21.5" text-anchor="middle" class="tt">lth-a@{HOST}: ~</text>'
           f'<rect x=".5" y=".5" width="{SW - 1}" height="{SH - 1}" rx="12" fill="none" stroke="{LINE}"/>'
           + gtext(0, SCY - 12, prompt('fastfetch'))
           + f'<clipPath id="cs"><rect x="{SCX - 8}" y="{SCY - 2}" width="{PX - SCX - 4}" height="{H * LH + 4}"/></clipPath>'
           f'<g clip-path="url(#cs)"><g class="sc fr">{"".join(stack)}</g>{"".join(snow)}</g>'
           + lg + ''.join(info) + ''.join(bot) + '</svg>')
    with open(path, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(svg)
    print(len(svg.encode()), 'bytes', file=sys.stderr)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'sheet':
        sheet(sys.argv[2], [int(a) for a in sys.argv[3:]])
    elif len(sys.argv) > 1 and sys.argv[1] == 'quick':
        build(range(0, NF, int(sys.argv[2])), os.path.join(HERE, 'previews', 'quick.svg'))
    else:
        build()
