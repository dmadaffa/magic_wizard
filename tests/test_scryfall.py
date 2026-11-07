import os
import time
import tomllib
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from lib.scryfall import (
    CardNotFoundError,
    RateLimitedError,
    fetch_card,
    fetch_card_names,
    fetch_cards,
    fetch_sets,
    load_sets,
    search_cards,
)
from tests.conftest import load_scryfall

_INSTANT_JSON = load_scryfall("instant")


def _ok(json_data):
    m = Mock()
    m.status_code = 200
    m.json.return_value = json_data
    m.raise_for_status.return_value = None
    return m


def _not_found():
    m = Mock()
    m.status_code = 404
    m.json.return_value = {"object": "error", "status": 404}
    return m


def test_returns_scryfall_card_object(scryfall):
    with patch("lib.scryfall.requests.get", return_value=_ok(scryfall("instant"))):
        result = fetch_card("Ember Sting")
    assert result["name"] == "Ember Sting"
    assert result["mana_cost"] == "{R}"
    assert result["legalities"]["modern"] == "legal"


def test_presentation_keys_are_dropped(scryfall):
    with patch("lib.scryfall.requests.get", return_value=_ok(scryfall("transform"))):
        result = fetch_card("Tidewatch Apprentice")
    assert "prices" not in result
    assert all("image_uris" not in face for face in result["card_faces"])


def test_faces_and_related_parts_are_kept(scryfall):
    with patch("lib.scryfall.requests.get", return_value=_ok(scryfall("transform"))):
        dfc = fetch_card("Tidewatch Apprentice")
    with patch("lib.scryfall.requests.get", return_value=_ok(scryfall("token_maker"))):
        token_maker = fetch_card("Ember Caller")
    assert [f["name"] for f in dfc["card_faces"]] == ["Tidewatch Apprentice", "Tidewatch Horror"]
    assert dfc["cmc"] == 1.0 and dfc["color_identity"] == ["U"]
    assert {"component": "token", "name": "Spark"}.items() <= token_maker["all_parts"][0].items()


def test_raises_card_not_found_on_404():
    with (
        patch("lib.scryfall.requests.get", return_value=_not_found()),
        pytest.raises(CardNotFoundError),
    ):
        fetch_card("Fake Card That Does Not Exist")


def _rate_limited(retry_after=None):
    m = Mock()
    m.status_code = 429
    m.headers = {} if retry_after is None else {"Retry-After": str(retry_after)}
    return m


def _waits(mock_sleep):
    # The 0.55s spacing sleeps are below 1; anything above is a rate-limit wait.
    return [c.args[0] for c in mock_sleep.call_args_list if c.args[0] >= 1.0]


def test_retries_on_429_then_succeeds():
    responses = [_rate_limited(), _ok(_INSTANT_JSON)]
    with (
        patch("lib.scryfall.requests.get", side_effect=responses) as mock_get,
        patch("lib.scryfall.time.sleep"),
    ):
        result = fetch_card("Ember Sting")
    assert result["name"] == "Ember Sting"
    assert mock_get.call_count == 2


def test_sleeps_between_every_request():
    with (
        patch("lib.scryfall.requests.get", return_value=_ok(_INSTANT_JSON)) as mock_get,
        patch("lib.scryfall.time.sleep") as mock_sleep,
    ):
        fetch_card("Ember Sting")
    # At minimum one rate-limit sleep must occur before the successful request
    assert mock_sleep.call_count >= 1
    assert mock_get.call_count == 1


@pytest.mark.parametrize(
    ("retry_after", "expected_wait"),
    [(None, 30), (10, 30), (90, 90)],
    ids=["no-header", "short-retry-after", "long-retry-after"],
)
def test_429_waits_at_least_30s_once_then_retries(retry_after, expected_wait):
    responses = [_rate_limited(retry_after), _ok(_INSTANT_JSON)]
    with (
        patch("lib.scryfall.requests.get", side_effect=responses) as mock_get,
        patch("lib.scryfall.time.sleep") as mock_sleep,
    ):
        fetch_card("Ember Sting")
    assert _waits(mock_sleep) == [expected_wait]
    assert mock_get.call_count == 2


def test_spacing_sleep_precedes_the_request_and_the_retry():
    responses = [_rate_limited(), _ok(_INSTANT_JSON)]
    with (
        patch("lib.scryfall.requests.get", side_effect=responses),
        patch("lib.scryfall.time.sleep") as mock_sleep,
    ):
        fetch_card("Ember Sting")
    sleeps = [c.args[0] for c in mock_sleep.call_args_list]
    # Literals: lowering the spacing below 0.5s would break Scryfall's 2/second limit.
    assert sleeps == [0.55, 30, 0.55]


