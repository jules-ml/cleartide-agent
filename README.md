# Cleartide Autonomous Collections Agent

Governed agent for accounts-receivable follow-up. The agent classifies a customer reply, retrieves account evidence, and recommends a next step. A deterministic policy layer decides whether that step is allowed. Routine cases can proceed. Risky or unauthorized cases go to a person, with an audit record either way.

This repository is the academic build. It uses a deterministic stand-in for the reasoning layer, so the demo does not need a model or an API key.

## Class demo

Setup and the five-minute screen-share script are in [DEMO.md](DEMO.md).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python setup_database.py
python seed_data.py
python -m pytest
python run_synthetic_evaluation.py
python run_traceability.py
python run_demo.py --serve
```

`python` in those commands is the virtualenv interpreter. Activate the environment first. On this machine the system command before activation is `python3`.

`seed_data.py` loads the historical fixture into `data/cleartide.db`. Run it once. A second run inserts duplicate payments, promises, and delivery rows. The class demo rebuilds a separate file, `data/demo_cleartide.db`.

The local dashboard is at <http://127.0.0.1:8765>. Keys 1 through 7 switch views. If the server will not start, open [docs/backup/demo_report.html](docs/backup/demo_report.html).

## Live demo (Streamlit)

Placeholder until the Cloud app is deployed: <https://cleartide-aca.streamlit.app>

Deploy from [jules-ml/cleartide-agent](https://github.com/jules-ml/cleartide-agent). Main file: `streamlit_app.py`. Choose Python 3.12. The app builds its own demo database on startup. It does not use secrets or an API key. `runtime.txt` pins 3.12 for hosts that still read that file; the Streamlit deploy dialog is the setting that matters.

The published URL above is a placeholder. Confirm it after the app is created. Until this branch is merged, point the deploy at branch `cursor/capstone-demo-61e7`. After merge, use `main`.

## Where to read next

- [docs/architecture.md](docs/architecture.md) — decision path
- [docs/agentic_system.md](docs/agentic_system.md) — what is agentic, and where policy comes from
- [docs/business_value.md](docs/business_value.md) — roll-off collections, qualitative only
- [docs/limitations.md](docs/limitations.md)
- [docs/AI_DISCLOSURE.md](docs/AI_DISCLOSURE.md)
- [docs/traceability_matrix.md](docs/traceability_matrix.md)
