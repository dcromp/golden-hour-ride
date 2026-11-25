"""Adds what the lidar surface model and Ordnance Survey footprints know to assets/<course>_osm.js:
every building at its surveyed height, and the hedges and trees along the road where they really stand.

Heights above ground: Environment Agency LiDAR Composite first-return surface model (trees, hedges and roofs included)
  minus the bare-earth model already in assets/<course>.js. Open Government Licence.
Building footprints: OS OpenMap Local (Ordnance Survey, Open Government Licence). Download the ESRI Shapefile zip for the
  course's 100 km square from https://osdatahub.os.uk/downloads/open/OpenMapLocal and unzip it into tools/.cache/os/.
  Without it, the OpenStreetMap buildings already in the file are kept and only given their surveyed heights.
Run after build_course.py and build_course_osm.py:  python3 tools/build_course_surface.py tiptree
"""
import base64, glob, json, math, os, struct, sys, time, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor

KEY = [a for a in sys.argv[1:] if not a.startswith('--')][0] if len(sys.argv) > 1 else 'tiptree'
FETCH_ONLY = '--fetch-only' in sys.argv
course = json.loads(open(f'assets/{KEY}.js').read().split(' = ', 2)[2].rstrip().rstrip(';'))
cE, cN = course['origin']; SIZE, CELLS = course['size'], course['cells']; HALF = SIZE / 2
road = [(p[0], p[2]) for p in course['road']]

# the download and GeoTIFF code from the terrain script, pointed at the surface model
src = open('tools/build_course.py').read()
ns = {'math': math, 'os': os, 'struct': struct, 'time': time, 'urllib': urllib, 'ThreadPoolExecutor': ThreadPoolExecutor,
      'CACHE': 'tools/.cache/dsm', 'UA': {'User-Agent': 'golden-hour-ride-poc'},
      'WCS': 'https://environment.data.gov.uk/geoservices/datasets/df4e3ec3-315e-48aa-aaaf-b5ae74d7b2bb/wcs',
      'COV': 'df4e3ec3-315e-48aa-aaaf-b5ae74d7b2bb__Lidar_Composite_Elevation_FZ_DSM_1m'}
os.makedirs(ns['CACHE'], exist_ok=True)
exec(src[src.index('def get('):src.index('def to_bng')] + src[src.index('def read_tiff'):src.index('# ---- route')], ns)
exec(src[src.index('def to_bng'):src.index('def read_tiff')], ns); to_bng = ns['to_bng']

REACH, TILE, RES = 160, 500, 1            # survey the strip this far either side of the road, at 1 m
surf = ns['Grids'](TILE, RES)
keys = sorted({(math.floor((x + cE + dx) / TILE), math.floor((cN - z + dz) / TILE)) for x, z in road for dx in (-REACH, REACH) for dz in (-REACH, REACH)})
for attempt in range(6):                  # the server times out now and then: ask again for what is missing
    surf.g = {k: v for k, v in surf.g.items() if v}
    surf.need(keys)
    missing = sum(1 for k in keys if not surf.g.get(k))
    print('surface tiles: %d, missing %d' % (len(keys), missing))
    if not missing: break
if FETCH_ONLY: sys.exit()

# ---- the files this adds to
import subprocess
def read_osm(): return json.loads(open(f'assets/{KEY}_osm.js').read().split(' = ', 1)[1].rstrip().rstrip(';'))
osm = read_osm()
if 'surveyed' in osm:                     # already added to: start again from a fresh OpenStreetMap layer
    subprocess.run([sys.executable, 'tools/build_course_osm.py', KEY], check=True, stdout=subprocess.DEVNULL); osm = read_osm()

# ---- ground and surface
raw = base64.b64decode(course['dem']); W = CELLS + 1; CELL = SIZE / CELLS
dem = [course['demMin'] + v / 65535 * (course['demMax'] - course['demMin']) for v in struct.unpack('<%dH' % (W * W), raw)]
def ground(x, z):
    fx = min(CELLS - 1e-6, max(0, (x + HALF) / CELL)); fz = min(CELLS - 1e-6, max(0, (z + HALF) / CELL))
    ix, iz = int(fx), int(fz); u, v = fx - ix, fz - iz; k = iz * W + ix
    return (dem[k] * (1 - u) + dem[k + 1] * u) * (1 - v) + (dem[k + W] * (1 - u) + dem[k + W + 1] * u) * v
