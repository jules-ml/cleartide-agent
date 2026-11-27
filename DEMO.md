# Class demo

Five-minute screen share of the Cleartide Autonomous Collections Agent. The dashboard is local. It does not call a model and it does not need a network connection after the Python packages are installed.

## Setup, once

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python setup_database.py
python seed_data.py
```

`python` after activation is the virtualenv interpreter. Before activation this environment only has `python3`.

`seed_data.py` loads the historical development fixture into `data/cleartide.db`. Do not run it again. Repeated inserts add duplicate payments, promises, and delivery rows. Tests and the class demo do not need a second seed.

The class demo uses a different file, `data/demo_cleartide.db`, which the commands below rebuild.

## Commands

```bash
source .venv/bin/activate
python -m pytest
python run_synthetic_evaluation.py
python run_traceability.py
python run_demo.py --serve
```

`pytest` is the regression suite.

`run_synthetic_evaluation.py` scores the labeled set and writes `evals/synthetic_results.json`. The dashboard charts read that file. Re-run it whenever you want fresh numbers. Do not edit the JSON.

`run_traceability.py` runs pytest and writes `docs/traceability_matrix.md` from the JUnit results.

`run_demo.py --serve` rebuilds the demo database, checks the five scenarios, refreshes the offline backup, then serves the dashboard at <http://127.0.0.1:8765>. Keys 1 through 7 switch views.

`python run_demo.py` does the same without staying up. Use it to refresh `docs/backup/demo_report.html` and `docs/backup/transcript.md`.

If the live server fails, open `docs/backup/demo_report.html` in a browser. It already contains the scenario results, the evaluation summary, and the traceability rows from the last generation. Disposition clicks are disabled there. The transcript at `docs/backup/transcript.md` states what the live click writes. Screenshots of the seven views are in `docs/backup/screenshots/`.

## Live demo (Streamlit)

Placeholder until the Cloud app is deployed: <https://cleartide-aca.streamlit.app>

| Setting | Value |
|---|---|
| Repository | `jules-ml/cleartide-agent` |
| Main file | `streamlit_app.py` |
| Python | 3.12 |

Deploy this branch, `cursor/capstone-demo-61e7`, until it is merged. After merge, deploy `main`. The app creates `data/streamlit_demo.db` on startup, so `setup_database.py` and `seed_data.py` are not required there. No secrets and no API key. Reviewer notes stay until **Reset demo** rebuilds that database. `runtime.txt` records 3.12; choose the same version in the Streamlit deploy dialog.

Run it locally with:

```bash
streamlit run streamlit_app.py --server.headless true
```

## Five-minute walkthrough

Open the Streamlit app. The first screen is the live book, not a slide.

| Time | What to do |
|---|---|
| 0:00–0:40 | Point at the five open accounts, the balances, and the risk gauge. The header counts are from the database and start at zero. |
| 0:40–1:20 | Click **Promise to pay → approve** on Northline Roll-Off. Watch Intent, Tools, Risk, Recommend, Policy, and Audit light up. The badge is AUTO-APPROVED. The card turns teal and a promise is noted. |
| 1:20–2:20 | Click **Payment plan → escalate** on Coastal Container Service. The badge is ESCALATED under PR-5.2. Open **Reviewer Inbox**, read the brief, and record APPROVE or RESOLVED with a note. The decision row is not edited. |
| 2:20–3:10 | Click **Threat language → block**. The draft says “legal action.” The badge is BLOCKED. PR-3 fails. Nothing is sent. |
| 3:10–3:50 | If there is time, click **Already paid → ledger** and **Quiet hours → revise**. The ledger tool shows the payment was not found. Quiet hours revises SMS to email and then approves. |
| 3:50–4:20 | Open **Audit Trail**. Newest decision first. Attempt a rewrite and show the refusal. |
| 4:20–5:00 | Open **Policy**, then **Evaluation**. The policy file is the authority. The charts are measured against the agent’s own labels, not revenue. |

The same five cases are also on **Guided walkthrough** if a button is easier than the console. Free text still works: an unclear sentence escalates instead of crashing.

## Reading that goes with the walkthrough

- `docs/architecture.md`
- `docs/agentic_system.md` — agent versus a fixed script, and where policy comes from
- `docs/business_value.md`
- `docs/limitations.md`
- `docs/AI_DISCLOSURE.md` — complete the author section before submission
- `docs/traceability_matrix.md`
