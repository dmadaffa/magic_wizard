import pytest

from agents.card_view import main
from lib.cache import CardCache
from lib.scryfall import trim_card


def _cache_with(tmp_path, scryfall, **cards):
    cache = CardCache(tmp_path / "cache.jsonl")
    for name, fixture in cards.items():
        cache.put(name, trim_card(scryfall(fixture)))
    return cache


def test_single_faced_card_is_one_header_plus_text(tmp_path, scryfall, capsys):
    cache = _cache_with(tmp_path, scryfall, **{"Ember Sting": "instant"})
    assert main(["Ember Sting"], cache=cache) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("Ember Sting | {R} | CMC 1 | identity R | Instant | standard:")
    assert out[1] == "    Ember Sting deals 2 damage to any target."


def test_multi_faced_card_lists_each_face_with_access(tmp_path, scryfall, capsys):
    cache = _cache_with(tmp_path, scryfall, **{"Mara Voss": "modal_dfc_transform"})
    main(["Mara Voss"], cache=cache)
    out = capsys.readouterr().out
    assert "Mara Voss // Mara the Unbroken | modal_dfc | CMC 2 | identity GW" in out
    assert "[face 1: cast] Mara Voss | {G}{W} | Legendary Creature — Human Advocate | 1/4" in out
    assert "[face 2: cast, transform] Mara the Unbroken | {3}{G}{W}{W}" in out


def test_uncached_card_reports_and_fails(tmp_path, capsys):
    cache = CardCache(tmp_path / "cache.jsonl")
    assert main(["Nope"], cache=cache) == 1
    assert "NOT CACHED: Nope" in capsys.readouterr().err


def _legality_part(out: str) -> str:
    return out.splitlines()[0].rsplit(" | ", 1)[1]


@pytest.mark.parametrize(
    ("fmt", "expected"),
    [
        pytest.param(None, "standard:not_legal, modern:legal, pioneer:legal, legacy:legal, commander:legal", id="no-format-defaults"),
        pytest.param("Pauper", "pauper:legal", id="simple"),
        pytest.param("Pauper Commander", "paupercommander:legal", id="spaces-removed"),
        pytest.param("Pre-Modern", "premodern:not_legal", id="hyphen-removed"),
        pytest.param("Draft", "draft:unknown", id="no-scryfall-key"),
        pytest.param("explorer", "explorer:unknown", id="explorer-has-no-key"),
    ],
)
def test_legality_shown_for_the_format(tmp_path, scryfall, capsys, fmt, expected):
    cache = _cache_with(tmp_path, scryfall, **{"Ember Sting": "instant"})
    main(["Ember Sting"], cache=cache, fmt=fmt)
    assert _legality_part(capsys.readouterr().out) == expected
