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


def test_park_collapses_to_pk():
    """TCL writes 'Bellwoods Pk', OSM writes 'Bellwoods Park'. Collapse to match.
    Mid-name 'Park' (e.g. 'High Park Ave') is rewritten on both sides symmetrically,
    so matching is preserved."""
    assert normalize_street("Bellwoods Pk") == "BELLWOODS PK"
    assert normalize_street("Bellwoods Park") == "BELLWOODS PK"
    assert normalize_street("Wychwood Pk") == normalize_street("Wychwood Park")
    assert normalize_street("High Park Avenue") == normalize_street("High Park Ave") == "HIGH PK AVE"


def test_mc_mac_collapse():
    """TCL writes 'Mc Gregor', OSM writes 'McGregor' / 'MacGregor'. Collapse to match."""
    assert normalize_street("Mc Gregor Ave") == "MCGREGOR AVE"
    assert normalize_street("McGregor Avenue") == "MCGREGOR AVE"
    assert normalize_street("Mac Gregor Ave") == "MACGREGOR AVE"
    assert normalize_street("MacGregor Avenue") == "MACGREGOR AVE"
    assert normalize_street("Mac") == "MAC"


def test_saint_collapses_to_st():
    """TCL writes 'St Leonard', OSM may write 'Saint Leonard' or 'St. Leonard'."""
    assert normalize_street("St Leonard's Ave") == "ST LEONARDS AVE"
    assert normalize_street("Saint Leonard's Avenue") == "ST LEONARDS AVE"
    assert normalize_street("St. Leonard's Avenue") == "ST LEONARDS AVE"


def test_apostrophes_stripped():
    """Both straight ' and curly ’ apostrophes are removed before tokenization."""
    assert normalize_street("St. Hilda's Avenue") == normalize_street("St. Hilda’s Avenue")
    assert normalize_street("St Helen's Ave") == normalize_street("St. Helens Avenue")


if __name__ == "__main__":
    test_suffix_expansion()
    test_direction_expansion()
    test_periods_stripped()
    test_empty_inputs()
    test_no_suffix()
    test_tcl_short_suffixes_match_osm_long()
    test_park_collapses_to_pk()
    test_mc_mac_collapse()
    test_saint_collapses_to_st()
    test_apostrophes_stripped()
    print("ok")
