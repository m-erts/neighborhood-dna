#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["duckdb==1.5.6", "scikit-learn==1.9.1"]
# ///
"""Neighborhood DNA from Overture Maps Places. FOSS4G Hiroshima 2026.

    python dna.py WEST SOUTH EAST NORTH NAME [RELEASE | extract.parquet]
    python dna.py 132.35 34.30 132.55 34.48 hiroshima

Writes NAME.geojson: one H3 cell per feature with its category shares (the
DNA), Hill numbers, TF-IDF signature and HDBSCAN label. Nothing is downloaded:
DuckDB reads the parquet on S3 and pushes the bbox filter down to storage.
"""
import json
import sys

import duckdb
from sklearn.cluster import HDBSCAN

S3 = "s3://overturemaps-us-west-2/release"
# H3_RES 8: hexagons of 0.6-0.8 km2, the area drifts with location (CAVEATS 4).
# LEVEL 1: the 13 top branches of the taxonomy; 2 gives ~125 groups.
# MIN_POI 10: below that the diversity metrics are sampling noise.
H3_RES, LEVEL, MIN_POI = 8, 1, 10

west, south, east, north, name = *map(float, sys.argv[1:5]), sys.argv[5]
if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
    sys.exit("bbox order is WEST SOUTH EAST NORTH (lon lat lon lat)")

duckdb.sql("INSTALL httpfs; LOAD httpfs; INSTALL spatial; LOAD spatial; SET http_retries = 6;"
           "INSTALL h3 FROM community; LOAD h3; SET s3_region = 'us-west-2';")
source = sys.argv[6] if len(sys.argv) > 6 else max(  # default: the newest release on S3
    path.split("/")[4] for path, in duckdb.sql(f"FROM glob('{S3}/*/theme=places/*/*')").fetchall())
files = source if source.endswith(".parquet") else f"{S3}/{source}/theme=places/type=place/*"
duckdb.sql(f"""CREATE TABLE places AS
SELECT h3_latlng_to_cell(bbox.ymin, bbox.xmin, {H3_RES}) AS cell, sources[1].dataset AS provider,
       taxonomy.hierarchy[least({LEVEL}, len(taxonomy.hierarchy))] AS category
FROM read_parquet('{files}') WHERE len(taxonomy.hierarchy) > 0
 AND bbox.xmin BETWEEN {west} AND {east} AND bbox.ymin BETWEEN {south} AND {north}""")

cells = duckdb.sql(f"""WITH shares AS (
    SELECT cell, category, n / sum(n) OVER c AS p, sum(n) OVER c AS poi
    FROM (SELECT cell, category, count(*)::DOUBLE AS n FROM places GROUP BY ALL)
    WINDOW c AS (PARTITION BY cell) QUALIFY poi >= {MIN_POI}
), weighted AS (  -- TF-IDF: share in the cell x smoothed inverse cell frequency
    SELECT *, p * (1 + ln((1 + count(DISTINCT cell) OVER ()) / (1 + count(*) OVER k))) AS w
    FROM shares WINDOW k AS (PARTITION BY category))
SELECT ST_AsGeoJSON(ST_GeomFromText(h3_cell_to_boundary_wkt(cell))) AS geometry,
       h3_h3_to_string(cell) AS h3, any_value(poi)::INT AS poi, count(*) AS richness,
       round(exp(-sum(p * ln(p))), 3) AS hill_q1, round(1 / sum(p * p), 3) AS hill_q2,
       round(max(p), 3) AS top_share, max(p) >= 0.5 AS flagged,
       first(category ORDER BY p DESC, category) AS dominant,  -- ties: alphabetical
       map_from_entries(list((category, round(p, 3)) ORDER BY p DESC, category)) AS dna,
       map_from_entries(list((category, round(w, 3)) ORDER BY w DESC, category)) AS tfidf
FROM weighted GROUP BY cell ORDER BY h3""")
cells = [dict(zip(cells.columns, row)) for row in cells.fetchall()]
if len(cells) < 10:
    sys.exit(f"only {len(cells)} cells hold {MIN_POI}+ categorised places: widen the bbox")
categories = sorted({category for cell in cells for category in cell["dna"]})
labels = HDBSCAN(min_cluster_size=10, copy=True).fit_predict(
    [[cell["tfidf"].get(category, 0) for category in categories] for cell in cells])
blend = dict(duckdb.sql("""SELECT provider, round(100 * count(*) / sum(count(*)) OVER (), 1)
                           FROM places GROUP BY 1 ORDER BY 2 DESC""").fetchall())
meta = dict(source=source, bbox=[west, south, east, north], h3_res=H3_RES,
            taxonomy_level=LEVEL, min_poi=MIN_POI, providers_pct=blend)
features = [dict(type="Feature", geometry=json.loads(cell.pop("geometry")),
                 properties=dict(cell, cluster=int(label))) for cell, label in zip(cells, labels)]
with open(f"{name}.geojson", "w") as out:
    json.dump(dict(type="FeatureCollection", metadata=meta, features=features), out)
print(f"{name}.geojson: {len(cells)} cells, {sum(c['flagged'] for c in cells)} flagged, Overture "
      f"{source}\nHDBSCAN {labels.max() + 1} clusters, {(labels < 0).mean():.0%} noise\n{blend}")
