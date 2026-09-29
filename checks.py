#!/usr/bin/env python3
"""Robustness checks behind the talk. Run them before trusting any dna.py number.

    python checks.py                              # newest Overture release on S3
    python checks.py 2026-09-23.1 2026-08-19.0    # primary release, then one to diff against

Each city is pulled from S3 once per release into data/ as a slim parquet extract
(a box twice as wide and tall as the study box, so the box-shift check needs no
second scan). Everything else runs locally in a few seconds. The script rewrites
docs/RESULTS.md and docs/data/results.json: the only source of the numbers quoted
in README.md, in the figures and in the slides.
"""
import datetime
import itertools
import json
import math
import pathlib
import sys

import duckdb
from sklearn.cluster import HDBSCAN
from sklearn.preprocessing import normalize

S3 = "s3://overturemaps-us-west-2/release"
AREA_KM2, DLON = 366.0, 0.20   # the same ground area for every city, as on the slides
H3_RES, LEVEL, MIN_POI, FLAG = 8, 1, 10, 0.5
SHIFT_KM = 4.0
BINS = [10, 20, 40, 80, 160, 320]
CITIES = {"hiroshima": (34.390, 132.450), "belgrade": (44.805, 20.450),
          "amsterdam": (52.370, 4.900), "london": (51.510, -0.120)}
# Well-known neighbourhoods, one point each; the H3 cell under the point is reported.
DISTRICTS = [
    ("london", "City of London, Bank", "financial district", 51.5134, -0.0890),
    ("london", "Shoreditch", "bars, studios, offices", 51.5262, -0.0780),
    ("london", "Muswell Hill", "residential suburb", 51.5905, -0.1440),
    ("amsterdam", "Zuidas", "financial district", 52.3375, 4.8730),
    ("amsterdam", "De Pijp", "cafes and market streets", 52.3550, 4.8950),
    ("amsterdam", "Buitenveldert", "residential suburb", 52.3300, 4.8700),
    ("hiroshima", "Kamiyacho", "offices, prefectural government", 34.3960, 132.4575),
    ("hiroshima", "Nagarekawa", "nightlife quarter", 34.3915, 132.4655),
    ("hiroshima", "Ushita", "residential suburb", 34.4130, 132.4760),
]
# What the slides showed on 2 September 2026, computed on release 2026-07-22.0, which
# Overture has since deleted. Copied from docs/slides-as-delivered.pdf, pages 4 to 6.
STAGE = {"release": "2026-07-22.0",
         "cells": {"hiroshima": 255, "belgrade": 221, "amsterdam": 364, "london": 586},
         "flagged": {"hiroshima": 15, "belgrade": 12, "amsterdam": 36, "london": 15},
         "hill_q2": {"hiroshima": 5.32, "belgrade": 6.31, "amsterdam": 5.81, "london": 5.81},
         "hill_q2_meta": {"hiroshima": 5.19, "belgrade": 6.51, "amsterdam": 5.97, "london": 6.72},
         "meta_pct": {"belgrade": 93, "london": 62},
         "largest_gap_richness": 1, "largest_gap_hill_q2": 2.2}
ROOT = pathlib.Path(__file__).parent
DATA, DOCS = ROOT / "data", ROOT / "docs"
TODAY = datetime.datetime.now(datetime.UTC).date()

con = duckdb.connect()
con.sql("INSTALL httpfs; LOAD httpfs; INSTALL h3 FROM community; LOAD h3;"
        "SET s3_region = 'us-west-2'; SET http_retries = 6;")


def box(lat, lon, dy_km=0.0, dx_km=0.0, scale=1.0):
    """West, south, east, north of a box of AREA_KM2 centred on a point.

    The width is fixed in degrees and the height compensates for latitude, so the
    four cities get the same ground area. scale=2 doubles both sides.
    """
    km_per_deg_lon = 111.320 * math.cos(math.radians(lat))
    height = AREA_KM2 / (DLON * km_per_deg_lon) / 110.574
    lat, lon = lat + dy_km / 110.574, lon + dx_km / km_per_deg_lon
    return (round(lon - DLON * scale / 2, 4), round(lat - height * scale / 2, 4),
            round(lon + DLON * scale / 2, 4), round(lat + height * scale / 2, 4))


