"""
Run the Lifeblood pipeline end to end:  ingest -> anonymise -> clean -> model -> validate -> publish.

    python -m pipeline.run                       # uses samples/incoming (synthetic data)
    python -m pipeline.run --incoming path/to/exports --out data/published

Writes the modelled tables, a data-quality log and a run manifest (runs/<run_id>.json, runs/history.json).
Exits non-zero if any `error`-level check fails, so CI blocks a bad publish.
"""
import argparse, json, os, sys, time, uuid
from datetime import datetime, timezone
import pandas as pd, yaml
from pipeline import stages

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Ctx:
    def __init__(self, incoming, out):
        self.cfg = yaml.safe_load(open(os.path.join(ROOT, "pipeline", "config.yml")))
        self.incoming, self.out, self.log, self.stages = incoming, out, [], []
    def note(self, stage, check, rows, finding, action):
        self.log.append(dict(stage=stage, check=check, rows_affected=int(rows), finding=finding, action=action))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--incoming", default=os.path.join(ROOT, "samples", "incoming"))
    ap.add_argument("--out", default=os.path.join(ROOT, "data", "published"))
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    ctx = Ctx(a.incoming, a.out)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]

    def step(name, fn, *args):
        t = time.perf_counter(); res = fn(*args, ctx)
        rows = len(res) if isinstance(res, pd.DataFrame) else len(res["fact_responses"]) if isinstance(res, dict) else None
        ctx.stages.append(dict(stage=name, rows_out=rows, seconds=round(time.perf_counter() - t, 3)))
        print(f"  {name:<10} {rows if rows is not None else '':>6} rows  {ctx.stages[-1]['seconds']}s")
        return res

    print(f"run {run_id}")
    raw = step("ingest", lambda c: stages.ingest(c))
    anon = step("anonymise", stages.anonymise, raw)
    clean = step("clean", stages.clean, anon)
    tables = step("model", stages.model, clean)
    t = time.perf_counter(); checks = stages.validate(tables, ctx)
    ctx.stages.append(dict(stage="validate", rows_out=len(tables["fact_responses"]), seconds=round(time.perf_counter() - t, 3)))
    failed = [c for c in checks if c["level"] == "error" and not c["passed"]]
    for c in checks: print(f"  {'PASS' if c['passed'] else 'FAIL' if c['level']=='error' else 'WARN'}  {c['name']}")

    status = "failed" if failed else "success"
    if not failed:
        for name, df in tables.items():
            df.to_csv(os.path.join(a.out, f"{name}.csv"), index=False)
        pd.DataFrame(ctx.log).to_csv(os.path.join(a.out, "data_quality_log.csv"), index=False)
        ctx.stages.append(dict(stage="publish", rows_out=len(tables["fact_responses"]), seconds=0.0))
    fact = tables["fact_responses"]
    manifest = dict(run_id=run_id, finished_at=datetime.now(timezone.utc).isoformat(timespec="seconds"), status=status,
                    trigger=os.environ.get("GITHUB_EVENT_NAME", "local"), commit=os.environ.get("GITHUB_SHA", "")[:7],
                    source_files=sorted(set(raw.source_file)), rows_in=int(len(raw)), rows_out=int(len(fact)),
                    donors=int(fact.donor_id.nunique()), donation_rate=round(float(fact.donated.mean()), 4),
                    stages=ctx.stages, checks=checks, log=ctx.log)
    rdir = os.path.join(ROOT, "runs"); os.makedirs(rdir, exist_ok=True)
    json.dump(manifest, open(os.path.join(rdir, "latest.json"), "w"), indent=2)
    hist_p = os.path.join(rdir, "history.json")
    hist = json.load(open(hist_p)) if os.path.exists(hist_p) else []
    hist.append({k: manifest[k] for k in ("run_id", "finished_at", "status", "trigger", "commit", "rows_in", "rows_out", "donors", "donation_rate")})
    json.dump(hist[-50:], open(hist_p, "w"), indent=2)
    print(f"{status}: {len(raw)} rows in -> {len(fact)} rows out")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
