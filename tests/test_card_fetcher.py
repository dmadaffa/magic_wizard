import os
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


@pytest.fixture(autouse=True)
def _no_batch_by_default():
    """Scryfall boundary: by default the batch request matches nothing, so the
    per-card tests below exercise the one-by-one path. Batch tests patch it again."""
    with patch("agents.card_fetcher.fetch_cards", return_value={}) as batch:
        yield batch


def _all_found(names):
    return {n: {**_FAKE_CARD, "name": n} for n in names}


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


def test_dirty_cli_name_is_a_cache_hit(tmp_path):
    cache = CardCache(tmp_path / "cache.jsonl")
    cache.put("Invented Card", _FAKE_CARD)
    with patch("agents.card_fetcher.fetch_card") as mock_fetch:
        main(["Invented Card\r"], cache=cache)
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


def test_cards_are_fetched_in_batches_of_75_with_one_cache_write_each(tmp_path):
    cache = CardCache(tmp_path / "cache.jsonl")
    names = [f"Invented Card {i}" for i in range(76)]
    with (
        patch("agents.card_fetcher.fetch_cards", side_effect=_all_found) as batch,
        patch("agents.card_fetcher.fetch_card") as single,
        patch("lib.cache.os.replace", wraps=os.replace) as replace,
    ):
        code = main(names, cache=cache)
    assert [len(c.args[0]) for c in batch.call_args_list] == [75, 1]
    single.assert_not_called()
    assert replace.call_count == 2
    assert code == 0
    assert all(cache.get(n) is not None for n in names)


def test_unmatched_names_are_retried_one_by_one(tmp_path, capsys):
    cache = CardCache(tmp_path / "cache.jsonl")
    outcomes = {"Card B": _FAKE_CARD}

    def single(name):
        if name in outcomes:
            return outcomes[name]
        raise CardNotFoundError(name)

    with (
        patch("agents.card_fetcher.fetch_cards", side_effect=lambda ns: _all_found(["Card A"])),
        patch("agents.card_fetcher.fetch_card", side_effect=single) as mock_single,
    ):
        code = main(["Card A", "Card B", "Card C"], cache=cache)
    out = capsys.readouterr().out
    assert [c.args[0] for c in mock_single.call_args_list] == ["Card B", "Card C"]
    assert code == 1
    assert cache.get("Card B") is not None and cache.get("Card C") is None
    assert "Fetched    : 2" in out
    assert "- Card C" in out.partition("Not found")[2]


def test_names_differing_only_in_whitespace_are_requested_once(tmp_path, capsys):
    path = tmp_path / "cache.jsonl"
    cache = CardCache(path)
    with patch("agents.card_fetcher.fetch_cards", side_effect=lambda ns: _all_found(ns)) as batch:
        code = main(["Invented Card", "Invented Card "], cache=cache)
    assert batch.call_count == 1 and len(batch.call_args.args[0]) == 1
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1
    assert code == 0
    assert "Fetched    : 2" in capsys.readouterr().out


def test_unmatched_whitespace_variants_get_one_retry_and_are_both_listed(tmp_path, capsys):
    cache = CardCache(tmp_path / "cache.jsonl")
    with patch("agents.card_fetcher.fetch_card", side_effect=CardNotFoundError("x")) as single:
        code = main(["Fake Card", "Fake Card "], cache=cache)
    out = capsys.readouterr().out
    assert single.call_count == 1 and code == 1
    assert "Not found  : 2" in out


def test_failed_batch_request_falls_back_to_one_by_one(tmp_path):
    cache = CardCache(tmp_path / "cache.jsonl")
    with (
        patch("agents.card_fetcher.fetch_cards", side_effect=requests.HTTPError("500")),
        patch("agents.card_fetcher.fetch_card", return_value=_FAKE_CARD) as single,
    ):
        code = main(["Card A", "Card B"], cache=cache)
    assert single.call_count == 2 and code == 0
    assert cache.get("Card A") is not None


def test_refresh_batch_replaces_stale_entry_and_keeps_unmatched_one(tmp_path, capsys):
    cache = CardCache(tmp_path / "cache.jsonl")
    _put_aged(cache, "Card A", "2020-01-15T00:00:00+00:00")
    _put_aged(cache, "Card B", "2020-01-15T00:00:00+00:00")
    new = {**_FAKE_CARD, "type_line": "Sorcery"}
    with (
        patch("agents.card_fetcher.fetch_cards", return_value={"Card A": new}),
        patch("agents.card_fetcher.fetch_card", side_effect=CardNotFoundError("x")),
    ):
        code = main(["Card A", "Card B"], cache=cache, refresh=True)
    out = capsys.readouterr().out
    assert code == 0
    assert cache.get("Card A")["scryfall"]["type_line"] == "Sorcery"
    assert cache.get("Card B")["fetched_at"] == "2020-01-15T00:00:00+00:00"
    assert "Fetched    : 1" in out and "Kept stale : 1" in out


def test_rate_limit_lists_earlier_unmatched_names_too_and_never_retries(tmp_path, capsys):
    cache = CardCache(tmp_path / "cache.jsonl")
    names = [f"Invented Card {i}" for i in range(76)]
    outcomes = [_all_found(names[:74]), RateLimitedError("limited")]
    with (
        patch("agents.card_fetcher.fetch_cards", side_effect=outcomes),
        patch("agents.card_fetcher.fetch_card") as single,
    ):
        code = main(names, cache=cache)
    out = capsys.readouterr().out
    single.assert_not_called()
    assert code == 1
    assert cache.get(names[0]) is not None and cache.get(names[75]) is None
    assert "Not fetched (Scryfall rate limit), try again later: 2" in out
    _, heading, listed = out.partition("Not fetched (Scryfall rate limit)")
    assert heading
    assert [line.strip() for line in listed.splitlines() if "- " in line] == [
        "- Invented Card 74",
        "- Invented Card 75",
    ]


def test_dirty_names_are_requested_by_their_normalized_name(tmp_path):
    cache = CardCache(tmp_path / "cache.jsonl")
    with (
        patch("agents.card_fetcher.fetch_cards", side_effect=_all_found) as batch,
        patch("agents.card_fetcher.fetch_card") as single,
    ):
        main(["Invented Card ", "Other  Card\r"], cache=cache)
    assert batch.call_args.args[0] == ["Invented Card", "Other Card"]
    single.assert_not_called()
    assert cache.get("Other Card") is not None


def test_unmatched_dirty_name_is_retried_by_its_normalized_name(tmp_path):
    cache = CardCache(tmp_path / "cache.jsonl")
    with patch("agents.card_fetcher.fetch_card", return_value=_FAKE_CARD) as single:
        main(["Invented Card "], cache=cache)
    single.assert_called_once_with("Invented Card")


@pytest.mark.parametrize("refresh", [False, True], ids=["new-card", "refresh-keeps-stale"])
def test_cache_write_error_is_reported_not_a_crash(tmp_path, capsys, refresh):
    cache = CardCache(tmp_path / "cache.jsonl")
    if refresh:
        _put_aged(cache, "Card A", "2020-01-15T00:00:00+00:00")
    with (
        patch("agents.card_fetcher.fetch_cards", side_effect=_all_found),
        patch("lib.cache.os.replace", side_effect=PermissionError("locked")),
    ):
        code = main(["Card A", "Card A "], cache=cache, refresh=refresh)
    captured = capsys.readouterr()
    assert "locked" in captured.err
    assert "Fetched    : 0" in captured.out
    if refresh:
        assert code == 0 and "Kept stale : 2" in captured.out
    else:
        assert code == 1 and "Not found  : 2" in captured.out