def extract(city, release):
    """Pull one city from S3 unless the extract is already in data/."""
    target = DATA / f"{city}_{release}.parquet"
    if not target.exists():
        DATA.mkdir(exist_ok=True)
        west, south, east, north = box(*CITIES[city], scale=2.0)
        con.sql(f"""
        COPY (SELECT id, bbox, taxonomy, sources, confidence
              FROM read_parquet('{S3}/{release}/theme=places/type=place/*')
              WHERE bbox.xmin BETWEEN {west} AND {east}
                AND bbox.ymin BETWEEN {south} AND {north})
        TO '{target}' (FORMAT parquet, COMPRESSION zstd)""")
    return target


def load(releases):
    con.sql("""CREATE TABLE places (release VARCHAR, city VARCHAR, lat DOUBLE, lon DOUBLE,
               hierarchy VARCHAR[], provider VARCHAR, confidence DOUBLE, updated TIMESTAMP)""")
    for release in releases:
        for city in CITIES:
            con.sql(f"""
            INSERT INTO places
            SELECT '{release}', '{city}', bbox.ymin, bbox.xmin, taxonomy.hierarchy,
                   sources[1].dataset, confidence,
                   try_cast(sources[1].update_time AS TIMESTAMP)
            FROM read_parquet('{extract(city, release)}')""")


def inside(shift=(0, 0)):
    """SQL predicate: the place lies in the study box of its city."""
    return " OR ".join(
        "(city = '{}' AND lon BETWEEN {} AND {} AND lat BETWEEN {} AND {})".format(
            city, *(box(*centre, *shift)[i] for i in (0, 2, 1, 3)))
        for city, centre in CITIES.items())


def cells(release, res=H3_RES, level=LEVEL, min_poi=MIN_POI, provider=None, shift=(0, 0)):
    """One row per city and H3 cell, with the metrics dna.py writes."""
    only = f"AND provider = '{provider}'" if provider else ""
    return con.sql(f"""
    WITH shares AS (
        SELECT city, cell, category, n / sum(n) OVER c AS p, sum(n) OVER c AS poi
        FROM (SELECT city, h3_latlng_to_cell(lat, lon, {res}) AS cell,
                     hierarchy[least({level}, len(hierarchy))] AS category,
                     count(*)::DOUBLE AS n
              FROM places
              WHERE release = '{release}' AND len(hierarchy) > 0 AND ({inside(shift)}) {only}
              GROUP BY ALL)
        WINDOW c AS (PARTITION BY city, cell) QUALIFY poi >= {min_poi}
    ), weighted AS (
        SELECT *, max(p) OVER (PARTITION BY city, cell) AS top,
               p * (1 + ln((1 + count(DISTINCT cell) OVER (PARTITION BY city))
                           / (1 + count(*) OVER (PARTITION BY city, category)))) AS w
        FROM shares
    )
    SELECT city, h3_h3_to_string(cell) AS h3, any_value(poi)::INT AS poi,
           count(*) AS richness, exp(-sum(p * ln(p))) AS hill_q1,
           1 / sum(p * p) AS hill_q2, max(p) AS top_share, max(p) >= {FLAG} AS flagged,
           first(category ORDER BY p DESC, category) AS dominant,
           h3_cell_area(cell, 'km^2') AS km2, count(*) FILTER (p = top) > 1 AS tied,
           map_from_entries(list((category, p) ORDER BY p DESC, category)) AS dna,
           map_from_entries(list((category, w) ORDER BY w DESC, category)) AS tfidf
    FROM weighted GROUP BY city, cell""")


def by_city(relation, index, value="v"):
    """Cities as columns. The relation must hold city, <index> and <value>."""
    relation.create_view("to_pivot", replace=True)
    return con.sql(f"""
        PIVOT (SELECT city, {index}, {value} AS v FROM to_pivot)
        ON city IN ({', '.join(repr(c) for c in CITIES)}) USING first(v)
        ORDER BY {index}""")


def medians(release, parameter, values, label, metric="hill_q2"):
    """Median of a metric per city while one parameter of cells() moves."""
    union = []
    for i, (name, value) in enumerate(values.items()):
        cells(release, **{parameter: value}).create_view(f"v_{parameter}_{i}", replace=True)
        union.append(f"SELECT city, '{name}' AS {label}, median({metric}) AS v "
                     f"FROM v_{parameter}_{i} GROUP BY city")
    return by_city(con.sql(" UNION ALL ".join(union)), label)


