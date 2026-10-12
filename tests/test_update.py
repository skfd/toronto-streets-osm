"""update must fail loudly: a nonzero exit is what makes Task Scheduler retry."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import run
from src import osm_refresh


def test_a_failed_extract_fetch_exits_nonzero_and_says_so(monkeypatch, capsys):
    def boom(**_):
        raise RuntimeError("osm-extracts fetch ontario exited 1")
    monkeypatch.setattr(run, "cmd_download", lambda args: None)
    monkeypatch.setattr(osm_refresh, "run", boom)
    monkeypatch.setattr(run, "cmd_compare", lambda args: pytest.fail("compare ran"))
    with pytest.raises(SystemExit) as exc:
        run.cmd_update(None)
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "ERROR" in err and "OSM refresh failed" in err and "exited 1" in err


def test_a_compare_with_no_input_exits_nonzero(monkeypatch, capsys):
    monkeypatch.setattr(run, "cmd_download", lambda args: None)
    monkeypatch.setattr(osm_refresh, "run", lambda **_: {})
    monkeypatch.setattr(run, "cmd_compare", lambda args: None)
    monkeypatch.setattr(run, "_autopush_docs", lambda day: pytest.fail("pushed"))
    with pytest.raises(SystemExit) as exc:
        run.cmd_update(None)
    assert exc.value.code == 1
    assert "Compare recorded no history row" in capsys.readouterr().err
