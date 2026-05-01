"""Sanity checks for normalize_street -- the join-key for TCL vs OSM comparison."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.normalize import normalize_street


def test_suffix_expansion():
    assert normalize_street("Yonge Street") == "YONGE ST"
    assert normalize_street("Yonge St") == "YONGE ST"


def test_direction_expansion():
    assert normalize_street("Bloor Street West") == "BLOOR ST W"
    assert normalize_street("Bloor St W") == "BLOOR ST W"


def test_periods_stripped():
    assert normalize_street("Bloor St. W.") == "BLOOR ST W"


def test_empty_inputs():
    assert normalize_street(None) == ""
    assert normalize_street("") == ""
    assert normalize_street("   ") == ""


def test_no_suffix():
    assert normalize_street("Yonge") == "YONGE"


if __name__ == "__main__":
    test_suffix_expansion()
    test_direction_expansion()
    test_periods_stripped()
    test_empty_inputs()
    test_no_suffix()
    print("ok")
