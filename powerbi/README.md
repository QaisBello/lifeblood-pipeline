# Lifeblood Pipeline: Power BI

The control room of the pipeline as a Power BI report: every run, the stages and quality gates of the latest run, the change log, and the published anonymised data (synthetic, as in the rest of this repo).

This folder is a Power BI project (`Lifeblood_Pipeline.pbip`): a TMDL semantic model and a PBIR report. It is generated from one Python spec, checked against Microsoft's JSON schemas, and its numbers are recomputed independently in pandas.

## Open it

1. Open **`Lifeblood_Pipeline.pbip`** in Power BI Desktop. In versions before mid-2025, first turn on the preview features for Power BI Project (.pbip), the TMDL model format and the PBIR report format.
2. Click **Refresh**. The model reads this repo's cleaned CSVs from GitHub through the **BaseUrl** parameter. If asked, choose **Anonymous** access for `raw.githubusercontent.com`.
3. Check the visuals against [`docs/expected_values.md`](docs/expected_values.md).

## Pages

- **Control room:** latest run status, rows in and out, quality gates passed, error gates failed; rows out of each stage; every run; the change log.
- **Published data:** drive slicer; check-ins, donors, donation rate and deferrals; check-ins by drive; deferral reasons.

## Model

- **Tables:** Runs, Stages, Checks, Change Log, Responses, Drives.
- **Relationships:** Responses[drive_id] to Drives[drive_id].
- **17 DAX measures** in display folders: Runs (Run Count, Latest Status, Latest Rows In, Latest Rows Out, Rows Removed, Rows In, Rows Out, Rows Out Stage); Quality gates (Gates Passed, Gates, Gates Summary, Errors Failed); Published data (Check-ins, Donors, Donation Rate, Deferrals); Change log (Changes Logged). The full DAX is in [`docs/measures.md`](docs/measures.md).

## Notes

- The run records are JSON. Power Query parses `runs/history.json` and `runs/latest.json` with `Json.Document`, so the report updates whenever GitHub Actions publishes a new run.
- The data in this repo is synthetic (see the main README); the real drives are in the Lifeblood Ledger.
- `tools/expected.py` checks that the published tables agree with the latest run record (rows, donors, donation rate): they do.

## Rebuild and check

```bash
pip install jsonschema referencing pandas numpy
python tools/spec.py        # the spec: writes the .pbip and its folders
python tools/validate.py    # Microsoft schemas, field and DAX references, name clashes
python tools/expected.py    # what the report should show, checked against the project's own results
```

`tools/pbikit.py` is a small shared library for writing Power BI projects as code. It is used across the portfolio and encodes lessons from real Power BI Desktop runs: names are case-insensitive; a format string must not start with a quote; empty CSV cells must become null before a type change; in DAX, `BLANK() = FALSE()` is true.
