import tomllib
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from lib.scryfall import (
    CardNotFoundError,
    RateLimitedError,
    fetch_card,
    fetch_card_names,
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
