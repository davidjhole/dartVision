"""Printability checks for the hardware STLs:  python tests/check_stls.py
Each part must be watertight, have no non-manifold edges, be one solid body and
have no 'islands' (regions that start printing in mid-air) in its saved orientation.
Needs: pip install trimesh shapely
"""
import collections, glob, os, sys
import numpy as np
import trimesh
from shapely.affinity import affine_transform
from shapely.ops import unary_union

ok = True
for path in sorted(glob.glob(os.path.join(os.path.dirname(__file__), "..", "hardware", "*", "stl", "*.stl"))):
    m = trimesh.load(path)
    edges = collections.Counter(map(tuple, np.sort(m.edges, axis=1)))
    bad = sum(1 for v in edges.values() if v != 2)
    bodies = [b for b in m.split(only_watertight=False) if abs(b.volume) > 1]
    prev, islands = None, []
    for z in np.arange(0.1, m.bounds[1, 2] - 0.05, 0.2):
        s = m.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
        if s is None:
            prev = None
            continue
        p, T = s.to_2D()
        cur = [affine_transform(g, [T[0, 0], T[0, 1], T[1, 0], T[1, 1], T[0, 3], T[1, 3]]) for g in p.polygons_full]
        if prev:
            u = unary_union(prev).buffer(0.3)
            islands += [round(z, 1) for g in cur if g.area > 0.5 and not g.intersects(u)]
        prev = cur
    good = m.is_watertight and bad == 0 and len(bodies) == 1 and not islands
    ok &= good
    print(f"{'ok  ' if good else 'FAIL'} {os.path.basename(path):14s} watertight={m.is_watertight} "
          f"non-manifold={bad} bodies={len(bodies)} islands_at_z={islands[:5]}")
sys.exit(0 if ok else 1)
