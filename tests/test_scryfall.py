from unittest.mock import patch, Mock, call
import pytest
import requests
from lib.scryfall import fetch_card, CardNotFoundError, _MAX_RETRIES

_BOLT_JSON = {
    "name": "Cinder Dart",
    "mana_cost": "{R}",
    "cmc": 1.0,
    "type_line": "Instant",
    "colors": ["R"],
    "color_identity": ["R"],
    "oracle_text": "Cinder Dart deals 3 damage to any target.",
    "power": None,
    "toughness": None,
    "loyalty": None,
    "legalities": {
        "standard": "not_legal",
        "modern": "legal",
        "pioneer": "not_legal",
        "legacy": "legal",
        "commander": "legal",
    },
}

_DFC_JSON = {
    "name": "Tidewatch Apprentice // Tidewatch Horror",
    "mana_cost": "",
    "cmc": 1.0,
    "type_line": "Creature",
    "colors": ["U"],
    "color_identity": ["U"],
    "legalities": {
        "standard": "not_legal",
        "modern": "legal",
        "pioneer": "not_legal",
        "legacy": "legal",
        "commander": "legal",
    },
    "card_faces": [
        {"name": "Tidewatch Apprentice", "mana_cost": "{U}", "oracle_text": "At the beginning..."},
        {"name": "Tidewatch Horror", "mana_cost": "", "oracle_text": "Flying"},
    ],
}


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


def test_returns_card_fields():
    with patch("lib.scryfall.requests.get", return_value=_ok(_BOLT_JSON)):
        result = fetch_card("Cinder Dart")
    assert result["name"] == "Cinder Dart"
    assert result["mana_cost"] == "{R}"
    assert result["type_line"] == "Instant"


def test_colors_are_pipe_joined():
    with patch("lib.scryfall.requests.get", return_value=_ok(_BOLT_JSON)):
        result = fetch_card("Cinder Dart")
    assert result["colors"] == "R"
    assert result["color_identity"] == "R"


def test_format_legality_fields_present():
    with patch("lib.scryfall.requests.get", return_value=_ok(_BOLT_JSON)):
        result = fetch_card("Cinder Dart")
    assert result["legal_modern"] == "legal"
    assert result["legal_standard"] == "not_legal"
    assert result["legal_commander"] == "legal"


def test_raises_card_not_found_on_404():
    with patch("lib.scryfall.requests.get", return_value=_not_found()):
        with pytest.raises(CardNotFoundError):
            fetch_card("Fake Card That Does Not Exist")


def test_double_faced_card_uses_front_face_mana_cost():
    with patch("lib.scryfall.requests.get", return_value=_ok(_DFC_JSON)):
        result = fetch_card("Tidewatch Apprentice")
    assert result["mana_cost"] == "{U}"


def test_double_faced_card_uses_front_face_oracle_text():
    with patch("lib.scryfall.requests.get", return_value=_ok(_DFC_JSON)):
        result = fetch_card("Tidewatch Apprentice")
    assert result["oracle_text"] == "At the beginning..."


def _rate_limited():
    m = Mock()
    m.status_code = 429
    return m


def test_retries_on_429_then_succeeds():
    responses = [_rate_limited(), _ok(_BOLT_JSON)]
    with patch("lib.scryfall.requests.get", side_effect=responses) as mock_get, \
         patch("lib.scryfall.time.sleep"):
        result = fetch_card("Cinder Dart")
    assert result["name"] == "Cinder Dart"
    assert mock_get.call_count == 2


def test_retries_exhaust_max_retries_then_raises():
    # All attempts return 429 — the final call also 429, raise_for_status blows up
    rate_limited_responses = [_rate_limited()] * (_MAX_RETRIES + 1)
    last = _rate_limited()
    last.raise_for_status.side_effect = requests.HTTPError("429")
    responses = rate_limited_responses[:-1] + [last]
    with patch("lib.scryfall.requests.get", side_effect=responses), \
         patch("lib.scryfall.time.sleep"):
        with pytest.raises(requests.HTTPError):
            fetch_card("Cinder Dart")


def test_sleeps_between_every_request():
    with patch("lib.scryfall.requests.get", return_value=_ok(_BOLT_JSON)) as mock_get, \
         patch("lib.scryfall.time.sleep") as mock_sleep:
        fetch_card("Cinder Dart")
    # At minimum one rate-limit sleep must occur before the successful request
    assert mock_sleep.call_count >= 1
    assert mock_get.call_count == 1


def test_backoff_increases_with_each_retry():
    responses = [_rate_limited(), _rate_limited(), _ok(_BOLT_JSON)]
    with patch("lib.scryfall.requests.get", side_effect=responses), \
         patch("lib.scryfall.time.sleep") as mock_sleep:
        fetch_card("Cinder Dart")
    sleep_args = [c.args[0] for c in mock_sleep.call_args_list]
    # Extract the backoff waits (values >= 1.0 — rate-limit sleeps are 0.55)
    backoff_waits = [s for s in sleep_args if s >= 1.0]
    assert len(backoff_waits) == 2
    assert backoff_waits[1] > backoff_waits[0]