def hdbscan_sweep():
    """HDBSCAN over a grid of settings. Signatures are rounded to 3 decimals, as in dna.py."""
    rows = []
    for city in CITIES:
        found = con.sql(f"SELECT dna, tfidf FROM now WHERE city = '{city}' ORDER BY h3").fetchall()
        categories = sorted({k for dna, _ in found for k in dna})
        sizes = (5, 10, 15, 25)
        variants = [(0, "shares", 3, sizes), (1, "tf-idf", 3, sizes),
                    (1, "tf-idf, L2 norm", 3, sizes), (1, "tf-idf, not rounded", 9, (10,))]
        for column, label, digits, sizes in variants:
            matrix = [[round(row[column].get(k, 0), digits) for k in categories] for row in found]
            matrix = normalize(matrix) if label.endswith("norm") else matrix
            for size in sizes:
                labels = HDBSCAN(min_cluster_size=size, copy=True).fit_predict(matrix)
                rows.append((city, f"{label}, {size:02d}", int(labels.max() + 1),
                             round(100 * float((labels < 0).mean()))))
    con.sql("CREATE OR REPLACE TABLE hdbscan (city VARCHAR, signature_and_min_cluster_size"
            " VARCHAR, clusters INT, noise_pct INT)")
    con.executemany("INSERT INTO hdbscan VALUES (?, ?, ?, ?)", rows)
    return by_city(con.sql("""
        SELECT city, signature_and_min_cluster_size,
               clusters || ' clusters, ' || noise_pct || '% noise' AS v
        FROM hdbscan"""), "signature_and_min_cluster_size")


class Report:
    """Collects every table twice: Markdown for people, JSON for the figures."""

    def __init__(self):
        self.lines, self.data = [], {}

    def text(self, *paragraphs):
        self.lines += list(paragraphs)

    def table(self, key, relation, digits=2, note=None):
        rows = relation.fetchall()
        self.data[key] = [dict(zip(relation.columns, row)) for row in rows]

        def show(value):
            if value is None:
                return "-"
            return f"{value:.{digits}f}" if isinstance(value, float) else str(value)
        self.lines += ["| " + " | ".join(relation.columns) + " |",
                       "|" + "|".join(" --- " for _ in relation.columns) + "|",
                       *("| " + " | ".join(show(v) for v in row) + " |" for row in rows), ""]
        if note:
            self.lines += [note, ""]