def above(x, z):                          # height of whatever stands here above the ground: None where there is no survey
    E, N = x + cE, cN - z; g = surf.g.get((math.floor(E / TILE), math.floor(N / TILE)))
    if not g: return None
    w, h, d = g
    px = min(w - 1, max(0, int((E % TILE) / RES))); py = min(h - 1, max(0, int((TILE - (N % TILE)) / RES)))
    v = d[py * w + px]
    return v - ground(x, z) if -500 < v < 2000 else None

# ---- distance to the ridden road: exact near it, from a coarse grid further out
line = []
for a, b in zip(road, road[1:] + road[:1]):
    n = max(1, round(math.hypot(b[0] - a[0], b[1] - a[1]) / 3))
    line += [(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n) for k in range(n)]
HC = 40; rhash = {}
for p in line: rhash.setdefault((math.floor(p[0] / HC), math.floor(p[1] / HC)), []).append(p)
def road_near(x, z):                      # exact when closer than 40 m, else 99
    cx, cz = math.floor(x / HC), math.floor(z / HC); best = 99 * 99
    for i in (cx - 1, cx, cx + 1):
        for j in (cz - 1, cz, cz + 1):
            for px, pz in rhash.get((i, j), ()):
                d = (px - x) ** 2 + (pz - z) ** 2
                if d < best: best = d
    return math.sqrt(best)
GC = 10; coarse = {}
R = int((REACH + 40) / GC)
for px, pz in line[::2]:
    cx, cz = round(px / GC), round(pz / GC)
    for i in range(cx - R, cx + R + 1):
        for j in range(cz - R, cz + R + 1):
            d = math.hypot(i * GC - px, j * GC - pz)
            if d < coarse.get((i, j), 1e9): coarse[(i, j)] = d
road_far = lambda x, z: coarse.get((round(x / GC), round(z / GC)), 1e9)
road_all = lambda x, z: math.sqrt(min((px - x) ** 2 + (pz - z) ** 2 for px, pz in road))

# ---- the ridden road's width and markings, every road control point (15 m)
# Width: the usual width for the road's class (or OSM's width/lanes tags), narrowed to fit between whatever the lidar
# finds standing beside it (hedges, walls, buildings) with a verge of at least 0.6 m. Markings follow the Traffic Signs
# Manual, chapter 5: no centre line under 5.5 m; diagram 1008 (2 m mark, 4 m gap) at 40 mph or less, 1008.1 (3 m, 6 m)
# above; edge lines (1012.1) on unlit classified roads above 40 mph. [width m, centre 0/1/2, edge 0/1, mph]
CLASS_W = {'trunk': 7.3, 'primary': 7.3, 'secondary': 6.4, 'tertiary': 5.8, 'unclassified': 4.6, 'residential': 5.5, 'living_street': 4.5, 'service': 3.5, 'track': 3.0}
CLASS_MPH = {'residential': 30, 'living_street': 20, 'service': 20}
ways = []
for e in json.load(open(f'tools/.cache/osm_roads_{KEY}.json')).get('elements', []):
    t = e.get('tags', {})
    if e.get('type') != 'way' or 'geometry' not in e or t.get('highway', '').replace('_link', '') not in CLASS_W: continue
    pts = [(E - cE, -(N - cN)) for E, N in (to_bng(p['lat'], p['lon']) for p in e['geometry'])]
    ways.append((t, pts))
whash = {}
for k, (t, pts) in enumerate(ways):
    for (ax, az), (bx, bz) in zip(pts, pts[1:]):
        n = max(1, math.ceil(math.hypot(bx - ax, bz - az) / 4))
        for j in range(n + 1):
            x, z = ax + (bx - ax) * j / n, az + (bz - az) * j / n; whash.setdefault((math.floor(x / 20), math.floor(z / 20)), []).append((x, z, k))
