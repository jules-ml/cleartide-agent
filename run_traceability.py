"""Build the requirements matrix from a real pytest run."""

import csv
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CSV_PATH = ROOT / "docs" / "requirements_traceability.csv"
JUNIT_PATH = ROOT / "evals" / "pytest_junit.xml"
OUT_JSON = ROOT / "docs" / "traceability_results.json"
OUT_MD = ROOT / "docs" / "traceability_matrix.md"


def _tests_by_file(junit_path: Path) -> dict[str, list[dict]]:
    tree = ET.parse(junit_path)
    grouped: dict[str, list[dict]] = {}
    for case in tree.iter("testcase"):
        classname = case.get("classname") or ""
        file_name = (case.get("file") or "").replace("\\", "/")
        if not file_name and classname.startswith("tests."):
            module = classname.split(".", 1)[1].split(".", 1)[0]
            file_name = f"tests/{module}.py"
        name = case.get("name")
        failed = case.find("failure") is not None or case.find("error") is not None
        grouped.setdefault(file_name, []).append(
            {"name": name, "passed": not failed}
        )
    return grouped


def main():
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            f"--junitxml={JUNIT_PATH}",
        ],
        cwd=ROOT,
    )
    grouped = _tests_by_file(JUNIT_PATH)
    rows = []

    with CSV_PATH.open(encoding="utf-8") as handle:
        for record in csv.DictReader(handle):
            files = [
                part.strip()
                for part in (record.get("verification_artifact") or "").split(";")
                if part.strip().startswith("tests/")
            ]
            passed = []
            failed = []
            for file_name in files:
                for test in grouped.get(file_name, []):
                    label = f"{file_name}::{test['name']}"
                    if test["passed"]:
                        passed.append(label)
                    else:
                        failed.append(label)
            if not files:
                result = "NO AUTOMATED TEST"
            elif failed:
                result = "FAIL"
            elif passed:
                result = "PASS"
            else:
                result = "TESTS NOT FOUND"
            rows.append(
                {
                    "requirement_id": record["requirement_id"],
                    "requirement_summary": record["requirement_summary"],
                    "implementation_artifact": record["implementation_artifact"],
                    "status": record["status"],
                    "result": result,
                    "passed_tests": passed,
                    "failed_tests": failed,
                }
            )

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "pytest_exit_code": completed.returncode,
        "requirements": rows,
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = [
        "# Requirements traceability",
        "",
        "Generated from `docs/requirements_traceability.csv` joined to a pytest JUnit run.",
        "A requirement passes here only when every test in its mapped test files passed.",
        "",
        "FR-6.4 does not use a human rater. The automated stand-ins are:",
        "five required plain-language sections (what the customer said, what the agent found, what it recommends, why it stopped, what the reviewer decides);",
        "every rule id and controlled enum in that brief is paired with a fixed plain-English gloss;",
        "the brief contains no JSON blobs or stack traces;",
        "the Flesch-Kincaid grade of the agent-written sentences is at or below 8.",
        "Grade 8 is the usual plain-language ceiling for a public notice, so an office reviewer does not need college prose.",
        "Customer quotes and drafts are kept verbatim and are left out of the grade.",
        "",
        f"Pytest exit code: {completed.returncode}",
        "",
        "| Requirement | Matrix result | Passing tests | Failed tests |",
        "|---|---|---|---|",
    ]
    for row in rows:
        if not str(row["requirement_id"]).startswith("FR-"):
            continue
        lines.append(
            "| {id} | {result} | {passed} | {failed} |".format(
                id=row["requirement_id"],
                result=row["result"],
                passed="<br>".join(row["passed_tests"]) or "—",
                failed="<br>".join(row["failed_tests"]) or "—",
            )
        )
    lines.append("")
    lines.append("Policy and governance rows are in `docs/traceability_results.json`.")
    lines.append("")
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(OUT_MD)
    print(f"pytest exit {completed.returncode}")
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
