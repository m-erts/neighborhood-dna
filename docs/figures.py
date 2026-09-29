#!/usr/bin/env python3
"""Draw docs/assets/*.svg from docs/data. No plotting library, no hand-typed numbers.

    python docs/figures.py

Colours and type come from DESIGN.md (Spatial Terminal). The figures are static
so that GitHub can show them in README.md; the slides and the demo add hover.
"""
import json
import math
import pathlib
from xml.sax.saxutils import escape

DOCS = pathlib.Path(__file__).parent
DATA, ASSETS = DOCS / "data", DOCS / "assets"

# DESIGN.md tokens
CANVAS, SURFACE, ACCENT = "#0B0F19", "#111827", "#38BDF8"
TEXT, TEXT_2, TEXT_3, GRID = "#E5E7EB", "#9CA3AF", "#7B8494", "#1F2937"
ROSE, AMBER, EMERALD, INDIGO, SLATE = "#F43F5E", "#F59E0B", "#10B981", "#818CF8", "#64748B"
SANS = "Inter, -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"
MONO = "'JetBrains Mono', 'Geist Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
# top share: one hue, brighter means more mono-functional (validated on CANVAS)
RAMP = [(0.25, "#0C4A6E"), (0.30, "#0369A1"), (0.40, "#0EA5E9"), (0.50, "#38BDF8"), (9, "#BAE6FD")]
RAMP_LABELS = ["under 0.25", "0.25 to 0.30", "0.30 to 0.40", "0.40 to 0.50", "0.50 and over"]

# The 13 level-1 branches of the Overture taxonomy, folded into the four DESIGN.md
# clusters. Order is fixed: a branch keeps its place and colour in every bar.
CLUSTERS = [
    ("Food, beverage and nightlife", ROSE, [("food_and_drink", "food and drink", "#F43F5E")]),
    ("Retail, commerce and services", AMBER, [
        ("shopping", "shopping", "#F59E0B"),
        ("services_and_business", "services and business", "#FCD34D"),
        ("lifestyle_services", "lifestyle", "#B45309")]),
    ("Civic, arts and culture", EMERALD, [
        ("health_care", "health", "#10B981"), ("education", "education", "#6EE7B7"),
        ("community_and_government", "civic", "#047857"),
        ("cultural_and_historic", "heritage", "#34D399"),
        ("arts_and_entertainment", "arts", "#A7F3D0"),
        ("sports_and_recreation", "sport", "#059669")]),
    ("Transit and mobility", INDIGO, [
        ("travel_and_transportation", "transport", "#818CF8"), ("lodging", "lodging", "#C7D2FE")]),
    ("Other", SLATE, [("geographic_entities", "geographic", "#64748B")]),
]
BRANCHES = [(key, label, colour) for _, _, members in CLUSTERS for key, label, colour in members]
CITY_NAMES = {"hiroshima": "Hiroshima", "belgrade": "Belgrade",
              "amsterdam": "Amsterdam", "london": "London"}


def luminance(colour):
    channels = [int(colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def ink(colour):
    """Text colour that stays readable on a filled mark."""
    return CANVAS if luminance(colour) > 0.2 else "#FFFFFF"


def text(x, y, content, size=14, colour=TEXT, family=SANS, weight=400, anchor="start", **extra):
    attributes = "".join(f' {k.replace("_", "-")}="{v}"' for k, v in extra.items())
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-family="{family}" font-size="{size}" '
            f'font-weight="{weight}" fill="{colour}" text-anchor="{anchor}"{attributes}>'
            f'{escape(str(content))}</text>')


def svg(width, height, body, title, description, crop=0, framed=True, foot=0):
    """crop hides the heading band, foot the footnote, framed=False the card: for slides."""
    height -= foot
    frame = (f'<rect y="{crop}" width="{width}" height="{height - crop}" rx="8" fill="{CANVAS}"/>'
             f'<rect x="0.5" y="{crop + 0.5}" width="{width - 1}" height="{height - crop - 1}" '
             f'rx="8" fill="none" stroke="#FFFFFF" stroke-opacity="0.08"/>') if framed else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 {crop} {width} {height - crop}" '
            f'role="img" aria-labelledby="t d">'
            f'<title id="t">{escape(title)}</title><desc id="d">{escape(description)}</desc>'
            f'{frame}{"".join(body)}</svg>\n')