def report(releases):
    now, out = releases[0], Report()
    cells(now).create_view("now", replace=True)
    try:  # row count of the whole release: parquet footers only, a few seconds
        world = con.sql(f"""SELECT count(*) FROM read_parquet(
            '{S3}/{now}/theme=places/type=place/*')""").fetchone()[0]
    except duckdb.Error:  # offline, or the release has left S3
        world = None
    out.data["meta"] = dict(
        release=now, compared_with=releases[1:], generated=str(TODAY), places_in_release=world,
        h3_res=H3_RES, taxonomy_level=LEVEL, min_poi=MIN_POI, flag=FLAG, area_km2=AREA_KM2,
        boxes={city: box(*centre) for city, centre in CITIES.items()})
    out.text(f"""# Results

Generated by `python checks.py {' '.join(releases)}` on {TODAY}.
Do not edit by hand: rerun the script. Every number in README.md, in the figures
and in the slides comes from this file or from `docs/data/results.json`.

Overture release `{now}`, taxonomy level {LEVEL}, H3 resolution {H3_RES}, at least
{MIN_POI} categorised places per cell, flag at top share >= {FLAG}. Each city is a
box of {AREA_KM2:.0f} km2. The whole release holds {world or 0:,} places.

| city | west south east north |
| --- | --- |""",
             *(f"| {city} | {' '.join(f'{v:.4f}' for v in box(*centre))} |"
               for city, centre in CITIES.items()), """
## 1. Summary
""")
    out.table("summary", con.sql("""
        SELECT city, count(*) AS cells, sum(poi)::INT AS places,
               count(*) FILTER (flagged) AS flagged, median(richness) AS richness,
               median(hill_q1) AS hill_q1, median(hill_q2) AS hill_q2,
               median(top_share) AS top_share, avg(km2) AS mean_cell_km2,
               count(*) FILTER (tied) AS tied_top_category
        FROM now GROUP BY city ORDER BY city"""), note="""\
Medians across cells. `mean_cell_km2` shows that H3 cells are not equal-area.
`tied_top_category` counts cells where two categories share first place, so
`dominant` is decided by alphabetical order.""")

    out.text("Coverage: how much of what Overture holds in the box reaches the metrics.\n")
    out.table("coverage", con.sql(f"""
        WITH boxed AS (
            SELECT city, h3_latlng_to_cell(lat, lon, {H3_RES}) AS cell, confidence, updated,
                   coalesce(len(hierarchy), 0) > 0 AS categorised
            FROM places WHERE release = '{now}' AND ({inside()})
        ), per_cell AS (
            SELECT city, cell, count(*) FILTER (categorised) AS n FROM boxed GROUP BY ALL
        )
        SELECT city, (SELECT count(*) FROM boxed b WHERE b.city = p.city) AS places_in_box,
               100 * sum(n) / (SELECT count(*) FROM boxed b WHERE b.city = p.city)
                   AS categorised_pct,
               count(*) FILTER (n > 0) AS cells_with_places,
               count(*) FILTER (n >= {MIN_POI}) AS cells_kept,
               100 * sum(n) FILTER (n >= {MIN_POI}) / sum(n) AS places_in_kept_cells_pct,
               (SELECT 100 * avg((confidence < 0.5)::INT) FROM boxed b WHERE b.city = p.city)
                   AS confidence_under_half_pct,
               (SELECT median(updated)::DATE::VARCHAR FROM boxed b WHERE b.city = p.city)
                   AS median_update
        FROM per_cell p GROUP BY city ORDER BY city"""), 1, note="""\
`cells_kept` have at least 10 categorised places. The rest are dropped, not drawn as zeros.
`confidence_under_half_pct` is the share of places Overture itself scores below 0.5;
`dna.py` does not filter on confidence. `median_update` is the median `update_time` of
the first source: the date of the provider's delivery, not of the last visit to the place.""")
    out.text("Share of categorised places by level-1 branch, %:\n")
    out.table("branches", con.sql(f"""
        WITH counted AS (
            SELECT city, hierarchy[1] AS branch, count(*) AS n
            FROM places WHERE release = '{now}' AND len(hierarchy) > 0 AND ({inside()})
            GROUP BY ALL)
        PIVOT (SELECT city, branch, 100 * n / sum(n) OVER (PARTITION BY city) AS v,
                      100 * sum(n) OVER (PARTITION BY branch) / sum(n) OVER () AS four_cities
               FROM counted)
        ON city IN ({', '.join(repr(c) for c in CITIES)}) USING first(v)
        ORDER BY four_cities DESC"""), 1)

    out.text("## 2. Check 1: control for cell size\n",
             "Median category richness by places per cell:\n")
    bins = " ".join(f"WHEN poi < {hi} THEN '{i + 1}. {lo}-{hi - 1}'"
                    for i, (lo, hi) in enumerate(itertools.pairwise(BINS)))
    con.sql(f"""CREATE OR REPLACE VIEW binned AS
        SELECT city, CASE {bins} ELSE '{len(BINS)}. {BINS[-1]}+' END AS places_per_cell,
               median(richness) AS richness, median(hill_q2) AS hill_q2, count(*) AS cells
        FROM now GROUP BY ALL""")
    out.table("bins_richness",
              by_city(con.sql("FROM binned"), "places_per_cell", "richness"), 1)
    out.text("Median Hill q2 by places per cell:\n")
    out.table("bins_hill_q2", by_city(con.sql("FROM binned"), "places_per_cell", "hill_q2"))
    out.text("Cells per bin:\n")
    out.table("bins_cells", by_city(con.sql("FROM binned"), "places_per_cell", "cells"))
    out.text("Largest gap between cities inside one bin, and the Pearson correlation of"
             " each metric with log(places per cell), four cities pooled:\n")
    out.table("bins_gap", con.sql("""
        SELECT (SELECT max(g) FROM (SELECT max(richness) - min(richness) AS g
                FROM binned GROUP BY places_per_cell)) AS largest_gap_richness,
               (SELECT max(g) FROM (SELECT max(hill_q2) - min(hill_q2) AS g
                FROM binned GROUP BY places_per_cell)) AS largest_gap_hill_q2,
               corr(richness, ln(poi)) AS r_richness, corr(hill_q2, ln(poi)) AS r_hill_q2
        FROM now"""))

    out.text("## 3. Check 2: the sources column\n",
             "Share of categorised places by first source, %:\n")
    out.table("providers", by_city(con.sql(f"""
        SELECT city, provider, 100 * count(*) / sum(count(*)) OVER (PARTITION BY city) AS pct
        FROM places WHERE release = '{now}' AND len(hierarchy) > 0 AND ({inside()})
        GROUP BY city, provider"""), "provider", "pct"), 1)
    cells(now, provider="meta").create_view("meta_only", replace=True)
    out.text("Median Hill q2, every source against Meta only:\n")
    out.table("meta_only", con.sql("""
        WITH medians AS (
            SELECT city, 'all' AS s, median(hill_q2) AS q, count(*) AS n FROM now GROUP BY 1
            UNION ALL
            SELECT city, 'meta', median(hill_q2), count(*) FROM meta_only GROUP BY 1)
        SELECT city, max(q) FILTER (s = 'all') AS all_sources,
               max(rank) FILTER (s = 'all') AS rank_all,
               max(q) FILTER (s = 'meta') AS meta_only,
               max(rank) FILTER (s = 'meta') AS rank_meta,
               max(n) FILTER (s = 'meta') AS cells_meta
        FROM (SELECT *, rank() OVER (PARTITION BY s ORDER BY q DESC) AS rank FROM medians)
        GROUP BY city ORDER BY rank_all"""))

    out.text("## 4. HDBSCAN: is there a typology at all?\n",
             "Clusters found and share of cells labelled noise. `dna.py` runs the"
             " `tf-idf, 10` row. The last row feeds HDBSCAN the same signature without"
             " rounding it to three decimals.\n")
    out.table("hdbscan", hdbscan_sweep())

    out.text("## 5. Sensitivity\n", "Median Hill q2 by H3 resolution:\n")
    out.table("by_h3_res", medians(now, "res", {7: 7, 8: 8, 9: 9}, "h3_res"))
    out.text("Median Hill q2 by the MIN_POI threshold:\n")
    out.table("by_min_poi",
              medians(now, "min_poi", {"05": 5, "10": 10, "20": 20}, "min_poi"))
    out.text(f"Median Hill q2 with the box shifted by {SHIFT_KM:.0f} km:\n")
    out.table("by_shift", medians(now, "shift", {
        "1. centre": (0, 0), "2. north": (SHIFT_KM, 0), "3. south": (-SHIFT_KM, 0),
        "4. east": (0, SHIFT_KM), "5. west": (0, -SHIFT_KM)}, "box"))
    out.text("Median Hill q1 by taxonomy level (9 stands for the leaf):\n")
    out.table("by_level", medians(now, "level", {1: 1, 2: 2, 3: 3, 9: 9},
                                  "taxonomy_level", metric="hill_q1"))
    out.text("Distinct categories per taxonomy level, four extracts pooled:\n")
    out.table("categories_per_level", con.sql(f"""
        SELECT level AS taxonomy_level,
               count(DISTINCT hierarchy[least(level, len(hierarchy))]) AS categories
        FROM places, (SELECT unnest([1, 2, 3, 9]) AS level)
        WHERE release = '{now}' AND len(hierarchy) > 0 GROUP BY level ORDER BY level"""))

    out.text("## 6. Named districts\n",
             "One H3 cell each: the cell under a point inside the neighbourhood.\n")
    con.sql("CREATE OR REPLACE TABLE districts (city VARCHAR, district VARCHAR,"
            " known_as VARCHAR, lat DOUBLE, lon DOUBLE)")
    con.executemany("INSERT INTO districts VALUES (?, ?, ?, ?, ?)", DISTRICTS)
    con.sql(f"""CREATE OR REPLACE VIEW district_cells AS
        SELECT d.city, d.district, d.known_as, c.h3, c.poi AS places,
               c.hill_q1, c.hill_q2, c.top_share, c.flagged, c.dna, d.rowid AS position
        FROM districts d JOIN now c
          ON c.city = d.city AND c.h3 = h3_latlng_to_cell_string(d.lat, d.lon, {H3_RES})""")
    found = con.sql("SELECT * EXCLUDE (position) FROM district_cells ORDER BY position")
    out.data["districts"] = [dict(zip(found.columns, row)) for row in found.fetchall()]
    out.table("districts_table", con.sql("""
        SELECT city, district, known_as, h3, places, hill_q2, top_share,
               array_to_string(list_transform(map_entries(dna)[:3], e ->
                   e.key || ' ' || round(100 * e.value)::INT || '%'), ', ') AS top_three
        FROM district_cells ORDER BY position"""))

    for old in releases[1:]:
        cells(old).create_view("old", replace=True)
        out.text(f"## 7. Release drift: `{old}` against `{now}`\n")
        out.table("drift", con.sql("""
            SELECT coalesce(a.city, b.city) AS city,
                   count(*) FILTER (b.flagged) AS flagged_old,
                   count(*) FILTER (a.flagged) AS flagged_new,
                   count(*) FILTER (a.flagged AND b.flagged) AS flagged_in_both,
                   median(b.hill_q2) AS hill_q2_old, median(a.hill_q2) AS hill_q2_new,
                   count(*) FILTER (a.h3 IS NULL OR b.h3 IS NULL) AS cells_in_one_release
            FROM now a FULL JOIN old b USING (city, h3)
            GROUP BY 1 ORDER BY 1"""))
    stage(out, now)
    return out


