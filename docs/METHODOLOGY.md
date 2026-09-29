# Methodology

What `dna.py` computes, in the order it computes it. The numbers that test these
choices are in [RESULTS.md](RESULTS.md); what can go wrong is in
[CAVEATS.md](../CAVEATS.md).

## 1. Input

Overture Maps Places, one row per place, read as GeoParquet from
`s3://overturemaps-us-west-2/release/<release>/theme=places/type=place/`.
Three columns are used:

| column | used for |
| --- | --- |
| `bbox` (struct of four doubles) | the bounding-box filter and the position of the place |
| `taxonomy.hierarchy` (list of strings) | the category, from the broadest branch to the leaf |
| `sources[1].dataset` | the provider of the place |

The filter `bbox.xmin BETWEEN west AND east AND bbox.ymin BETWEEN south AND north`
compares plain numeric columns. DuckDB checks it against the row-group
statistics in each parquet footer and fetches only the row groups that can
contain a match. That is why a city costs 30 to 42 MiB of an 11 GB dataset.
The geometry column is never read.

Places without a taxonomy are skipped: 1.6% to 7.5% of the places in the four
test cities.

## 2. Cells

Every place falls into the H3 cell of resolution 8 that contains its point
(`h3_latlng_to_cell`). Cells with fewer than `MIN_POI = 10` categorised places
are dropped. Resolution 8 cells average 0.58 to 0.78 km² in the test cities.

## 3. DNA

For a cell with `n_i` places in category `i` and `N` places in total, the share
is `p_i = n_i / N`. The vector of shares is the DNA of the cell. The category
is `taxonomy.hierarchy[LEVEL]`, with `LEVEL = 1`: the 13 top branches.

## 4. Diversity

| output | formula | reads as |
| --- | --- | --- |
| `richness` | number of categories with `n_i > 0` | how many functions are present; grows with `N` |
| `hill_q1` | `exp(−Σ p_i ln p_i)` | effective number of functions |
| `hill_q2` | `1 / Σ p_i²` | effective number of dominant functions |
| `top_share` | `max p_i` | how mono-functional the cell is |
| `flagged` | `top_share ≥ 0.5` | one function holds half the places |
| `dominant` | `argmax p_i`, ties broken alphabetically | the leading function |

Hill numbers come from ecology, where they count species in a habitat
(Hill 1973, [doi:10.2307/1934352](https://doi.org/10.2307/1934352)). A cell
with four equally common functions has `hill_q1 = hill_q2 = 4`. They depend on
sample size far less than richness does (Chao and Jost 2012,
[doi:10.1890/11-1952.1](https://doi.org/10.1890/11-1952.1)), which is the
subject of check 1.

The flag threshold is declared and not fitted: 0.5 means "half", and it is
easy to defend in a planning meeting.

## 5. TF-IDF signature

The share of a function says what a cell is made of. The signature says what
is unusual about it compared with the rest of the box:

```
tfidf_i = p_i × (1 + ln((1 + C) / (1 + c_i)))
```

`C` is the number of cells kept, `c_i` the number of cells where function `i`
occurs. This is the smoothed inverse document frequency of scikit-learn's
`TfidfTransformer`, with shares in place of raw counts and without the final
L2 normalisation. A test compares the two implementations. Food and drink
occurs almost everywhere and keeps a weight near 1; lodging is rarer and gains
weight.

## 6. HDBSCAN

`HDBSCAN(min_cluster_size=10)` from scikit-learn runs on the signatures,
Euclidean distance, all other parameters at their defaults. The label goes
into `cluster`; `-1` means noise. In the four test cities every cell is noise
(RESULTS, section 4). The step is kept because the absence of clusters is a
finding: at this scale the function mix is a continuum.

## 7. Output

A GeoJSON FeatureCollection, one hexagon per cell, in WGS 84. Properties:
`h3`, `poi`, `richness`, `hill_q1`, `hill_q2`, `top_share`, `flagged`,
`dominant`, `dna`, `tfidf`, `cluster`. The collection carries a `metadata`
member with the source release, the bbox, the parameters and
`providers_pct`, the provider blend of the box. Cells are sorted by H3 index
and map entries by value, so the same input gives the same bytes.

## 8. The two checks

**Check 1, cell size.** Cells are binned by place count (10 to 19, 20 to 39,
40 to 79, 80 to 159, 160 to 319, 320 and over) and cities are compared by
their medians inside each bin.

**Check 2, provider blend.** The metrics are recomputed on the places of one
provider (`sources[1].dataset = 'meta'`) and the ranking of the cities is
compared with the ranking on all sources.

`checks.py` adds sensitivity runs for the H3 resolution, the `MIN_POI`
threshold, the taxonomy level, a 4 km shift of the box, and a comparison of
two releases.

## 9. The test boxes

The four cities use boxes of the same ground area, 366 km². The width is
fixed at 0.20 degrees of longitude and the height follows from the latitude
`φ` of the centre:

```
width_km  = 0.20 × 111.320 × cos(φ)
height_deg = 366 / width_km / 110.574
```

| city | centre (lat, lon) | west south east north |
| --- | --- | --- |
| Hiroshima | 34.390, 132.450 | 132.35 34.2999 132.55 34.4801 |
| Belgrade | 44.805, 20.450 | 20.35 44.7002 20.55 44.9098 |
| Amsterdam | 52.370, 4.900 | 4.8 52.2483 5.0 52.4917 |
| London | 51.510, −0.120 | −0.22 51.3906 −0.02 51.6294 |

The four cities are a test bench. Nobody plans Hiroshima by comparing it with
Belgrade; the point of the comparison is to see which metrics survive a change
of country, language and data provider.
