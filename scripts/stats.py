import datetime as dt
import http.client
import json
import os
import sys
import time
import urllib.error
import urllib.request
from xml.dom import minidom
from xml.parsers.expat import ExpatError

# edit these freely
USER = "lth-a"
HOST = "archlinux"
DESCRIPTION = "builds websites, bots and tools, mostly at night"
DEPENDS = ["coffee", "neovim", "pacman", "penguins"]
OPT_DEPS = ("polar-bear", "emotional support")
CONFLICTS = ["windows-update", "mornings"]
# the optional dep, sleeping in the corner. set to "" to evict him
BEAR = r"""
    _       _
   (_)-----(_)
   /  -   -  \
  |     o     |
   \  `---'  /
  .-`-.___.-`-.
 (_____) (_____)
"""

FONT = "ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', 'DejaVu Sans Mono', monospace"
FS = 14
LH = 17.5
CW = 0.62 * FS  # widest glyph we plan for
W = 960
PAD = 24
TOP = 34
CELLS = 20

C = dict(text="#c9d4e5", dim="#5f6f89", blue="#1793d1", cyan="#5cc8ff", green="#7ee787",
         red="#ff7b72", white="#f0f6fc", empty="#1a2638")

QUERY = """
query($login: String!, $after: String, $privacy: RepositoryPrivacy) {
  user(login: $login) {
    createdAt
    followers { totalCount }
    repositories(ownerAffiliations: OWNER, isFork: false, privacy: $privacy, first: 100, after: $after) {
      pageInfo { hasNextPage endCursor }
      nodes {
        stargazerCount
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) { edges { size node { name color } } }
      }
    }
    contributionsCollection {
      contributionCalendar { totalContributions weeks { contributionDays { date contributionCount } } }
    }
  }
}"""

DAYS = "contributionCalendar { weeks { contributionDays { date contributionCount } } }"


def die(msg):
    print(f"stats: {msg}", file=sys.stderr)
    sys.exit(1)


