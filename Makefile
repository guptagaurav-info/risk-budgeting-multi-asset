PY ?= python
export PYTHONPATH := src

.PHONY: all ingest run test clean
all: ingest run
ingest:
	$(PY) -m riskbud.ingest
run:
	$(PY) -m riskbud.pipeline
test:
	$(PY) -m pytest -q tests
clean:
	rm -rf reports/figures/*.png reports/metrics.json