def way_at(x, z):
    best = (15 ** 2, None)
    for i in (-1, 0, 1):
        for j in (-1, 0, 1):
            for px, pz, k in whash.get((math.floor(x / 20) + i, math.floor(z / 20) + j), ()):
                d = (px - x) ** 2 + (pz - z) ** 2
                if d < best[0]: best = (d, k)
    return ways[best[1]][0] if best[1] is not None else {}
def num(v):
    try: return float(str(v).split()[0].replace('m', ''))
    except (ValueError, IndexError): return None

tags, raw = [], []
for k, (x, z) in enumerate(road):
    a, b = road[k - 1], road[(k + 1) % len(road)]; L = math.hypot(b[0] - a[0], b[1] - a[1]) or 1; nx, nz = -(b[1] - a[1]) / L, (b[0] - a[0]) / L
    tags.append(way_at(x, z))
    clear = []
    for side in (-1, 1):                  # how far out the first thing standing more than 0.9 m high is, each side
        hit = 14
        for step in range(3, 29):
            o = step * 0.5; hv = above(x + nx * o * side, z + nz * o * side)
            if hv is not None and hv > 0.9: hit = o; break
        clear.append(hit)
    raw.append(sum(clear) - 1.2)
K = len(road); near = lambda k, r: [(k + d) % K for d in range(-r, r + 1)]
def vote(k, f):                           # the commonest value over 150 m: a junction or a parked car doesn't change the road
    c = {}
    for j in near(k, 5): v = f(tags[j]); c[v] = c.get(v, 0) + 1
    return max(c, key=c.get)
prof = []
for k in range(K):
    cls = vote(k, lambda t: t.get('highway', 'unclassified').replace('_link', ''))
    tw = vote(k, lambda t: num(t.get('width')) or (num(t.get('lanes')) and num(t.get('lanes')) * 3.1) or 0)
    fit = sorted(raw[j] for j in near(k, 5))[7]                      # the room between hedges, ignoring the odd narrow spot
    w = max(3.0, min(tw or CLASS_W.get(cls, 4.6), fit))
    mph = vote(k, lambda t: num(t.get('maxspeed')) or 0) or CLASS_MPH.get(cls, 60)
    nomark = vote(k, lambda t: t.get('lane_markings') == 'no')
    unlit = vote(k, lambda t: t.get('lit') != 'yes')
    prof.append([w, cls, mph, nomark, unlit])
ws = [sum(prof[j][0] for j in near(k, 2)) / 5 for k in range(K)]     # a 75 m average, so the width eases in and out
for k, p in enumerate(prof):
    w, cls, mph, nomark, unlit = p; w = ws[k]
    centre = 0 if w < 5.5 or nomark or cls in ('service', 'track', 'living_street') else (1 if mph <= 40 else 2)
    edge = 1 if cls in ('trunk', 'primary', 'secondary', 'tertiary') and mph > 40 and unlit and w >= 5.5 else 0
    prof[k] = [round(w, 2), centre, edge, int(mph)]
