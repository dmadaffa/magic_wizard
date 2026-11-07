import json
import os
from pathlib import Path
from unittest.mock import patch

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


def test_put_fsyncs_flushed_temp_file_before_rename(tmp_path):
    path = tmp_path / "cache.jsonl"
    cache = CardCache(path)
    events = []
    real_fsync, real_replace = os.fsync, os.replace

    def fake_fsync(fd):
        # The data must already be flushed to the OS when fsync runs.
        events.append(("fsync", os.fstat(fd).st_size))
        real_fsync(fd)

    def fake_replace(src, dst):
        events.append(("replace", Path(src).name))
        real_replace(src, dst)

    with patch("lib.cache.os.fsync", fake_fsync), patch("lib.cache.os.replace", fake_replace):
        cache.put("Ember Sting", _INSTANT)

    assert [e[0] for e in events] == ["fsync", "replace"]
    assert events[0][1] > 0
    assert events[1][1] == "cache.jsonl.tmp"


def test_put_normalizes_name(tmp_path):
    cache = CardCache(tmp_path / "cache.jsonl")
    cache.put("Invented Card\r", _INSTANT)
    entry = cache.get("Invented Card")
    assert entry is not None
    assert entry["name"] == "Invented Card"


def test_get_many_keys_are_the_callers_names(tmp_path):
    cache = CardCache(tmp_path / "cache.jsonl")
    cache.put("Invented Card", _INSTANT)
    results = cache.get_many([" Invented  Card "])
    assert list(results) == [" Invented  Card "]
    assert results[" Invented  Card "] is not None


def test_load_merges_dirty_keys_keeping_newest(tmp_path):
    path = tmp_path / "cache.jsonl"
    old = {"name": "Invented Card\r", "fetched_at": "2026-01-01T00:00:00+00:00",
           "scryfall": {**_INSTANT, "type_line": "Sorcery"}}
    new = {"name": "Invented Card", "fetched_at": "2026-02-01T00:00:00+00:00",
           "scryfall": {**_INSTANT, "type_line": "Instant"}}
    path.write_text("\n".join(json.dumps(e) for e in (new, old)) + "\n", encoding="utf-8")
    cache = CardCache(path)
    entry = cache.get("Invented Card")
    assert entry["scryfall"]["type_line"] == "Instant"
    assert entry["name"] == "Invented Card"

    cache.put("Ember Sting", _INSTANT)
    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [e["name"] for e in lines] == ["Invented Card", "Ember Sting"]


def test_load_tie_on_fetched_at_keeps_later_line(tmp_path):
    path = tmp_path / "cache.jsonl"
    stamp = "2026-01-01T00:00:00+00:00"
    first = {"name": "Invented Card", "fetched_at": stamp,
             "scryfall": {**_INSTANT, "type_line": "Sorcery"}}
    second = {"name": "Invented Card\r", "fetched_at": stamp,
              "scryfall": {**_INSTANT, "type_line": "Instant"}}
    path.write_text("\n".join(json.dumps(e) for e in (first, second)) + "\n", encoding="utf-8")
    assert CardCache(path).get("Invented Card")["scryfall"]["type_line"] == "Instant"


def test_multiple_cards_stored_independently(tmp_path):
    cache = CardCache(tmp_path / "cache.jsonl")
    cache.put("Ember Sting", _INSTANT)
    cache.put("Tidewatch Apprentice", _DFC)
    assert cache.get("Ember Sting")["scryfall"]["mana_cost"] == "{R}"
    assert cache.get("Tidewatch Apprentice")["scryfall"]["layout"] == "transform"


def test_put_many_stores_every_entry_with_one_rewrite_and_keeps_others(tmp_path):
    path = tmp_path / "cache.jsonl"
    cache = CardCache(path)
    cache.put("Old Card", _INSTANT)
    with patch("lib.cache.os.replace", wraps=os.replace) as replace:
        cache.put_many({"Ember Sting": _INSTANT, "Tidewatch Apprentice": _DFC})
    assert replace.call_count == 1
    assert cache.get("Old Card") is not None
    entry = cache.get("Tidewatch Apprentice")
    assert entry["scryfall"] == _DFC and entry["fetched_at"]
    assert set(entry) == {"name", "fetched_at", "scryfall"}
    assert len(path.read_text(encoding="utf-8").splitlines()) == 3


def test_put_many_normalizes_names_and_replaces_existing(tmp_path):
    path = tmp_path / "cache.jsonl"
    cache = CardCache(path)
    cache.put("Ember Sting", {"name": "old"})
    cache.put_many({"Ember Sting ": _INSTANT})
    assert cache.get("Ember Sting")["scryfall"] == _INSTANT
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1


def test_put_many_fsyncs_the_temp_file_before_the_rename(tmp_path):
    cache = CardCache(tmp_path / "cache.jsonl")
    order = []
    with (
        patch("lib.cache.os.fsync", side_effect=lambda fd: order.append("fsync")),
        patch("lib.cache.os.replace", side_effect=lambda *a: order.append("replace")),
    ):
        cache.put_many({"Ember Sting": _INSTANT})
    assert order == ["fsync", "replace"]
