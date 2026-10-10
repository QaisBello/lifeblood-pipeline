"""The five pipeline stages. Each takes a DataFrame plus the run context and returns a DataFrame;
every stage records what it changed in ctx.log so the run manifest can show it."""
from __future__ import annotations
import fnmatch, hashlib, hmac, os, re
import pandas as pd


# ------------------------------------------------------------------ 1. ingest
def ingest(ctx) -> pd.DataFrame:
    """Read every export in the incoming folder, map its columns to the canonical schema, tag its drive."""
    frames = []
    for fn in sorted(os.listdir(ctx.incoming)):
        if not fn.lower().endswith((".csv", ".xlsx")):
            continue
        drive = next((d for d in ctx.cfg["drives"] if fnmatch.fnmatch(fn.lower(), d["file"])), None)
        if drive is None:
            ctx.note("ingest", "Unknown file", 1, f"{fn} matches no drive in config.yml", "Skipped")
            continue
        path = os.path.join(ctx.incoming, fn)
        raw = pd.read_csv(path, dtype=str) if fn.endswith(".csv") else pd.read_excel(path, dtype=str)
        mapping = {}
        for canon, keys in ctx.cfg["columns"].items():
            hit = next((c for c in raw.columns if any(k in c.lower() for k in keys) and c not in mapping), None)
            if hit is not None:
                mapping[hit] = canon
        df = raw.rename(columns=mapping)[list(mapping.values())]
        df["source_drive"] = drive["id"]; df["source_file"] = fn
        unmapped = [c for c in raw.columns if c not in mapping]
        ctx.note("ingest", "Columns mapped", len(df), f"{fn}: {len(mapping)} columns mapped" + (f", {len(unmapped)} ignored" if unmapped else ""), f"Tagged as {drive['id']}")
        frames.append(df)
    out = pd.concat(frames, ignore_index=True)
    out["timestamp"] = pd.to_datetime(out["timestamp"])
    return out


# ------------------------------------------------------------------ 2. anonymise
def _norm_phone(p):
    d = re.sub(r"\D", "", str(p or ""))
    return d[-10:] if len(d) >= 10 else None

