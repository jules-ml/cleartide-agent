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

| Time | View | What to say |
|---|---|---|
| 0:00–0:30 | 1 Overview | Roll-off invoices age while the trucks keep moving. Cleartide is a governed agent for that follow-up, not an unrestricted chatbot. |
| 0:30–1:00 | 1 Overview | Point at the path: intent, tools, risk, recommendation, policy, audit. The agent recommends. The policy file authorizes. |
| 1:00–2:00 | 2 Autonomous | Run scenario 1. “I’ll pay the invoice on Friday.” Intent, promise history, low risk, email draft, verdict APPROVE, audit timeline. |
| 2:00–2:40 | 3 Human review | Run scenario 2. The agent proposes plan terms. Medium risk has `autonomous_allowed: false` in `config/policy.yaml`. Verdict ESCALATE. Click RESOLVED, show the audit note, run the account again, and show the disposition in the rationale. The decision row itself is not edited. |
| 2:40–3:20 | 4 Policy block | Run scenario 3. The injected draft says “legal action.” Show PR-3, the field `message_body`, and the term list copied from `config/policy.yaml`. The message is not sent. |
| 3:20–4:00 | 5 Audit, then 6 Evaluation | Open a decision and attempt a rewrite. Then show the charts. Policy-violation rate is the number to point at. These are harness metrics for the deterministic agent, not revenue. |
| 4:00–4:30 | Business | Use `docs/business_value.md`. Cans on site, aging invoices, first-party voice. No invented dollar results. |
| 4:30–5:00 | 7 Traceability, then limitations | A requirement names code and a test that passed. Then one limitation: the brain is a deterministic stand-in, and the policy layer is what stays when a model is added. |

Scenario 4 (ledger does not confirm payment) and scenario 5 (SMS inside quiet hours, revised once to email) are in the same runner if there is a question. They print in the terminal transcript.

## Reading that goes with the walkthrough

- `docs/architecture.md`
- `docs/agentic_system.md` — agent versus a fixed script, and where policy comes from
- `docs/business_value.md`
- `docs/limitations.md`
- `docs/AI_DISCLOSURE.md` — complete the author section before submission
- `docs/traceability_matrix.md`
