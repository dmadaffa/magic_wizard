import pytest
from lib.cache import CardCache

_SAMPLE = {"name": "Cinder Dart", "mana_cost": "{R}", "cmc": "1.0", "type_line": "Instant"}


def test_unknown_card_returns_none(tmp_path):
    cache = CardCache(tmp_path / "cache.csv")
    assert cache.get("Nonexistent Card") is None


def test_stored_card_can_be_retrieved(tmp_path):
    cache = CardCache(tmp_path / "cache.csv")
    cache.put("Cinder Dart", _SAMPLE)
    result = cache.get("Cinder Dart")
    assert result["name"] == "Cinder Dart"
    assert result["mana_cost"] == "{R}"


def test_get_many_returns_hits_and_misses(tmp_path):
    cache = CardCache(tmp_path / "cache.csv")
    cache.put("Cinder Dart", _SAMPLE)
    results = cache.get_many(["Cinder Dart", "Island"])
    assert results["Cinder Dart"] is not None
    assert results["Island"] is None


def test_putting_same_card_twice_keeps_latest_value(tmp_path):
    cache = CardCache(tmp_path / "cache.csv")
    cache.put("Cinder Dart", {**_SAMPLE, "type_line": "Sorcery"})
    cache.put("Cinder Dart", {**_SAMPLE, "type_line": "Instant"})
    assert cache.get("Cinder Dart")["type_line"] == "Instant"


def test_cache_persists_across_instances(tmp_path):
    path = tmp_path / "cache.csv"
    CardCache(path).put("Cinder Dart", _SAMPLE)
    assert CardCache(path).get("Cinder Dart") is not None


def test_multiple_cards_stored_independently(tmp_path):
    cache = CardCache(tmp_path / "cache.csv")
    cache.put("Cinder Dart", _SAMPLE)
    cache.put("Island", {**_SAMPLE, "name": "Island", "mana_cost": ""})
    assert cache.get("Cinder Dart")["mana_cost"] == "{R}"
    assert cache.get("Island")["mana_cost"] == ""
