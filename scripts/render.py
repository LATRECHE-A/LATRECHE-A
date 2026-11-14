# penguin + polar bear on a spinning ice floe under a starry sky, fastfetch style -> assets/terminal.svg
# python render.py                      full build
# python render.py quick 12             every 12th frame only -> previews/quick.svg
# python render.py sheet NAME 0 24 ... just those frames as text in previews/NAME.html
import math, os, sys
from collections import Counter
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))

# ascii grid for the 3d scene
W, H = 90, 58
FS, LH = 9, 10            # scene font size and row pitch
CELL = LH / (FS * 0.6)    # cell height / width
SX, SY = 2, 3             # subsamples per cell
FPS, LOOP = 10, 8.0
NF = round(FPS * LOOP)

# camera + world
EL, DIST, TX, TY, HW = 15, 7.0, 0.0, 0.37, 0.86
HH = HW * H * CELL / W
YT, YW, YB = 0.0, -0.1, -0.6


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


def rotx(p, a):
    c, s = math.cos(a), math.sin(a)
    return np.stack([p[0], c * p[1] - s * p[2], s * p[1] + c * p[2]])


def rotz(p, a):
    c, s = math.cos(a), math.sin(a)
    return np.stack([c * p[0] - s * p[1], s * p[0] + c * p[1], p[2]])


def sstep(a, b, x):
    t = min(max((x - a) / (b - a), 0), 1)
    return t * t * (3 - 2 * t)


def win(ph, a, b, e):
    # 1 from a to b around the loop, eased in and out over e
    x = (ph - a) % 1
    return sstep(0, e, x) * (1 - sstep(b - a - e, b - a, x))


def spin(ph):
    # linger on the front and back, rush through the side views where they line up
    return SPIN0 + 2 * math.pi * ph - 0.35 * math.sin(4 * math.pi * ph)


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


PPOS, PYAW = (-0.32, 0.17), 0.68
BPOS, BYAW = (0.3, -0.15), 0.28
SPIN0 = math.atan2(BPOS[1] - PPOS[1], BPOS[0] - PPOS[0])   # angle where they stand side by side
PP = np.array([[PPOS[0]], [floor_at(*PPOS) - 0.01], [PPOS[1]]])
BP = np.array([[BPOS[0]], [floor_at(*BPOS) - 0.01], [BPOS[1]]])
PIV = np.array([[0], [0.03], [0]])
NECK = np.array([[0], [0.66], [0.02]])


def flipper(q, s, a):
    x, y, z = q[0] - s * 0.19, q[1] - 0.57, q[2] + 0.01
    c, sn = math.cos(s * a), math.sin(s * a)
    return ell((c * x + sn * y, c * y - sn * x, z), (0, -0.12, 0), (0.032, 0.135, 0.072))


def wave(ph):
    # flipper goes up while the penguin faces us
    up = sstep(0.3, 0.85, math.cos(PYAW + spin(ph)))
    return 0.3 + up * (0.85 + 0.45 * math.sin(2 * math.pi * 10 * ph))


def roll(ph):
    return 0.09 * math.sin(2 * math.pi * 4 * ph)


def penguin(q, ph):
    # waddle: the body rocks over the feet
    w = rotz(q - PIV, -roll(ph)) + PIV
    d = smin(ell(w, (0, 0.27, 0), (0.24, 0.27, 0.21)), ell(w, (0, 0.5, 0.005), (0.18, 0.22, 0.17)), 0.1)
    d = smin(d, sph(w, (0, 0.77, 0.01), 0.16), 0.04)
    fl = np.minimum(flipper(w, 1, 0.3), flipper(w, -1, wave(ph)))
    bu = ell(w, (0, 0.738, 0.165), (0.06, 0.03, 0.095))
    bl = ell(w, (0, 0.706, 0.16), (0.045, 0.021, 0.08))
    ft = 9.0
    for s in (-1, 1):
        x0 = s * 0.095
        f = ell(q, (x0, 0.022, 0.07), (0.06, 0.022, 0.06))
        for a in (-0.6, 0, 0.6):
            a += s * 0.2
            f = smin(f, cap(q, (x0, 0.02, 0.07), (x0 + math.sin(a) * 0.105, 0.016, 0.07 + math.cos(a) * 0.105), 0.019), 0.012)
        ft = np.minimum(ft, f)
    ey = np.minimum(sph(w, (0.058, 0.8, 0.132), 0.036), sph(w, (-0.058, 0.8, 0.132), 0.036))
    parts = [d, fl, bu, bl, ft, ey]
    return np.minimum.reduce([smin(d, fl, 0.015), bu, bl, ft, ey]), parts, w


def fur(q):
    x, y, z = q[0] * 110, q[1] * 110, q[2] * 110
    return np.sin(x + 2.1 * np.sin(y * 0.45 + z * 0.3)) * np.sin(z * 0.8 - x * 0.35 + 1.7 * np.sin(y * 0.6))


def head_pose(ph):
    # the bear looks over at the penguin for a while, then back at us with two little nods
    yaw = -0.62 * win(ph, 0.06, 0.5, 0.09)
    nod = 0.16 * win(ph, 0.795, 0.995, 0.02) * (0.5 - 0.5 * math.cos(2 * math.pi * 10 * ph))
    return yaw, nod


def bear(q, ph):
    yaw, nod = head_pose(ph)
    d = smin(ell(q, (0, 0.3, -0.04), (0.29, 0.29, 0.27)), ell(q, (0, 0.56, 0), (0.21, 0.22, 0.19)), 0.12)
    for s in (-1, 1):
        # front legs down to the paws, hind legs forward with the soles showing
        d = smin(d, cap(q, (s * 0.17, 0.58, 0.05), (s * 0.15, 0.1, 0.19), 0.066), 0.05)
        d = smin(d, ell(q, (s * 0.15, 0.055, 0.23), (0.072, 0.052, 0.088)), 0.03)
        d = smin(d, cap(q, (s * 0.17, 0.16, 0.0), (s * 0.22, 0.12, 0.29), 0.085), 0.06)
        d = smin(d, ell(q, (s * 0.225, 0.135, 0.355), (0.074, 0.098, 0.045)), 0.03)
    d = d - 0.0022 * fur(q)
    h = rotx(roty(q - NECK, -yaw), -nod) + NECK
    hd = smin(sph(h, (0, 0.86, 0.05), 0.165), ell(h, (0, 0.8, 0.205), (0.088, 0.075, 0.11)), 0.05)
    for s in (-1, 1):
        hd = smin(hd, ell(h, (s * 0.13, 1.0, 0.02), (0.07, 0.066, 0.04)), 0.025)
    hd = hd - 0.0022 * fur(h)
    no = ell(h, (0, 0.842, 0.303), (0.048, 0.034, 0.03))
    ey = np.minimum(sph(h, (0.074, 0.918, 0.172), 0.03), sph(h, (-0.074, 0.918, 0.172), 0.03))
    parts = [d, hd, no, ey]
    return np.minimum.reduce([smin(d, hd, 0.05), no, ey]), parts, h


# bounding spheres so far away points skip the character sdfs
PB = (PP[:, 0] + [0, 0.48, 0], 0.62)
BB = (BP[:, 0] + [0, 0.52, 0], 0.72)