def hexagons(features, x0, y0, width, km_per_px=None):
    """Project the cells of one city into a panel. Returns polygons and the panel height."""
    rings = [f["geometry"]["coordinates"][0] for f in features]
    lons = [p[0] for ring in rings for p in ring]
    lats = [p[1] for ring in rings for p in ring]
    lat0 = (min(lats) + max(lats)) / 2
    kx, ky = 111.320 * math.cos(math.radians(lat0)), 110.574
    scale = 1 / km_per_px if km_per_px else width / ((max(lons) - min(lons)) * kx)
    left = x0 + (width - (max(lons) - min(lons)) * kx * scale) / 2
    out = []
    for feature, ring in zip(features, rings):
        points = " ".join(f"{left + (lon - min(lons)) * kx * scale:.1f},"
                          f"{y0 + (max(lats) - lat) * ky * scale:.1f}" for lon, lat in ring[:-1])
        out.append((points, feature["properties"]))
    return out, (max(lats) - min(lats)) * ky * scale


def shade(share):
    return next(colour for limit, colour in RAMP if share < limit)


def cell_marks(polygons):
    """Filled cells first, then a white ring on the flagged ones so it is never covered."""
    fills = [f'<polygon points="{points}" fill="{shade(p["top_share"])}" stroke="{CANVAS}" '
             f'stroke-width="0.8"/>' for points, p in polygons]
    rings = [f'<polygon points="{points}" fill="none" stroke="#FFFFFF" stroke-width="1.6" '
             f'stroke-linejoin="round"/>' for points, p in polygons if p["flagged"]]
    return fills + rings


def ramp_legend(x, y):
    body = [text(x, y + 11, "top share", 12, TEXT_2, MONO)]
    x += 92
    for (_, colour), label in zip(RAMP, RAMP_LABELS):
        body += [f'<rect x="{x}" y="{y}" width="14" height="14" rx="2" fill="{colour}"/>',
                 text(x + 20, y + 11, label, 12, TEXT_2, MONO)]
        x += 34 + len(label) * 7.3
    body += [f'<rect x="{x + 1}" y="{y + 1}" width="12" height="12" rx="2" fill="none" '
             f'stroke="#FFFFFF" stroke-width="1.6"/>',
             text(x + 20, y + 11, "flagged: one function holds half the places", 12, TEXT_2, MONO)]
    return body


def banner(cities):
    city = cities["hiroshima"]
    meta, cells = city["metadata"], [f["properties"] for f in city["features"]]
    width, height = 1200, 380
    box = " ".join(f"{v:g}" for v in meta["bbox"])
    lines = [(f"$ python dna.py {box} hiroshima", TEXT),
             (f"hiroshima.geojson: {len(cells)} cells, {sum(c['flagged'] for c in cells)} flagged, "
              f"Overture {meta['source']}", TEXT_2),
             (f"HDBSCAN {max(c['cluster'] for c in cells) + 1} clusters, "
              f"{sum(c['cluster'] < 0 for c in cells) / len(cells):.0%} noise", TEXT_2),
             (str(meta["providers_pct"]), TEXT_2)]
    body = [text(48, 84, "Neighborhood DNA", 44, TEXT, SANS, 700, letter_spacing="-0.5"),
            text(48, 120, "50 lines of Python over Overture Maps Places", 19, TEXT_2),
            f'<rect x="48.5" y="156.5" width="700" height="176" rx="6" fill="{SURFACE}" '
            f'stroke="#FFFFFF" stroke-opacity="0.08"/>']
    for i, (line, colour) in enumerate(lines):
        shown = line if len(line) <= 78 else line[:75] + "..."
        body.append(text(72, 198 + i * 30, shown, 14, colour, MONO, xml_space="preserve"))
    body.append(f'<rect x="72" y="{198 + len(lines) * 30 - 13}" width="9" height="17" '
                f'fill="{ACCENT}"/>')
    polygons, _ = hexagons(city["features"], 800, 0, 352)
    lowest = max(float(c.split(",")[1]) for points, _ in polygons for c in points.split())
    body.append(f'<g transform="translate(0 {(height - lowest) / 2:.1f})">'
                f'{"".join(cell_marks(polygons))}</g>')
    return dict(width=width, height=height, body=body, title="Neighborhood DNA", head=0,
                description=f"Terminal output of dna.py for Hiroshima next to the map it "
                f"produces: {len(cells)} H3 cells shaded by top category share.")


