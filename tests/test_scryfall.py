from unittest.mock import Mock, patch

import pytest
import requests

from lib.scryfall import _MAX_RETRIES, CardNotFoundError, fetch_card
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


def _rate_limited():
    m = Mock()
    m.status_code = 429
    return m


def test_retries_on_429_then_succeeds():
    responses = [_rate_limited(), _ok(_INSTANT_JSON)]
    with patch("lib.scryfall.requests.get", side_effect=responses) as mock_get, \
         patch("lib.scryfall.time.sleep"):
        result = fetch_card("Ember Sting")
    assert result["name"] == "Ember Sting"
    assert mock_get.call_count == 2


def test_retries_exhaust_max_retries_then_raises():
    # All attempts return 429 — the final call also 429, raise_for_status blows up
    rate_limited_responses = [_rate_limited()] * (_MAX_RETRIES + 1)
    last = _rate_limited()
    last.raise_for_status.side_effect = requests.HTTPError("429")
    responses = rate_limited_responses[:-1] + [last]
    with patch("lib.scryfall.requests.get", side_effect=responses), \
         patch("lib.scryfall.time.sleep"), pytest.raises(requests.HTTPError):
        fetch_card("Ember Sting")


def test_sleeps_between_every_request():
    with patch("lib.scryfall.requests.get", return_value=_ok(_INSTANT_JSON)) as mock_get, \
         patch("lib.scryfall.time.sleep") as mock_sleep:
        fetch_card("Ember Sting")
    # At minimum one rate-limit sleep must occur before the successful request
    assert mock_sleep.call_count >= 1
    assert mock_get.call_count == 1


def test_backoff_increases_with_each_retry():
    responses = [_rate_limited(), _rate_limited(), _ok(_INSTANT_JSON)]
    with patch("lib.scryfall.requests.get", side_effect=responses), \
         patch("lib.scryfall.time.sleep") as mock_sleep:
        fetch_card("Ember Sting")
    sleep_args = [c.args[0] for c in mock_sleep.call_args_list]
    # Extract the backoff waits (values >= 1.0 — rate-limit sleeps are 0.55)
    backoff_waits = [s for s in sleep_args if s >= 1.0]
    assert len(backoff_waits) == 2
    assert backoff_waits[1] > backoff_waits[0]


def test_backoff_waits_are_1_2_4_8_16_seconds():
    responses = [_rate_limited()] * _MAX_RETRIES + [_ok(_INSTANT_JSON)]
    with patch("lib.scryfall.requests.get", side_effect=responses), \
         patch("lib.scryfall.time.sleep") as mock_sleep:
        fetch_card("Ember Sting")
    backoff_waits = [c.args[0] for c in mock_sleep.call_args_list if c.args[0] >= 1.0]
    assert backoff_waits == [1, 2, 4, 8, 16]


def test_429_retry_message_goes_to_stderr(capsys):
    responses = [_rate_limited(), _ok(_INSTANT_JSON)]
    with patch("lib.scryfall.requests.get", side_effect=responses), \
         patch("lib.scryfall.time.sleep"):
        fetch_card("Ember Sting")
    captured = capsys.readouterr()
    assert "429" in captured.err
    assert captured.out == ""
