import json, os, shutil
import pandas as pd
import pytest
from pipeline import run, stages

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLES = os.path.join(ROOT, "samples", "incoming")


@pytest.fixture()
def out(tmp_path, monkeypatch):
    monkeypatch.setenv("PIPELINE_SECRET", "test-secret")
    monkeypatch.setattr(run, "ROOT", str(tmp_path))          # keep run manifests out of the repo
    os.makedirs(tmp_path / "pipeline"); shutil.copy(os.path.join(ROOT, "pipeline", "config.yml"), tmp_path / "pipeline")
    return tmp_path


def test_end_to_end_publishes_without_pii(out):
    assert run.main(["--incoming", SAMPLES, "--out", str(out / "pub")]) == 0
    fact = pd.read_csv(out / "pub" / "fact_responses.csv")
    raw = pd.concat([pd.read_csv(os.path.join(SAMPLES, f), dtype=str) for f in os.listdir(SAMPLES)])
    text = fact.to_csv()
    for col in ["Email address", "Email address ", "First Name"]:
        for v in raw.get(col, pd.Series(dtype=str)).dropna().head(50):
            assert v.strip() not in text, f"PII value leaked: {v}"
    assert not fact.duplicated(["donor_id", "drive_id"]).any()


def test_misfiled_responses_are_reassigned(out):
    run.main(["--incoming", SAMPLES, "--out", str(out / "pub")])
    m = json.load(open(out / "runs" / "latest.json"))
    moved = next(l for l in m["log"] if l["check"] == "Wrong form")
    assert moved["rows_affected"] == 3


def test_ids_are_stable_and_key_dependent(monkeypatch):
    ctx = run.Ctx(SAMPLES, "/tmp")
    raw = stages.ingest(ctx)
    monkeypatch.setenv("PIPELINE_SECRET", "a"); a1 = stages.anonymise(raw, ctx).donor_id
    monkeypatch.setenv("PIPELINE_SECRET", "a"); a2 = stages.anonymise(raw, ctx).donor_id
    monkeypatch.setenv("PIPELINE_SECRET", "b"); b = stages.anonymise(raw, ctx).donor_id
    assert (a1 == a2).all() and (a1 != b).all()


def test_failed_check_blocks_publish(out, monkeypatch):
    real = stages.validate
    monkeypatch.setattr(stages, "validate", lambda t, c: [dict(name="forced", level="error", passed=False)] + real(t, c))
    assert run.main(["--incoming", SAMPLES, "--out", str(out / "pub2")]) == 1
    assert not os.path.exists(out / "pub2" / "fact_responses.csv")
