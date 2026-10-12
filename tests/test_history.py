"""History record: append/replace by day, ordering, git backfill, page render."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src import config, history, report


@pytest.fixture(autouse=True)
def tmp_docs(tmp_path, monkeypatch):
    # Never touch the real docs/: the record and the page both live there.
    monkeypatch.setattr(config, "DOCS_DIR", str(tmp_path))
    monkeypatch.setattr(config, "HISTORY_PATH", str(tmp_path / "history.jsonl"))
    return tmp_path


def _result(missing, extra, **extra_totals):
    totals = {"tcl_streets": 13327, "osm_streets": 10820, "missing": missing,
              "missing_ln": 2255, "missing_ramp": 530, "missing_major": 52,
              "missing_private": 207, "extra": extra, "matched": 10246, **extra_totals}
    return {"computed_at": "2026-07-17T01:07:12+00:00",
            "tcl_filename": "centreline-2026-07-16.geojson",
            "osm_extract_downloaded": "2026-07-16T15:00:00+00:00",
            "totals": totals}


# Mirrors the markup templates/streets.html renders (header meta + tab buttons),
# cut down to the parts backfill reads.
PAGE = """
      <p class="header-meta">
        Computed 2026-08-28T15:07:12.000000+00:00 ·
        TCL <code>centreline-2026-07-16.geojson</code> ·
        OSM extract 2026-07-16T15:00:00.000000+00:00 ·
        TCL streets <strong>13327</strong> ·
        OSM streets <strong>10820</strong>
      </p>
      <nav class="tabs">
        <button class="active lead" data-tab="missing">Local streets (37)</button>
        <button class="lead" data-tab="extra">Extra in OSM (574)</button>
        <button class="lead" data-tab="missing-private">Private (207)</button>
        <button data-tab="missing-major">Major arterials (52)</button>
        <button data-tab="missing-ln">Laneways ({ln})</button>
        <button data-tab="matched">Matched (10246)</button>
      </nav>
"""


def test_record_appends_and_replaces_same_day():
    history.record(_result(40, 600), day="2026-07-15")
    history.record(_result(37, 574), day="2026-07-16")
    history.record(_result(36, 570), day="2026-07-16")
    rows = history.load()
    assert [r["date"] for r in rows] == ["2026-07-15", "2026-07-16"]
    assert rows[1]["missing"] == 36 and rows[1]["extra"] == 570
    assert rows[1]["source"] == "live"
    assert rows[1]["osm_date"] == "2026-07-16"


def test_a_rerun_on_the_same_extract_replaces_its_row_not_today():
    # A manual compare on a months-old extract is not a new observation.
    history.record(_result(37, 574))
    history.record(_result(36, 570))
    rows = history.load()
    assert [r["date"] for r in rows] == ["2026-07-16"]
    assert rows[0]["missing"] == 36


def test_load_is_oldest_first_and_empty_when_absent(tmp_docs):
    assert history.load() == []
    lines = [{"date": "2026-07-16", "missing": 1}, {"date": "2026-05-01", "missing": 2}]
    (tmp_docs / "history.jsonl").write_text(
        "\n".join(json.dumps(r) for r in lines) + "\n\n", encoding="utf-8")
    assert [r["date"] for r in history.load()] == ["2026-05-01", "2026-07-16"]


def test_parse_page_reads_tabs_and_leaves_absent_fields_out():
    row = history.parse_page(PAGE.format(ln=2255), "2026-08-28")
    # Dated by the OSM extract, not the render stamp or the commit.
    assert row["date"] == "2026-07-16"
    assert row["source"] == "git"
    assert row["missing"] == 37 and row["extra"] == 574 and row["missing_ln"] == 2255
    assert row["tcl_streets"] == 13327 and row["osm_streets"] == 10820
    assert "missing_ramp" not in row  # no Ramps tab on this page


def test_parse_page_without_tabs_is_skipped():
    assert history.parse_page("<h2>Reports</h2>", "2026-05-01") is None


def test_parse_page_falls_back_to_commit_date():
    page = PAGE.format(ln=1).replace("OSM extract 2026-07-16T15:00:00.000000+00:00", "OSM extract -")
    assert history.parse_page(page, "2026-06-13")["date"] == "2026-06-13"


def test_backfill_last_page_per_date_wins_and_skips_recorded():
    history.record(_result(30, 500), day="2026-09-01")
    old = PAGE.replace("2026-07-16T15", "2026-06-03T15")
    pages = [
        ("aaa1111", "2026-06-03", old.format(ln=9999)),
        ("bbb2222", "2026-06-04", old.format(ln=2255)),  # re-render of same data
        ("ccc3333", "2026-07-16", PAGE.format(ln=2255)),
        ("ddd4444", "2026-09-01", PAGE.format(ln=1).replace("2026-07-16T15", "2026-09-01T15")),
    ]
    assert history.backfill(pages) == 2
    rows = history.load()
    assert [(r["date"], r["source"]) for r in rows] == [
        ("2026-06-03", "git"), ("2026-07-16", "git"), ("2026-09-01", "live")]
    assert rows[0]["commit"] == "bbb2222" and rows[0]["missing_ln"] == 2255
    assert history.backfill(pages) == 0  # idempotent


def test_render_history_with_no_rows(tmp_docs):
    report.render_history()
    html = (tmp_docs / "history.html").read_text(encoding="utf-8")
    assert '<script type="application/json" id="history-data">[]</script>' in html
    assert (tmp_docs / "history.js").is_file()


def test_render_history_with_several_rows(tmp_docs):
    history.backfill([("ccc3333", "2026-07-16", PAGE.format(ln=2255))])
    history.record(_result(30, 500), day="2026-09-01")
    report.render_history()
    html = (tmp_docs / "history.html").read_text(encoding="utf-8")
    data = html.split('id="history-data">')[1].split("</script>")[0]
    assert [r["date"] for r in json.loads(data)] == ["2026-07-16", "2026-09-01"]
    assert "2 comparisons" in html and "from 2026-07-16 to 2026-09-01" in html
    assert "reconstructed <code>ccc3333</code>" in html
    assert "<td class=\"num\">–</td>" in html  # the page had no Ramps tab
    assert "<td class=\"num\">10,246</td>" in html


def test_a_row_is_dated_by_the_extracts_data_not_its_upload():
    # ontario-2026-10-10 holds data replicated 10-10 but was published 10-11 GMT.
    from src.osm_refresh import _extract_time
    latest = {"source_last_modified": "Sun, 11 Oct 2026 21:43:54 GMT",
              "replication_timestamp": "2026-10-10T20:21:21+00:00",
              "data_date": "2026-10-10"}
    assert history._local_date(_extract_time(latest)) == "2026-10-10"
    del latest["replication_timestamp"]
    assert history._local_date(_extract_time(latest)) == "2026-10-10"