def scene(p, ph, full=False):
    q = roty(p, -spin(ph))
    qp = roty(q - PP, -PYAW)
    qb = roty(q - BP, -BYAW)
    if full:
        dp, pp, pw = penguin(qp, ph)
        db, bp, bh = bear(qb, ph)
        parts = [floe(q), *pp, *bp]
        return np.minimum.reduce([floe(q), dp, db]), parts, (pw, qb, bh)
    d = floe(q)
    for (c, r), fn, lq in ((PB, penguin, qp), (BB, bear, qb)):
        bd = sph(q, c, r)
        near = bd < 0.05
        if near.any():
            bd[near] = fn(lq[:, near], ph)[0]
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


def project(p):
    d = np.asarray(p, float) - RO
    z = d @ FW
    x, y = (d @ RT) / z * DIST, (d @ UP) / z * DIST
    return (x / (2 * HW) + 0.5) * W - 0.5, (0.5 - y / (2 * HH)) * H - 0.5


RD = rays(W * SX, H * SY)
RDC = rays(W, H)
BC, BR = np.array([0, 0.32, 0.0]), 1.35


def march(ro, rd, ph, steps=110, eps=0.002):
    n = rd.shape[1]
    ro = np.broadcast_to(ro, rd.shape)
    oc = ro - BC[:, None]
    b = (rd * oc).sum(0)
    disc = b * b - ((oc * oc).sum(0) - BR * BR)
    alive = disc > 0
    sq = np.sqrt(np.maximum(disc, 0))
    t = np.maximum(-b - sq, 0)
    tfar = -b + sq
    hit = np.zeros(n, bool)
    for _ in range(steps):
        idx = np.nonzero(alive)[0]
        if not len(idx):
            break
        d = scene(ro[:, idx] + rd[:, idx] * t[idx], ph)
        h = d < eps
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
ICET, ICES, PDARK, PWHITE, BEAKU, BEAKL, FEET, EYE, BEAR, INEAR, PAD, NOSE = range(1, 13)
# parts from scene(full=True) -> material and object id (1 ice, 3 penguin, 5 flipper, 4 bear, 6 bear head)
MATOF = np.array([ICET, PDARK, PDARK, BEAKU, BEAKL, FEET, EYE, BEAR, BEAR, NOSE, EYE])
OIDOF = np.array([1, 3, 5, 3, 3, 3, 3, 4, 6, 6, 6])
ANIMAL = np.array([0, 1, 1, 3, 4, 3, 4])
# per material: char ramp dark -> bright, light thresholds for colour, colour classes
MATS = {
    PDARK: ('-=+*#', (0.55,), 'bc'),
    PWHITE: ('+*#%@', (0.45,), 'fg'),
    BEAR: ('=+*#%@', (0.4,), 'fg'),
    ICET: (' .:', (0.85,), 'kd'),
    ICES: (':|', (2,), 'k'),
    BEAKU: ('*#%', (0.5,), 'ij'),
    BEAKL: ('=+*', (2,), 'h'),
    FEET: ('=*#', (0.45, 0.8), 'hij'),
    INEAR: ('+*', (2,), 'l'),
    PAD: ('o@', (2,), 'b'),
    NOSE: ('@', (2,), 'a'),
}
OUTC = {PDARK: 'c', PWHITE: 'f', BEAR: 'g', ICET: 'd', ICES: 'd', BEAKU: 'i', BEAKL: 'i', FEET: 'i',
        EYE: 'a', INEAR: 'f', PAD: 'f', NOSE: 'f'}
COLORS = {
    'a': '#4a3478', 'b': '#6a4fa3', 'c': '#ab8fdc', 'd': '#9b5de5', 'e': '#c98bff',
    'f': '#dcc8ff', 'g': '#f8f2ff', 'h': '#b8622a', 'i': '#f0883e', 'j': '#ffb27a',
    'k': '#4f2a8a', 'l': '#ee82d8',
    'm': '#1d7a3c', 'n': '#2fc25a', 'o': '#6dff95', 'p': '#d2ffdf',
}
# shades close enough to swap when it saves a colour switch
SUB = 5   # cost of using a near shade, in bytes
NEAR = {'a': 'bk', 'b': 'ac', 'c': 'b', 'd': 'e', 'e': 'l', 'f': 'g', 'g': 'f',
        'h': 'i', 'i': 'hj', 'j': 'i', 'k': 'da', 'l': '', 'm': 'n', 'n': 'mo', 'o': 'np', 'p': 'o'}


def look(mat, l, drop=0):
    ramp, th, cl = MATS[mat]
    i = 0
    while i < len(th) and l >= th[i]:
        i += 1
    j = int(round(min(max(l, 0), 1) * (len(ramp) - 1)))
    return ramp[max(0, j - drop)], cl[i]


def classify(p, ph, n):
    _, parts, (pw, qb, bh) = scene(p, ph, True)
    m = np.argmin(np.array(parts), axis=0)
    mat, oid = MATOF[m], OIDOF[m]
    side = (mat == ICET) & (n[1] < 0.8)
    mat = np.where(side, ICES, mat)
    oid = np.where(side, 2, oid)
    # tux style white belly and face mask
    x, y, z = pw
    white = ((z > 0) & ((x / 0.165) ** 2 + ((y - 0.34) / 0.35) ** 2 < 1)) | \
            ((z > 0.04) & (((np.abs(x) - 0.062) / 0.074) ** 2 + ((y - 0.805) / 0.085) ** 2 < 1)) | \
            ((z > 0.08) & ((x / 0.1) ** 2 + ((y - 0.725) / 0.055) ** 2 < 1))
    mat = np.where((m == 1) & white, PWHITE, mat)
    # inner ears, foot pads
    x, y, z = bh
    inner = (z > 0.03) & ((((np.abs(x) - 0.13) / 0.046) ** 2 + ((y - 0.995) / 0.044) ** 2) < 1)
    mat = np.where((m == 8) & inner, INEAR, mat)
    x, y, z = qb
    fx = np.abs(x) - 0.225
    pad = ((fx / 0.042) ** 2 + ((y - 0.11) / 0.036) ** 2 < 1)
    for o in (-0.042, 0, 0.042):
        pad |= ((fx - o) / 0.018) ** 2 + ((y - 0.195) / 0.02) ** 2 < 1
    mat = np.where((m == 7) & (z > 0.37) & pad, PAD, mat)
    return mat, oid, m, qb, bh


def shade_hits(p, ph, rd):
    n = normal(p, ph)
    mat, oid, m, qb, bh = classify(p, ph, n)
    dif = np.clip(LIGHT @ n, 0, 1) * shadow(p, ph)
    fil = np.clip(FILL @ n, 0, 1)
    amb = 0.5 + 0.5 * n[1]
    rim = (1 - np.clip(-(rd * n).sum(0), 0, 1)) ** 2.5
    lum = (0.25 * amb + 0.8 * dif + 0.15 * fil) * occl(p, n, ph) + 0.45 * rim
    # soft fur grain on the bear
    lum = np.where(mat == BEAR, lum * (1 + 0.12 * fur(np.where(m == 8, bh, qb) * 0.7)), lum)
    return mat, lum, oid


