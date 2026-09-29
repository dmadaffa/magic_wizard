"""CLI contract of lib/deck_parser.py: stdout is the JSON document, stderr the summary."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "lib" / "deck_parser.py"

DECK = """// Modern Zorbling Tempo
4 Quillfox Scout
2 Mistvale Drifter

// Sideboard
1 Thornbark Hermit
"""


def run_cli(tmp_path, *extra, deck=DECK):
    path = tmp_path / "deck.txt"
    path.write_text(deck, encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(path), *extra],
        capture_output=True, text=True, encoding="utf-8", check=True,
    )


def test_stdout_is_exactly_the_json_document(tmp_path):  # reproduces; also guards the header format without an argument
    result = run_cli(tmp_path)
    deck = json.loads(result.stdout)
    assert deck["main"] == [
        {"qty": 4, "name": "Quillfox Scout"},
        {"qty": 2, "name": "Mistvale Drifter"},
    ]
    assert deck["side"] == [{"qty": 1, "name": "Thornbark Hermit"}]
    assert deck["format"] == "Modern"


def test_summary_goes_to_stderr(tmp_path):  # reproduces
    result = run_cli(tmp_path)
    assert "Main deck: 6 cards (2 unique)" in result.stderr
    assert "Sideboard: 1 cards (1 unique)" in result.stderr
    assert "Format: Modern" in result.stderr


@pytest.mark.parametrize("args, expected", [
    (["pioneer"], "Pioneer"),  # decision: a CLI format beats the header format; fails at HEAD only on the JSON parse
    (["pauper", "commander"], "Pauper Commander"),  # reproduces: all remaining tokens form one format
])
def test_cli_format_argument_overrides_header_format(tmp_path, args, expected):
    result = run_cli(tmp_path, *args)
    assert json.loads(result.stdout)["format"] == expected
    assert f"Format: {expected}" in result.stderr


def test_format_is_null_when_unknown(tmp_path):  # guard: no header and no argument gives JSON null, not a missing key or a string; fails at HEAD only on the JSON parse
    result = run_cli(tmp_path, deck="4 Quillfox Scout\n")
    assert json.loads(result.stdout)["format"] is None
    assert "Format: unknown" in result.stderr
