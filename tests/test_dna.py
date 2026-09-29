"""Offline tests: dna.py runs on a synthetic extract with the Overture Places schema.

The fixture is built on the fly from H3 cell centres, so every expected number
below is known in advance. Nothing here touches S3. The live check sits in
test_live.py and runs only when DNA_LIVE=1.
"""
import ast
import json
import math
import pathlib
import subprocess
import sys

import duckdb
import pytest
from sklearn.feature_extraction.text import TfidfTransformer

ROOT = pathlib.Path(__file__).parent.parent
SCRIPT = ROOT / "dna.py"
BBOX = ["132.30", "34.30", "132.60", "34.50"]

# cell index -> places per category. Index 0 is the centre cell, 1..18 its two rings.
MONO = {"food_and_drink": 90, "shopping": 5, "services_and_business": 5}
TIED = {"shopping": 5, "education": 5}
SPARSE = {"food_and_drink": 9}                       # below MIN_POI, must vanish
EVEN = {"food_and_drink": 4, "shopping": 4, "health_care": 4, "lodging": 4}
LAYOUT = {0: MONO, 1: TIED, 2: SPARSE, **{i: EVEN for i in range(3, 19)}}


@pytest.fixture(scope="module")
def extract(tmp_path_factory):
    """A parquet file shaped like an Overture Places extract."""
    path = tmp_path_factory.mktemp("data") / "places.parquet"
    con = duckdb.connect()
    con.sql("INSTALL h3 FROM community; LOAD h3;")
    con.sql("""CREATE TABLE layout (i INT, category VARCHAR, n INT);
               CREATE TABLE ring AS
               SELECT row_number() OVER (ORDER BY cell) - 1 AS i, cell
               FROM (SELECT unnest(h3_grid_disk(
                         h3_latlng_to_cell(34.39, 132.45, 8), 2)) AS cell)""")
    con.executemany("INSERT INTO layout VALUES (?, ?, ?)",
                    [(i, c, n) for i, mix in LAYOUT.items() for c, n in mix.items()])
    con.sql(f"""
    COPY (
        SELECT uuid()::VARCHAR AS id,
               {{'xmin': h3_cell_to_lng(cell), 'xmax': h3_cell_to_lng(cell),
                 'ymin': h3_cell_to_lat(cell), 'ymax': h3_cell_to_lat(cell)}} AS bbox,
               {{'primary': category || '_leaf', 'hierarchy': [category, category || '_leaf'],
                 'alternates': NULL::VARCHAR[]}} AS taxonomy,
               [{{'property': '',
                  'dataset': CASE WHEN k % 4 = 0 THEN 'Foursquare' ELSE 'meta' END}}] AS sources
        FROM layout JOIN ring USING (i), range(n) AS t(k)
        UNION ALL  -- a place without a category must be ignored, not counted
        SELECT uuid()::VARCHAR, {{'xmin': 132.45, 'xmax': 132.45, 'ymin': 34.39, 'ymax': 34.39}},
               NULL, [{{'property': '', 'dataset': 'meta'}}]
    ) TO '{path}' (FORMAT parquet)""")
    cells = dict(con.sql("SELECT i, h3_h3_to_string(cell) FROM ring").fetchall())
    return path, cells


def run(cwd, *args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd,
                          capture_output=True, text=True, check=False)


@pytest.fixture(scope="module")
def output(extract, tmp_path_factory):
    path, cells = extract
    cwd = tmp_path_factory.mktemp("run")
    done = run(cwd, *BBOX, "test", str(path))
    assert done.returncode == 0, done.stderr
    collection = json.loads((cwd / "test.geojson").read_text())
    by_cell = {f["properties"]["h3"]: f for f in collection["features"]}
    return collection, by_cell, cells, done.stdout


def test_the_promise_of_fifty_lines():
    source = SCRIPT.read_text()
    tree = ast.parse(source)
    docstring = range(tree.body[0].lineno, tree.body[0].end_lineno + 1)
    code = [line for number, line in enumerate(source.splitlines(), 1)
            if line.strip() and not line.strip().startswith("#") and number not in docstring]
    assert len(code) <= 50, f"dna.py has {len(code)} lines of code, the talk promised 50"


def test_readme_shows_the_script_verbatim():
    assert SCRIPT.read_text().strip() in (ROOT / "README.md").read_text()