def maps(cities, summary):
    width, panel, top = 1200, 250, 138
    gap = (width - 96 - 4 * panel) / 3
    tallest, body = 0, [text(48, 46, "The blocks where one function owns the street",
                             24, TEXT, SANS, 700)]
    scale = max((m["bbox"][2] - m["bbox"][0])
                * 111.320 * math.cos(math.radians((m["bbox"][1] + m["bbox"][3]) / 2))
                for m in (c["metadata"] for c in cities.values())) / panel
    for i, (key, city) in enumerate(cities.items()):
        x = 48 + i * (panel + gap)
        polygons, tall = hexagons(city["features"], x, top + 8, panel, km_per_px=scale)
        tallest = max(tallest, tall)
        row = summary[key]
        body += [text(x, top - 30, CITY_NAMES[key], 18, TEXT, SANS, 600),
                 text(x, top - 10, f"{row['flagged']} of {row['cells']} cells flagged",
                      13, TEXT_2, MONO), *cell_marks(polygons)]
    base = top + tallest + 40
    body += ramp_legend(48, base)
    body += [f'<rect x="{width - 48 - 5 / scale:.1f}" y="{base + 37}" width="{5 / scale:.1f}" '
             f'height="2" fill="{TEXT_2}"/>',
             text(width - 48 - 5 / scale - 10, base + 42, "5 km", 12, TEXT_2, MONO, anchor="end")]
    release = next(iter(cities.values()))["metadata"]["source"]
    body.append(text(48, base + 42, f"H3 resolution 8, the same 366 km2 box in every city, "
                     f"Overture {release}. Same scale in all four panels.", 12, TEXT_3, MONO))
    return dict(width=width, height=base + 66, body=body, head=76,
                title="Top category share by H3 cell in four cities",
                description="Hexagon maps of Hiroshima, Belgrade, Amsterdam and London. Brighter "
                "cells are more mono-functional; flagged cells carry a white ring.")


def dna_bar(x, y, width, height, dna):
    """One stacked bar: fixed branch order, 2 px gaps, labels only where they fit."""
    body, cursor = [], x
    for key, label, colour in BRANCHES:
        share = dna.get(key, 0)
        span = share * width
        if span < 0.5:
            continue
        body.append(f'<rect x="{cursor:.1f}" y="{y}" width="{max(span - 2, 0.6):.1f}" '
                    f'height="{height}" fill="{colour}"><title>{escape(label)} '
                    f'{share:.0%}</title></rect>')
        for caption in (f"{label} {share:.0%}", f"{share:.0%}"):
            if len(caption) * 7.3 + 14 <= span - 2:
                body.append(text(cursor + 7, y + height / 2 + 4.5, caption, 12, ink(colour),
                                 MONO, 500))
                break
        cursor += span
    return body