def stage(out, now):
    """Set the numbers of the stage slides next to the numbers of this run."""
    summary = {row["city"]: row for row in out.data["summary"]}
    ranks = {row["city"]: row for row in out.data["meta_only"]}
    blend = next(row for row in out.data["providers"] if row["provider"] == "meta")
    gap = out.data["bins_gap"][0]
    rows = []
    for city in CITIES:
        rows += [(f"{city}: cells", STAGE["cells"][city], summary[city]["cells"]),
                 (f"{city}: flagged cells", STAGE["flagged"][city], summary[city]["flagged"]),
                 (f"{city}: median Hill q2", STAGE["hill_q2"][city], summary[city]["hill_q2"]),
                 (f"{city}: median Hill q2, Meta only", STAGE["hill_q2_meta"][city],
                  ranks[city]["meta_only"])]
    rows += [(f"{city}: places from Meta, %", share, blend[city])
             for city, share in STAGE["meta_pct"].items()]
    rows += [("largest gap in a density bin, richness", STAGE["largest_gap_richness"],
              gap["largest_gap_richness"]),
             ("largest gap in a density bin, Hill q2", STAGE["largest_gap_hill_q2"],
              gap["largest_gap_hill_q2"])]
    con.sql("CREATE OR REPLACE TABLE stage (number VARCHAR, on_stage DOUBLE, now DOUBLE)")
    con.executemany("INSERT INTO stage VALUES (?, ?, ?)", rows)
    out.text("## 8. On stage against now\n",
             f"The slides were computed on release `{STAGE['release']}`, which Overture has"
             f" deleted. This run uses `{now}`.\n")
    out.table("stage", con.sql("""
        SELECT number, on_stage, now, 100 * (now - on_stage) / on_stage AS change_pct
        FROM stage ORDER BY rowid"""))
    order_then = sorted(CITIES, key=lambda c: -STAGE["hill_q2_meta"][c])
    order_now = sorted(CITIES, key=lambda c: -ranks[c]["meta_only"])
    out.text(f"Ranking by median Hill q2 with Meta places only, on stage: "
             f"{', '.join(order_then)}. Now: {', '.join(order_now)}.\n",
             "With all sources London and Amsterdam were level on stage (5.81 each), which the"
             " slide counted as London moving from third place to first. In this release"
             " London starts second.\n")


if __name__ == "__main__":
    wanted = sys.argv[1:] or [max(
        path.split("/")[4]
        for path, in con.sql(f"FROM glob('{S3}/*/theme=places/*/*')").fetchall())]
    load(wanted)
    result = report(wanted)
    (DOCS / "data").mkdir(parents=True, exist_ok=True)
    (DOCS / "RESULTS.md").write_text("\n".join(result.lines))
    (DOCS / "data" / "results.json").write_text(json.dumps(result.data, indent=1))
    print("\n".join(result.lines))
