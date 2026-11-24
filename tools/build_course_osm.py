"""Builds assets/<course>_osm.js: buildings, woods, single trees, hedges and walls around a course.

Source: OpenStreetMap (© OpenStreetMap contributors, ODbL), fetched once from the Overpass service and cached in
tools/.cache, or read from a folder of saved Overpass responses given as the second argument.
Run after build_course.py:  python3 tools/build_course_osm.py tiptree
"""
import base64, glob, json, math, os, sys, time, urllib.parse, urllib.request

KEY = sys.argv[1] if len(sys.argv) > 1 else 'tiptree'
SRC = sys.argv[2] if len(sys.argv) > 2 else None
course = json.loads(open(f'assets/{KEY}.js').read().split(' = ', 2)[2].rstrip().rstrip(';'))
cE, cN = course['origin']; SIZE, CELLS = course['size'], course['cells']; HALF = SIZE / 2
road = [(p[0], p[2]) for p in course['road']]

# reuse the grid-reference maths from the terrain script without running it
src = open('tools/build_course.py').read()
ns = {'math': math}; exec(src[src.index('def to_bng'):src.index('def read_tiff')], ns); to_bng = ns['to_bng']
def local(lat, lon):
    E, N = to_bng(lat, lon); return (E - cE, -(N - cN))

# distance to the nearest point of the road line
def road_dist(x, z):
    return math.sqrt(min((px - x) ** 2 + (pz - z) ** 2 for px, pz in road))

def overpass(name, what):                # one Overpass query over the box around the course's waypoints, kept in tools/.cache
    path = f'tools/.cache/{name}_{KEY}.json'
    if not os.path.exists(path):
        cfg = {}; exec(src[src.index('COURSES = {'):src.index('KEY = ')], cfg)
        wp = cfg['COURSES'][KEY]['waypoints']; pad = 0.02
        box = '%f,%f,%f,%f' % (min(p[0] for p in wp) - pad, min(p[1] for p in wp) - pad * 1.6, max(p[0] for p in wp) + pad, max(p[1] for p in wp) + pad * 1.6)
        q = f'[out:json][timeout:120][bbox:{box}];({what});out geom;'
        os.makedirs('tools/.cache', exist_ok=True)
        for attempt in range(6):             # the public servers are often busy: try each in turn, a few times
            host = ['https://overpass-api.de/api/interpreter', 'https://overpass.kumi.systems/api/interpreter'][attempt % 2]
            try:
                req = urllib.request.Request(host, data=urllib.parse.urlencode({'data': q}).encode(), headers={'User-Agent': 'golden-hour-ride-poc'})
                data = urllib.request.urlopen(req, timeout=180).read(); json.loads(data); break
            except Exception as ex:
                if attempt == 5: raise
                print('  map server busy, trying again:', ex); time.sleep(5 + attempt * 5)
        open(path, 'wb').write(data)
    return path
def fetch():                             # everything the scenery uses
    return [overpass('osm', 'way[building];way[natural=wood];way[landuse=forest];relation[natural=wood];relation[landuse=forest];way[barrier~"^(hedge|wall|retaining_wall)$"];node[natural=tree];'),
            overpass('osm_roads', 'way[highway~"^(motorway|trunk|primary|secondary|tertiary|unclassified|residential|living_street|service|track|motorway_link|trunk_link|primary_link|secondary_link|tertiary_link)$"];')]

els = {}
for f in (glob.glob(os.path.join(SRC, '*.json')) if SRC else fetch()):
    for e in json.load(open(f)).get('elements', []):
        els[(e['type'], e['id'])] = e
print('elements:', len(els))
ring = lambda geom: [local(p['lat'], p['lon']) for p in geom]
inside = lambda x, z, m=0: abs(x) < HALF - m and abs(z) < HALF - m

def best_box(pts):                       # smallest rectangle around a footprint, trying each wall's direction
    best = None
    for (x1, z1), (x2, z2) in zip(pts, pts[1:]):
        L = math.hypot(x2 - x1, z2 - z1)
        if L < 0.5: continue
        ux, uz = (x2 - x1) / L, (z2 - z1) / L
        us = [x * ux + z * uz for x, z in pts]; vs = [-x * uz + z * ux for x, z in pts]
        w, d = max(us) - min(us), max(vs) - min(vs)
        if best is None or w * d < best[0]:
            cu, cv = (max(us) + min(us)) / 2, (max(vs) + min(vs)) / 2
            best = (w * d, cu * ux - cv * uz, cu * uz + cv * ux, w, d, math.atan2(uz, ux))
    return best

def height(t):
    try: return max(2.5, float(str(t.get('height', '')).replace('m', '').strip()))
    except ValueError: pass
    try: return max(2.5, float(t['building:levels']) * 3)
    except (KeyError, ValueError): pass
    b = t.get('building')
    if b == 'church' or t.get('amenity') == 'place_of_worship': return 13
    if b in ('garage', 'garages', 'shed', 'hut', 'carport', 'roof', 'greenhouse'): return 2.6
    return 5.6