def districts(results):
    rows = results["districts"]
    width, left, bar, row_height = 1200, 300, 640, 46
    body = [text(48, 46, "Three kinds of neighbourhood, three cities", 24, TEXT, SANS, 700),
            text(48, 72, "Each bar is one H3 cell of about 0.6 km2: the share of its places "
                 "by function.", 14, TEXT_2)]
    y = 108
    for name, colour, members in CLUSTERS:
        body.append(f'<rect x="48" y="{y - 11}" width="12" height="12" rx="2" fill="{colour}"/>')
        body.append(text(68, y, name, 13, TEXT, SANS, 500))
        cursor = 300
        for _, label, tint in members:
            body.append(f'<rect x="{cursor}" y="{y - 10}" width="10" height="10" rx="2" '
                        f'fill="{tint}"/>')
            body.append(text(cursor + 15, y, label, 12, TEXT_2, MONO))
            cursor += 15 + len(label) * 7.3 + 18
        y += 22
    y += 14
    body += [text(left + bar + 40, y, "places", 12, TEXT_3, MONO, anchor="end", dx=36),
             text(left + bar + 150, y, "Hill q2", 12, TEXT_3, MONO, anchor="end"),
             text(left + bar + 232, y, "top share", 12, TEXT_3, MONO, anchor="end")]
    y += 10
    previous = None
    for row in rows:
        if row["city"] != previous:
            y += 16
            body += [f'<rect x="48" y="{y}" width="{width - 96}" height="1" fill="#FFFFFF" '
                     f'fill-opacity="0.08"/>',
                     text(48, y + 24, CITY_NAMES[row["city"]], 13, TEXT_3, MONO)]
            y += 36
            previous = row["city"]
        body += [text(48, y + 15, row["district"], 15, TEXT, SANS, 600),
                 text(48, y + 33, row["known_as"], 12, TEXT_2, MONO),
                 *dna_bar(left, y, bar, 30, row["dna"]),
                 text(left + bar + 76, y + 20, f"{row['places']:,}", 13, TEXT, MONO, anchor="end"),
                 text(left + bar + 150, y + 20, f"{row['hill_q2']:.2f}", 13, TEXT, MONO,
                      anchor="end"),
                 text(left + bar + 232, y + 20, f"{row['top_share']:.2f}", 13,
                      TEXT, MONO, 700 if row["flagged"] else 400, anchor="end")]
        if row["flagged"]:
            body.append(f'<rect x="{left + bar + 196}" y="{y + 26}" width="36" height="2" '
                        f'fill="{ACCENT}"/>')
        y += row_height
    body.append(text(48, y + 22, f"Underlined top share: flagged, one function holds half the "
                     f"places. Overture {results['meta']['release']}, taxonomy level 1.",
                     12, TEXT_3, MONO))
    return dict(width=width, height=y + 46, body=body, head=84,
                title="DNA of nine named districts",
                description="Stacked bars of category shares for a financial district, a going-out "
                "district and a residential suburb in London, Amsterdam and Hiroshima.")


def panel(x, y, width, height, title, unit, top, table, bins, label_lines, note):
    """Lines for four cities over density bins, with the range between cities shaded."""
    body = [text(x, y - 40, title, 17, TEXT, SANS, 600), text(x, y - 20, unit, 12, TEXT_2, MONO)]
    ticks = [top * i / 4 for i in range(5)]
    for tick in ticks:
        ty = y + height - tick / top * height
        body += [f'<rect x="{x}" y="{ty:.1f}" width="{width}" height="1" fill="{GRID}"/>',
                 text(x - 10, ty + 4, f"{tick:g}", 12, TEXT_2, MONO, anchor="end")]
    step = width / (len(bins) - 1)
    xs = [x + i * step for i in range(len(bins))]
    for px, name in zip(xs, bins):
        body.append(text(px, y + height + 22, name, 12, TEXT_2, MONO, anchor="middle"))
    body.append(text(x + width / 2, y + height + 44, "places per cell", 12, TEXT_3, MONO,
                     anchor="middle"))
    series = {city: [row[city] for row in table] for city in CITY_NAMES}

    def py(value):
        return y + height - value / top * height
    low = [min(values[i] for values in series.values()) for i in range(len(bins))]
    high = [max(values[i] for values in series.values()) for i in range(len(bins))]
    band = " ".join(f"{px:.1f},{py(v):.1f}" for px, v in zip(xs, high))
    band += " " + " ".join(f"{px:.1f},{py(v):.1f}" for px, v in reversed(list(zip(xs, low))))
    body.append(f'<polygon points="{band}" fill="{ACCENT}" fill-opacity="0.16"/>')
    for city, values in series.items():
        points = " ".join(f"{px:.1f},{py(v):.1f}" for px, v in zip(xs, values))
        body.append(f'<polyline points="{points}" fill="none" stroke="{TEXT_2}" '
                    f'stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>')
        for px, value, name in zip(xs, values, bins):
            body.append(f'<circle cx="{px:.1f}" cy="{py(value):.1f}" r="4" fill="{TEXT_2}" '
                        f'stroke="{CANVAS}" stroke-width="2"><title>{CITY_NAMES[city]}, '
                        f'{name} places: {value:g}</title></circle>')
    if label_lines:
        ends = sorted(((values[-1], city) for city, values in series.items()), reverse=True)
        placed = None
        for value, city in ends:
            ty = py(value) + 4
            ty = ty if placed is None else max(ty, placed + 15)
            body.append(text(xs[-1] + 12, ty, f"{CITY_NAMES[city]} {value:.2f}", 12, TEXT, MONO))
            placed = ty
    else:
        body.append(text(xs[-1] + 12, py(high[-1]) + 4, "all four", 12, TEXT, MONO))
        body.append(text(xs[-1] + 12, py(high[-1]) + 20, "cities", 12, TEXT, MONO))
    body.append(text(x, y + height + 76, note, 14, TEXT, SANS, 500))
    return body