def hash2(c, r):
    v = np.sin(c * 12.9898 + r * 78.233) * 43758.5453
    return v - np.floor(v)


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


# sky layout, in cells
CR, RR = np.meshgrid(np.arange(W), np.arange(H))
HZ = round(project([0, YW, -2.2])[1])          # where the sea meets the sky
# cells the animals can ever reach: bear up to its ears, penguin with the flipper out
BUSY = np.zeros((H, W), bool)
for a in np.linspace(0, 2 * np.pi, 96, endpoint=False):
    for top, rad in ((1.12, 0.6), (0.95, 0.76), (0.72, 0.92)):
        pts = [project([rad * math.cos(a), y, rad * math.sin(a)]) for y in np.linspace(0, top, 24)]
        for c, r in pts:
            r = int(round(r))
            if 0 <= r < H:
                BUSY[r, max(0, int(c) - 2):int(c) + 3] = True
for r in range(H):
    on = np.nonzero(BUSY[r])[0]
    if len(on):
        BUSY[r, on[0]:on[-1] + 1] = True
LEAF = (10, 10, 19)                            # stem joint col, row, middle leaflet length in columns
LEAFLETS = ((0, 1.0), (33, 0.86), (-33, 0.86), (64, 0.7), (-64, 0.7), (93, 0.38), (-93, 0.38))
SPARKS = ((28, 1, 1.0, '#ffffff'), (41, 4, 0.7, '#ffd6f5'), (57, 2, 0.85, '#e6d6ff'),
          (68, 5, 0.6, '#ffffff'), (79, 1, 1.1, '#ffd6f5'), (86, 9, 0.75, '#e6d6ff'))
PEAK = (1.6 / 2.6) ** 1.6 * (1 / 2.6)


def leaf_at(x, y):
    # x columns right, y columns up from the joint -> (distance from the rib 0..1, leaflet angle) or None
    best = None
    for ang, k in LEAFLETS:
        a = math.radians(ang)
        u = x * math.sin(a) + y * math.cos(a)
        v = x * math.cos(a) - y * math.sin(a)
        n = LEAF[2] * k
        if not 0 < u < n:
            continue
        t = u / n
        # pinched at the base, widest past the middle, pointy tip, serrated edge
        w = 0.15 * n * t ** 1.6 * (1 - t) / PEAK
        w *= 0.75 + 0.25 * ((t * 8) % 1)
        if abs(v) < w and (best is None or abs(v) / w < best[0]):
            best = (abs(v) / w, ang)
    if best:
        return best
    # stem, bending a little
    if -4 < y < 0.6 and abs(x - 0.06 * y * y) < 0.32:
        return 0.0, 180
    return None


def leaf_cells():
    out = {}
    lc, lr, n = LEAF
    for r in range(0, int(lr) + 4):
        for c in range(0, int(lc + n) + 2):
            hits, ys = [], []
            for i in range(4):
                for j in range(4):
                    h = leaf_at(c - 0.375 + i * 0.25 - lc, (lr - (r - 0.375 + j * 0.25)) * CELL)
                    if h:
                        hits.append(h)
                        ys.append(j)
            cv = len(hits) / 16
            if cv < 0.19:
                continue
            d = sum(h[0] for h in hits) / len(hits)
            ang = Counter(h[1] for h in hits).most_common(1)[0][0]
            if ang == 180:
                out[(r, c)] = ('|', 'n')
            elif d < 0.32 and cv > 0.55:
                # midrib, drawn the way the leaflet points on screen
                a = math.radians(ang)
                th = math.degrees(math.atan2(math.sin(a), math.cos(a) / CELL))
                ch = '|' if abs(th) < 22.5 else '-' if abs(th) > 67.5 else '/' if th > 0 else '\\'
                out[(r, c)] = (ch, 'p')
            elif cv > 0.8:
                out[(r, c)] = ('@' if d < 0.55 else '#' if d < 0.8 else '%', 'o' if d < 0.6 else 'n')
            else:
                my = sum(ys) / len(ys)
                ch = '.' if my > 2 else "'" if my < 1 else ':' if cv < 0.45 else '*'
                out[(r, c)] = (ch, 'n' if cv > 0.45 else 'm')
    return out


LEAFC = leaf_cells()
RESERVED = np.zeros((H, W), bool)
for r, c in LEAFC:
    RESERVED[r, c] = True


def make_stars(occ, n=80):
    # ascii stars only where nothing ever moves, a few colours and three twinkle speeds
    rng = np.random.default_rng(5)
    free = ~occ & ~RESERVED
    rs, cs = zip(*LEAFC)
    free[:max(rs) + 2, :max(cs) + 3] = False
    for c, r, _, _ in SPARKS:
        free[max(0, r - 1):r + 2, max(0, c - 3):c + 4] = False
    out, tries = [], 0
    while len(out) < n and tries < 20000:
        tries += 1
        c, r = int(rng.integers(1, W - 1)), int(rng.integers(0, HZ - 1))
        if not free[r, c] or any(abs(c - a) < 3 and abs(r - b) < 2 for a, b, _, _, _ in out):
            continue
        x = rng.random()
        ch, cl = (('.', 'c') if x < 0.45 else ("'", 'b') if x < 0.55 else ('+', 'f') if x < 0.78
                  else ('*', 'g') if x < 0.92 else ('*', 'l'))
        out.append((c, r, ch, cl, int(rng.integers(0, 3))))
    return out


def world(loc, who, ph, vec=False):
    # local point (or direction) on the penguin 'p' or on the bear's head 'b' -> world
    v = np.array(loc, float)[:, None]
    if who == 'p':
        q = rotz(v if vec else v - PIV, roll(ph)) + (0 if vec else PIV)
        q = roty(q, PYAW) + (0 if vec else PP)
    else:
        yaw, nod = head_pose(ph)
        q = roty(rotx(v if vec else v - NECK, nod), yaw) + (0 if vec else NECK)
        q = roty(q, BYAW) + (0 if vec else BP)
    return roty(q, spin(ph))[:, 0]


def glints(ph):
    # one bright cell per eye and on the nose, where the light bounces to the camera
    out = []
    for loc, rad, who in (((0.058, 0.8, 0.132), 0.036, 'p'), ((-0.058, 0.8, 0.132), 0.036, 'p'),
                          ((0.074, 0.918, 0.172), 0.03, 'b'), ((-0.074, 0.918, 0.172), 0.03, 'b'),
                          ((0, 0.85, 0.305), 0.03, 'b')):
        c = world(loc, who, ph)
        h = unit(LIGHT + unit(RO - c))
        cc, rr = project(c + h * rad)
        out.append((int(round(rr)), int(round(cc))))
    return out


def puffs(ph):
    # little breath clouds from the beak and the nose, drifting off the way they face
    out = []
    for loc, base, who in (((0, 0.72, 0.27), 0.02, 'p'), ((0, 0.83, 0.34), 0.14, 'b')):
        for k in range(4):
            age = ((ph - base - k * 0.25) % 1) / 0.16
            f = world((0, 0, 1), who, ph, True)
            if age >= 1 or f[2] < -0.3:
                continue
            c, r = project(world(loc, who, ph))
            side = min(max(f[0] * 3, -1), 1)
            out.append((int(round(c + side * (2 + 11 * age))), int(round(r - 0.5 - 4 * age)), age))
    return out


