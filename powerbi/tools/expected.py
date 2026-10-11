"""What the Power BI report should show, recomputed from the run records and published tables.
Run from powerbi/:  python tools/expected.py   (writes docs/expected_values.md; exit code 1 on any disagreement)"""
import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pbikit  # noqa: E402
import spec  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(ROOT)
L = json.load(open(os.path.join(REPO, "runs", "latest.json")))
H = json.load(open(os.path.join(REPO, "runs", "history.json")))
f = pd.read_csv(os.path.join(REPO, "data", "published", "fact_responses.csv"))
problems = pbikit.check_sorts(spec.SPEC, REPO)
if H[-1]["run_id"] != L["run_id"]:
    problems.append("history.json's last run is not latest.json")
if len(f) != L["rows_out"]:
    problems.append(f"published rows {len(f)} vs latest run rows_out {L['rows_out']}")
if f.donor_id.nunique() != L["donors"]:
    problems.append(f"donors {f.donor_id.nunique()} vs run {L['donors']}")
if round(f.donated.mean(), 4) != round(L["donation_rate"], 4):
    problems.append(f"donation rate {f.donated.mean():.4f} vs run {L['donation_rate']}")
passed = sum(c["passed"] for c in L["checks"])
lines = ["# Expected values", "", "From `tools/expected.py`: the published tables agree with the latest run record: "
         f"**{'yes' if not problems else 'NO: ' + '; '.join(problems)}**.", "",
         "## Control room", "", "| Card | Expected |", "|---|---:|",
         f"| Latest run | {L['status'].upper()} |", f"| Rows in | {L['rows_in']} |", f"| Rows published | {L['rows_out']} |",
         f"| Quality gates | {passed} of {len(L['checks'])} passed |",
         f"| Error gates failed | {sum(1 for c in L['checks'] if not c['passed'] and c['level'] == 'error')} |", "",
         "Runs: " + ", ".join(f"{r['rows_in']} in / {r['rows_out']} out" for r in H), "",
         "## Published data (all drives)", "", "| Card | Expected |", "|---|---:|",
         f"| Check-ins | {len(f)} |", f"| Donors | {f.donor_id.nunique()} |", f"| Donation rate | {f.donated.mean():.1%} |",
         f"| Deferrals | {(~f.donated).sum()} |"]
os.makedirs(os.path.join(ROOT, "docs"), exist_ok=True)
open(os.path.join(ROOT, "docs", "expected_values.md"), "w").write("\n".join(lines) + "\n")
print("\n".join(lines))
sys.exit(1 if problems else 0)
