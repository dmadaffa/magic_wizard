from unittest.mock import patch, Mock
import pytest
import requests
from lib.scryfall import fetch_card, CardNotFoundError

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
