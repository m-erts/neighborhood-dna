"""Live canary: the newest Overture release still has the columns dna.py reads.

Skipped unless DNA_LIVE=1, because it scans S3 for about 15 seconds. CI runs it
weekly. When Overture changes the places schema again, this is the test that
fails first.
"""
import json
import os
import pathlib
import subprocess
import sys

import pytest

SCRIPT = pathlib.Path(__file__).parent.parent / "dna.py"
HIROSHIMA = ["132.35", "34.2999", "132.55", "34.4801"]

pytestmark = pytest.mark.skipif(os.environ.get("DNA_LIVE") != "1",
                                reason="set DNA_LIVE=1 to scan Overture on S3")


def test_newest_release_runs_end_to_end(tmp_path):
    done = subprocess.run([sys.executable, str(SCRIPT), *HIROSHIMA, "hiroshima"],
                          cwd=tmp_path, capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stderr
    collection = json.loads((tmp_path / "hiroshima.geojson").read_text())
    cells = [f["properties"] for f in collection["features"]]
    assert 200 < len(cells) < 320, "Hiroshima had 252 cells in release 2026-09-23.1"
    assert {"h3", "poi", "hill_q1", "hill_q2", "top_share", "dominant", "dna"} <= set(cells[0])
    assert collection["metadata"]["providers_pct"]["meta"] > 50