# the rest of the road network: every other road within sight of the course, as [width in metres, [x, z, x, z, ...]]
ROAD_W = {'motorway': 9, 'trunk': 8, 'primary': 7.5, 'secondary': 7, 'tertiary': 6, 'unclassified': 4.6, 'residential': 5.4, 'living_street': 4.6, 'service': 3.2, 'track': 2.6}
ROAD_SEEN = 650
def road_way(e, t):
    kind = t['highway'].replace('_link', '')
    if t.get('access') == 'private' and kind == 'service' and t.get('service') == 'driveway': return
    if t.get('tunnel') in ('yes', 'building_passage'): return
    pts = ring(e['geometry']); run = []
    def flush():
        if len(run) >= 2: roads.append([ROAD_W[kind], [round(v, 1) for p in run for v in p]])
    for p in pts:
        if inside(p[0], p[1], 15) and road_dist(p[0], p[1]) < ROAD_SEEN: run.append(p)
        else: flush(); run = []
    flush()

buildings, woods, holes, trees, lines, roads = [], [], [], [], [], []
for e in els.values():
    t = e.get('tags', {})
    if e['type'] == 'node':
        if t.get('natural') == 'tree':
            x, z = local(e['lat'], e['lon'])
            if inside(x, z, 20) and road_dist(x, z) > 4.5: trees.append([round(x, 1), round(z, 1)])
        continue
    if e['type'] == 'way' and 'geometry' in e:
        if t.get('highway'): road_way(e, t); continue
        pts = ring(e['geometry'])
        if t.get('building') and len(pts) >= 4:
            b = best_box(pts)
            if not b: continue
            _, x, z, w, d, ang = b
            if w < d: w, d, ang = d, w, ang + math.pi / 2
            if not inside(x, z, 40) or w > 90 or w < 2 or d < 2: continue
            rd = road_dist(x, z)
            if rd > 700 or rd < d / 2 + 4.5: continue          # skip what you'd never see, and anything overlapping the road
            h = height(t); small = h < 3.5
            buildings.append([round(x, 1), round(z, 1), round(w, 1), round(d, 1), round(ang, 3), round(h, 1), 0 if (small or d > 14) else 1])
        elif t.get('natural') == 'wood' or t.get('landuse') == 'forest':
            if len(pts) >= 4: woods.append(pts)
        elif t.get('barrier') in ('hedge', 'wall', 'retaining_wall'):
            kind = 0 if t['barrier'] == 'hedge' else 1
            for (x1, z1), (x2, z2) in zip(pts, pts[1:]):
                L = math.hypot(x2 - x1, z2 - z1); n = max(1, math.ceil(L / 6))
                for k in range(n):
                    ax, az = x1 + (x2 - x1) * k / n, z1 + (z2 - z1) * k / n; bx, bz = x1 + (x2 - x1) * (k + 1) / n, z1 + (z2 - z1) * (k + 1) / n
                    mx, mz = (ax + bx) / 2, (az + bz) / 2
                    if inside(mx, mz, 20) and 4.4 < road_dist(mx, mz) < 400: lines.append([round(ax, 1), round(az, 1), round(bx, 1), round(bz, 1), kind])
    elif e['type'] == 'relation' and (t.get('natural') == 'wood' or t.get('landuse') == 'forest'):
        for m in e.get('members', []):
            if m.get('type') == 'way' and 'geometry' in m and len(m['geometry']) >= 3:
                (holes if m.get('role') == 'inner' else woods).append(ring(m['geometry']))

# woodland as a grid matching the terrain's vertices
W = CELLS + 1; mask = bytearray(W * W)
def fill(poly, val):
    if poly[0] != poly[-1]: poly = poly + [poly[0]]
    zs = [p[1] for p in poly]
    for iz in range(max(0, math.ceil((min(zs) + HALF) / SIZE * CELLS)), min(CELLS, math.floor((max(zs) + HALF) / SIZE * CELLS)) + 1):
        z = -HALF + iz * SIZE / CELLS; xs = []
        for (x1, z1), (x2, z2) in zip(poly, poly[1:]):
            if (z1 <= z < z2) or (z2 <= z < z1): xs.append(x1 + (z - z1) / (z2 - z1) * (x2 - x1))
        xs.sort()
        for a, b in zip(xs[::2], xs[1::2]):
            for ix in range(max(0, math.ceil((a + HALF) / SIZE * CELLS)), min(CELLS, math.floor((b + HALF) / SIZE * CELLS)) + 1): mask[iz * W + ix] = val
for p in woods: fill(p, 1)
for p in holes: fill(p, 0)
bits = bytearray((len(mask) + 7) // 8)
for i, v in enumerate(mask):
    if v: bits[i >> 3] |= 1 << (i & 7)
print('other roads: %d pieces, %.1f km' % (len(roads), sum(math.hypot(r[1][k + 2] - r[1][k], r[1][k + 3] - r[1][k + 1]) for r in roads for k in range(0, len(r[1]) - 2, 2)) / 1000))
print('buildings %d, single trees %d, hedge/wall pieces %d (hedge %d), woodland %.2f km2' % (len(buildings), len(trees), len(lines), sum(1 for l in lines if l[4] == 0), sum(mask) * (SIZE / CELLS) ** 2 / 1e6))
out = {'buildings': buildings, 'trees': trees, 'lines': lines, 'roads': roads, 'woods': base64.b64encode(bytes(bits)).decode(), 'credit': 'Buildings, woods and hedges © OpenStreetMap contributors.'}
open(f'assets/{KEY}_osm.js', 'w').write(f'window.RIDE_COURSES.{KEY}.osm = ' + json.dumps(out, separators=(',', ':')) + ';\n')
print(f'wrote assets/{KEY}_osm.js', os.path.getsize(f'assets/{KEY}_osm.js') // 1024, 'KB')
