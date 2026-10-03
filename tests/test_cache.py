import pytest

from lib.cache import CardCache
from tests.conftest import load_scryfall

_INSTANT = load_scryfall("instant")
_DFC = load_scryfall("transform")


def test_unknown_card_returns_none(tmp_path):
    cache = CardCache(tmp_path / "cache.jsonl")
    assert cache.get("Nonexistent Card") is None


def test_stored_card_can_be_retrieved(tmp_path):
    cache = CardCache(tmp_path / "cache.jsonl")
    cache.put("Ember Sting", _INSTANT)
    entry = cache.get("Ember Sting")
    assert entry["name"] == "Ember Sting"
    assert entry["scryfall"]["mana_cost"] == "{R}"
    assert entry["fetched_at"]


def test_nested_card_faces_round_trip(tmp_path):
    path = tmp_path / "cache.jsonl"
    CardCache(path).put("Tidewatch Apprentice", _DFC)
    assert CardCache(path).get("Tidewatch Apprentice")["scryfall"] == _DFC


def test_get_many_returns_hits_and_misses(tmp_path):
    cache = CardCache(tmp_path / "cache.jsonl")
    cache.put("Ember Sting", _INSTANT)
    results = cache.get_many(["Ember Sting", "Missing Card"])
    assert results["Ember Sting"] is not None
    assert results["Missing Card"] is None


def test_putting_same_card_twice_keeps_latest_value(tmp_path):
    cache = CardCache(tmp_path / "cache.jsonl")
    cache.put("Ember Sting", {**_INSTANT, "type_line": "Sorcery"})
    cache.put("Ember Sting", {**_INSTANT, "type_line": "Instant"})
    assert cache.get("Ember Sting")["scryfall"]["type_line"] == "Instant"


def test_cache_persists_across_instances(tmp_path):
    path = tmp_path / "cache.jsonl"
    CardCache(path).put("Ember Sting", _INSTANT)
    assert CardCache(path).get("Ember Sting") is not None


def test_failed_put_leaves_cache_untouched(tmp_path):
    path = tmp_path / "cache.jsonl"
    cache = CardCache(path)
    cache.put("Ember Sting", _INSTANT)
    cache.put("Tidewatch Apprentice", _DFC)
    before = path.read_bytes()

    # A set is not JSON-serializable. The second card keeps its position, so
    # the first line is written and then the write fails partway through.
    with pytest.raises(TypeError):
        cache.put("Tidewatch Apprentice", {**_DFC, "colors": {"U"}})

    assert path.read_bytes() == before
    assert [p.name for p in tmp_path.iterdir()] == ["cache.jsonl"]


def test_multiple_cards_stored_independently(tmp_path):
    cache = CardCache(tmp_path / "cache.jsonl")
    cache.put("Ember Sting", _INSTANT)
    cache.put("Tidewatch Apprentice", _DFC)
    assert cache.get("Ember Sting")["scryfall"]["mana_cost"] == "{R}"
    assert cache.get("Tidewatch Apprentice")["scryfall"]["layout"] == "transform"
