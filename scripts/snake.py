# a scaly purple snake that slithers through the contribution graph and eats it
# python3 snake.py light.svg dark.svg          (needs GITHUB_TOKEN)
# python3 snake.py --demo light.svg dark.svg   fake calendar, works offline (or SNAKE_DEMO=1)
import datetime as dt
import heapq
import http.client
import json
import math
import os
import random
import sys
import time
import urllib.error
import urllib.request

W = 960
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
LEVEL = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2, "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}

# snake shape, in px of the 960 wide image
SEGS = 72           # scale segments in the body
FAT = 6.4           # half width of the body at its thickest
SP0, SP1 = 2.35, 3.1  # segment spacing when it shows up / after the meal
AMP, LAM = 2.6, 62  # side to side wave
EAT = 6             # a cell is eaten once the head axis gets this close to its centre
# one diamond on the back over 8 scale rows, half width as a share of the body at each row edge
RIM = (0, .3, .62, .88, .98, .88, .62, .3, 0)
DARK = (0, 0, .32, .62, .78, .62, .32, 0, 0)

THEMES = {
    "light": dict(
        cells=["#ebedf0", "#e2d1fb", "#c19af5", "#9254de", "#5b21b6"], label="#6e5a8f", flash="#fdf8ff", puff="#b98cf2",
        body=["#1f0638", "#4c1585", "#6d24b5", "#9655dc", "#e7d2ff"], line="#16042a",
        mark="#13031f", ring="#d6b3ff", dots="#f3e8ff", eye="#ffe27a", eye2="#d08f1a", tongue="#ff4f9e",
        shadow=("#12002a", ".3", 0.9, (1.2, 2.4))),
    "dark": dict(
        cells=["#161b22", "#2a1650", "#46237f", "#6a35b8", "#a66cff"], label="#8b7aa8", flash="#c9a6ff", puff="#a66cff",
        body=["#2a0b52", "#6a23b8", "#9447e6", "#b77dff", "#f6ecff"], line="#12031f",
        mark="#1a0530", ring="#d7b6ff", dots="#fbf5ff", eye="#ffe27a", eye2="#d08f1a", tongue="#ff6fb1",
        shadow=("#9d5cff", ".45", 2.2, (0, 0.6))),
}

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        weeks { contributionDays { date weekday contributionCount contributionLevel } }
      }
    }
  }
}"""


def die(msg):
    print(f"snake: {msg}", file=sys.stderr)
    sys.exit(1)


def gql(token, login):
    body = json.dumps({"query": QUERY, "variables": {"login": login}}).encode()
    headers = {"Authorization": f"bearer {token}", "Content-Type": "application/json",
               "User-Agent": "profile-snake"}
    err = "no response"
    for attempt in range(3):
        time.sleep(5 * attempt)
        try:
            req = urllib.request.Request("https://api.github.com/graphql", data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as r:
                res = json.load(r)
            break
        except urllib.error.HTTPError as e:
            err = f"github api returned {e.code}: {' '.join(e.read().decode(errors='replace').split())[:300]}"
            if e.code < 500:
                die(err)
        except (OSError, http.client.HTTPException, ValueError) as e:  # api hiccups, try again
            err = f"could not talk to github api: {e!r}"
    else:
        die(err)
    if res.get("errors"):
        die("graphql error: " + "; ".join(e.get("message", "?") for e in res["errors"]))
    user = (res.get("data") or {}).get("user")
    if not user:
        die(f"user {login} not found")
    return user


def fetch(login):
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        die("GITHUB_TOKEN is not set (try --demo for a fake calendar)")
    cal = []
    try:
        for w in gql(token, login)["contributionsCollection"]["contributionCalendar"]["weeks"]:
            slot = [None] * 7
            for d in w["contributionDays"]:
                lvl = LEVEL.get(d["contributionLevel"], 1 if d["contributionCount"] else 0)
                slot[d["weekday"]] = (dt.date.fromisoformat(d["date"]), lvl)
            cal.append(slot)
    except (KeyError, TypeError, ValueError, IndexError) as e:
        die(f"unexpected calendar data from github: {e!r}")
    if not cal:
        die("contribution calendar came back empty")
    return cal


def demo():
    # quiet winter, busy since may, like the real thing
    rnd = random.Random(7)
    end = dt.date(2026, 11, 14)
    day = end - dt.timedelta(days=364)
    day -= dt.timedelta(days=(day.weekday() + 1) % 7)
    days = []
    while day <= end:
        busy = 0.8 if day.month >= 5 and day.year == end.year else 0.12
        n = rnd.choice([1, 2, 3, 5, 8, 13, 21]) if rnd.random() < busy else 0
        days.append((day, n))
        day += dt.timedelta(days=1)
    nz = sorted(n for _, n in days if n)
    q = [nz[len(nz) * k // 4] for k in (1, 2, 3)]
    cal = []
    for d, n in days:
        if d.weekday() == 6 or not cal:
            cal.append([None] * 7)
        cal[-1][(d.weekday() + 1) % 7] = (d, 0 if not n else 1 + sum(n > x for x in q))
    return cal


def dist(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


def mix(a, b, f):
    return (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)


def tour(cells, start, nw):
    # greedy nearest cell first, then 2-opt. moving across columns costs a bit more than along
    # them so it sweeps up and down, sharp turns cost extra since the snake has to loop round,
    # and it should finish near a side so it doesn't crawl all the way back to leave
    d = lambda a, b: math.hypot(1.35 * (a[0] - b[0]), a[1] - b[1])
    out = lambda c: min(c[0] + 3, nw + 2 - c[0])

    def bend(a, b, c):
        ux, uy, ox, oy = b[0] - a[0], b[1] - a[1], c[0] - b[0], c[1] - b[1]
        return 1.5 * max(0, -(ux * ox + uy * oy) / (math.hypot(ux, uy) * math.hypot(ox, oy)))

    pts, left = [(start[0] - 1, start[1]), start], set(cells)
    while left:
        pick = min(left, key=lambda c: (d(pts[-1], c) + bend(pts[-2], pts[-1], c), c))
        left.remove(pick)
        pts.append(pick)
    # untangle, the start stays put
    n, better = len(pts), True
    while better:
        better = False
        for i in range(2, n - 1):
            for j in range(i + 1, n):
                a, b, c = pts[i - 1], pts[i], pts[j]
                old = d(a, b) + bend(pts[i - 2], a, b) + bend(a, b, pts[i + 1])
                new = d(a, c) + bend(pts[i - 2], a, c) + bend(a, c, pts[j - 1])
                if j + 1 < n:
                    e = pts[j + 1]
                    old += d(c, e) + bend(pts[j - 1], c, e)
                    new += d(b, e) + bend(pts[i + 1], b, e)
                    if j + 2 < n:
                        old += bend(c, e, pts[j + 2])
                        new += bend(b, e, pts[j + 2])
                else:
                    old += out(c)
                    new += out(b)
                if new < old - 1e-6:
                    pts[i:j + 1] = pts[i:j + 1][::-1]
                    better = True
    return pts[2:]


def lengths(pts):
    s = [0.0]
    for i in range(1, len(pts)):
        s.append(s[-1] + dist(pts[i - 1], pts[i]))
    return s


def corridor(a, b, busy, nw):
    # cheapest walk over the grid from cell a to cell b, it only steps on food it hasn't eaten
    # yet when there is no way around
    best, prev, heap = {a: 0}, {}, [(0, a)]
    while heap:
        d, c = heapq.heappop(heap)
        if c == b:
            break
        if d > best[c]:
            continue
        for dc in (-1, 0, 1):
            for dr in (-1, 0, 1):
                n = (c[0] + dc, c[1] + dr)
                if not (dc or dr) or not (-3 <= n[0] <= nw + 2 and 0 <= n[1] <= 6):
                    continue
                cost = d + (1.41 if dc and dr else 1)
                if dc and dr and (c[0] + dc, c[1]) in busy and (c[0], c[1] + dr) in busy:
                    cost += 1
                if n in busy and n != b:
                    cost += 8
                if cost < best.get(n, 1e9):
                    best[n], prev[n] = cost, c
                    heapq.heappush(heap, (cost, n))
    walk = [b]
    while walk[-1] != a:
        walk.append(prev[walk[-1]])
    return walk[::-1]


def clear(a, b, block, r):
    # does the segment a-b keep at least r away from every point in block
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = dx * dx + dy * dy or 1
    for p in block:
        f = min(1, max(0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / n))
        if math.hypot(a[0] + dx * f - p[0], a[1] + dy * f - p[1]) < r:
            return False
    return True


def pull(pts, block, r):
    # cut corners of a grid walk wherever the straight line stays clear of food
    out, i = [pts[0]], 0
    while i < len(pts) - 1:
        j = len(pts) - 1
        while j > i + 1 and not clear(pts[i], pts[j], block, r):
            j -= 1
        out.append(pts[j])
        i = j
    return out


def drive(pos, ang, way, R):
    # steer like a car with a smallest turning circle R so the path is round everywhere, no cusps.
    # way is (x, y, reach, pref, food): switch to the next target within reach (or for food, once
    # the head is over it), and when the target is behind, loop round on the pref side
    pts, bend = [pos], [0.0]
    for tx, ty, reach, pref, food in way:
        side, spun = 0, 0.0
        for _ in range(4000):
            dx, dy = tx - pos[0], ty - pos[1]
            d = math.hypot(dx, dy)
            ca, sa = math.cos(ang), math.sin(ang)
            along, aside = dx * ca + dy * sa, abs(dy * ca - dx * sa)
            if d <= reach or (along < 0 and d < min(reach + 4, 9)) or (food and -4 < along < 11 and aside < 4.5):
                break
            diff = (math.atan2(dy, dx) - ang + math.pi) % (2 * math.pi) - math.pi
            if not side and abs(diff) > 1 / R:
                # pick a way round, unless the target is inside that turning circle: then run on first
                s = 1 if diff > 0 else -1
                if pref and abs(diff) > 2.6:
                    s = 1 if pref[1] * ca - pref[0] * sa > 0 else -1
                if math.hypot(dx + sa * R * s, dy - ca * R * s) > R + 1.5:
                    side, spun = s, 0.0
            if side and abs(diff) > 1 / R and (diff * side > 0 or abs(diff) > 2.4) and spun < 7:
                turn = side / R
            else:
                side = 0
                turn = max(-1 / R, min(1 / R, diff)) if abs(diff) <= 1 / R else 0
            spun += abs(turn)
            ang += turn
            pos = (pos[0] + math.cos(ang), pos[1] + math.sin(ang))
            pts.append(pos)
            bend.append(turn)
    return pts, bend, ang


def smooth(pts, w=2, n=2):
    for _ in range(n):
        k = 2 * w + 1
        pts = pts[:w] + [(sum(p[0] for p in pts[i - w:i + w + 1]) / k, sum(p[1] for p in pts[i - w:i + w + 1]) / k)
                         for i in range(w, len(pts) - w)] + pts[len(pts) - w:]
    return pts


def wiggle(pts, bend):
    # side to side wave, faded out in tight bends so they stay round
    s = lengths(pts)
    flat = [min(1.0, max(0.0, 1 - (abs(b) - 0.02) / 0.05)) for b in bend]
    lo = [min(flat[max(i - 20, 0):i + 21]) for i in range(len(pts))]
    amp = [sum(lo[max(i - 20, 0):i + 21]) / len(lo[max(i - 20, 0):i + 21]) for i in range(len(pts))]
    out = []
    for i, p in enumerate(pts):
        a, b = pts[max(i - 3, 0)], pts[min(i + 3, len(pts) - 1)]
        n = dist(a, b) or 1
        o = AMP * amp[i] * math.sin(2 * math.pi * s[i] / LAM)
        out.append((p[0] - (b[1] - a[1]) / n * o, p[1] + (b[0] - a[0]) / n * o))
    return out


def resample(pts, step):
    s = lengths(pts)
    out, j, k = [], 0, 0
    while k * step <= s[-1]:
        x = k * step
        while s[j + 1] < x:
            j += 1
        f = (x - s[j]) / ((s[j + 1] - s[j]) or 1)
        out.append(mix(pts[j], pts[j + 1], f))
        k += 1
    return out


def bezier(pts):
    # smooth path through the points as one C and then S commands in tenths of a px,
    # plus the length of each piece so key points line up with what the browser measures
    q = [(round(x * 10), round(y * 10)) for x, y in pts]
    ext = [q[0]] + q + [q[-1]]
    d, segs, dense, total = [f"M{q[0][0] / 10:g} {q[0][1] / 10:g}"], [], [(q[0][0] / 10, q[0][1] / 10, 0.0)], 0.0
    for i in range(1, len(ext) - 2):
        p0, p1, p2, p3 = ext[i - 1:i + 3]
        c1 = (round(p1[0] + (p2[0] - p0[0]) / 6), round(p1[1] + (p2[1] - p0[1]) / 6))
        c2 = (round(p2[0] - (p3[0] - p1[0]) / 6), round(p2[1] - (p3[1] - p1[1]) / 6))
        if i > 1:
            c1 = (2 * p1[0] - prev[0], 2 * p1[1] - prev[1])  # what S does
            d.append("s" + rel([c2, p2], p1))
        else:
            d.append("c" + rel([c1, c2, p2], p1))
        prev = c2
        n, ln, last = 10, 0.0, p1
        for k in range(1, n + 1):
            t = k / n
            u = 1 - t
            pt = (u ** 3 * p1[0] + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t ** 3 * p2[0],
                  u ** 3 * p1[1] + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t ** 3 * p2[1])
            ln += dist(last, pt) / 10
            last = pt
            dense.append((pt[0] / 10, pt[1] / 10, total + ln))
        total += ln
        segs.append(ln)
    return "".join(d), segs, dense


def rel(pts, o):
    out = ""
    for x, y in pts:
        for v in (x - o[0], y - o[1]):
            t = f"{v / 10:g}"
            t = t.replace("0.", ".") if t.startswith(("0.", "-0.")) else t
            out += t if t.startswith("-") or not out else " " + t
    return out


def keys(knots, L):
    # knots are (time, distance) joined by straight lines, clamp them to the path and keep the bends
    pts = []
    for (ta, a), (tb, b) in zip(knots, knots[1:]):
        pts.append((ta, a))
        for edge in (0, L):
            if (a - edge) * (b - edge) < 0:
                pts.append((ta + (tb - ta) * (edge - a) / (b - a), edge))
    pts.append(knots[-1])
    pts = [(t, min(max(v, 0), L)) for t, v in pts]
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        (t0, v0), (t1, v1), (t2, v2) = out[-1], pts[i], pts[i + 1]
        if abs(v0 + (v2 - v0) * (t1 - t0) / ((t2 - t0) or 1) - v1) > 0.05:
            out.append(pts[i])
    out.append(pts[-1])
    return out


def fmt_keys(T, pts, L):
    kt, kp, last = [], [], -1
    for t, v in pts:
        f = round(t / T, 5)
        if f <= last:
            continue
        kt.append(n5(f))
        kp.append(n5(v / L))
        last = f
    kt[0], kt[-1] = "0", "1"
    return ";".join(kt), ";".join(kp)


def body_width(u):
    # u is 0 at the neck and 1 at the tip of the tail
    if u < 0.12:
        return 4.7 + (FAT - 4.7) * math.sin(u / 0.12 * math.pi / 2)
    if u < 0.4:
        return FAT
    k = (u - 0.4) / 0.6
    return max(0.45, FAT * (1 - k ** 1.7) ** 0.75)


def plan(cal):
    nw = len(cal)
    gap = 3.4
    P = min(17.0, (W - 62 + gap) / nw)
    cs = round(P - gap, 2)
    x0 = (W - (34 + nw * P - gap)) / 2 + 34
    y0 = 24
    H = math.ceil(y0 + 7 * P - gap + 14)
    R = P / 2  # tightest turn, a u-turn between two columns
    center = lambda c, r: (x0 + c * P + cs / 2, y0 + r * P + cs / 2)
    cell_of = lambda x, y: (round((x - x0 - cs / 2) / P), round((y - y0 - cs / 2) / P))
    food = [(c, r) for c, w in enumerate(cal) for r, d in enumerate(w) if d and d[1]]
    y3 = center(0, 3)[1]
    order = tour(food, (-2.5, 3), nw) if food else []
    rank = {c: k for k, c in enumerate(order)}

    # waypoints: in from the left, every cell, going round uneaten food on the longer hops
    way, busy, cur = [((-40, y3), -1, False)], set(order), (-3, 3)
    for k, c in enumerate(order):
        if max(abs(c[0] - cur[0]), abs(c[1] - cur[1])) > 1:
            walk = [center(*x) for x in corridor(cur, c, busy, nw)]
            block = [center(*x) for x in busy if x != c]
            way += [(p, k, False) for p in pull(walk, block, 0.55 * P)[1:-1]]
        way.append((center(*c), k, True))
        busy.discard(c)
        cur = c

    # how early to turn for the next one, and which side to loop to on a hairpin
    steer, prev = [], (-90, y3)
    for i, (b, k, eat) in enumerate(way):
        nxt = way[i + 1][0] if i + 1 < len(way) else None
        u = ((b[0] - prev[0]) / (dist(prev, b) or 1), (b[1] - prev[1]) / (dist(prev, b) or 1))
        th = 0
        if nxt:
            o = ((nxt[0] - b[0]) / (dist(b, nxt) or 1), (nxt[1] - b[1]) / (dist(b, nxt) or 1))
            th = math.acos(max(-1, min(1, u[0] * o[0] + u[1] * o[1])))
        reach = max(2, min(R * math.tan(min(th, 3.1) / 2), 6 if eat or th > 1.75 else 0.6 * P))
        pref = None
        if th > 2:
            best = 9
            for s in (1, -1):
                n = (-u[1] * s, u[0] * s)
                c, r = cell_of(b[0] + n[0] * P, b[1] + n[1] * P)
                cost = 1.5 if r > 6 else 1 if r < 0 else 2 if rank.get((c, r), -1) > k - (0 if eat else 0.5) else 0
                cost -= 0.5 if n[0] * (nxt[0] - b[0]) + n[1] * (nxt[1] - b[1]) > 0 else 0
                if cost < best:
                    best, pref = cost, n
        steer.append((b[0], b[1], reach, pref, eat))
        prev = b
    pts, bend, ang = drive((-90, y3), 0.0, steer, R)

    # leave by whichever side is the shorter drive from here, turning round included
    ex = pts[-1]
    pref = (0, 1 if ex[1] < y3 - 1 else -1)
    outs = []
    for side in ((1,) if not order else (-1, 1)):
        x = -30 if side < 0 else W + 30
        outs.append(drive(ex, ang, [(x, ex[1], 2, pref, False), (x + 40 * side, ex[1], 2, None, False)], R)[:2])
    tail_pts, tail_bend = min(outs, key=lambda o: len(o[0]))
    pts += tail_pts[1:]
    bend += tail_bend[1:]

    waved = wiggle(smooth(pts), bend)
    path, segs, dense = bezier(resample(waved, 4.0))
    L = sum(segs)

    # a cell is eaten the moment the head covers its centre, wherever along the path that is
    fs, hit, near = set(food), {}, {}
    for i, (x, y, s) in enumerate(dense):
        a, b = dense[max(i - 3, 0)], dense[min(i + 3, len(dense) - 1)]
        n = math.hypot(b[0] - a[0], b[1] - a[1]) or 1
        for k in (-4, -1, 2, 5, 8, 11):
            px, py = x + k * (b[0] - a[0]) / n, y + k * (b[1] - a[1]) / n
            c = cell_of(px, py)
            if c in fs and c not in hit:
                cx, cy = center(*c)
                e = math.hypot(px - cx, py - cy)
                if e < EAT:
                    hit[c] = s
                elif e < near.get(c, (1e9, 0))[0]:
                    near[c] = (e, s)
    # the snake is gone once its tail is off the picture
    s_off = next((s for x, y, s in reversed(dense) if -12 < x < W + 12), L)

    # speed scales with the amount of food so a busy year doesn't take forever
    t0 = 0.5
    want = min(50, max(28, 22 + 0.1 * len(order)))
    v = min(240, max(110, L / want))
    te = {}
    for c in food:
        s = hit[c] if c in hit else near[c][1] if c in near else None
        te[c] = None if s is None else t0 + s / v
    gone = t0 + (s_off + 1.5 + SEGS * SP1 + 14) / v
    fade = gone + 1.5
    T = round(fade + 0.6 + 0.45 + 0.4, 2)
    meals = sorted((t, c) for c, t in te.items() if t is not None)

    # growth: spacing between segments goes up as it eats
    grow = [(0, SP0)]
    if meals:
        m = 8
        for k in range(m + 1):
            t = meals[min(len(meals) - 1, k * (len(meals) - 1) // m)][0]
            if t > grow[-1][0] + 0.05:
                grow.append((t, SP0 + (SP1 - SP0) * k / m))
        grow[-1] = (grow[-1][0], SP1)
    grow.append((T, grow[-1][1]))

    def seg_keys(gap0, mul):
        kn = [(t, v * (t - t0) - gap0 - mul * sp) for t, sp in grow]
        return fmt_keys(T, keys(kn, L), L)

    head = fmt_keys(T, keys([(0, -v * t0), (T, v * (T - t0))], L), L)
    body = [seg_keys(1.5, i) for i in range(1, SEGS + 1)]

    # the darkest cells are big meals, you can watch them slide down the body
    gulps = []
    for t, (c, r) in meals:
        if cal[c][r][1] == 4 and (not gulps or t > gulps[-1][0] + 0.6):
            s0, s1 = v * (t - t0) - 12, v * (t + 2.4 - t0) - 12 - 2.4 * 44
            gulps.append((t, fmt_keys(T, keys([(0, s0), (t, s0), (t + 2.4, s1), (T, s1)], L), L)))

    cells = {}
    for c, w in enumerate(cal):
        for r, d in enumerate(w):
            if d:
                cells[(c, r)] = [d[1], te.get((c, r))]
    return dict(cal=cal, P=P, cs=cs, x0=x0, y0=y0, H=H, center=center, path=path, L=L, T=T,
                head=head, body=body, gulps=gulps, cells=cells, fade=fade, gone=gone, t0=t0, v=v)


def n2(x, k=2):
    t = f"{x:.{k}f}".rstrip("0").rstrip(".")
    t = t.replace("0.", ".", 1) if t.startswith(("0.", "-0.")) else t
    return "0" if t in ("", "-0") else t


def n5(x):
    return n2(x, 5)


def times(T, pts):
    # list of (time, value) to keyTimes/values, times clamped and kept increasing
    kt, vals, last = [], [], -1
    for t, val in pts:
        f = round(min(max(t / T, 0), 1), 5)
        if f <= last:
            f = round(last + 0.00001, 5)
        kt.append(n5(f))
        vals.append(val)
        last = f
    kt[0], kt[-1] = "0", "1"
    return ";".join(kt), ";".join(vals)


def grid(pl, th):
    T, P, cs, x0, y0 = pl["T"], pl["P"], pl["cs"], pl["x0"], pl["y0"]
    h, rr = n2(cs / 2), n2(cs * 0.2)
    out = [f'<g font-family="{FONT}" font-size="10" fill="{th["label"]}">']
    last = -9
    for c, w in enumerate(pl["cal"]):
        d = next((x for x in w if x), None)
        if d and (c == 0 or d[0].day <= 7) and x0 + c * P + 22 <= W:
            if c - last < 3 and out[-1].startswith("<text"):
                out.pop()
            out.append(f'<text x="{n2(x0 + c * P)}" y="{n2(y0 - 7)}">{MONTHS[d[0].month - 1]}</text>')
            last = c
    for r, name in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        out.append(f'<text x="{n2(x0 - 7)}" y="{n2(y0 + r * P + cs / 2 + 3.5)}" text-anchor="end">{name}</text>')
    out.append("</g>")
    empty = th["cells"][0]
    out.append(f'<g fill="{empty}">')
    for (c, r) in sorted(pl["cells"]):
        out.append(f'<rect x="{n2(x0 + c * P)}" y="{n2(y0 + r * P)}" width="{n2(cs)}" height="{n2(cs)}" rx="{rr}"/>')
    out.append("</g>")
    rings = []
    for (c, r), (lvl, t) in sorted(pl["cells"].items()):
        if not lvl:
            continue
        col = th["cells"][lvl]
        cx, cy = pl["center"](c, r)
        back = pl["fade"] + 0.6 * c / len(pl["cal"])
        if t is None:
            t = back - 1
        kt, vals = times(T, [(0, col), (t, col), (t + 0.06, th["flash"]), (t + 0.28, empty),
                             (back, empty), (back + 0.45, col), (T, col)])
        fill = f'<animate attributeName="fill" dur="{T}s" repeatCount="indefinite" keyTimes="{kt}" values="{vals}"/>'
        kt, vals = times(T, [(0, "1"), (t, "1"), (t + 0.07, "1.32"), (t + 0.28, ".86"), (t + 0.4, "1"),
                             (back, "1"), (back + .01, ".35"), (back + 0.45, "1.12"), (back + 0.6, "1"), (T, "1")])
        size = (f'<animateTransform attributeName="transform" type="scale" dur="{T}s" repeatCount="indefinite" '
                f'keyTimes="{kt}" values="{vals}"/>')
        out.append(f'<g transform="translate({n2(cx)} {n2(cy)})"><rect x="-{h}" y="-{h}" width="{n2(cs)}" '
                   f'height="{n2(cs)}" rx="{rr}" fill="{col}">{fill}{size}</rect></g>')
        # a little ring puffs out where it bit
        kt, vals = times(T, [(0, "0"), (t, "0"), (t + 0.02, ".9"), (t + 0.42, "0"), (T, "0")])
        kt2, r2 = times(T, [(0, "3"), (t, "3"), (t + 0.42, n2(cs * 0.95)), (T, n2(cs * 0.95))])
        rings.append(f'<circle cx="{n2(cx)}" cy="{n2(cy)}" r="3" opacity="0">'
                     f'<animate attributeName="opacity" dur="{T}s" repeatCount="indefinite" keyTimes="{kt}" values="{vals}"/>'
                     f'<animate attributeName="r" dur="{T}s" repeatCount="indefinite" keyTimes="{kt2}" values="{r2}"/></circle>')
    out.append(f'<g fill="none" stroke="{th["puff"]}" stroke-width="1.2">' + "".join(rings) + "</g>")
    return out


def motion(T, k):
    return (f'<animateMotion dur="{T}s" repeatCount="indefinite" calcMode="linear" rotate="auto" '
            f'keyTimes="{k[0]}" keyPoints="{k[1]}"><mpath xlink:href="#p"/></animateMotion>')


def strip(rx, w, h0, h1, col):
    # only the strip of a segment behind the next one shows, so markings are drawn as that strip,
    # h0 wide at its back edge and h1 where the next segment covers it
    a, b = -rx * math.sqrt(1 - (h0 / w) ** 2), -rx * math.sqrt(1 - (h1 / w) ** 2) + 3.5
    return (f'<path d="M{n2(a)} {n2(-h0)}A{n2(rx)} {n2(w)} 0 0 0 {n2(a)} {n2(h0)}L{n2(b)} {n2(h1)}'
            f'A{n2(rx)} {n2(w)} 0 0 1 {n2(b)} {n2(-h1)}z" fill="{col}"/>')


def snake(pl, th):
    T = pl["T"]
    out = []
    for t, k in pl["gulps"]:
        kt, vals = times(T, [(0, "0"), (t, "0"), (t + 0.2, "1"), (t + 1.7, "1"), (t + 2.4, "0"), (T, "0")])
        out.append(f'<g>{motion(T, k)}<ellipse rx="6.2" ry="{n2(FAT + 1.3)}" fill="url(#b)" transform="scale(0)">'
                   f'<animateTransform attributeName="transform" type="scale" dur="{T}s" repeatCount="indefinite" '
                   f'keyTimes="{kt}" values="{vals}"/></ellipse></g>')
    # body, tail first so every scale overlaps the one behind it
    for i in range(SEGS, 0, -1):
        u = i / SEGS
        w = body_width(u)
        rx = max(w * 0.92, 4.6 - 1.2 * u)
        g = [motion(T, pl["body"][i - 1]), f'<ellipse rx="{n2(rx)}" ry="{n2(w)}" fill="url(#b)"/>']
        ph = (i - 4) % 11
        if i >= 4 and u < 0.93 and ph < 8:
            for prof, col in ((RIM, th["ring"]), (DARK, th["mark"])):
                if prof[ph] or prof[ph + 1]:
                    g.append(strip(rx, w, w * prof[ph + 1], w * prof[ph], col))
        elif i >= 4 and u < 0.9 and ph == 9:
            for s in (-1, 1):
                g.append(f'<ellipse cx="{n2(-rx * 0.6 + 1.5)}" cy="{n2(s * w * 0.72)}" rx="1.5" ry="{n2(w * 0.17)}" fill="{th["mark"]}" opacity=".75"/>')
        # glossy scale dots, staggered
        if u < 0.9:
            for f in ((0.3, -0.3) if i % 2 else (0.62, -0.62)):
                xr = -rx * math.sqrt(1 - f * f) + 1.1
                g.append(f'<ellipse cx="{n2(xr)}" cy="{n2(w * f)}" rx=".6" ry="{n2(max(.3, w * .07))}" fill="{th["dots"]}" opacity=".3"/>')
        out.append("<g>" + "".join(g) + "</g>")
    # head, pointing +x
    eye = lambda s: (f'<ellipse cx="3.2" cy="{s * 3.7}" rx="2.9" ry="1.25" fill="{th["mark"]}" opacity=".45"/>'
                     f'<g transform="translate(3.6 {s * 5.6})"><ellipse rx="2.6" ry="2.2" fill="url(#e)" stroke="{th["line"]}" stroke-width=".55"/>'
                     f'<ellipse rx=".45" ry="1.7" fill="#0a0212"/><circle cx=".75" cy="{-s * .8}" r=".55" fill="#fff"/></g>')
    out.append(
        "<g>" + motion(T, pl["head"]) +
        f'<g transform="translate(11 0)" stroke="{th["tongue"]}" stroke-width=".85" stroke-linecap="round" stroke-linejoin="round" fill="none"><path d="M0 0h8.6l3.1-2.3M8.6 0l3.1 2.3">'
        f'{tongue(pl)}</path></g>'
        # spade shaped head, the open end tucks into the neck
        f'<path d="M-8.5-4.5C-6-4.8-4.5-8.2-.5-8.2c5 0 10.5 3.6 12.3 5.8.8 1 .8 3.8 0 4.8C10 4.6 4.5 8.2-.5 8.2-4.5 8.2-6 4.8-8.5 4.5" '
        f'fill="url(#b)" stroke="{th["line"]}" stroke-width=".6"/>'
        f'<path d="M-2.5-7.2C3-7.4 8.4-4.6 10.9-2M-2.5 7.2C3 7.4 8.4 4.6 10.9 2" stroke="{th["ring"]}" stroke-width=".5" fill="none" opacity=".6"/>'
        f'<path d="M-7.5-3 4.4 0-7.5 3-5 0z" fill="{th["mark"]}" opacity=".85"/>'
        f'<path d="M-6.6-4.8C-2-4.2 2-3.2 6.6-1.4M-6.6 4.8C-2 4.2 2 3.2 6.6 1.4" stroke="{th["ring"]}" stroke-width=".7" fill="none" opacity=".5"/>'
        f'<path d="M5.8-2.7 8.6-1.25v2.5L5.8 2.7" stroke="{th["line"]}" stroke-width=".35" fill="none" opacity=".5"/>'
        f'<ellipse cx="2" rx="5.5" ry="2.4" fill="{th["dots"]}" opacity=".18"/>'
        + eye(-1) + eye(1) +
        f'<ellipse cx="10.5" cy="-1.6" rx=".62" ry=".4" fill="#0a0212"/><ellipse cx="10.5" cy="1.6" rx=".62" ry=".4" fill="#0a0212"/>'
        "</g>")
    return out


def tongue(pl):
    # flick roughly every 1.2 s while the head is on screen, all on the main clock
    T, pts, t = pl["T"], [(0, "0 1")], pl["t0"] + 0.4
    while t + 0.4 < pl["gone"]:
        pts += [(t, "0 1"), (t + 0.07, "1 1"), (t + 0.12, ".86 .45"), (t + 0.17, "1 1"), (t + 0.22, ".86 .45"),
                (t + 0.27, "1 1"), (t + 0.35, "0 1")]
        t += 1.05 + 0.35 * ((t * 7.3) % 1)
    pts.append((T, "0 1"))
    kt, vals = times(T, pts)
    return (f'<animateTransform attributeName="transform" type="scale" additive="sum" dur="{T}s" '
            f'repeatCount="indefinite" keyTimes="{kt}" values="{vals}"/>')


def render(pl, th):
    T, H = pl["T"], pl["H"]
    b, sh = th["body"], th["shadow"]
    rgb = [n2(int(sh[0][k:k + 2], 16) / 255) for k in (1, 3, 5)]
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
           f'viewBox="0 0 {W} {H}" width="{W}" height="{H}">',
           "<defs>",
           f'<path id="p" d="{pl["path"]}"/>',
           f'<linearGradient id="b" x2="0" y2="1"><stop offset="0" stop-color="{b[0]}"/><stop offset=".15" stop-color="{b[1]}"/>'
           f'<stop offset=".33" stop-color="{b[2]}"/><stop offset=".45" stop-color="{b[3]}"/><stop offset=".5" stop-color="{b[4]}"/>'
           f'<stop offset=".55" stop-color="{b[3]}"/><stop offset=".67" stop-color="{b[2]}"/><stop offset=".85" stop-color="{b[1]}"/>'
           f'<stop offset="1" stop-color="{b[0]}"/></linearGradient>',
           f'<radialGradient id="e" cx=".4" cy=".4"><stop offset="0" stop-color="#fffbe6"/><stop offset=".45" stop-color="{th["eye"]}"/>'
           f'<stop offset="1" stop-color="{th["eye2"]}"/></radialGradient>',
           f'<filter id="f" x="-50%" y="-50%" width="200%" height="200%" color-interpolation-filters="sRGB">'
           f'<feColorMatrix values="0 0 0 0 {rgb[0]} 0 0 0 0 {rgb[1]} 0 0 0 0 {rgb[2]} 0 0 0 {sh[1]} 0"/>'
           f'<feGaussianBlur stdDeviation="{sh[2]}"/></filter>',
           "</defs>"]
    out += grid(pl, th)
    # soft shadow (a glow on dark pages) from a flat copy of the snake
    out.append(f'<use xlink:href="#s" transform="translate({sh[3][0]} {sh[3][1]})" filter="url(#f)"/>')
    out.append('<g id="s">' + "".join(snake(pl, th)) + "</g>")
    out.append("</svg>")
    return "\n".join(out) + "\n"


def save(paths, texts):
    # write both to temp files first, then swap them in, so a failure never leaves a mixed pair
    done = []
    try:
        for path, text in zip(paths, texts):
            if os.path.isdir(path):
                raise IsADirectoryError("it is a directory")
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            with open(path + ".tmp", "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
            done.append(path + ".tmp")
        for path in paths:
            os.replace(path + ".tmp", path)
    except OSError as e:
        for tmp in done:
            try:
                os.remove(tmp)
            except OSError:
                pass
        die(f"could not write {path}: {e}")


def main():
    args = [a for a in sys.argv[1:] if a != "--demo"]
    if len(args) != 2:
        die("usage: snake.py [--demo] light.svg dark.svg")
    if "--demo" in sys.argv or os.environ.get("SNAKE_DEMO") == "1":
        cal = demo()
    else:
        cal = fetch(os.environ.get("GITHUB_REPOSITORY_OWNER") or "LATRECHE-A")
    pl = plan(cal)
    svgs = [render(pl, THEMES[name]) for name in ("light", "dark")]
    save(args, svgs)
    eaten = sum(1 for lvl, t in pl["cells"].values() if lvl)
    print(f"snake: {eaten} cells, {pl['L']:.0f}px path, {pl['T']}s loop")


if __name__ == "__main__":
    main()
