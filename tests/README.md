# Tests

Run them from the repository root after the one-time setup in [DEMO.md](../DEMO.md):

```bash
source .venv/bin/activate
python -m pytest
```

`python setup_database.py` and `python seed_data.py` must already have been run once. Do not run `seed_data.py` again. New tests use their own account ids, or the isolated demo database, and clean up the rows they create.

`python run_traceability.py` runs this same suite and rewrites `docs/traceability_matrix.md` from the results.