def test_second_429_raises_without_a_third_request():
    responses = [_rate_limited(), _rate_limited(), _ok(_INSTANT_JSON)]
    with (
        patch("lib.scryfall.requests.get", side_effect=responses) as mock_get,
        patch("lib.scryfall.time.sleep"),
        pytest.raises(RateLimitedError, match="rate"),
    ):
        fetch_card("Ember Sting")
    assert mock_get.call_count == 2


def test_429_message_is_printed_before_the_wait(capsys):
    seen = []

    def fake_sleep(seconds):
        if seconds >= 1.0:
            seen.append(capsys.readouterr().err)

    responses = [_rate_limited(), _ok(_INSTANT_JSON)]
    with (
        patch("lib.scryfall.requests.get", side_effect=responses),
        patch("lib.scryfall.time.sleep", side_effect=fake_sleep),
    ):
        fetch_card("Ember Sting")
    assert len(seen) == 1
    message = seen[0]
    assert "longer than usual" in message
    assert "rate limit" in message.lower()
    assert "30" in message
    assert capsys.readouterr().out == ""


def _pyproject_version():
    root = Path(__file__).resolve().parent.parent
    with open(root / "pyproject.toml", "rb") as f:
        return tomllib.load(f)["project"]["version"]


@pytest.mark.parametrize(
    "call",
    [lambda: fetch_card("Ember Sting"), fetch_card_names],
    ids=["fetch_card", "fetch_card_names"],
)
def test_requests_send_user_agent_with_version_and_accept_json(call):
    response = _ok({"data": ["Ember Sting"], **_INSTANT_JSON})
    with (
        patch("lib.scryfall.requests.get", return_value=response) as mock_get,
        patch("lib.scryfall.time.sleep"),
    ):
        call()
    headers = mock_get.call_args.kwargs["headers"]
    assert headers["User-Agent"] == (
        f"magic-wizard/{_pyproject_version()} "
        "(+https://github.com/dmadaffa/magic_wizard)"
    )
    assert headers["Accept"] == "application/json"


def _page(cards, next_page=None):
    body = {"object": "list", "data": cards, "has_more": next_page is not None}
    if next_page:
        body["next_page"] = next_page
    return _ok(body)


def test_search_pages_one_reads_only_first_page():
    responses = [_page([_INSTANT_JSON], "https://x/p2"), _page([_INSTANT_JSON])]
    with (
        patch("lib.scryfall.requests.get", side_effect=responses) as mock_get,
        patch("lib.scryfall.time.sleep"),
    ):
        result = search_cards("f:standard")
    assert len(result) == 1 and mock_get.call_count == 1
    assert mock_get.call_args.kwargs["params"] == {"q": "f:standard", "order": "edhrec"}
    assert mock_get.call_args.kwargs["headers"]["Accept"] == "application/json"


def test_search_pages_two_concatenates_and_trims():
    second = {**_INSTANT_JSON, "name": "Second Card"}
    responses = [_page([_INSTANT_JSON], "https://x/p2"), _page([second])]
    with (
        patch("lib.scryfall.requests.get", side_effect=responses) as mock_get,
        patch("lib.scryfall.time.sleep"),
    ):
        result = search_cards("f:standard", pages=2)
    assert [c["name"] for c in result] == ["Ember Sting", "Second Card"]
    assert mock_get.call_args.args[0] == "https://x/p2"
    assert all("prices" not in c for c in result)


def test_search_no_match_gives_empty_list():
    with patch("lib.scryfall.requests.get", return_value=_not_found()), patch("lib.scryfall.time.sleep"):
        assert search_cards("f:standard xyzzy") == []


def test_search_goes_through_429_backoff():
    responses = [_rate_limited(), _page([_INSTANT_JSON])]
    with (
        patch("lib.scryfall.requests.get", side_effect=responses) as mock_get,
        patch("lib.scryfall.time.sleep") as mock_sleep,
    ):
        assert len(search_cards("f:standard")) == 1
    assert mock_get.call_count == 2 and _waits(mock_sleep) == [30.0]


def test_fetch_sets_returns_data():
    with patch("lib.scryfall.requests.get", return_value=_ok({"data": [{"code": "xaa"}]})), patch("lib.scryfall.time.sleep"):
        assert fetch_sets() == [{"code": "xaa"}]