def background(ph, grid, wcells):
    t = 2 * math.pi * ph
    tw = (YW - RO[1]) / RDC[1]
    x, z = RO[0] + RDC[0] * tw, RO[2] + RDC[2] * tw
    rr = np.hypot(x, z)
    a = -spin(ph)
    qx, qz = math.cos(a) * x + math.sin(a) * z, math.cos(a) * z - math.sin(a) * x
    de = np.max([nx * qx + nz * qz - e - (YT - YW) * math.tan(SLOPE) for nx, nz, e in EDGES], axis=0)
    # rings move out twice per loop
    ring = np.cos(2 * math.pi * (de * 6.0 - 2 * ph))
    de, ring, rr = de.reshape(H, W), ring.reshape(H, W), rr.reshape(H, W)
    hsh = hash2(CR, RR)
    mc = LEAF[0]
    for r in range(H):
        for c in range(W):
            if grid[r][c] is not None:
                continue
            if RESERVED[r, c]:
                grid[r][c] = (' ', None)
                continue
            if r < HZ:
                grid[r][c] = (' ', None)
                continue
            if (r, c) in wcells:
                grid[r][c] = wcells[(r, c)]
                continue
            fade = min(max((1.6 - rr[r, c]) / 0.5, 0), 1)
            h = hsh[r, c]
            gl = abs(c - mc - 1.2 * math.sin(r * 1.9 + 3 * t)) < 1.6 + 0.12 * (r - HZ)
            if de[r, c] < 0.05:
                grid[r][c] = ('~', 'e')
            elif gl and math.sin(r * 2.3 + c * 0.7 - 4 * t) > -0.2:
                grid[r][c] = ('-' if (r + c) % 3 else '=', 'n' if r < HZ + 6 else 'm')
            elif ring[r, c] > 0.8 and h < 0.7 * fade:
                grid[r][c] = ('~' if rr[r, c] < 1.2 else '-', 'k')
            elif ring[r, c] > 0.1 and h < 0.12 * fade:
                grid[r][c] = ('.', 'k')
            elif r == HZ and hash2(c // 3, 7) < 0.6:
                grid[r][c] = ('_', 'k')
            elif hash2((c + int(ph * 2 * W)) // 5 % (W // 5 + 1), r) < 0.07 and h < 0.6:
                grid[r][c] = ('-', 'a')
            else:
                grid[r][c] = (' ', None)
    for c, r, age in puffs(ph):
        for dc, dr, need in ((0, 0, 0), (1, 0, 0.3), (-1, 0, 0.5), (0, -1, 0.6), (1, -1, 0.75)):
            cc, r2 = c + dc, r + dr
            if 0 <= r2 < H and 0 <= cc < W and age >= need and not RESERVED[r2, cc]                     and grid[r2][cc][1] in (None, 'k', 'd', 'e', 'l'):
                ch = 'o' if dc == dr == 0 and 0.15 < age < 0.7 else '.' if age > 0.8 or dc or dr else 'O' if age < 0.85 else '.'
                ch = '.' if age < 0.15 else ch
                grid[r2][cc] = (ch, 'g' if age < 0.45 else 'f' if age < 0.75 else 'c')


REFL = {PDARK: 'a', PWHITE: 'c', BEAR: 'c', BEAKU: 'h', BEAKL: 'h', FEET: 'h', ICET: 'k', ICES: 'k',
        EYE: None, INEAR: 'b', PAD: 'a', NOSE: None}


def reflections(ph, cand):
    # dim, wobbling mirror image of the floe and the animals in the water
    if not cand:
        return {}
    idx = np.array([r * W + c for r, c in cand])
    d = RDC[:, idx]
    p = RO[:, None] + d * ((YW - RO[1]) / d[1])
    t = 2 * math.pi * ph
    sx = 0.06 * np.sin(29 * p[2] + 3 * t + 2 * p[0]) + 0.03 * np.sin(47 * p[2] - 5 * t)
    sz = 0.03 * np.sin(19 * p[0] - 2 * t + 6 * p[2])
    nn = np.stack([-sx, np.ones_like(sx), -sz])
    nn /= np.linalg.norm(nn, axis=0)
    rd = d - 2 * (d * nn).sum(0) * nn
    tt, hit = march(p + rd * 0.004, rd, ph, 45, 0.005)
    out = {}
    hi = np.nonzero(hit)[0]
    if len(hi):
        q = p[:, hi] + rd[:, hi] * tt[hi]
        n = normal(q, ph)
        mat = classify(q, ph, n)[0]
        lum = 0.3 + 0.7 * np.clip(LIGHT @ n, 0, 1)
        for k, i in enumerate(hi):
            cl = REFL[mat[k]]
            r, c = cand[i]
            # broken horizontal streaks so it reads as water
            if cl == 'k':
                if math.sin(c * 0.45 + r * 2.1 + 3 * t) + hash2(c, r) > 0.6:
                    out[cand[i]] = ('~', 'k')
            elif cl:
                out[cand[i]] = ('-~='[int(lum[k] * 2.99)], cl)
    return out


def render(ph):
    S = SX * SY
    t, hit = march(RO[:, None], RD, ph)
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
    A = ANIMAL[G]
    for sh in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        nb, nz = np.roll(G, sh, (0, 1)), np.roll(Z, sh, (0, 1))
        gap = np.where(ANIMAL[nb] == A, 0.035, 0.08)
        E |= (G >= 3) & (nb != G) & (nz > Z + gap)
        if sh != (-1, 0):
            # no outline along the waterline, the foam does that
            E |= (G >= 1) & (G <= 2) & (nb == 0)
        E |= (G == 1) & (nb == 2)
    mat, lum, oid, E = cells(mat), cells(lum), cells(G), cells(E)
    cov = {k: (oid == k).mean(-1) for k in range(1, 7)}
    gr = {k: grad(cov[k]) for k in (3, 4, 5, 6, 1)}
    gr[0] = grad(cov[1] + cov[2])
    grid, dark = [], set()
    for r in range(H):
        row = []
        for c in range(W):
            ms, ls, os_, es = mat[r, c], lum[r, c], oid[r, c], E[r, c]
            nobj = (ms > 0).sum()
            if (ms == EYE).sum() >= 2:
                row.append((' ', None))
                dark.add((r, c))
                continue
            if (ms == NOSE).sum() >= 2:
                row.append(('@', 'a'))
                dark.add((r, c))
                continue
            nb = (ms == BEAKU).sum() + (ms == BEAKL).sum()
            if nb >= 2:
                m = BEAKU if (ms == BEAKU).sum() >= (ms == BEAKL).sum() else BEAKL
            elif (ms == FEET).sum() >= 3:
                m = FEET
            elif (ms == PAD).sum() >= 3:
                m = PAD
            elif nobj >= 2 or es.any():
                vals, cnt = np.unique(ms[ms > 0], return_counts=True)
                m = vals[np.argmax(cnt)]
            else:
                row.append(None)
                continue
            if m == EYE:
                m = PDARK
            l = float(ls[ms == m].mean()) if (ms == m).any() else 0.5
            if es.any():
                ow = np.bincount(os_[es], minlength=7)
                k = int(np.argmax(ow[3:])) + 3 if ow[3:].any() else 1
                if k == 1 and ((os_ == 0).any() or not (os_ == 2).any()):
                    k = 0
                gx, gy = gr[k][0][r, c], gr[k][1][r, c]
                if abs(gx) + abs(gy) > 0.05:
                    ch = edge_char(gx, gy, k < 3)
                    if m in (BEAKU, BEAKL):
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
    for rc in glints(ph):
        if rc in dark:
            grid[rc[0]][rc[1]] = ("'", 'g')
    # open water: what the cell sees mirrored
    cand = [(r, c) for r in range(HZ, H) for c in range(W) if grid[r][c] is None]
    background(ph, grid, reflections(ph, cand))
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


def static_layer():
    g = [[(' ', None)] * W for _ in range(H)]
    for (r, c), v in LEAFC.items():
        if 0 <= r < H and 0 <= c < W:
            g[r][c] = v
    return g


def sheet(name, frames):
    out = ['<html><body style="background:#120c1f;margin:8px;display:grid;'
           'grid-template-columns:repeat(2,auto);gap:6px 14px;justify-content:start">']
    st = static_layer()
    for c, r, ch, cl, _ in make_stars(BUSY):
        st[r][c] = (ch, cl)
    for f in frames:
        g = render(f / NF)
        g = [[st[r][c] if st[r][c][1] else g[r][c] for c in range(W)] for r in range(H)]
        g = [smooth(row, lambda o: 0 if o == 'e' else 20) for row in g]
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
BG = '#120c1f'

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
frng = np.random.default_rng(11)
FLAKES = [(frng.uniform(0, 1), frng.uniform(0, 1), int(frng.choice([1, 1, 2])), str(frng.choice(list(".*'+.*"))))
          for _ in range(26)]


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


def row_text(row, y, tags, base):
    # try the row with a few default colours on the <text> itself, keep the shortest
    cnt = Counter(cl for ch, cl in row if cl)
    if not cnt:
        return ''
    best = None
    for dflt in [base] + [k for k, _ in cnt.most_common(3) if k != base]:
        tg = dict(tags)
        if dflt != base:
            tg[base] = (f'<a class="{base}">', '</a>')
            tg[dflt] = ('', '')
        s = runs(smooth(row, lambda o: len(tg[o][0]) + len(tg[o][1])), tg)
        s = f'<text y="{y}"' + (f' class="{dflt}"' if dflt != base else '') + f'>{s}</text>'
        if best is None or len(s) < len(best):
            best = s
    return best


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


# hyprland desktop around the terminal: wallpaper, floating waybar pills, bordered window
TB = 30                                # old title bar strip, cut off the top of the terminal
GAP, BW, RND = 12, 2, 10               # gaps, border width, rounding
PY, PH, PG, BCW = 10, 26, 6, 7.2       # pill top, pill height, pill spacing, bar char width
CPU = [12, 9, 17, 34, 23, 15, 8, 11]   # one sample per second
WS = 'oaoee'                           # workspaces: occupied, active, empty


def rrect(x, y, w, h, r):
    return (f'M{num(x + r)} {num(y)}H{num(x + w - r)}A{r} {r} 0 0 1 {num(x + w)} {num(y + r)}'
            f'V{num(y + h - r)}A{r} {r} 0 0 1 {num(x + w - r)} {num(y + h)}H{num(x + r)}'
            f'A{r} {r} 0 0 1 {num(x)} {num(y + h - r)}V{num(y + r)}A{r} {r} 0 0 1 {num(x + r)} {num(y)}Z')


def desktop(iw, ih, title):
    tw, wy = iw + 2 * (BW + GAP), PY + PH + 10
    th = wy + ih + 2 * BW + GAP
    cy, by = PY + PH / 2, PY + 17

    def txt(x, s, c=None):
        xs = ' '.join(num(x + i * BCW) for i in range(len(s)))
        return f'<text x="{xs}" y="{by}"' + (f' class="{c}"' if c else '') + f'>{esc(s)}</text>'

    def arc(x, y, r, a0, a1):
        p = [(x + r * math.sin(math.radians(a)), y - r * math.cos(math.radians(a))) for a in (a0, a1)]
        big = 1 if (a1 - a0) % 360 > 180 else 0
        return f'M{num(p[0][0])} {num(p[0][1])}A{r} {r} 0 {big} 1 {num(p[1][0])} {num(p[1][1])}'

    # modules: (width, x -> markup)
    def m_arch(x):
        return (f'<path d="M{num(x + 7)} {num(cy - 7)}L{num(x + 14.5)} {num(cy + 6)}H{num(x - .5)}Z'
                f'M{num(x + 7)} {num(cy - 1)}L{num(x + 10.4)} {num(cy + 4.6)}H{num(x + 3.6)}Z" '
                f'fill="url(#ym)" fill-rule="evenodd"/>' + txt(x + 21, 'arch', 'ya'))

    def m_ws(x):
        out = []
        for s in WS:
            if s == 'a':
                out.append(f'<rect class="yg" x="{num(x - 2)}" y="{num(cy - 6)}" width="26" height="12" rx="6" '
                           f'fill="#c45cff" filter="url(#yu)"/>'
                           f'<rect x="{num(x)}" y="{num(cy - 4)}" width="22" height="8" rx="4" fill="url(#ym)"/>')
                x += 30
            else:
                out.append(f'<circle cx="{num(x + 3)}" cy="{num(cy)}" r="{3 if s == "o" else 2.6}" '
                           + ('fill="#9d8cbf"/>' if s == 'o' else 'fill="none" stroke="#5c4a85" stroke-width="1.2"/>'))
                x += 14
        return ''.join(out)

    def m_title(x):
        k = x + 21 + 5 * BCW + 8
        return (f'<rect x="{num(x + .7)}" y="{num(cy - 5.5)}" width="14" height="11" rx="2.5" fill="none" '
                f'stroke="#b07cff" stroke-width="1.3"/>'
                f'<path d="M{num(x + 3.6)} {num(cy - 2.4)}l2.6 2.4-2.6 2.4M{num(x + 7.6)} {num(cy + 2.6)}h3.6" '
                f'fill="none" stroke="#e0a8ff" stroke-width="1.2" stroke-linecap="round"/>'
                + txt(x + 21, 'kitty', 'ya')
                + f'<path d="M{num(k)} {num(cy - 6)}v12" stroke="#3a2961"/>' + txt(k + 9, title))

    def m_clock(x):
        return (f'<path d="M{num(x + 6)} {num(cy - 6)}A6 6 0 1 0 {num(x + 11.6)} {num(cy + 2.2)}'
                f'A4.8 4.8 0 0 1 {num(x + 6)} {num(cy - 6)}Z" fill="#e0a8ff"/>'
                + txt(x + 19, '03 14', 'yk') + txt(x + 19 + 2 * BCW, ':', 'yk yc'))

    sx, dx = 19, 4.5
    pts = [(i * dx, cy + 6 - v / 40 * 12) for i, v in enumerate(CPU * 2 + CPU[:1])]
    line = ' '.join(f'{num(a)},{num(b)}' for a, b in pts)

    def m_cpu(x):
        tx = x + sx + 7 * dx + 7
        nums = ''.join(f'<text x="{" ".join(num(tx + i * BCW) for i in range(3))}" y="{by + 20 * k}">'
                       f'{v:>2}%</text>' for k, v in enumerate(CPU))
        return (f'<rect x="{num(x + 1.5)}" y="{num(cy - 4.5)}" width="9" height="9" rx="1.5" fill="none" '
                f'stroke="#b07cff" stroke-width="1.3"/><rect x="{num(x + 4.5)}" y="{num(cy - 1.5)}" width="3" height="3" '
                f'fill="#e0a8ff"/><path d="M{num(x + 4.5)} {num(cy - 7)}v2M{num(x + 7.5)} {num(cy - 7)}v2'
                f'M{num(x + 4.5)} {num(cy + 5)}v2M{num(x + 7.5)} {num(cy + 5)}v2M{num(x - 1)} {num(cy - 1.5)}h2'
                f'M{num(x - 1)} {num(cy + 1.5)}h2M{num(x + 11)} {num(cy - 1.5)}h2M{num(x + 11)} {num(cy + 1.5)}h2" '
                f'stroke="#b07cff" stroke-width="1.1"/>'
                f'<clipPath id="ys"><rect x="{num(x + sx)}" y="{PY + 3}" width="{num(7 * dx + .8)}" height="{PH - 6}"/></clipPath>'
                f'<clipPath id="yn"><rect x="{num(tx - 1)}" y="{PY + 2}" width="{num(3 * BCW + 2)}" height="{PH - 4}"/></clipPath>'
                f'<g clip-path="url(#ys)"><g transform="translate({num(x + sx)} 0)"><g class="yz">'
                f'<polygon points="0,{num(cy + 7)} {line} {num(16 * dx)},{num(cy + 7)}" fill="url(#yv)"/>'
                f'<polyline points="{line}" fill="none" stroke="#e0a8ff" stroke-width="1.2" stroke-linejoin="round"/>'
                f'</g></g></g><g clip-path="url(#yn)"><g class="yn">{nums}</g></g>')

    def m_mem(x):
        return (f'<rect x="{num(x + .6)}" y="{num(cy - 4)}" width="12" height="7" rx="1" fill="none" stroke="#b07cff" '
                f'stroke-width="1.2"/><path d="M{num(x + 3.6)} {num(cy - 2)}v3M{num(x + 6.6)} {num(cy - 2)}v3'
                f'M{num(x + 9.6)} {num(cy - 2)}v3M{num(x + 2)} {num(cy + 3)}v2.6M{num(x + 4.6)} {num(cy + 3)}v2.6'
                f'M{num(x + 8.6)} {num(cy + 3)}v2.6M{num(x + 11.2)} {num(cy + 3)}v2.6" stroke="#e0a8ff" stroke-width="1.1"/>'
                + txt(x + 19, '3.1G'))

    def m_temp(x):
        return (f'<path d="M{num(x + 3)} {num(cy + 2)}V{num(cy - 5)}" stroke="#b07cff" stroke-width="3.6" '
                f'stroke-linecap="round"/><path d="M{num(x + 3)} {num(cy + 2)}V{num(cy - 2)}" stroke="#ff6ad5" '
                f'stroke-width="1.4" stroke-linecap="round"/><circle cx="{num(x + 3)}" cy="{num(cy + 3.4)}" r="3" '
                f'fill="#ff6ad5"/>' + txt(x + 12, '47°'))

    def m_tray(x):
        wx, wb = x + 7, cy + 4.6
        wifi = ''.join(arc(wx, wb, r, -45, 45) for r in (4, 7.5, 11))
        vx = x + 27
        bx = vx + 30 + 3 * BCW
        return (f'<path d="{wifi}" fill="none" stroke="#b07cff" stroke-width="1.5" stroke-linecap="round"/>'
                f'<circle cx="{num(wx)}" cy="{num(wb)}" r="1.4" fill="#e0a8ff"/>'
                f'<path d="M{num(vx)} {num(cy - 2.6)}h2.6l3.6-3.4v12l-3.6-3.4h-2.6Z" fill="#b07cff"/>'
                f'<path d="{arc(vx + 7, cy, 3, 45, 135)}{arc(vx + 7, cy, 5.8, 40, 140)}" fill="none" stroke="#b07cff" '
                f'stroke-width="1.3" stroke-linecap="round"/>' + txt(vx + 17, '64%')
                + f'<rect x="{num(bx + .6)}" y="{num(cy - 4.5)}" width="17" height="9" rx="2.2" fill="none" '
                f'stroke="#b07cff" stroke-width="1.2"/><rect x="{num(bx + 18.2)}" y="{num(cy - 2)}" width="1.6" '
                f'height="4" rx=".6" fill="#b07cff"/><rect x="{num(bx + 2.4)}" y="{num(cy - 2.7)}" '
                f'width="{num(13.4 * .87)}" height="5.4" rx="1" fill="url(#ym)"/>' + txt(bx + 25, '87%'))

    def m_power(x):
        return (f'<path d="{arc(x + 1, cy + .6, 5.6, 40, 320)}M{num(x + 1)} {num(cy - 6.6)}v5.6" fill="none" '
                f'stroke="#ff6ad5" stroke-width="1.6" stroke-linecap="round"/>')

    left = [(14 + 7 + 4 * BCW, m_arch), (sum(30 if s == 'a' else 14 for s in WS) - 8, m_ws),
            (21 + 5 * BCW + 17 + len(title) * BCW, m_title)]
    right = [(sx + 7 * dx + 7 + 3 * BCW, m_cpu), (19 + 4 * BCW, m_mem), (12 + 3 * BCW, m_temp),
             (82 + 6 * BCW, m_tray), (2, m_power)]
    pills, mods = [], []

    def place(x, w, fn, pad=12):
        pills.append((x, w + 2 * pad))
        mods.append(fn(x + pad))

    x = GAP
    for w, fn in left:
        place(x, w, fn)
        x += w + 24 + PG
    x = tw - GAP
    for w, fn in reversed(right):
        x -= w + 24
        place(x, w, fn)
        x -= PG
    cw = 19 + 5 * BCW
    place((tw - cw) / 2 - 12, cw, m_clock)

    # stars where the wallpaper shows
    rng = np.random.default_rng(7)
    stars = []
    for _ in range(500):
        x, y = rng.uniform(4, tw - 4), rng.uniform(3, th - 3)
        if GAP - 3 < x < tw - GAP + 3 and wy - 3 < y < th - GAP + 3:
            continue
        if any(px - 3 < x < px + pw + 3 and PY - 3 < y < PY + PH + 3 for px, pw in pills):
            continue
        r = rng.choice([.5, .6, .8, 1.1])
        c = ' class="yt" style="animation-delay:-%ss"' % num(rng.uniform(0, 4)) if r > .7 and len(stars) % 2 else ''
        stars.append(f'<circle cx="{num(x)}" cy="{num(y)}" r="{r}" opacity="{num(rng.uniform(.3, .8))}"{c}/>')

    ww, wh, cx0, cy0 = iw + 2 * BW, ih + 2 * BW, tw / 2, wy + (ih + 2 * BW) / 2
    edge = f'x="{GAP + BW / 2}" y="{wy + BW / 2}" width="{iw + BW}" height="{ih + BW}" rx="{RND + BW / 2}"'
    css = ('.yb text{font-size:12px;fill:#cfc2ea}.yb .ya{fill:#b07cff;font-weight:700}.yb .yk{fill:#f1e6ff;font-weight:700}'
           '.yp{fill:#150d27;fill-opacity:.86;stroke:url(#yl)}'
           '.yc{animation:yc 2s steps(1) infinite}@keyframes yc{50%{opacity:0}}'
           '.yg{animation:yg 4s ease-in-out infinite}@keyframes yg{50%{opacity:.3}}'
           '.yt{animation:yt 3s ease-in-out infinite}@keyframes yt{50%{opacity:.1}}'
           f'.yz{{animation:yz {len(CPU)}s steps({len(CPU)}) infinite}}'
           f'@keyframes yz{{from{{transform:translateX(-{num(dx)}px)}}to{{transform:translateX(-{num(dx * (len(CPU) + 1))}px)}}}}'
           f'.yn{{animation:yn {len(CPU)}s steps({len(CPU)}) infinite}}'
           f'@keyframes yn{{to{{transform:translateY(-{20 * len(CPU)}px)}}}}')
    before = (
        f'<style>{css}</style><defs>'
        f'<linearGradient id="yw" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#0e0820"/>'
        f'<stop offset=".55" stop-color="#140a2c"/><stop offset="1" stop-color="#1f0d3d"/></linearGradient>'
        f'<radialGradient id="yr1" cx=".82" cy=".02" r=".55"><stop offset="0" stop-color="#ff4fd8" stop-opacity=".42"/>'
        f'<stop offset="1" stop-color="#ff4fd8" stop-opacity="0"/></radialGradient>'
        f'<radialGradient id="yr2" cx=".08" cy=".98" r=".7"><stop offset="0" stop-color="#7b2ff7" stop-opacity=".55"/>'
        f'<stop offset="1" stop-color="#7b2ff7" stop-opacity="0"/></radialGradient>'
        f'<linearGradient id="yl" x2="0" y2="1"><stop offset="0" stop-color="#6d52a8"/>'
        f'<stop offset="1" stop-color="#2a1d45"/></linearGradient>'
        f'<linearGradient id="yh" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".09"/>'
        f'<stop offset=".6" stop-color="#fff" stop-opacity="0"/></linearGradient>'
        f'<linearGradient id="ym" x2="1" y2="1"><stop offset="0" stop-color="#9b5cff"/>'
        f'<stop offset="1" stop-color="#ff6ad5"/></linearGradient>'
        f'<linearGradient id="yv" x2="0" y2="1"><stop offset="0" stop-color="#e0a8ff" stop-opacity=".35"/>'
        f'<stop offset="1" stop-color="#e0a8ff" stop-opacity="0"/></linearGradient>'
        f'<linearGradient id="yd" gradientUnits="userSpaceOnUse" x1="{num(cx0 - ww / 2)}" y1="{num(cy0)}" '
        f'x2="{num(cx0 + ww / 2)}" y2="{num(cy0)}"><stop offset="0" stop-color="#6a2cf5"/>'
        f'<stop offset=".38" stop-color="#b05cff"/><stop offset=".5" stop-color="#ff6ad5"/><stop offset=".56" stop-color="#ffc8f2"/>'
        f'<stop offset=".64" stop-color="#ff6ad5"/><stop offset="1" stop-color="#7b2ff7"/>'
        f'<animateTransform attributeName="gradientTransform" type="rotate" values="0 {num(cx0)} {num(cy0)};'
        f'360 {num(cx0)} {num(cy0)}" dur="12s" repeatCount="indefinite"/></linearGradient>'
        f'<filter id="yu" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="3"/></filter>'
        f'<filter id="yf" x="-5%" y="-5%" width="110%" height="115%"><feGaussianBlur stdDeviation="9"/></filter>'
        f'<filter id="ye" x="-5%" y="-50%" width="110%" height="200%"><feGaussianBlur stdDeviation="3"/></filter>'
        f'<clipPath id="yo"><path clip-rule="evenodd" d="M0 0H{tw}V{th}H0Z{rrect(GAP, wy, ww, wh, RND + BW)}"/></clipPath>'
        f'</defs>'
        f'<rect width="{tw}" height="{th}" rx="14" fill="url(#yw)"/>'
        f'<rect width="{tw}" height="{th}" rx="14" fill="url(#yr2)"/><rect width="{tw}" height="{th}" rx="14" fill="url(#yr1)"/>'
        f'<g fill="#f1e6ff">{"".join(stars)}</g>'
        f'<g clip-path="url(#yo)"><rect x="{GAP}" y="{wy + 5}" width="{ww}" height="{wh}" rx="{RND + BW}" '
        f'fill="#030108" opacity=".8" filter="url(#yf)"/></g>'
        f'<g fill="#05020c" opacity=".7" filter="url(#ye)">'
        + ''.join(f'<rect x="{num(px)}" y="{PY + 2}" width="{num(pw)}" height="{PH}" rx="{PH / 2}"/>' for px, pw in pills)
        + '</g><g class="yb">'
        + ''.join(f'<rect class="yp" x="{num(px + .5)}" y="{PY + .5}" width="{num(pw - 1)}" height="{PH - 1}" rx="{(PH - 1) / 2}"/>'
                  f'<rect x="{num(px + 1.5)}" y="{PY + 1.5}" width="{num(pw - 3)}" height="{PH / 2}" rx="{(PH - 3) / 2}" fill="url(#yh)"/>'
                  for px, pw in pills)
        + ''.join(mods) + '</g>'
        f'<g fill="none" stroke="url(#yd)"><rect {edge} stroke-width="16" stroke-opacity=".05"/>'
        f'<rect {edge} stroke-width="9" stroke-opacity=".1"/><rect {edge} stroke-width="5" stroke-opacity=".25"/></g>'
        f'<rect x="{GAP + BW}" y="{wy + BW}" width="{iw}" height="{ih}" rx="{RND}" fill="{BG}" fill-opacity=".93"/>')
    after = f'<rect {edge} fill="none" stroke="url(#yd)" stroke-width="{BW}"/>'
    return before, after, GAP + BW, wy + BW, tw, th


def build(ids=range(NF), path=os.path.join(HERE, '..', 'assets', 'terminal.svg')):
    frames = []
    for f in ids:
        frames.append(render(f / NF))
        print(f'\rframe {f + 1}/{NF}', end='', file=sys.stderr)
    print(file=sys.stderr)
    # sky cells that something ever passes through, stars stay out of those
    occ = np.zeros((H, W), bool)
    for g in frames:
        occ |= np.array([[ch != ' ' for ch, _ in row] for row in g])
    occ |= np.roll(occ, 1, 1) | np.roll(occ, -1, 1)
    stars = make_stars(occ)

    # most used colour is the default fill, the next two get the short <a> and bare <tspan> wrappers
    def colour_tags(frs):
        cnt = Counter(cl for g in frs for row in g for ch, cl in row if cl)
        top = [k for k, _ in cnt.most_common()]
        tags = {k: (f'<a class="{k}">', '</a>') for k in COLORS}
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
        rows = ''.join(row_text(row, LH - 2 + r * LH, tags, top[0]) for r, row in enumerate(g))
        stack.append(f'<g transform="translate({SCX} {SCY + k * FH})">{rows}</g>')

    # the leaf glows, the stars twinkle, both sit still outside the film strip
    st = static_layer()
    still = ''.join(row_text(row, LH - 2 + r * LH, tags, top[0]) for r, row in enumerate(st))
    tws = ''
    for i, (c, r, ch, cl, k) in enumerate(stars):
        dur = LOOP / (1, 2, 4)[k]
        tws += (f'<text y="{LH - 2 + r * LH}" class="{cl} t{k}" style="animation-delay:-{num(hash2(i, 3) * dur)}s">'
                f'{" " * c}{esc(ch)}</text>')

    nf = len(frames)
    used = set(top)
    css = [f'text{{font-family:{FONT};font-size:13px;fill:#e2d9f3;white-space:pre}}',
           f'.sc text{{font-size:{FS}px;fill:{COLORS[top[0]]}}}',
           f'.sc a{{fill:{COLORS[top[1]]}}}.sc tspan{{fill:{COLORS[top[2]]}}}',
           ''.join(f'.sc .{k}{{fill:{COLORS[k]}}}' for k in COLORS if k in used or k in 'fgbcklmnop'),
           '.ku{fill:#b07cff;font-weight:700}.cy{fill:#e0a8ff}.dm{fill:#75659a}.wh{fill:#f8f2ff}'
           '.cu{fill:#e2d9f3}',
           f'.fr{{animation:fr {num(LOOP)}s steps({nf}) infinite}}',
           f'@keyframes fr{{to{{transform:translateY(-{nf * FH}px)}}}}']
    for k in range(3):
        css.append(f'.t{k}{{animation:t{k} {num(LOOP / (1, 2, 4)[k])}s ease-in-out infinite}}'
                   f'@keyframes t{k}{{0%,100%{{opacity:1}}50%{{opacity:.15}}}}')
    # green halo that breathes behind the leaf, four point sparkles, a couple of shooting stars
    css += [f'.lh{{animation:lh {num(LOOP / 2)}s ease-in-out infinite}}'
            '@keyframes lh{0%,100%{opacity:.6}50%{opacity:1}}',
            f'.tw{{animation:tw {num(LOOP / 2)}s ease-in-out infinite}}'
            '@keyframes tw{0%,100%{transform:scale(.45) rotate(0);opacity:.5}50%{transform:scale(1) rotate(20deg);opacity:1}}',
            '.ss{opacity:0;animation:ss 14s linear infinite}'
            '@keyframes ss{0%{opacity:0;transform:translate(0,0)}1%{opacity:1}6%{opacity:0;transform:translate(190px,66px)}'
            '100%{opacity:0;transform:translate(190px,66px)}}']
    lx, ly = SCX + (LEAF[0] + 0.5) * FS * 0.58, SCY + (LEAF[1] - 4) * LH
    star4 = 'M0-7Q.7-.7 7 0Q.7 .7 0 7Q-.7 .7-7 0Q-.7-.7 0-7Z'
    sparks = ''.join(
        f'<g transform="translate({num(SCX + (c + 0.5) * FS * 0.58)} {SCY + r * LH + 4}) scale({sz})">'
        f'<g class="tw" style="animation-delay:-{num(hash2(c, r) * LOOP / 2)}s">'
        f'<circle r="9" fill="url(#sg)"/><path d="{star4}" fill="{col}"/></g></g>'
        for c, r, sz, col in SPARKS)
    shoot = ''.join(
        f'<g class="ss" style="animation-delay:-{d}s"><g transform="translate({x} {y})">'
        f'<path d="M0 0L-52-18" stroke="url(#sl)" stroke-width="1.6" stroke-linecap="round"/>'
        f'<circle r="1.7" fill="#fff"/></g></g>'
        for x, y, d in ((SCX + 230, SCY + 6, 0), (SCX + 60, SCY + 30, 7)))
    glow = (f'<radialGradient id="gl"><stop offset="0" stop-color="#5dff8a" stop-opacity=".38"/>'
            f'<stop offset=".5" stop-color="#22c55e" stop-opacity=".12"/><stop offset="1" stop-color="#22c55e" stop-opacity="0"/></radialGradient>'
            f'<radialGradient id="sg"><stop offset="0" stop-color="#fff" stop-opacity=".55"/>'
            f'<stop offset="1" stop-color="#d9b8ff" stop-opacity="0"/></radialGradient>'
            f'<linearGradient id="sl" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="-52" y2="-18">'
            f'<stop offset="0" stop-color="#fff"/><stop offset="1" stop-color="#e9c8ff" stop-opacity="0"/></linearGradient>'
            f'<filter id="lf" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="1.8" result="b"/>'
            f'<feMerge><feMergeNode in="b"/><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>'
            f'<ellipse class="lh" cx="{num(lx)}" cy="{num(ly)}" rx="78" ry="62" fill="url(#gl)"/>' + sparks + shoot)

    # snow drifts down on its own, one row per step, same loop as the scene
    fall = (H + 2) * LH
    snow = []
    for i, (fx, f0, k, ch) in enumerate(FLAKES):
        dur = LOOP / k
        snow.append(f'<text class="s{k}" x="{num(SCX + fx * W * FS * 0.58)}" y="{SCY - LH}" '
                    f'style="animation-delay:-{num(f0 * dur)}s">{esc(ch)}</text>')
    for k in (1, 2):
        css.append(f'.s{k}{{fill:#e0ccff;font-size:11px;animation:s{k} {num(LOOP / k)}s steps({H + 2}) infinite}}'
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

    before, after, ox, oy, tw, th = desktop(SW, SH - TB, f'lth-a@{HOST}: ~')
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{tw}" height="{th}" viewBox="0 0 {tw} {th}" '
           f'xml:space="preserve" role="img" aria-label="lth-a running fastfetch on arch, a penguin and a polar bear on an ice floe">'
           f'<style>{"".join(css)}</style>' + before + f'<g transform="translate({ox} {oy - TB})">'
           + gtext(0, SCY - 12, prompt('fastfetch'))
           + f'<clipPath id="cs"><rect x="{SCX - 8}" y="{SCY - 2}" width="{PX - SCX - 4}" height="{H * LH + 4}"/></clipPath>'
           f'<g clip-path="url(#cs)">{glow}<g class="sc" transform="translate({SCX} {SCY})"><g filter="url(#lf)">{still}</g>{tws}</g>'
           f'<g class="sc fr">{"".join(stack)}</g>{"".join(snow)}</g>'
           + lg + ''.join(info) + ''.join(bot) + '</g>' + after + '</svg>')
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
