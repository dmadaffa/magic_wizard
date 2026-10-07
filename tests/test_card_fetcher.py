from unittest.mock import patch

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