def test_load_sets_refreshes_only_when_older_than_a_day(tmp_path):
    path = tmp_path / "sets.json"
    calls = []

    def fetch():
        calls.append(1)
        return [{"code": "xaa"}]

    assert load_sets(path, fetch) == [{"code": "xaa"}] and len(calls) == 1
    load_sets(path, fetch)
    assert len(calls) == 1
    old = time.time() - 2 * 86400
    os.utime(path, (old, old))
    load_sets(path, fetch)
    assert len(calls) == 2


def test_load_sets_failed_download_uses_existing_file_and_warns(tmp_path, capsys):
    path = tmp_path / "sets.json"
    path.write_text('[{"code": "xaa"}]')
    old = time.time() - 2 * 86400
    os.utime(path, (old, old))

    def fetch():
        raise RuntimeError("offline")

    assert load_sets(path, fetch) == [{"code": "xaa"}]
    assert "offline" in capsys.readouterr().err


def _collection(cards, not_found=()):
    return _ok({
        "object": "list",
        "not_found": [{"name": n} for n in not_found],
        "data": cards,
    })


def test_fetch_cards_posts_identifiers_in_one_request():
    with (
        patch("lib.scryfall.requests.post", return_value=_collection([_INSTANT_JSON])) as mock_post,
        patch("lib.scryfall.time.sleep"),
    ):
        result = fetch_cards(["Ember Sting"])
    assert mock_post.call_count == 1
    assert mock_post.call_args.args[0].endswith("/cards/collection")
    assert mock_post.call_args.kwargs["json"] == {"identifiers": [{"name": "Ember Sting"}]}
    assert mock_post.call_args.kwargs["headers"]["Accept"] == "application/json"
    assert mock_post.call_args.kwargs["headers"]["User-Agent"].startswith("magic-wizard/")
    assert result["Ember Sting"]["mana_cost"] == "{R}"


def test_fetch_cards_trims_the_cards():
    with (
        patch("lib.scryfall.requests.post", return_value=_collection([_INSTANT_JSON])),
        patch("lib.scryfall.time.sleep"),
    ):
        result = fetch_cards(["Ember Sting"])
    assert "prices" not in result["Ember Sting"]


@pytest.mark.parametrize(
    ("requested", "card"),
    [
        ("ember sting", _INSTANT_JSON),
        ("Tidewatch Horror", load_scryfall("transform")),
        ("TIDEWATCH APPRENTICE", load_scryfall("transform")),
    ],
    ids=["case-differs", "back-face-name", "front-face-name-upper"],
)
def test_fetch_cards_matches_by_name_or_face_name_ignoring_case(requested, card):
    # The position of a card in data is not used: an unrelated card comes first.
    other = {**_INSTANT_JSON, "name": "Unrelated Card"}
    with (
        patch("lib.scryfall.requests.post", return_value=_collection([other, card])),
        patch("lib.scryfall.time.sleep"),
    ):
        result = fetch_cards([requested])
    assert result[requested]["name"] == card["name"]


def test_fetch_cards_leaves_unmatched_names_out_of_the_result():
    with (
        patch("lib.scryfall.requests.post", return_value=_collection([_INSTANT_JSON], not_found=["Fake Card"])),
        patch("lib.scryfall.time.sleep"),
    ):
        result = fetch_cards(["Ember Sting", "Fake Card"])
    assert list(result) == ["Ember Sting"]


def test_fetch_cards_full_name_match_beats_a_face_name_match_in_any_data_order():
    # The first card's back face is named like the second card's full name.
    dfc = load_scryfall("transform")
    clash = {**_INSTANT_JSON, "name": dfc["card_faces"][1]["name"]}
    with (
        patch("lib.scryfall.requests.post", return_value=_collection([dfc, clash])),
        patch("lib.scryfall.time.sleep"),
    ):
        result = fetch_cards([clash["name"]])
    assert result[clash["name"]]["name"] == clash["name"]
    assert "card_faces" not in result[clash["name"]]


def test_fetch_cards_retries_once_after_a_429():
    responses = [_rate_limited(), _collection([_INSTANT_JSON])]
    with (
        patch("lib.scryfall.requests.post", side_effect=responses) as mock_post,
        patch("lib.scryfall.time.sleep") as mock_sleep,
    ):
        fetch_cards(["Ember Sting"])
    assert mock_post.call_count == 2
    assert [c.args[0] for c in mock_sleep.call_args_list] == [0.55, 30, 0.55]


def test_fetch_cards_second_429_raises():
    with (
        patch("lib.scryfall.requests.post", side_effect=[_rate_limited(), _rate_limited()]) as mock_post,
        patch("lib.scryfall.time.sleep"),
        pytest.raises(RateLimitedError),
    ):
        fetch_cards(["Ember Sting"])
    assert mock_post.call_count == 2
