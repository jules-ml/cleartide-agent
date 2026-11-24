"""Run the labeled synthetic set and write the metrics file."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEMO_DB = ROOT / "data" / "demo_cleartide.db"
os.environ["CLEARTIDE_DB_PATH"] = str(DEMO_DB)

from demo.seed import build_demo_database
from demo.synthetic_cases import build_synthetic_cases
from src.agent import DEVELOPMENT_REASONING_MODE
from src.synthetic_eval import evaluate_synthetic_cases


RESULTS_PATH = ROOT / "evals" / "synthetic_results.json"
CASES_PATH = ROOT / "evals" / "synthetic_scenarios.json"


def main():
    cases = build_synthetic_cases()
    CASES_PATH.write_text(json.dumps(cases, indent=2), encoding="utf-8")
    build_demo_database(DEMO_DB)
    results, summary = evaluate_synthetic_cases(cases, cleanup=True)
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "reasoning_mode": DEVELOPMENT_REASONING_MODE,
        "case_count": len(cases),
        "summary": summary,
        "results": results,
    }
    RESULTS_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Cases: {summary['total_cases']}")
    for key in (
        "decision_accuracy",
        "intent_accuracy",
        "action_accuracy",
        "policy_violation_rate",
        "policy_compliance_rate",
        "escalation_precision",
        "escalation_recall",
        "escalation_accuracy",
        "failure_handling_rate",
        "channel_accuracy",
    ):
        value = summary[key]
        shown = "n/a" if value is None else f"{value * 100:.1f}%"
        print(f"{key}: {shown}")
    failures = [item for item in results if not item["decision_correct"]]
    print(f"Decision mismatches: {len(failures)}")
    for item in failures[:12]:
        print(
            f"  {item['case_id']} {item['archetype']}: "
            f"intent {item['actual_intent']} "
            f"action {item['actual_final_action']} "
            f"status {item['actual_final_status']}"
        )
    print(RESULTS_PATH)


if __name__ == "__main__":
    main()