ws = [p[0] for p in prof]
hw_at = lambda x, z: 0                    # filled once the road's half-width can be looked up
print('road width: %.1f to %.1f m (median %.1f); centre line on %d%%, edge lines on %d%% of the loop' % (min(ws), max(ws), sorted(ws)[len(ws) // 2], 100 * sum(1 for p in prof if p[1]) // len(prof), 100 * sum(1 for p in prof if p[2]) // len(prof)))
whw = {}
for (px, pz), p in zip(road, prof): whw.setdefault((math.floor(px / HC), math.floor(pz / HC)), []).append((px, pz, p[0] / 2))
def hw_at(x, z):                          # half-width of the ridden road nearest a point
    best = (1e9, 3.5)
    for i in (-1, 0, 1):
        for j in (-1, 0, 1):
            for px, pz, h in whw.get((math.floor(x / HC) + i, math.floor(z / HC) + j), ()):
                d = (px - x) ** 2 + (pz - z) ** 2
                if d < best[0]: best = (d, h)
    return best[1]

# ---- buildings: OS footprints, cut into rectangles, each at its surveyed height
def shp_polygons(path):
    buf = open(path, 'rb').read(); o = 100
    while o < len(buf):
        size = struct.unpack_from('>i', buf, o + 4)[0] * 2
        if struct.unpack_from('<i', buf, o + 8)[0] == 5:
            x0, y0, x1, y1 = struct.unpack_from('<4d', buf, o + 12)
            if x1 > cE - HALF and x0 < cE + HALF and y1 > cN - HALF and y0 < cN + HALF:
                nparts, npts = struct.unpack_from('<2i', buf, o + 44)
                parts = list(struct.unpack_from('<%di' % nparts, buf, o + 52)) + [npts]
                xy = struct.unpack_from('<%dd' % (npts * 2), buf, o + 52 + nparts * 4)
                yield [(xy[k * 2] - cE, cN - xy[k * 2 + 1]) for k in range(parts[0], parts[1])]      # the outer ring, in local metres
        o += 8 + size

def frame(pts):                           # the direction of the smallest rectangle around a footprint
    best = None
    for (x1, z1), (x2, z2) in zip(pts, pts[1:]):
        L = math.hypot(x2 - x1, z2 - z1)
        if L < 0.5: continue
        ux, uz = (x2 - x1) / L, (z2 - z1) / L
        us = [x * ux + z * uz for x, z in pts]; vs = [-x * uz + z * ux for x, z in pts]
        a = (max(us) - min(us)) * (max(vs) - min(vs))
        if best is None or a < best[0]: best = (a, ux, uz, min(us), max(us), min(vs), max(vs))
    return best
def area(pts): return abs(sum(x1 * z2 - x2 * z1 for (x1, z1), (x2, z2) in zip(pts, pts[1:]))) / 2

def rectangles(pts):                      # a footprint as one to six rectangles: [u0, u1, v0, v1] in its own frame
    f = frame(pts)
    if not f: return None, []
    a, ux, uz, u0, u1, v0, v1 = f
    if a < 9 or area(pts) > 0.82 * a or u1 - u0 > 140 or v1 - v0 > 140: return f, [[u0, u1, v0, v1]]
    nu, nv = math.ceil(u1 - u0), math.ceil(v1 - v0); loc = [(x * ux + z * uz - u0, -x * uz + z * ux - v0) for x, z in pts]
    grid = [[0] * nu for _ in range(nv)]
    for j in range(nv):                   # fill the footprint, one-metre cells
        y = j + 0.5; xs = sorted(x1 + (y - y1) / (y2 - y1) * (x2 - x1) for (x1, y1), (x2, y2) in zip(loc, loc[1:]) if (y1 <= y < y2) or (y2 <= y < y1))
        for xa, xb in zip(xs[::2], xs[1::2]):
            for i in range(max(0, round(xa)), min(nu, round(xb))): grid[j][i] = 1
    total = sum(map(sum, grid)); out = []; left = total
    while left > 0.08 * total and len(out) < 6:
        best = (0, 0, 0, 0, 0); hts = [0] * nu            # the largest rectangle of filled cells still uncovered
        for j in range(nv):
            hts = [hts[i] + 1 if grid[j][i] else 0 for i in range(nu)]; stack = []
            for i in range(nu + 1):
                cur = hts[i] if i < nu else 0; start = i
                while stack and stack[-1][1] >= cur:
                    s0, hh = stack.pop(); start = s0
                    if hh * (i - s0) > best[0]: best = (hh * (i - s0), s0, i, j - hh + 1, j + 1)
                stack.append((start, cur))
        a2, i0, i1, j0, j1 = best
        if a2 < 14 or min(i1 - i0, j1 - j0) < 3: break
        for j in range(j0, j1):
            for i in range(i0, i1): grid[j][i] = 0
        left -= a2; out.append([u0 + i0, u0 + i1, v0 + j0, v0 + j1])
    return f, out or [[u0, u1, v0, v1]]

pct = lambda v, p: sorted(v)[min(len(v) - 1, int(len(v) * p))]
os_file = 'tools/.cache/os/' + next((f for f in os.listdir('tools/.cache/os') if f.endswith('_Building.shp')), '') if os.path.isdir('tools/.cache/os') else ''
footprints = []
if os.path.isfile(os_file):
    buildings = []; measured = 0
    for pts in shp_polygons(os_file):
        cx, cz = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
        if abs(cx) > HALF - 40 or abs(cz) > HALF - 40: continue
        far = road_far(cx, cz)
        if far > 1e8 and road_all(cx, cz) > 700: continue           # never seen from the road
        if far < REACH + 60: footprints.append(pts)
        f, rects = rectangles(pts)
        if not f: continue
        _, ux, uz = f[:3]
        for ru0, ru1, rv0, rv1 in rects:
            w, d, ang = ru1 - ru0, rv1 - rv0, math.atan2(uz, ux)
            cu, cv = (ru0 + ru1) / 2, (rv0 + rv1) / 2; x, z = cu * ux - cv * uz, cu * uz + cv * ux
            if w < 2.5 or d < 2.5 or max(w, d) > 120: continue
            corners = [(x + (a * w / 2) * ux - (b * d / 2) * uz, z + (a * w / 2) * uz + (b * d / 2) * ux) for a, b in ((0, 0), (1, 1), (1, -1), (-1, 1), (-1, -1), (1, 0), (-1, 0), (0, 1), (0, -1))]
            if min(road_near(px, pz) for px, pz in corners) < 4.2: continue           # it would stand on the road
            if w < d: w, d, ang = d, w, ang + math.pi / 2
            hs = []
            for a in range(int(w) + 1):
                for b in range(int(d) + 1):
                    lu, lv = (a + 0.5 - (int(w) + 1) / 2) * 0.86, (b + 0.5 - (int(d) + 1) / 2) * 0.86
                    hv = above(x + lu * math.cos(ang) - lv * math.sin(ang), z + lu * math.sin(ang) + lv * math.cos(ang))
                    if hv is not None: hs.append(hv)
            if len(hs) >= 6 and pct(hs, 0.9) > 1.8:
                top, low = pct(hs, 0.9), pct(hs, 0.3); measured += 1
                pitched = top - low > 0.9 and d <= 16
                h = max(2.3, top - min(4.6, d * 0.42) * 0.92) if pitched else max(2.2, pct(hs, 0.6))
            else: h, pitched = (2.6, False) if w * d < 30 else (5.6, d <= 14)
            buildings.append([round(x, 1), round(z, 1), round(w, 1), round(d, 1), round(ang, 3), round(h, 1), 1 if pitched else 0])
    print('buildings: %d from OS footprints (was %d from OpenStreetMap), %d with a surveyed height' % (len(buildings), len(osm['buildings']), measured))
    osm['buildings'] = buildings
else:
    print('no OS OpenMap Local buildings in tools/.cache/os: keeping the OpenStreetMap ones')

# ---- hedges and trees: whatever stands above the ground beside the road and is not a building or a road
B = 2                                     # worked in two-metre blocks
blocked = set()
def fill(poly):
    zs = [p[1] for p in poly]
    for j in range(math.floor(min(zs)) - 2, math.ceil(max(zs)) + 3):
        y = j + 0.5; xs = sorted(x1 + (y - y1) / (y2 - y1) * (x2 - x1) for (x1, y1), (x2, y2) in zip(poly, poly[1:]) if (y1 <= y < y2) or (y2 <= y < y1))
        for xa, xb in zip(xs[::2], xs[1::2]):
            for i in range(math.floor(xa) - 2, math.ceil(xb) + 3): blocked.add((i // B, j // B))
for pts in footprints: fill(pts)
if not footprints:                        # no OS footprints: keep clear of the OpenStreetMap boxes instead
    for x, z, w, d, ang, h, roof in osm['buildings']:
        c, s = math.cos(ang), math.sin(ang); fill([(x + a * (w / 2 + 1) * c - b * (d / 2 + 1) * s, z + a * (w / 2 + 1) * s + b * (d / 2 + 1) * c) for a, b in ((1, 1), (1, -1), (-1, -1), (-1, 1), (1, 1))])
for w, flat in osm.get('roads', []):
    for k in range(0, len(flat) - 2, 2):
        ax, az, bx, bz = flat[k:k + 4]; n = max(1, math.ceil(math.hypot(bx - ax, bz - az)))
        for t in range(n + 1):
            x, z = ax + (bx - ax) * t / n, az + (bz - az) * t / n; r = math.ceil((w / 2 + 1.2) / B)
            for i in range(-r, r + 1):
                for j in range(-r, r + 1): blocked.add((math.floor(x / B) + i, math.floor(z / B) + j))

veg = {}                                  # block -> height of what grows there
for (ti, tj), g in surf.g.items():
    if not g: continue
    w, h, d = g; n = int(TILE / B); step = int(B / RES)
    for bj in range(n):
        N = (tj + 1) * TILE - (bj + 0.5) * B; z = cN - N
        for bi in range(n):
            x = ti * TILE + (bi + 0.5) * B - cE
            if road_far(x, z) > REACH: continue
            key = (math.floor(x / B), math.floor(z / B))
            if key in blocked: continue
            top = -1e9
            for a in range(step):
                row = (bj * step + a) * w + bi * step
                for v in d[row:row + step]:
                    if v > top: top = v
            if not (-500 < top < 2000): continue
            hgt = top - ground(x, z)
            if hgt > 1.2: veg[key] = min(hgt, 32)
print('surveyed blocks with something growing: %d (%.2f km2)' % (len(veg), len(veg) * B * B / 1e6))

TREE = 4.5; trees = []; SP = 3
for (i, j), hgt in veg.items():
    if hgt < TREE: continue
    top = True
    for a in range(-SP, SP + 1):          # one tree at each high point of the canopy
        for b in range(-SP, SP + 1):
            o = veg.get((i + a, j + b), 0)
            if o > hgt or (o == hgt and (a, b) > (0, 0)): top = False; break
        if not top: break
    x, z = (i + 0.5) * B, (j + 0.5) * B
    if top and road_near(x, z) > hw_at(x, z) + 1.1: trees.append([round(x, 1), round(z, 1), round(hgt, 1)])

HEDGE_REACH = 90; hedges = []
low = {k: v for k, v in veg.items() if v < TREE}
for (i, j), hgt in low.items():
    x, z = (i + 0.5) * B, (j + 0.5) * B
    if road_far(x, z) > HEDGE_REACH + 8: continue
    near = [(a, b) for a in range(-3, 4) for b in range(-3, 4) if (i + a, j + b) in low]
    if len(near) < 3: continue                                    # a stray reading, a parked car
    if all((i + a, j + b) in veg for a, b in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1))) and (i + j) % 2: continue      # thin out the middle of a thicket
    rd = road_near(x, z)
    if rd < hw_at(x, z) + 0.7 or (rd > HEDGE_REACH): continue
    sxx = sum(a * a for a, b in near); szz = sum(b * b for a, b in near); sxz = sum(a * b for a, b in near)
    ang = 0.5 * math.atan2(2 * sxz, sxx - szz)                    # the way the hedge runs here
    hedges += [round(x, 1), round(z, 1), round(ang, 2), round(min(hgt, 4.2), 1)]
print('trees %d, hedge pieces %d' % (len(trees), len(hedges) // 4))

# ---- write: surveyed trees and hedges replace the mapped ones inside the strip
SEEN = REACH - 12
osm['trees'] = [t for t in osm['trees'] if road_all(t[0], t[1]) > SEEN] + trees
osm['lines'] = [l for l in osm['lines'] if l[4] != 0 or road_all((l[0] + l[2]) / 2, (l[1] + l[3]) / 2) > SEEN]
osm['hedges'] = hedges; osm['surveyed'] = SEEN; osm['roadw'] = prof
osm['credit'] = ('Buildings: Ordnance Survey OpenMap Local, © Crown copyright and database right. ' if footprints else '') + 'Hedge, tree and building heights: Environment Agency LiDAR. Roads and woods © OpenStreetMap contributors.'
open(f'assets/{KEY}_osm.js', 'w').write(f'window.RIDE_COURSES.{KEY}.osm = ' + json.dumps(osm, separators=(',', ':')) + ';\n')
print(f'wrote assets/{KEY}_osm.js', os.path.getsize(f'assets/{KEY}_osm.js') // 1024, 'KB')
