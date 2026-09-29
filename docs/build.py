#!/usr/bin/env python3
"""Build the figures and the slides from the data.

    python docs/build.py

Writes docs/assets/*.svg and docs/index.html. Every number on a slide is read from
docs/data/results.json; the code on the code slide is dna.py itself.
Needs the dev extras: pygments for the highlighting, segno for the QR code.
"""
import ast
import html
import json
import pathlib
import random
import re
import string

import figures
import segno
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import PythonLexer

DOCS = pathlib.Path(__file__).parent
REPO = "https://github.com/m-erts/neighborhood-dna"
SQL = ("SELECT|FROM|WHERE|AND|AS|WITH|OVER|WINDOW|QUALIFY|PARTITION BY|GROUP BY|ORDER BY|"
       "CREATE TABLE|BETWEEN|DISTINCT|DESC|INSTALL|LOAD|SET|ALL")
# the steps of the pipeline: title, first words of the first and of the last line
OUTLINE = [("Parameters", 'S3 = "s3://', "H3_RES, LEVEL, MIN_POI"),
           ("Read the bbox", "west, south, east, north", "sys.exit(\"bbox order"),
           ("Attach to S3, pick a release", 'duckdb.sql("INSTALL', "files = source"),
           ("Scan the places in the bbox", 'duckdb.sql(f"""CREATE TABLE', " AND bbox.xmin BETWEEN"),
           ("DNA, TF-IDF, Hill numbers: SQL", 'cells = duckdb.sql(f"""WITH', "FROM weighted"),
           ("HDBSCAN on the signatures", "cells = [dict(zip", "    [[cell[\"tfidf\"]"),
           ("Provider blend", "blend = dict(", "FROM places GROUP BY 1"),
           ("Write the GeoJSON", "meta = dict(", '      f"{source}')]


def code_lines(source):
    """Lines of code the way the test counts them: no blanks, comments or docstring."""
    doc = ast.parse(source).body[0]
    skipped = range(doc.lineno, doc.end_lineno + 1)
    return sum(1 for number, line in enumerate(source.splitlines(), 1)
               if line.strip() and not line.strip().startswith("#") and number not in skipped)


def highlighted(source):
    """dna.py as one span per line, SQL keywords marked inside the strings."""
    marked = highlight(source, PythonLexer(), HtmlFormatter(nowrap=True))

    def sql(match):
        return re.sub(rf"\b({SQL})\b", r'<span class="q">\1</span>', match.group(0))
    marked = re.sub(r'<span class="s[2a]?">[^<]*</span>', sql, marked)
    lines, carried = [], ""
    for line in marked.rstrip("\n").split("\n"):   # a span may run over several lines
        line = carried + line
        opened = re.findall(r"<span[^>]*>|</span>", line)
        stack = []
        for tag in opened:
            stack.pop() if tag == "</span>" else stack.append(tag)
        lines.append(f'<span class="l">{line}{"</span>" * len(stack)}</span>')
        carried = "".join(stack)
    return "".join(lines)   # each line is a block, a newline would double the spacing


def outline(source):
    lines, items = source.splitlines(), []
    for title, first, last in OUTLINE:
        start = next(i for i, line in enumerate(lines, 1) if line.strip().startswith(first))
        end = next(i for i, line in enumerate(lines, 1)
                   if i >= start and line.strip().startswith(last.strip()))
        items.append(f'<li><button type="button" data-lines="{start}-{end}" aria-pressed="false">'
                     f'{html.escape(title)}<small>lines {start} to {end}</small></button></li>')
    return "\n        ".join(items)


def idea(cell):
    """The real cell behind slide 3: a bar, its legend and a handful of dots."""
    labels = {key: (label, colour) for key, label, colour in figures.BRANCHES}
    bar, legend = [], []
    for key, label, colour in figures.BRANCHES:
        share = cell["dna"].get(key, 0)
        if share <= 0:
            continue
        caption = f"{share:.0%}" if share >= 0.07 else ""
        bar.append(f'<span style="flex:{share:.4f};background:{colour};'
                   f'color:{figures.ink(colour)}" title="{label} {share:.0%}">{caption}</span>')
    for key, share in list(cell["dna"].items())[:6]:
        label, colour = labels[key]
        legend.append(f'<span><i style="background:{colour}"></i>{label} {share:.0%}</span>')
    rng, dots = random.Random(cell["h3"]), []
    colours = [labels[key][1] for key, share in cell["dna"].items()
               for _ in range(round(share * 40))]
    while len(dots) < len(colours):
        x, y = rng.uniform(30, 170), rng.uniform(20, 160)
        if abs(y - 90) < 80 - abs(x - 100) * 0.5 - 8:    # inside the hexagon
            dots.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="4.5" fill="{colours[len(dots)]}" '
                        f'stroke="#111827" stroke-width="1.5"/>')
    aria = ", ".join(f"{labels[k][0]} {v:.0%}" for k, v in cell["dna"].items())
    return dict(idea_bar="".join(bar), idea_legend="".join(legend), idea_dots="".join(dots),
                idea_aria=aria, idea_name=f"{cell['district']}, Hiroshima", idea_h3=cell["h3"],
                idea_places=f"{cell['places']:,}", idea_q1=f"{cell['hill_q1']:.2f}",
                idea_q2=f"{cell['hill_q2']:.2f}", idea_top=f"{cell['top_share']:.2f}")


