#!/usr/bin/env python3
"""Author-time tool: build the bundled Hudson estuary basemap GeoJSON.

Sources (both PUBLIC DOMAIN — Natural Earth 1:10m physical vectors):
  - ne_10m_land                     -> land polygons (coastline reference)
  - ne_10m_rivers_lake_centerlines  -> Hudson River channel (orientation)

We clip Natural Earth to the Hudson-estuary window, simplify the geometry to
keep the committed file small, and emit a single FeatureCollection where each
feature carries properties.kind in {"land","river"}. The web app bundles the
OUTPUT (src/basemap/hudson.geojson) and makes NO network request at runtime;
this script is only re-run by a maintainer refreshing the asset.

Usage (from repo root, with the two NE source files already downloaded):
  python3 web/scripts/build_basemap.py <ne_10m_land.json> <ne_10m_rivers.json> \
      web/src/basemap/hudson.geojson
"""
import json
import sys

from shapely.geometry import box, mapping, shape
from shapely.ops import unary_union

# A little wider than the data bbox (NY Harbor -> Troy, -74.10..-73.60 /
# 40.55..42.75) so the coastline gives context around the edges of the map.
CLIP = box(-74.75, 40.30, -72.90, 43.20)

# Simplification tolerance in degrees. ~0.0015 deg ~= 150 m at this latitude:
# small enough that the shoreline still reads, large enough to shrink the file.
LAND_TOL = 0.0015
RIVER_TOL = 0.0015


def clip_simplify(raw_geometry, tol):
    if raw_geometry is None:
        return None
    g = shape(raw_geometry).intersection(CLIP)
    if g.is_empty:
        return None
    g = g.simplify(tol, preserve_topology=True)
    if g.is_empty:
        return None
    return g


def load_features(path):
    with open(path) as fh:
        return json.load(fh)["features"]


def main():
    land_path, rivers_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]

    # ---- land: union all polygons, clip, simplify -> one (multi)polygon ----
    land_geoms = []
    for feat in load_features(land_path):
        g = clip_simplify(feat["geometry"], LAND_TOL)
        if g is not None:
            land_geoms.append(g)
    land = unary_union(land_geoms) if land_geoms else None

    out = {"type": "FeatureCollection", "features": []}
    if land is not None and not land.is_empty:
        out["features"].append(
            {"type": "Feature", "properties": {"kind": "land"},
             "geometry": mapping(land)}
        )

    # ---- rivers: keep only lines that touch the window (the Hudson + a few
    # tributaries fall in here); clip + simplify each ----
    river_geoms = []
    for feat in load_features(rivers_path):
        g = clip_simplify(feat["geometry"], RIVER_TOL)
        if g is not None:
            river_geoms.append(g)
    rivers = unary_union(river_geoms) if river_geoms else None
    if rivers is not None and not rivers.is_empty:
        out["features"].append(
            {"type": "Feature", "properties": {"kind": "river"},
             "geometry": mapping(rivers)}
        )

    text = json.dumps(out, separators=(",", ":"))
    with open(out_path, "w") as fh:
        fh.write(text)
    print(f"wrote {out_path}: {len(text)} bytes, "
          f"{len(out['features'])} features "
          f"(land={'yes' if land is not None else 'no'}, "
          f"rivers={'yes' if rivers is not None else 'no'})")


if __name__ == "__main__":
    main()