def cell_size(results):
    gap = results["bins_gap"][0]
    bins = [row["places_per_cell"].split(". ")[1] for row in results["bins_richness"]]
    body = [text(48, 46, "Check 1: the obvious metric sees nothing", 24, TEXT, SANS, 700),
            text(48, 72, "Median per density bin, one line per city. The shaded band is the "
                 "range between cities.", 14, TEXT_2)]
    body += panel(96, 150, 400, 250, "Category richness", "categories present in the cell", 16,
                  results["bins_richness"], bins, False,
                  f"Largest gap between cities: {gap['largest_gap_richness']:g} category. "
                  f"r = {gap['r_richness']:.2f} with log(places).")
    body += panel(680, 150, 400, 250, "Hill number, q = 2", "effective dominant categories", 8,
                  results["bins_hill_q2"], bins, True,
                  f"Largest gap between cities: {gap['largest_gap_hill_q2']:.2f}. "
                  f"r = {gap['r_hill_q2']:.2f} with log(places).")
    body.append(text(48, 510, f"Overture {results['meta']['release']}, H3 resolution 8, "
                     f"taxonomy level 1. Table: docs/RESULTS.md, section 2.", 12, TEXT_3, MONO))
    return dict(width=1200, height=534, body=body, head=84, foot=44,
                title="Richness against Hill q2 by density bin",
                description="Category richness rises with places per cell and is almost identical "
                "in four cities. Hill q2 flattens and separates the cities.")


