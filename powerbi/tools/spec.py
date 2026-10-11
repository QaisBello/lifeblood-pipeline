"""Power BI version of the Lifeblood Pipeline control room. Run from powerbi/:

    python tools/spec.py        # writes Lifeblood_Pipeline.pbip and its folders
    python tools/validate.py    # schema and reference checks
    python tools/expected.py    # what the visuals should show, checked against runs/latest.json

The run records are JSON: Power Query parses runs/history.json (every run) and runs/latest.json (stages and quality gates of
the latest run) with Json.Document. The published star schema is read from data/published/.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pbikit import C, M, build, card, color, lit, series_colors, slicer, text_box, visual  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAME = "Lifeblood_Pipeline"
TEAL, RED, GREY, INK = "#0F8A7A", "#D0304A", "#9AA3A0", "#13201B"

JSON = '''
    Source = Json.Document(Web.Contents(BaseUrl, [RelativePath = "{file}"])),'''
TABLES = {
    "Runs": dict(
        description="Every pipeline run (runs/history.json): when it finished, its status and row counts.",
        m='''
let''' + JSON.format(file="runs/history.json") + '''
    Records = Table.FromRecords(Source, {"run_id", "finished_at", "status", "trigger", "rows_in", "rows_out", "donors", "donation_rate"}, MissingField.UseNull),
    Typed = Table.TransformColumnTypes(Records, {{"run_id", type text}, {"finished_at", type datetimezone}, {"status", type text},
        {"trigger", type text}, {"rows_in", Int64.Type}, {"rows_out", Int64.Type}, {"donors", Int64.Type}, {"donation_rate", type number}}),
    Local = Table.TransformColumns(Typed, {{"finished_at", each DateTimeZone.RemoveZone(_), type datetime}}),
    Result = Table.AddIndexColumn(Local, "Run Number", 1, 1, Int64.Type)
in
    Result''',
        columns=[("run_id", "string", {"isKey": True}), ("finished_at", "dateTime", {"formatString": "dd mmm yyyy hh:nn"}), ("status", "string", {}),
                 ("trigger", "string", {}), ("rows_in", "int64", {}), ("rows_out", "int64", {}), ("donors", "int64", {}),
                 ("donation_rate", "double", {"formatString": "0.0%"}), ("Run Number", "int64", {})]),
    "Stages": dict(
        description="The latest run's stages in order (runs/latest.json): rows out and seconds taken.",
        m='''
let''' + JSON.format(file="runs/latest.json") + '''
    Stages = Table.FromRecords(Source[stages], {"stage", "rows_out", "seconds"}, MissingField.UseNull),
    Indexed = Table.AddIndexColumn(Stages, "Stage Order", 1, 1, Int64.Type),
    Result = Table.TransformColumnTypes(Indexed, {{"stage", type text}, {"rows_out", Int64.Type}, {"seconds", type number}})
in
    Result''',
        columns=[("stage", "string", {"sortByColumn": "Stage Order"}), ("rows_out", "int64", {}), ("seconds", "double", {"formatString": "0.000"}),
                 ("Stage Order", "int64", {"isHidden": True})]),
    "Checks": dict(
        description="Quality gates of the latest run (runs/latest.json). An error stops publishing; a warning is logged.",
        m='''
let''' + JSON.format(file="runs/latest.json") + '''
    Checks = Table.FromRecords(Source[checks], {"name", "level", "passed"}, MissingField.UseNull),
    Typed = Table.TransformColumnTypes(Checks, {{"name", type text}, {"level", type text}, {"passed", type logical}}),
    Result = Table.AddColumn(Typed, "Result", each if [passed] then "Passed" else if [level] = "error" then "FAILED" else "Warning", type text)
in
    Result''',
        columns=[("name", "string", {}), ("level", "string", {}), ("passed", "boolean", {}), ("Result", "string", {})]),
    "Change Log": dict(
        file="data/published/data_quality_log.csv", description="Every change the pipeline made, by stage, with rows affected.",
        columns=[("stage", "string", {}), ("check", "string", {}), ("rows_affected", "int64", {}), ("finding", "string", {}), ("action", "string", {})]),
    "Responses": dict(
        file="data/published/fact_responses.csv",
        description="The published fact table: one row per donor per drive, anonymised (keyed HMAC donor IDs).",
        columns=[("response_id", "string", {"isKey": True, "isHidden": True}), ("donor_id", "string", {"isHidden": True}),
                 ("drive_id", "string", {"isHidden": True}), ("drive_name", "string", {"isHidden": True}), ("drive_date", "dateTime", {"isHidden": True}),
                 ("submitted_at", "dateTime", {"isHidden": True}), ("age", "double", {"formatString": "0"}), ("age_band", "string", {}),
                 ("gender", "string", {}), ("institution_group", "string", {}), ("blood_group", "string", {}), ("first_time", "boolean", {}),
                 ("donated", "boolean", {}), ("deferral_reason", "string", {}), ("will_return", "boolean", {}), ("wants_reminder", "boolean", {}),
                 ("has_later_drive", "boolean", {}), ("came_back_later", "boolean", {})]),
    "Drives": dict(
        file="data/published/dim_drive.csv", description="The drives in the published data.",
        columns=[("drive_id", "string", {"isKey": True, "isHidden": True}), ("drive_name", "string", {"sortByColumn": "drive_date"}),
                 ("drive_date", "dateTime", {"formatString": "dd mmm yyyy"})]),
}
RELATIONSHIPS = [(("Responses", "drive_id"), ("Drives", "drive_id"), {})]

RU, CK, RS = "Runs", "Checks", "Responses"
LAST = "VAR _last = CALCULATE ( MAX ( Runs[Run Number] ), REMOVEFILTERS ( Runs ) )\n"
MEASURES = [
    ("Run Count", RU, "Runs", "#,0", "COUNTROWS ( Runs )", "Pipeline runs recorded."),
    ("Latest Status", RU, "Runs", "General", LAST + 'RETURN UPPER ( CALCULATE ( MAX ( Runs[status] ), REMOVEFILTERS ( Runs ), Runs[Run Number] = _last ) )',
     "Status of the latest run."),
    ("Latest Rows In", RU, "Runs", "#,0", LAST + "RETURN CALCULATE ( SUM ( Runs[rows_in] ), REMOVEFILTERS ( Runs ), Runs[Run Number] = _last )",
     "Rows read by the latest run."),
    ("Latest Rows Out", RU, "Runs", "#,0", LAST + "RETURN CALCULATE ( SUM ( Runs[rows_out] ), REMOVEFILTERS ( Runs ), Runs[Run Number] = _last )",
     "Rows published by the latest run."),
    ("Rows Removed", RU, "Runs", "#,0", "[Latest Rows In] - [Latest Rows Out]", "Duplicates and misfiled rows removed in cleaning."),
    ("Rows In", RU, "Runs", "#,0", "SUM ( Runs[rows_in] )", "Rows read."),
    ("Rows Out", RU, "Runs", "#,0", "SUM ( Runs[rows_out] )", "Rows published."),
    ("Gates Passed", CK, "Quality gates", "#,0", "CALCULATE ( COUNTROWS ( Checks ), Checks[passed] == TRUE () )", "Quality gates passed in the latest run."),
    ("Gates", CK, "Quality gates", "#,0", "COUNTROWS ( Checks )", "Quality gates run."),
    ("Gates Summary", CK, "Quality gates", "General", '[Gates Passed] & " of " & [Gates] & " passed"', "For the card."),
    ("Errors Failed", CK, "Quality gates", "#,0", 'CALCULATE ( COUNTROWS ( Checks ), Checks[passed] == FALSE (), Checks[level] = "error" ) + 0',
     "Failed error-level gates (any failure would have stopped publishing)."),
    ("Check-ins", RS, "Published data", "#,0", "COUNTROWS ( Responses )", "Published check-ins."),
    ("Donors", RS, "Published data", "#,0", "DISTINCTCOUNT ( Responses[donor_id] )", "Distinct anonymised donors."),
    ("Donation Rate", RS, "Published data", "0.0%", "DIVIDE ( CALCULATE ( [Check-ins], Responses[donated] == TRUE () ), [Check-ins] )",
     "Share of check-ins who donated."),
    ("Deferrals", RS, "Published data", "#,0", "CALCULATE ( [Check-ins], Responses[donated] == FALSE () )", "Check-ins turned away."),
    ("Changes Logged", "Change Log", "Change log", "#,0", "COUNTROWS ( 'Change Log' )", "Entries in the change log."),
]

p1, p2 = "control", "published"
rin, rout = M(RU, "Rows In", "Rows in"), M(RU, "Rows Out", "Rows out")
PAGES = [
    (p1, "Control room", [
        text_box(p1, "title", 24, 12, 1232, 52, "Lifeblood Pipeline control room: the latest run, its quality gates and every change it made", 18),
        card(p1, "status", 24, 76, 236, 96, M(RU, "Latest Status", "Latest run")),
        card(p1, "in", 272, 76, 236, 96, M(RU, "Latest Rows In", "Rows in")),
        card(p1, "out", 520, 76, 236, 96, M(RU, "Latest Rows Out", "Rows published")),
        card(p1, "gates", 768, 76, 236, 96, M(CK, "Gates Summary", "Quality gates"), size=18),
        card(p1, "err", 1016, 76, 240, 96, M(CK, "Errors Failed", "Error gates failed")),
        visual(p1, "stages", "clusteredColumnChart", 24, 184, 600, 250, {"Category": [C("Stages", "stage", "Stage")], "Y": [M("Stages", "Rows Out Stage", "Rows out")]},
               "Rows out of each stage, latest run", objects={"dataPoint": [{"properties": {"fill": color(TEAL)}}], "labels": [{"properties": {"show": lit(True)}}]},
               sort=(C("Stages", "stage"), "Ascending"), z=10),
        visual(p1, "checks", "tableEx", 640, 184, 616, 250,
               {"Values": [C(CK, "name", "Quality gate"), C(CK, "level", "Level"), C(CK, "Result")]}, "Quality gates, latest run", z=11),
        visual(p1, "history", "clusteredColumnChart", 24, 446, 400, 262, {"Category": [C(RU, "Run Number", "Run")], "Y": [rin, rout]},
               "Every run: rows in and out", objects={"dataPoint": series_colors([rin, rout], [GREY, TEAL])}, sort=(C(RU, "Run Number"), "Ascending"), z=12),
        visual(p1, "log", "tableEx", 440, 446, 816, 262,
               {"Values": [C("Change Log", "stage", "Stage"), C("Change Log", "check", "Check"), C("Change Log", "rows_affected", "Rows"),
                           C("Change Log", "finding", "Finding"), C("Change Log", "action", "Action")]}, "Change log", z=13),
    ]),
    (p2, "Published data", [
        text_box(p2, "title", 24, 12, 860, 52, "What the pipeline published (anonymised star schema)", 18),
        slicer(p2, "drive", 900, 8, 356, 64, C("Drives", "drive_name", "Drive"), None),
        card(p2, "ci", 24, 76, 300, 96, M(RS, "Check-ins", "Check-ins")),
        card(p2, "donors", 336, 76, 300, 96, M(RS, "Donors", "Donors")),
        card(p2, "rate", 648, 76, 300, 96, M(RS, "Donation Rate", "Donation rate")),
        card(p2, "def", 960, 76, 296, 96, M(RS, "Deferrals", "Deferrals")),
        visual(p2, "bydrive", "clusteredColumnChart", 24, 184, 600, 524, {"Category": [C("Drives", "drive_name", "Drive")], "Y": [M(RS, "Check-ins")]},
               "Check-ins by drive", objects={"dataPoint": [{"properties": {"fill": color(TEAL)}}], "labels": [{"properties": {"show": lit(True)}}]},
               sort=(C("Drives", "drive_name"), "Ascending"), z=10),
        visual(p2, "reasons", "clusteredBarChart", 640, 184, 616, 524, {"Category": [C(RS, "deferral_reason", "Reason")], "Y": [M(RS, "Deferrals")]},
               "Deferral reasons", objects={"dataPoint": [{"properties": {"fill": color(RED)}}], "labels": [{"properties": {"show": lit(True)}}]},
               sort=(M(RS, "Deferrals"), "Descending"), z=11),
    ]),
]
MEASURES.append(("Rows Out Stage", "Stages", "Runs", "#,0", "SUM ( Stages[rows_out] )", "Rows leaving each stage."))

SPEC = dict(name=NAME, root=ROOT, tables=TABLES, measures=MEASURES, relationships=RELATIONSHIPS, pages=PAGES,
            base_url="https://raw.githubusercontent.com/QaisBello/One-health-life-savers-blood-ledger-elt/main/",
            base_desc="The root of this repo on GitHub: run records in runs/, published tables in data/published/.")

if __name__ == "__main__":
    build(SPEC)
