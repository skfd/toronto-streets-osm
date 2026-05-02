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


def test_tcl_short_suffixes_match_osm_long():
    """TCL uses short forms (Crt, Crcl, Gt, Gdns, Grv, Hts, Ptwy, Crct, Bdge, Lwn)
    that must collapse to the same key as OSM's long forms."""
    pairs = [
        ("Alicewood Crt", "Alicewood Court"),
        ("Bridletowne Crcl", "Bridletowne Circle"),
        ("Avonwick Gt", "Avonwick Gate"),
        ("Allingham Gdns", "Allingham Gardens"),
        ("Indian Grv", "Indian Grove"),
        ("Clearview Hts", "Clearview Heights"),
        ("Guildpark Ptwy", "Guildpark Pathway"),
        ("Glendower Crct", "Glendower Circuit"),
        ("Leaside Bdge", "Leaside Bridge"),
        ("Alfresco Lwn", "Alfresco Lawn"),
    ]
    for short, long in pairs:
        assert normalize_street(short) == normalize_street(long), f"{short!r} != {long!r}"


if __name__ == "__main__":
    test_suffix_expansion()
    test_direction_expansion()
    test_periods_stripped()
    test_empty_inputs()
    test_no_suffix()
    test_tcl_short_suffixes_match_osm_long()
    print("ok")