def sources(results):
    body = [text(48, 46, "Check 2: one filter changes the ranking", 24, TEXT, SANS, 700),
            text(48, 72, "Overture blends providers, and the blend differs by city. Keep only "
                 "Meta places and London overtakes Belgrade.", 14, TEXT_2)]
    blend = {city: next(r[city] for r in results["providers"] if r["provider"] == "meta")
             for city in CITY_NAMES}
    body += [text(48, 126, "Places whose first source is Meta", 17, TEXT, SANS, 600),
             text(48, 146, "% of categorised places", 12, TEXT_2, MONO)]
    y = 176
    for city, share in sorted(blend.items(), key=lambda item: -item[1]):
        colour = ACCENT if city == "london" else TEXT_2
        body += [text(48, y + 15, CITY_NAMES[city], 14, TEXT, SANS, 500),
                 f'<rect x="150" y="{y}" width="300" height="20" fill="{GRID}"/>',
                 f'<path d="M150 {y}h{share * 3 - 4:.1f}a4 4 0 0 1 4 4v12a4 4 0 0 1 -4 4'
                 f'h-{share * 3 - 4:.1f}z" fill="{colour}"><title>{CITY_NAMES[city]}: '
                 f'{share:.1f}% Meta</title></path>',
                 text(462, y + 15, f"{share:.1f}", 13, TEXT, MONO)]
        y += 44
    x0, x1, top, height, low, high = 700, 1000, 150, 270, 5.0, 7.0

    def py(value):
        return top + height - (value - low) / (high - low) * height
    body += [text(560, 126, "Median Hill q2 across cells", 17, TEXT, SANS, 600)]
    for x in (x0, x1):
        body.append(f'<rect x="{x}" y="{top}" width="1" height="{height}" fill="{GRID}"/>')
    body += [text(x0, top + height + 28, "all sources", 13, TEXT, MONO, anchor="middle"),
             text(x1, top + height + 28, "Meta only", 13, TEXT, MONO, anchor="middle")]
    for row in sorted(results["meta_only"], key=lambda r: r["city"] == "london"):
        colour = ACCENT if row["city"] == "london" else TEXT_2
        a, b = py(row["all_sources"]), py(row["meta_only"])
        body += [f'<line x1="{x0}" y1="{a:.1f}" x2="{x1}" y2="{b:.1f}" stroke="{colour}" '
                 f'stroke-width="{2.5 if row["city"] == "london" else 2}" '
                 f'stroke-linecap="round"/>',
                 f'<circle cx="{x0}" cy="{a:.1f}" r="5" fill="{colour}" stroke="{CANVAS}" '
                 f'stroke-width="2"/>',
                 f'<circle cx="{x1}" cy="{b:.1f}" r="5" fill="{colour}" stroke="{CANVAS}" '
                 f'stroke-width="2"/>',
                 text(x0 - 14, a + 4, f"{CITY_NAMES[row['city']]} {row['all_sources']:.2f}",
                      13, TEXT, MONO, anchor="end"),
                 text(x1 + 14, b + 4, f"{row['meta_only']:.2f}", 13, TEXT, MONO)]
    london = next(r for r in results["meta_only"] if r["city"] == "london")
    ordinal = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th"}
    body.append(text(x1 + 60, py(london["meta_only"]) + 4,
                     f"London: {ordinal[london['rank_all']]} to {ordinal[london['rank_meta']]}",
                     13, TEXT, SANS, 600))
    body.append(text(48, 500, f"Overture {results['meta']['release']}. Meta only is a "
                     f"sensitivity test, not the truth. Table: docs/RESULTS.md, section 3.",
                     12, TEXT_3, MONO))
    return dict(width=1200, height=524, body=body, head=92, foot=44,
                title="Provider blend and the ranking of cities",
                description="Share of places sourced from Meta per city, and median Hill q2 with "
                "all sources against Meta only. London moves above Belgrade.")


def draw():
    """Write every figure twice: framed for README.md, bare for the slides."""
    results = json.loads((DATA / "results.json").read_text())
    cities = {key: json.loads((DATA / f"{key}.geojson").read_text()) for key in CITY_NAMES}
    summary = {row["city"]: row for row in results["summary"]}
    ASSETS.mkdir(exist_ok=True)
    figures = {"banner": banner(cities), "maps": maps(cities, summary),
               "districts": districts(results), "check-cell-size": cell_size(results),
               "check-sources": sources(results)}
    for name, figure in figures.items():
        head, foot = figure.pop("head"), figure.pop("foot", 0)
        (ASSETS / f"{name}.svg").write_text(svg(**figure))
        if head:
            (ASSETS / f"{name}-slide.svg").write_text(
                svg(**figure, crop=head, framed=False, foot=foot))
        print(f"docs/assets/{name}.svg")
    taxonomy = {"clusters": [{"name": name, "colour": colour,
                              "branches": [{"key": k, "label": lab, "colour": c}
                                           for k, lab, c in members]}
                             for name, colour, members in CLUSTERS],
                "ramp": [{"below": limit, "colour": colour, "label": label}
                         for (limit, colour), label in zip(RAMP, RAMP_LABELS)]}
    (DATA / "taxonomy.json").write_text(json.dumps(taxonomy, indent=1))
    return results, cities


if __name__ == "__main__":
    draw()
