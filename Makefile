# Everything that ends up in README.md, docs/RESULTS.md and the slides is rebuilt here.
RELEASE  ?= 2026-09-23.1
PREVIOUS ?= 2026-08-19.0
PYTHON   ?= python

.PHONY: all cities results cost slides card test live lint cite serve

all: cities results cost slides lint test

cities:   ## the four test cities, straight from S3 (about 15 s each)
	$(PYTHON) dna.py 132.35 34.2999 132.55 34.4801 docs/data/hiroshima $(RELEASE)
	$(PYTHON) dna.py 20.35 44.7002 20.55 44.9098 docs/data/belgrade $(RELEASE)
	$(PYTHON) dna.py 4.8 52.2483 5.0 52.4917 docs/data/amsterdam $(RELEASE)
	$(PYTHON) dna.py -0.22 51.3906 -0.02 51.6294 docs/data/london $(RELEASE)

results:  ## robustness checks -> docs/RESULTS.md, docs/data/results.json
	$(PYTHON) checks.py $(RELEASE) $(PREVIOUS)

cost:     ## megabytes and seconds per city -> docs/data/cost.json
	$(PYTHON) cost.py $(RELEASE)

slides:   ## docs/assets/*.svg and docs/index.html from docs/data
	$(PYTHON) docs/build.py

card:     ## docs/assets/card.png for link previews (needs Chrome, not part of `all`)
	$(PYTHON) docs/card.py

test:     ## offline, a few seconds
	$(PYTHON) -m pytest -q

live:     ## scans the newest Overture release on S3
	DNA_LIVE=1 $(PYTHON) -m pytest -q tests/test_live.py

lint:
	ruff check .

cite:
	cffconvert --validate

serve:    ## slides and demo at http://localhost:8000
	$(PYTHON) -m http.server 8000 --directory docs