def test_geojson_is_valid(output):
    collection, by_cell, _, _ = output
    assert collection["type"] == "FeatureCollection"
    assert len(by_cell) == 18            # 19 cells, one below the threshold
    for feature in collection["features"]:
        ring = feature["geometry"]["coordinates"][0]
        assert feature["geometry"]["type"] == "Polygon"
        assert ring[0] == ring[-1] and len(ring) in (6, 7)
        assert all(-180 <= x <= 180 and -90 <= y <= 90 for x, y in ring)


def test_cells_below_the_threshold_are_dropped(output):
    _, by_cell, cells, _ = output
    assert cells[2] not in by_cell


def test_mono_functional_cell(output):
    _, by_cell, cells, _ = output
    cell = by_cell[cells[0]]["properties"]
    shares = [0.9, 0.05, 0.05]
    assert cell["poi"] == 100 and cell["richness"] == 3
    assert cell["dominant"] == "food_and_drink" and cell["flagged"] is True
    assert cell["top_share"] == 0.9
    assert cell["hill_q1"] == pytest.approx(
        math.exp(-sum(p * math.log(p) for p in shares)), abs=1e-3)
    assert cell["hill_q2"] == pytest.approx(1 / sum(p * p for p in shares), abs=1e-3)


def test_even_cell_has_as_many_effective_categories_as_real_ones(output):
    _, by_cell, cells, _ = output
    cell = by_cell[cells[5]]["properties"]
    assert cell["hill_q1"] == pytest.approx(4) and cell["hill_q2"] == pytest.approx(4)
    assert cell["top_share"] == 0.25 and cell["flagged"] is False


def test_ties_break_alphabetically(output):
    _, by_cell, cells, _ = output
    cell = by_cell[cells[1]]["properties"]
    assert cell["top_share"] == 0.5 and cell["flagged"] is True
    assert cell["dominant"] == "education"
    assert list(cell["dna"]) == ["education", "shopping"]


def test_shares_sum_to_one(output):
    collection, _, _, _ = output
    for feature in collection["features"]:
        assert sum(feature["properties"]["dna"].values()) == pytest.approx(1, abs=5e-3)


def test_tfidf_matches_scikit_learn(output):
    collection, _, _, _ = output
    cells = [f["properties"] for f in collection["features"]]
    categories = sorted({c for cell in cells for c in cell["dna"]})
    counts = [[cell["dna"].get(c, 0) * cell["poi"] for c in categories] for cell in cells]
    shares = [[cell["dna"].get(c, 0) for c in categories] for cell in cells]
    idf = TfidfTransformer(norm=None, smooth_idf=True).fit(counts).idf_
    for cell, row in zip(cells, shares):
        for category, share, weight in zip(categories, row, idf):
            assert cell["tfidf"].get(category, 0) == pytest.approx(share * weight, abs=2e-3)


def test_metadata_records_the_run(output):
    collection, _, _, stdout = output
    meta = collection["metadata"]
    assert meta["bbox"] == [float(v) for v in BBOX]
    assert (meta["h3_res"], meta["taxonomy_level"], meta["min_poi"]) == (8, 1, 10)
    assert sum(meta["providers_pct"].values()) == pytest.approx(100, abs=0.2)
    assert set(meta["providers_pct"]) == {"meta", "Foursquare"}
    assert "18 cells, 2 flagged" in stdout


def test_two_runs_give_the_same_bytes(extract, tmp_path):
    path, _ = extract
    for name in ("a", "b"):
        assert run(tmp_path, *BBOX, name, str(path)).returncode == 0
    assert (tmp_path / "a.geojson").read_bytes() == (tmp_path / "b.geojson").read_bytes()


def test_swapped_bbox_is_refused(extract, tmp_path):
    path, _ = extract
    done = run(tmp_path, "34.30", "132.30", "34.50", "132.60", "swapped", str(path))
    assert done.returncode != 0 and "WEST SOUTH EAST NORTH" in done.stderr
    assert not (tmp_path / "swapped.geojson").exists()


def test_empty_bbox_asks_for_a_wider_one(extract, tmp_path):
    path, _ = extract
    done = run(tmp_path, "10.0", "10.0", "10.2", "10.2", "empty", str(path))
    assert done.returncode != 0 and "widen the bbox" in done.stderr
