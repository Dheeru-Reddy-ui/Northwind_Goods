# Convenience targets. On Windows without `make`, run the commands directly
# (see README) using the venv python: .venv/Scripts/python.exe

VENV=.venv
PY=$(VENV)/bin/python
PIP=$(VENV)/bin/pip

install:
	python -m venv $(VENV)
	$(PIP) install -r requirements.txt

seed:
	$(PY) -m app.store.seed

ingest:
	$(PY) -m app.knowledge.ingest

run:
	$(VENV)/bin/uvicorn app.main:app --reload --port 8000

test:
	$(PY) -m pytest

eval:
	$(PY) -m eval.run

.PHONY: install seed ingest run test eval