def gql(token, query, variables):
    body = json.dumps({"query": query, "variables": variables}).encode()
    headers = {"Authorization": f"bearer {token}", "Content-Type": "application/json",
               "User-Agent": "profile-stats"}
    for attempt in range(3):
        time.sleep(5 * attempt)
        try:
            req = urllib.request.Request("https://api.github.com/graphql", data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as r:
                res = json.load(r)
            break
        except urllib.error.HTTPError as e:
            err = f"github api returned {e.code}: {e.read().decode(errors='replace')[:300]}"
            if e.code == 401:
                raise PermissionError(err)
            if e.code < 500:
                die(err)
        except (OSError, http.client.HTTPException, ValueError) as e:  # api hiccups, try again
            err = f"could not talk to github api: {e!r}"
    else:
        die(err)
    if res.get("errors"):
        die("graphql error: " + "; ".join(e.get("message", "?") for e in res["errors"]))
    if not (res.get("data") or {}).get("user"):
        die(f"user {variables['login']} not found")
    return res["data"]["user"]


def days_of(cal):
    return {dt.date.fromisoformat(d["date"]): d["contributionCount"]
            for w in cal["weeks"] for d in w["contributionDays"]}


def fetch(token, login, public_only):
    var = {"login": login, "privacy": "PUBLIC" if public_only else None}
    user, repos = None, []
    while True:
        u = gql(token, QUERY, var)
        user = user or u
        repos += u["repositories"]["nodes"]
        page = u["repositories"]["pageInfo"]
        if not page["hasNextPage"]:
            break
        var["after"] = page["endCursor"]

    cal = user["contributionsCollection"]["contributionCalendar"]
    days = days_of(cal)
    if not days:
        die("contribution calendar came back empty")

    # the calendar only covers the last year, older years matter for the longest streak
    start = min(days)
    created = dt.datetime.fromisoformat(user["createdAt"].replace("Z", "+00:00")).date()
    parts = []
    for y in range(created.year, start.year + 1):
        a, b = max(created, dt.date(y, 1, 1)), min(start - dt.timedelta(days=1), dt.date(y, 12, 31))
        if a <= b:
            parts.append(f'y{y}: contributionsCollection(from: "{a}T00:00:00Z", to: "{b}T23:59:59Z") {{ {DAYS} }}')
    if parts:
        old = gql(token, "query($login: String!) { user(login: $login) { " + " ".join(parts) + " } }",
                  {"login": login})
        for v in old.values():
            for d, n in days_of(v["contributionCalendar"]).items():
                days.setdefault(d, n)
    return user, repos, cal["totalContributions"], days


def streaks(days):
    d, last = min(days), max(days)
    run = longest = 0
    while d <= last:
        run = run + 1 if days.get(d) else 0
        longest = max(longest, run)
        d += dt.timedelta(days=1)
    d = last if days[last] else last - dt.timedelta(days=1)  # today is not over yet
    cur = 0
    while days.get(d):
        cur += 1
        d -= dt.timedelta(days=1)
    return cur, longest


def languages(repos):
    size, color = {}, {}
    for r in repos:
        for e in r["languages"]["edges"]:
            name = e["node"]["name"]
            size[name] = size.get(name, 0) + e["size"]
            color[name] = e["node"]["color"] or C["text"]
    total = sum(size.values())
    top = sorted(size.items(), key=lambda x: -x[1])[:5]
    return [(n, color[n], 100 * s / total) for n, s in top], total


def human(n):
    for unit in ["B", "KiB", "MiB"]:
        if round(n, 2) < 1024:
            break
        n /= 1024
    else:
        unit = "GiB"
    return f"{n:.2f} {unit}" if unit != "B" else f"{n} B"


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def span(s, color=None, cls=None):
    attrs = (f' fill="{color}"' if color else "") + (f' class="{cls}"' if cls else "")
    return f"<tspan{attrs}>{esc(s)}</tspan>" if attrs else esc(s)


def text(x, y, inner, extra=""):
    if "  " in inner or inner[:1] == " " or inner[-1:] == " ":
        extra += ' xml:space="preserve"'
    return f'<text x="{x:.1f}" y="{y:.1f}"{extra}>{inner}</text>'


def prompt(cmd=None):
    out = span(USER, C["blue"], "b") + "@" + esc(HOST) + span(" ~", C["cyan"]) + span(" $ ", C["dim"])
    if not cmd:
        return out + f'<tspan fill="{C["text"]}" class="cur">&#9608;</tspan>'
    keys = "".join(f'<tspan class="key" style="animation-delay:{0.5 + i * 0.055:.2f}s">{esc(ch)}</tspan>'
                   for i, ch in enumerate(cmd))
    return out + f'<tspan fill="{C["white"]}">{keys}</tspan>'


def render(login, user, repos, total, days):
    cur, longest = streaks(days)
    langs, code = languages(repos)
    stars = sum(r["stargazerCount"] for r in repos)
    created = dt.datetime.fromisoformat(user["createdAt"].replace("Z", "+00:00"))
    today = dt.datetime.now(dt.timezone.utc)
    num = lambda n: span(f"{n:,}", C["cyan"])
    count = lambda n, w: num(n) + span(f" {w}" + ("" if n == 1 else "s"), C["dim"])

    rows = [
        ("Name", esc(USER)),
        ("Version", today.strftime("%Y.%m.%d") + "-1" + span(" (rolling release)", C["dim"])),
        ("Description", esc(DESCRIPTION)),
        ("URL", esc(f"https://github.com/{login}")),
        ("Depends On", esc("  ".join(DEPENDS))),
        ("Optional Deps", span(OPT_DEPS[0], C["white"]) + esc(": " + OPT_DEPS[1]) + span(" [installed]", C["green"])),
    ]
    if CONFLICTS:
        rows.append(("Conflicts With", span("  ".join(CONFLICTS), C["red"])))
    rows += [
        ("Contributions", num(total) + span(" in the last year", C["dim"])),
        ("Current Streak", count(cur, "day") + (span("  (touching grass)", C["dim"]) if cur == 0 else "")),
        ("Longest Streak", count(longest, "day")),
        ("Repositories", num(len(repos))),
        ("Stars", num(stars)),
        ("Followers", num(user["followers"]["totalCount"])),
        ("Languages", None),
        ("Installed Size", span(human(code), C["cyan"]) + span(" of code", C["dim"])),
        ("Install Date", created.strftime("%a %d %b %Y")),
    ]

    # every column gets its own x, sized for the widest font a visitor might have
    colon_x = PAD + (max(len(k) for k, _ in rows) + 1) * CW
    val_x = colon_x + 2 * CW
    bar_x = val_x + (max([len(n) for n, _, _ in langs] or [0]) + 2) * CW
    pct_x = bar_x + CELLS * 9 + 7 * CW

    lines = []
    y = TOP + PAD + FS * 0.8
    lines.append(text(PAD, y, prompt("pacman -Qi " + USER)))
    for k, v in rows:
        y += LH
        head = text(PAD, y, k, f' fill="{C["blue"]}"') + text(colon_x, y, ":", f' fill="{C["dim"]}"')
        if v is not None or not langs:
            lines.append(head + text(val_x, y, v or span("None", C["dim"])))
            continue
        for i, (name, color, pct) in enumerate(langs):
            if i:
                y += LH
                head = ""
            # empty track first, then the colored cells light up one by one
            t = 1.8 + len(lines) * 0.07
            cell = lambda j, fill, extra="": (f'<rect x="{bar_x + j * 9:.1f}" y="{y - 10:.1f}" width="8" '
                                              f'height="11" fill="{fill}"{extra}/>')
            cells = "".join(cell(j, C["empty"]) for j in range(CELLS)) + "".join(
                cell(j, color, f' class="px" style="animation-delay:{t + j * 0.04:.2f}s"')
                for j in range(max(1, round(pct / 100 * CELLS))))
            lines.append(head + text(val_x, y, esc(name)) + cells
                         + text(pct_x, y, span(f"{pct:.1f}%", C["cyan"]), ' text-anchor="end"'))
    y += LH * 2
    end = 1.6 + len(lines) * 0.07
    lines.append(text(PAD, y, prompt()))
    h = round(y + PAD + FS * 0.4)

    body = [f'<g>{lines[0]}</g>'] + [
        f'<g class="ln" style="animation-delay:{1.6 + i * 0.07:.2f}s">{ln}</g>' for i, ln in enumerate(lines[1:])]

    art = [ln for ln in BEAR.split("\n") if ln.strip()]
    if art:
        bx = W - PAD - 6 * CW - max(map(len, art)) * CW
        by = y - (len(art) - 1) * LH
        bear = "".join(text(bx, by + i * LH, esc(ln)) for i, ln in enumerate(art))
        zx = bx + (len(art[0].rstrip()) + 1) * CW
        zs = "".join(f'<text x="{zx:.1f}" y="{by - 2:.1f}" class="z" style="animation-delay:{end + i:.2f}s;'
                     f'font-size:{11 + 2 * i}px">z</text>' for i in range(3))
        body.append(f'<g class="ln" fill="{C["white"]}" style="animation-delay:{end:.2f}s">{bear}</g>'
                    f'<g fill="{C["cyan"]}">{zs}</g>')

    pl = lambda n, w: f"{n:,} {w}" + ("" if n == 1 else "s")
    alt = (f"pacman -Qi {USER}: {pl(total, 'contribution')} in the last year, current streak {pl(cur, 'day')}, "
           f"longest streak {pl(longest, 'day')}, {pl(len(repos), 'repo')}, {pl(stars, 'star')}, "
           f"top languages {', '.join(n for n, _, _ in langs) or 'none'}")
    css = (f"text{{font-family:{FONT};font-size:{FS}px}}"
           ".b{font-weight:700}"
           ".ln{animation:ln .3s ease-out both}"
           ".key{animation:key .01s both}"
           ".px{animation:px .12s both}"
           ".cur{animation:cur 1.1s step-end infinite}"
           ".z{opacity:0;animation:z 3s linear infinite}"
           "@keyframes ln{from{opacity:0;transform:translateY(5px)}}"
           "@keyframes key{from{visibility:hidden}}"
           "@keyframes px{from{opacity:0}}"
           "@keyframes cur{50%{visibility:hidden}}"
           "@keyframes z{0%{opacity:0;transform:translate(0,0)}25%{opacity:1}"
           "100%{opacity:0;transform:translate(14px,-34px)}}"
           "@media (prefers-reduced-motion:reduce){.ln,.key,.px,.cur{animation:none}.z{display:none}}")
    r = 12
    return "\n".join([
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{h}" viewBox="0 0 {W} {h}" '
        f'fill="{C["text"]}" role="img" aria-labelledby="t">',
        f'<title id="t">{esc(alt)}</title>',
        f"<style>{css}</style>",
        f'<rect x=".5" y=".5" width="{W - 1}" height="{h - 1}" rx="{r}" fill="#0b1220" stroke="#1f2a3c"/>',
        f'<path d="M.5 {TOP}V{r + .5}A{r} {r} 0 0 1 {r + .5} .5H{W - r - .5}A{r} {r} 0 0 1 {W - .5} {r + .5}V{TOP}Z" '
        f'fill="#111a2b" stroke="#1f2a3c"/>',
        '<circle cx="20" cy="17" r="6" fill="#ff5f57"/><circle cx="40" cy="17" r="6" fill="#febc2e"/>'
        '<circle cx="60" cy="17" r="6" fill="#28c840"/>',
        f'<text x="{W / 2:.0f}" y="21.5" text-anchor="middle" fill="#7d8ca6" style="font-size:13px">'
        f'{esc(USER)}@{esc(HOST)}: ~</text>',
        *body,
        "</svg>",
    ]) + "\n"


def main():
    if len(sys.argv) != 2:
        die("usage: python3 scripts/stats.py <out.svg>")
    out = sys.argv[1]
    tokens = [t for t in dict.fromkeys([os.environ.get("STATS_TOKEN"), os.environ.get("GITHUB_TOKEN")]) if t]
    if not tokens:
        die("no token, set STATS_TOKEN or GITHUB_TOKEN")
    login = os.environ.get("GITHUB_REPOSITORY_OWNER") or "LATRECHE-A"
    public_only = os.environ.get("STATS_PUBLIC_ONLY") == "1"

    for token in tokens:
        try:
            data = fetch(token, login, public_only)
            break
        except PermissionError as e:
            err = e
            if token != tokens[-1]:
                # expired or revoked secret, a public only card beats a frozen one
                print("::warning::STATS_TOKEN was rejected (expired?), falling back to GITHUB_TOKEN", flush=True)
    else:
        die(err)

    svg = render(login, *data)
    try:
        minidom.parseString(svg)
    except ExpatError as e:
        die(f"rendered svg is not valid xml ({e}), check the constants at the top")

    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out + ".tmp", "w", encoding="utf-8", newline="\n") as f:
        f.write(svg)
    os.replace(out + ".tmp", out)
    print(f"wrote {out} ({len(svg.encode()) / 1024:.1f} KiB)")


if __name__ == "__main__":
    main()
