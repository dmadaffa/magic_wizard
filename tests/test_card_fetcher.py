from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
import requests

from agents.card_fetcher import main
from lib.cache import CardCache
from lib.scryfall import CardNotFoundError, RateLimitedError

_FAKE_CARD = {
    "name": "Cinder Dart",
    "mana_cost": "{R}",
    "cmc": "1.0",
    "type_line": "Instant",
}


def test_fetched_card_is_stored_in_cache(tmp_path):
    cache = CardCache(tmp_path / "cache.jsonl")
    with patch("agents.card_fetcher.fetch_card", return_value=_FAKE_CARD):
        main(["Cinder Dart"], cache=cache)
    assert cache.get("Cinder Dart") is not None


def test_card_already_in_cache_skips_scryfall(tmp_path):
    cache = CardCache(tmp_path / "cache.jsonl")
    cache.put("Cinder Dart", _FAKE_CARD)
    with patch("agents.card_fetcher.fetch_card") as mock_fetch:
        main(["Cinder Dart"], cache=cache)
    mock_fetch.assert_not_called()


def test_returns_zero_exit_code_on_success(tmp_path):
    cache = CardCache(tmp_path / "cache.jsonl")
    with patch("agents.card_fetcher.fetch_card", return_value=_FAKE_CARD):
        code = main(["Cinder Dart"], cache=cache)
    assert code == 0


def test_returns_nonzero_exit_code_when_card_not_found(tmp_path):
    cache = CardCache(tmp_path / "cache.jsonl")
    with patch("agents.card_fetcher.fetch_card", side_effect=CardNotFoundError("x")):
        code = main(["Fake Card"], cache=cache)
    assert code != 0


def test_not_found_card_is_not_stored_in_cache(tmp_path):
    cache = CardCache(tmp_path / "cache.jsonl")
    with patch("agents.card_fetcher.fetch_card", side_effect=CardNotFoundError("x")):
        main(["Fake Card"], cache=cache)
    assert cache.get("Fake Card") is None


def test_only_missing_cards_are_fetched(tmp_path):
    cache = CardCache(tmp_path / "cache.jsonl")
    cache.put("Island", {**_FAKE_CARD, "name": "Island"})
    with patch("agents.card_fetcher.fetch_card", return_value=_FAKE_CARD) as mock_fetch:
        main(["Island", "Cinder Dart"], cache=cache)
    assert mock_fetch.call_count == 1
    mock_fetch.assert_called_once_with("Cinder Dart")


def test_rate_limit_stops_the_fetch_loop_and_lists_remaining_cards(tmp_path, capsys):
    cache = CardCache(tmp_path / "cache.jsonl")
    outcomes = [_FAKE_CARD, RateLimitedError("limited"), _FAKE_CARD]
    with patch("agents.card_fetcher.fetch_card", side_effect=outcomes) as mock_fetch:
        code = main(["Card A", "Card B", "Card C"], cache=cache)
    out = capsys.readouterr().out
    assert mock_fetch.call_count == 2
    assert code == 1
    assert cache.get("Card A") is not None
    assert cache.get("Card B") is None and cache.get("Card C") is None
    assert "Not found" not in out
    _, heading, listed = out.partition("Not fetched (Scryfall rate limit)")
    assert heading
    assert [line.strip() for line in listed.splitlines() if "- " in line] == [
        "- Card B",
        "- Card C",
    ]


def test_other_errors_do_not_stop_the_loop(tmp_path, capsys):
    cache = CardCache(tmp_path / "cache.jsonl")
    outcomes = [requests.HTTPError("500"), _FAKE_CARD]
    with patch("agents.card_fetcher.fetch_card", side_effect=outcomes) as mock_fetch:
        code = main(["Card A", "Card B"], cache=cache)
    out = capsys.readouterr().out
    assert mock_fetch.call_count == 2
    assert code == 1
    assert cache.get("Card B") is not None
    assert cache.get("Card A") is None
    _, _, not_found = out.partition("Not found")
    assert "- Card A" in not_found
    assert "rate limit" not in out


def _put_aged(cache, name, fetched_at, card=_FAKE_CARD):
    """Store a card as if it had been fetched at `fetched_at` (fakes the clock inside cache.put)."""
    with patch("lib.cache.datetime") as clock:
        clock.now.return_value = datetime.fromisoformat(fetched_at)
        cache.put(name, card)


def test_stale_cached_card_warns_and_is_not_refetched(tmp_path, capsys):
    cache = CardCache(tmp_path / "cache.jsonl")
    _put_aged(cache, "Old Card", "2020-01-15T00:00:00+00:00")
    cache.put("Fresh Card", _FAKE_CARD)
    with patch("agents.card_fetcher.fetch_card") as mock_fetch:
        code = main(["Old Card", "Fresh Card"], cache=cache)
    err = capsys.readouterr().err
    mock_fetch.assert_not_called()
    assert code == 0
    assert "Old Card" in err and "2020-01-15" in err and "--refresh" in err
    assert "Fresh Card" not in err


@pytest.mark.parametrize(("age_days", "warns"), [(85, False), (95, True)], ids=["85-days", "95-days"])
def test_staleness_threshold_is_about_three_months(tmp_path, capsys, age_days, warns):
    cache = CardCache(tmp_path / "cache.jsonl")
    _put_aged(cache, "Card A", (datetime.now(UTC) - timedelta(days=age_days)).isoformat())
    main(["Card A"], cache=cache)
    err = capsys.readouterr().err
    assert ("Card A" in err) == warns


def test_naive_fetched_at_does_not_crash(tmp_path, capsys):
    cache = CardCache(tmp_path / "cache.jsonl")
    _put_aged(cache, "Card A", "2020-01-15")
    assert main(["Card A"], cache=cache) == 0
    assert "Card A" in capsys.readouterr().err


def test_refresh_refetches_named_cached_cards(tmp_path):
    cache = CardCache(tmp_path / "cache.jsonl")
    _put_aged(cache, "Cinder Dart", "2020-01-15T00:00:00+00:00")
    new = {**_FAKE_CARD, "type_line": "Sorcery"}
    with patch("agents.card_fetcher.fetch_card", return_value=new) as mock_fetch:
        code = main(["Cinder Dart"], cache=cache, refresh=True)
    mock_fetch.assert_called_once_with("Cinder Dart")
    entry = cache.get("Cinder Dart")
    assert code == 0
    assert entry["scryfall"]["type_line"] == "Sorcery"
    assert entry["fetched_at"].startswith(str(datetime.now(UTC).year))


@pytest.mark.parametrize(
    "failure", [CardNotFoundError("x"), RateLimitedError("limited"), requests.HTTPError("500")]
)
def test_failed_refresh_keeps_stale_entry_and_warns(tmp_path, capsys, failure):
    cache = CardCache(tmp_path / "cache.jsonl")
    _put_aged(cache, "Old Card", "2020-01-15T00:00:00+00:00")
    with patch("agents.card_fetcher.fetch_card", side_effect=failure):
        code = main(["Old Card"], cache=cache, refresh=True)
    captured = capsys.readouterr()
    assert code == 0
    assert cache.get("Old Card")["fetched_at"] == "2020-01-15T00:00:00+00:00"
    assert "Old Card" in captured.err and "2020-01-15" in captured.err
    assert "Not found" not in captured.out and "rate limit" not in captured.out
    assert "older than 3 months" not in captured.err