def values(results, cities, source):
    meta = results["meta"]
    cost = json.loads((DOCS / "data" / "cost.json").read_text())
    summary = {row["city"]: row for row in results["summary"]}
    blend = next(row for row in results["providers"] if row["provider"] == "meta")
    ranks = {row["city"]: row for row in results["meta_only"]}
    levels = {row["taxonomy_level"]: row["categories"] for row in results["categories_per_level"]}
    drift = next(row for row in results["drift"] if row["city"] == "hiroshima")
    noise = {city: (max(f["properties"]["cluster"] for f in c["features"]) + 1,
                    sum(f["properties"]["cluster"] < 0 for f in c["features"]) / len(c["features"]))
             for city, c in cities.items()}     # what dna.py itself wrote
    checked = next(row for row in results["hdbscan"]
                   if row["signature_and_min_cluster_size"] == "tf-idf, 10")
    for city, (clusters, share) in noise.items():
        assert checked[city] == f"{clusters} clusters, {share:.0%} noise", (city, checked[city])
    assert len(set(noise.values())) == 1, "cities differ: reword the last slide"
    clusters, share = next(iter(noise.values()))
    smallest = min(summary.values(), key=lambda row: row["mean_cell_km2"])
    largest = max(summary.values(), key=lambda row: row["mean_cell_km2"])
    ordinal = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th"}
    hiroshima = cities["hiroshima"]
    cells = [f["properties"] for f in hiroshima["features"]]
    box = " ".join(f"{v:g}" for v in hiroshima["metadata"]["bbox"])
    terminal = (f"hiroshima.geojson: {len(cells)} cells, {sum(c['flagged'] for c in cells)} "
                f"flagged, Overture {hiroshima['metadata']['source']}\n"
                f"HDBSCAN {max(c['cluster'] for c in cells) + 1} clusters, "
                f"{sum(c['cluster'] < 0 for c in cells) / len(cells):.0%} noise\n"
                f"{hiroshima['metadata']['providers_pct']}")
    out = dict(
        release=meta["release"], previous=meta["compared_with"][0], hiroshima_bbox=box,
        terminal_output=html.escape(terminal, quote=True),
        places_millions=f"{meta['places_in_release'] / 1e6:.0f}",
        release_gb=f"{cost['release_gb']:g}",
        mib_low=f"{min(c['mib_read'] for c in cost['cities'].values()):.0f}",
        mib_high=f"{max(c['mib_read'] for c in cost['cities'].values()):.0f}",
        level_1=levels[1], level_2=levels[2],
        gap_richness=f"{results['bins_gap'][0]['largest_gap_richness']:g}",
        gap_hill=f"{results['bins_gap'][0]['largest_gap_hill_q2']:.2f}",
        london_rank_all=ordinal[ranks["london"]["rank_all"]],
        london_rank_meta=ordinal[ranks["london"]["rank_meta"]],
        area_low=f"{smallest['mean_cell_km2']:.2f}", area_low_city=smallest["city"].title(),
        area_high=f"{largest['mean_cell_km2']:.2f}", area_high_city=largest["city"].title(),
        drift_old=drift["flagged_old"], drift_new=drift["flagged_new"],
        drift_both=drift["flagged_in_both"], ties=summary["hiroshima"]["tied_top_category"],
        hdbscan=f"{clusters} clusters and {share:.0%} noise",
        code_lines=code_lines(source), code_html=highlighted(source), outline=outline(source),
        **idea(next(d for d in results["districts"] if d["district"] == "Kamiyacho")))
    for city, row in summary.items():
        out |= {f"{city}_cells": row["cells"], f"{city}_flagged": row["flagged"],
                f"{city}_meta": f"{blend[city]:.1f}", f"{city}_meta_round": f"{blend[city]:.0f}"}
    return out


if __name__ == "__main__":
    results, cities = figures.draw()
    source = (DOCS.parent / "dna.py").read_text()
    segno.make(REPO, error="m").save(str(DOCS / "assets" / "qr.svg"), scale=8, border=2,
                                     dark="#0B0F19", light="#FFFFFF", xmldecl=False)
    template = string.Template((DOCS / "slides.template.html").read_text())
    (DOCS / "index.html").write_text(template.substitute(values(results, cities, source)))
    readme = DOCS.parent / "README.md"     # the code block of the README is dna.py itself
    shown = re.sub(r"(<!-- dna.py:start -->\n).*?(<!-- dna.py:end -->)",
                   lambda m: f"{m.group(1)}```python\n{source.strip()}\n```\n{m.group(2)}",
                   readme.read_text(), flags=re.S)
    readme.write_text(shown)
    print("docs/assets/qr.svg\ndocs/index.html\nREADME.md")
