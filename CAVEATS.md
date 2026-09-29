# Caveats

The last slide of the talk promised "code, data and the full list of caveats".
This is the list. Each item either broke one of my own results or will break
yours. Numbers come from [`docs/RESULTS.md`](docs/RESULTS.md): Overture release
`2026-09-23.1`, four cities, a 366 km² box each.

Items 2, 4, 8, 9 and 10 are new. I found them after the talk, while packaging
the code, and two of them correct things I said on stage.

## The data

**1. `categories` is gone.** Overture removed it from the places schema in
release `2026-09-23.0`. Write against `taxonomy.hierarchy`. `basic_category`
still exists but it is flat: it has no branches to roll up to.

**2. A release lives for 60 days.** On stage I said that a pinned release
reproduces in December. It does not. Overture keeps about two monthly releases
in its buckets, and `2026-07-22.0`, the one behind the slides, was deleted
before the end of September. `dna.py` therefore takes the newest release unless
you name one, and it accepts a local parquet extract. If a number matters, keep
the extract: `checks.py` writes one per city into `data/`, 2 to 22 MB each.

**3. The sources column decides rankings.** Every place names the provider it
came from, and the blend differs by city: Belgrade is 92.7% Meta, London 60.8%.
Keep only Meta places and London's median Hill q2 rises from 5.97 to 6.74,
which moves it past Belgrade (6.38 to 6.52). Part of any difference between
two cities is a difference between two data pipelines. A single-provider slice
is a sensitivity test and not the truth.

**4. H3 cells are not equal-area.** I said "H3, because equal area matters".
H3 is closer to equal-area than a degree grid, and still not equal: at
resolution 8 the mean cell is 0.58 km² in Hiroshima and 0.78 km² in Belgrade, a
ratio of 1.36. A Belgrade cell collects places from a third more ground.
Comparing cities inside density bins (item 6) absorbs part of this.

**5. No confidence filter.** Overture scores every place. The share of places
with confidence below 0.5 is 7% in Hiroshima, 20% in London, 26% in Amsterdam
and 32% in Belgrade. `dna.py` counts them all. Add
`AND confidence >= 0.5` to the scan if closed or doubtful places would hurt
your use.

**6. There is no housing in a POI dataset.** A residential suburb does not
read as mono-functional. It reads as sparse and mixed: Muswell Hill has 335
places and a Hill q2 of 6.08, while the City of London has 3,563 and 2.89. Read
the place count next to the mix, never the mix alone.

## The metric

**7. Richness measures your data.** The number of categories present in a cell
rises with the number of places in it (r = 0.81 with log places) and barely
differs between cities: inside a density bin the four cities stay within one
category of each other. Hill q2 correlates at 0.24 and separates the cities by
up to 1.98. Compare cities only inside matched density bins.

**8. Ties.** In 37 Hiroshima cells two categories share first place. The
original script used `arg_max`, which returns either of them, so two runs over
the same data painted different maps. Ties now break alphabetically. That is
arbitrary, and it is the same every time.

**9. The shortlist moves between releases.** Hiroshima had 16 flagged cells in
`2026-08-19.0` and 13 in `2026-09-23.1`; 13 appear in both. Amsterdam went
from 38 to 39 with 32 in both. Most flagged cells sit close to the 0.5
threshold and hold few places, so a handful of new records moves them. State
the release next to every count.

**10. HDBSCAN finds no types.** The abstract promised a typology of
neighbourhoods. With `min_cluster_size=10` HDBSCAN labels every cell as noise
in all four cities. With `min_cluster_size=5` it finds two clusters at best
and still leaves 46% to 96% of the cells as noise. The result is also fragile: feed London the same signature without rounding it
to three decimals and two small clusters appear. The function mix of a city is
a continuum at this scale. `dna.py` still runs the step, because your city may
differ and because "no clusters here" is an answer.

**11. The taxonomy level is a dial.** Level 1 has 13 branches, level 2 has
126 groups. The median Hill q1 of Hiroshima is 6.58 at level 1 and 27.67 on the
leaves. Print the level next to every number.

**12. The 13 branches are unequal.** Pooled over the four cities,
`services_and_business` holds 29.8% of all places, `shopping` 16.5% and
`food_and_drink` 16.4%; `geographic_entities` holds 0.5%. A cell is far more
likely to be dominated by one of the big three. Which of the three depends on
the city: food and drink is 31.4% of Hiroshima, services and business 33.7% of
London.

**13. `MIN_POI = 10` is a choice.** Belgrade's median Hill q2 is 5.73 with a
threshold of 5, 6.38 with 10 and 6.79 with 20. London barely moves (5.95 to
6.00). Cells under the threshold are dropped and never drawn as zeros.

## The geometry

**14. The resolution is a dial too.** Median Hill q2 falls from resolution 7
to 9 in every city (Hiroshima 5.79, 5.33, 4.59). The order of the cities
changes between resolutions for London and Amsterdam, which sit close together.

**15. The boxes were drawn by hand.** Shifting a box by 4 km in any direction
moves the median Hill q2 by at most 0.27. Belgrade stays first and Hiroshima
last in all five positions.

**16. A place is a point.** `dna.py` reads the corner of the `bbox` struct and
never opens the geometry. For these point features the corner lies within
0.000023 degrees of the point, about two metres (measured on the Hiroshima
extract; every geometry in it is a point).

**17. No significance tests.** Neighbouring cells resemble each other, so a
t-test over cells would overstate its confidence. The repository reports
medians and gaps and claims no p-values.

## Licences

Code: MIT. Slides, figures and texts: CC BY 4.0, see `docs/LICENSE.md`.
Overture places carry the licence of their source. In these four cities that
is CDLA-Permissive-2.0 (Meta, Microsoft and others), Apache-2.0 (Foursquare)
and CC0-1.0 (AllThePlaces). Attribution rules:
<https://docs.overturemaps.org/attribution/>.