def anonymise(df, ctx) -> pd.DataFrame:
    """Link people across drives by phone OR email, replace them with a keyed hash, drop all PII.
    The key (PIPELINE_SECRET) never leaves the machine or GitHub Secrets, so IDs are stable across runs
    but cannot be reversed by anyone who only has the published data."""
    secret = os.environ.get("PIPELINE_SECRET", "local-dev-only").encode()
    phone = df["phone"].map(_norm_phone)
    email = df["email"].fillna("").str.strip().str.lower().where(lambda s: s.str.contains("@"))
    parent = {}
    def find(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    for p, e in zip(phone, email):
        keys = [k for k in (p and "p:" + p, isinstance(e, str) and "e:" + e) if k]
        for k in keys[1:]:
            parent[find(k)] = find(keys[0])
    root = [find("p:" + p) if p else (find("e:" + e) if isinstance(e, str) else None) for p, e in zip(phone, email)]
    df = df.copy()
    df["donor_id"] = ["D-" + hmac.new(secret, r.encode(), hashlib.sha256).hexdigest()[:10].upper() if r else None for r in root]
    linked = int(pd.Series(root).nunique())
    df = df.drop(columns=[c for c in ctx.cfg["pii"] if c in df.columns])
    ctx.note("anonymise", "PII removed", len(df), f"{len(ctx.cfg['pii'])} PII columns dropped; {linked} unique people linked by phone or email", "Replaced with HMAC donor_id")
    return df


# ------------------------------------------------------------------ 3. clean
def clean(df, ctx) -> pd.DataFrame:
    df = df.copy(); R = ctx.cfg["rules"]
    drives = {d["id"]: d for d in ctx.cfg["drives"]}
    # responses submitted on another drive's form: re-assign by date
    dates = {pd.Timestamp(d["date"]).date(): d["id"] for d in ctx.cfg["drives"]}
    df["drive_id"] = [dates.get(t.date(), s) for t, s in zip(df.timestamp, df.source_drive)]
    moved = int((df.drive_id != df.source_drive).sum())
    ctx.note("clean", "Wrong form", moved, "Responses dated on another drive's day", "Re-assigned by date")
    # duplicates: same person, same drive
    df = df.sort_values("timestamp")
    dup = df.duplicated(["donor_id", "drive_id"], keep="last") & df.donor_id.notna()
    ctx.note("clean", "Duplicates", int(dup.sum()), "Same person submitted twice for one drive", "Kept the latest")
    df = df[~dup].copy()
    # age
    age = pd.to_numeric(df["age"].astype(str).str.extract(r"(\d+)")[0], errors="coerce")
    lo, hi = R["age_valid"]; bad = age.notna() & ((age < lo) | (age > hi))
    ctx.note("clean", "Implausible ages", int(bad.sum()), f"Outside {lo}–{hi}", "Set to blank")
    df["age"] = age.mask(bad)
    df["age_band"] = pd.cut(df.age, [0, 17, 19, 21, 24, 200], labels=["Under 18", "18-19", "20-21", "22-24", "25+"]).astype(str).replace("nan", "Unknown")
    # gender
    g0 = int(df["gender"].isna().sum()); df["gender"] = df["gender"].fillna("Not captured")
    ctx.note("clean", "Missing gender", g0, "Gender left blank", "Labelled 'Not captured'")
    # institution
    def inst(x):
        t = str(x or "").lower().strip()
        for grp, keys in R["institution_groups"].items():
            if any(k in t for k in keys):
                return grp
        return "Unknown"
    df["institution_group"] = df["institution"].map(inst)
    ctx.note("clean", "Institution spellings", int(df["institution"].nunique()), "Free-text institution names", f"Grouped into {df.institution_group.nunique()} groups")
    # blood group
    bg = df["blood_group"].fillna("").str.replace(" ", "").str.upper()
    df["blood_group"] = bg.where(bg.isin(["O+", "O-", "A+", "A-", "B+", "B-", "AB+", "AB-"]), "Unknown")
    # first-time: two different questions across forms
    t = df.get("times", pd.Series(index=df.index, dtype=str)).fillna("")
    ft = df.get("first_time", pd.Series(index=df.index, dtype=str)).fillna("")
    df["first_time"] = (ft.str.lower() == "yes") | t.str.lower().str.contains("never|first")
    # outcome + reason
    df["donated"] = df["donated"].str.strip().str.lower() == "yes"
    def reason(row):
        if row.donated: return "Donated"
        txt = str(row.reason or "").lower()
        for k, pat in R["deferral_reasons"].items():
            if re.search(pat, txt): return k
        return "Underage" if (row.age == row.age and row.age < 18) else "Not specified"
    df["deferral_reason"] = df.apply(reason, axis=1)
    ctx.note("clean", "Free-text reasons", int((~df.donated).sum()), f"{df.loc[~df.donated, 'reason'].nunique()} different wordings", f"Classified into {df.loc[~df.donated, 'deferral_reason'].nunique()} reasons")
    df["will_return"] = df["will_return"].str.strip().str.lower() == "yes"
    df["wants_reminder"] = df["reminder"].str.strip().str.lower() == "yes"
    df["drive_name"] = df.drive_id.map(lambda d: drives[d]["name"])
    df["drive_date"] = df.drive_id.map(lambda d: str(drives[d]["date"]))
    return df


# ------------------------------------------------------------------ 4. model
def model(df, ctx):
    order = {d["id"]: i for i, d in enumerate(ctx.cfg["drives"])}
    df = df.copy(); df["drive_seq"] = df.drive_id.map(order)
    g = df.groupby("donor_id").drive_seq
    df["came_back_later"] = df.drive_seq < df.donor_id.map(g.max())
    df["has_later_drive"] = df.drive_seq < max(order.values())
    df["submitted_at"] = df.timestamp.dt.floor("min")
    fact = df[["donor_id", "drive_id", "drive_name", "drive_date", "submitted_at", "age", "age_band", "gender", "institution_group",
               "blood_group", "first_time", "donated", "deferral_reason", "will_return", "wants_reminder", "has_later_drive", "came_back_later"]].sort_values("submitted_at").reset_index(drop=True)
    fact.insert(0, "response_id", [f"R-{i+1:04d}" for i in range(len(fact))])
    donors = df.groupby("donor_id").agg(drives_attended=("drive_id", "nunique"), donations=("donated", "sum")).reset_index()
    drives = pd.DataFrame(ctx.cfg["drives"]).drop(columns=["file"]).rename(columns={"id": "drive_id", "name": "drive_name", "date": "drive_date"})
    ctx.note("model", "Star schema", len(fact), f"fact_responses {len(fact)} rows · dim_donor {len(donors)} · dim_drive {len(drives)}", "Written to data/published/")
    return {"fact_responses": fact, "dim_donor": donors, "dim_drive": drives}


# ------------------------------------------------------------------ 5. validate
def validate(tables, ctx):
    fact = tables["fact_responses"]; lo, hi = ctx.cfg["rules"]["age_valid"]
    rate = fact.donated.mean()
    tests = {
        "No PII columns in output": not any(c in fact.columns for c in ctx.cfg["pii"] + ["institution", "reason"]),
        "One row per donor per drive": not fact.duplicated(["donor_id", "drive_id"]).any(),
        "Every row maps to a known drive": fact.drive_id.isin([d["id"] for d in ctx.cfg["drives"]]).all(),
        "Ages within valid range or blank": fact.age.dropna().between(lo, hi).all(),
        "Deferral reason set for every non-donation": (fact.loc[~fact.donated, "deferral_reason"] != "Not specified").mean() > 0.9,
        "Donation rate between 30% and 95%": 0.30 <= rate <= 0.95,
    }
    results = [dict(name=c["name"], level=c["level"], passed=bool(tests[c["name"]])) for c in ctx.cfg["checks"]]
    return results
