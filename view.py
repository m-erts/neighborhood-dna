#!/usr/bin/env python3
"""Open a dna.py result as an interactive map in the browser.

    pip install ".[viz]"
    python view.py hiroshima.geojson     # writes hiroshima.html

Cells are shaded by top category share, flagged cells get a white outline.
For a viewer without Python, drop the GeoJSON on docs/demo.html.
"""
import pathlib
import sys

import geopandas as gpd
import numpy as np
from lonboard import Map, PolygonLayer

# top share classes, the same ramp as the figures (DESIGN.md accent, five steps)
STEPS = [0.25, 0.30, 0.40, 0.50]
RAMP = np.array([[12, 74, 110], [3, 105, 161], [14, 165, 233], [56, 189, 248], [186, 230, 253]],
                dtype=np.uint8)

if len(sys.argv) != 2:
    sys.exit(__doc__)
source = pathlib.Path(sys.argv[1])
cells = gpd.read_file(source)
layer = PolygonLayer.from_geopandas(
    cells[["h3", "poi", "hill_q1", "hill_q2", "top_share", "dominant", "geometry"]],
    get_fill_color=RAMP[np.digitize(cells["top_share"], STEPS)],
    get_line_color=[255, 255, 255],
    get_line_width=np.where(cells["flagged"], 30, 0).astype(np.float32),
    opacity=0.85, pickable=True)
target = source.with_suffix(".html")
Map(layer).to_html(target)
print(f"{target}: {len(cells)} cells, {int(cells['flagged'].sum())} flagged")
