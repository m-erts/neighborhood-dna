#!/usr/bin/env python3
"""What one city costs: megabytes read from S3 and seconds on the clock.

    python cost.py [RELEASE]

Every city is scanned cold, in a fresh DuckDB connection, with the query dna.py
runs. Then dna.py itself is timed end to end. Writes docs/data/cost.json. The
numbers depend on the network and the machine, so both are recorded.
"""
import datetime
import json
import pathlib
import platform
import re
import subprocess
import sys
import time
import urllib.request

import duckdb

S3 = "s3://overturemaps-us-west-2/release"
LIST = "https://overturemaps-us-west-2.s3.us-west-2.amazonaws.com/?list-type=2&prefix=release/"
ROOT = pathlib.Path(__file__).parent
BOXES = json.loads((ROOT / "docs/data/results.json").read_text())["meta"]["boxes"]


def newest():
    found = duckdb.sql(f"FROM glob('{S3}/*/theme=places/*/*')").fetchall()
    return max(path.split("/")[4] for path, in found)


def scan(release, west, south, east, north):
    con = duckdb.connect()
    con.sql("INSTALL httpfs; LOAD httpfs; SET s3_region = 'us-west-2';")
    started = time.time()
    plan = con.sql(f"""
    EXPLAIN ANALYZE
    SELECT bbox.ymin, bbox.xmin, taxonomy.hierarchy, sources[1].dataset
    FROM read_parquet('{S3}/{release}/theme=places/type=place/*')
    WHERE bbox.xmin BETWEEN {west} AND {east} AND bbox.ymin BETWEEN {south} AND {north}
      AND len(taxonomy.hierarchy) > 0""").fetchall()[0][1]
    return dict(scan_seconds=round(time.time() - started, 1),
                mib_read=float(re.search(r"in: ([\d.]+) MiB", plan).group(1)),
                http_get=int(re.search(r"#GET: (\d+)", plan).group(1)))


if __name__ == "__main__":
    duckdb.sql("INSTALL httpfs; LOAD httpfs; SET s3_region = 'us-west-2';")
    release = sys.argv[1] if len(sys.argv) > 1 else newest()
    listing = urllib.request.urlopen(f"{LIST}{release}/theme=places/type=place/").read().decode()
    sizes = [int(size) for size in re.findall(r"<Size>(\d+)</Size>", listing)]
    cost = dict(release=release, measured=str(datetime.datetime.now(datetime.UTC).date()),
                machine=f"{platform.system()} {platform.machine()}, Python "
                        f"{platform.python_version()}, DuckDB {duckdb.__version__}",
                release_files=len(sizes), release_gb=round(sum(sizes) / 1e9, 1), cities={})
    for city, box in BOXES.items():
        cost["cities"][city] = scan(release, *box)
        started = time.time()
        subprocess.run([sys.executable, str(ROOT / "dna.py"), *map(str, box),
                        f"/tmp/cost_{city}", release], check=True, capture_output=True)
        cost["cities"][city]["dna_py_seconds"] = round(time.time() - started, 1)
        print(city, cost["cities"][city], flush=True)
    (ROOT / "docs/data/cost.json").write_text(json.dumps(cost, indent=1))
