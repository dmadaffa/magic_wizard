import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "scryfall"


def load_scryfall(name: str) -> dict:
    """A real /cards/named response saved in tests/fixtures/scryfall/<name>.json."""
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture
def scryfall():
    return load_scryfall
