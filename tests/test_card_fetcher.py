from unittest.mock import patch, Mock
import pytest
from lib.cache import CardCache
from lib.scryfall import CardNotFoundError
from agents.card_fetcher import main

_FAKE_CARD = {
    "name": "Cinder Dart",
    "mana_cost": "{R}",
    "cmc": "1.0",
    "type_line": "Instant",
}


def test_fetched_card_is_stored_in_cache(tmp_path):
    cache = CardCache(tmp_path / "cache.csv")
    with patch("agents.card_fetcher.fetch_card", return_value=_FAKE_CARD):
        main(["Cinder Dart"], cache=cache)
    assert cache.get("Cinder Dart") is not None


def test_card_already_in_cache_skips_scryfall(tmp_path):
    cache = CardCache(tmp_path / "cache.csv")
    cache.put("Cinder Dart", _FAKE_CARD)
    with patch("agents.card_fetcher.fetch_card") as mock_fetch:
        main(["Cinder Dart"], cache=cache)
    mock_fetch.assert_not_called()


def test_returns_zero_exit_code_on_success(tmp_path):
    cache = CardCache(tmp_path / "cache.csv")
    with patch("agents.card_fetcher.fetch_card", return_value=_FAKE_CARD):
        code = main(["Cinder Dart"], cache=cache)
    assert code == 0


def test_returns_nonzero_exit_code_when_card_not_found(tmp_path):
    cache = CardCache(tmp_path / "cache.csv")
    with patch("agents.card_fetcher.fetch_card", side_effect=CardNotFoundError("x")):
        code = main(["Fake Card"], cache=cache)
    assert code != 0


def test_not_found_card_is_not_stored_in_cache(tmp_path):
    cache = CardCache(tmp_path / "cache.csv")
    with patch("agents.card_fetcher.fetch_card", side_effect=CardNotFoundError("x")):
        main(["Fake Card"], cache=cache)
    assert cache.get("Fake Card") is None


def test_only_missing_cards_are_fetched(tmp_path):
    cache = CardCache(tmp_path / "cache.csv")
    cache.put("Island", {**_FAKE_CARD, "name": "Island"})
    with patch("agents.card_fetcher.fetch_card", return_value=_FAKE_CARD) as mock_fetch:
        main(["Island", "Cinder Dart"], cache=cache)
    assert mock_fetch.call_count == 1
    mock_fetch.assert_called_once_with("Cinder Dart")
