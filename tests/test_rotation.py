import json
from datetime import date, timedelta
from urllib.parse import quote

import pytest

from agents.rotation_report import main
from lib import rotation as rot

TODAY = date(2026, 11, 2)
ROTATION = rot.Rotation(date(2027, 1, 29), rotating=["xaa", "xbb"], evergreen=["xev"])


def _set(code, set_type="expansion", digital=False, released="2026-06-01"):
    return {"object": "set", "code": code, "set_type": set_type, "digital": digital,
            "released_at": released}


SETS = [
    _set("xold", released="2020-01-01"),   # older than every rotating set: left out
    _set("xaa", released="2024-01-01"),    # rotating
    _set("xbb", released="2024-06-01"),    # rotating
    _set("xcc"),                           # new expansion not in the file: survives
    _set("xdd", "core", released="2024-01-01"),  # core on the cutoff date survives
    _set("xee", digital=True),             # digital: excluded
    _set("pxaa", "promo"),                 # other set types: excluded
    _set("xgg", "masters"),
    _set("xev", "masters", released="2019-01-01"),  # evergreen: always survives
]


def test_surviving_sets_rules():
    assert rot.surviving_sets(SETS, ROTATION) == ["xcc", "xdd", "xev"]


def test_surviving_sets_empty_when_no_rotating_code_in_sets():
    assert rot.surviving_sets([_set("xcc")], ROTATION) == []


@pytest.mark.parametrize("days, expected", [
    (184, "inactive"), (183, "active"), (1, "active"), (0, "stale"), (-30, "stale"),
])
def test_status_boundaries(days, expected):
    r = rot.Rotation(TODAY + timedelta(days=days), [], [])
    assert rot.status(r, TODAY) == expected


def test_load_rotation(tmp_path):
    p = tmp_path / "r.json"
    p.write_text(json.dumps({"next_rotation": "2027-01-29", "rotating": ["xaa"], "evergreen": ["xev"]}))
    assert rot.load_rotation(p) == rot.Rotation(date(2027, 1, 29), ["xaa"], ["xev"])


def test_survival_prefix_uses_in_not_date():
    prefix = rot.survival_prefix(["xcc", "xdd"])
    assert prefix == "(in:xcc or in:xdd)"


def test_rotating_query_excludes_surviving_printings_not_by_date_or_edition_group():
    # A card printed only in a rotating set plus a promo set must match: the filter
    # negates in: over the surviving codes, so a promo printing can't save it.
    surviving = rot.surviving_sets(SETS, ROTATION)
    (query,) = rot.rotating_query(surviving, ["Ember Sting", "Murk Prism"])
    assert query == 'f:standard -in:xcc -in:xdd -in:xev (!"Ember Sting" or !"Murk Prism")'
    assert "in:pxaa" not in query and "date" not in query and "-(e:" not in query


def test_rotating_query_splits_long_name_lists():
    names = [f"Invented Card Number {i:03d}" for i in range(200)]
    queries = rot.rotating_query(["xcc"], names)
    assert len(queries) > 1
    assert all(len(quote(q)) <= rot.MAX_QUERY_URL_CHARS for q in queries)
    assert sum(q.count("!") for q in queries) == 200


@pytest.mark.parametrize("colors, expected", [(["R", "W"], "id<=rw"), ([], "id<=c")])
def test_color_filter(colors, expected):
    assert rot.color_filter(colors) == expected


# --- CLI -------------------------------------------------------------------

def _files(tmp_path, next_rotation, sets=None):
    rot_file = tmp_path / "rotation.json"
    rot_file.write_text(json.dumps(
        {"next_rotation": next_rotation, "rotating": ["xaa"], "evergreen": []}
    ))
    deck = tmp_path / "deck.txt"
    deck.write_text("4 Ember Sting (XAA) 123\n20 Mountain\n2 Murk Prism (XCC) 7\n")
    sets_cache = tmp_path / "sets.json"
    sets_cache.write_text(json.dumps(sets if sets is not None else [_set("xaa", released="2024-01-01"), _set("xcc")]))
    return rot_file, deck, sets_cache


def _run(tmp_path, next_rotation, args=None, search=None, sets=None):
    rot_file, deck, sets_cache = _files(tmp_path, next_rotation, sets)
    queries = []

    def fake_search(query, pages=1):
        queries.append(query)
        return [{"name": "Ember Sting"}]

    code = main(args if args is not None else [str(deck)], today=TODAY,
                rotation_path=rot_file, sets_path=sets_cache, search=search or fake_search)
    return code, queries


def test_report_uses_clean_names_from_parser(tmp_path, capsys):
    code, queries = _run(tmp_path, "2027-01-29")
    out = capsys.readouterr().out
    assert code == 0
    assert queries == ['f:standard -in:xcc (!"Ember Sting" or !"Murk Prism")']
    assert "ROTATING: Ember Sting" in out
    assert "88 days left" in out


def test_report_inactive_far_rotation(tmp_path, capsys):
    _, queries = _run(tmp_path, "2027-06-01")
    assert queries == []
    assert "more than 6 months away" in capsys.readouterr().out


def test_report_stale_warns_on_stderr(tmp_path, capsys):
    _, queries = _run(tmp_path, "2026-10-01")
    captured = capsys.readouterr()
    assert queries == []
    assert "rotation date" in captured.err and "has passed" in captured.err


@pytest.mark.parametrize("next_rotation, expected", [
    ("2027-01-29", "(in:xcc)\n"), ("2027-06-01", "\n"),
])
def test_prefix_mode(tmp_path, capsys, next_rotation, expected):
    _run(tmp_path, next_rotation, args=["--prefix"])
    assert capsys.readouterr().out == expected


def test_report_when_no_deck_card_rotates(tmp_path, capsys):
    _run(tmp_path, "2027-01-29", search=lambda query, pages=1: [])
    assert "No cards in this deck rotate." in capsys.readouterr().out


_SKIPPED = (
    "Rotation report skipped: the rotating set codes in data/standard_rotation.json "
    "were not found in Scryfall's sets.\n"
)


@pytest.mark.parametrize("args, expected_out", [(None, _SKIPPED), (["--prefix"], "\n")])
def test_no_rotating_code_in_sets_warns_and_acts_inactive(tmp_path, capsys, args, expected_out):
    _, queries = _run(tmp_path, "2027-01-29", args=args, sets=[_set("xcc")])
    captured = capsys.readouterr()
    assert queries == []
    assert "no rotating set" in captured.err
    assert captured.out == expected_out
