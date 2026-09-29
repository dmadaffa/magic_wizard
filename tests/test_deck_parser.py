import pytest

from lib.deck_parser import parse, unique_names


def test_parses_card_quantities():
    deck = parse("4 Emberquill Volley\n2 Island")
    assert deck["main"] == [{"qty": 4, "name": "Emberquill Volley"}, {"qty": 2, "name": "Island"}]


def test_sideboard_via_comment_marker():
    deck = parse("4 Emberquill Volley\n// Sideboard\n2 Rustmoor Reliquary")
    assert len(deck["main"]) == 1
    assert deck["side"] == [{"qty": 2, "name": "Rustmoor Reliquary"}]


def test_sideboard_via_blank_line():
    deck = parse("4 Emberquill Volley\n\n2 Rustmoor Reliquary")
    assert deck["side"][0]["name"] == "Rustmoor Reliquary"
    assert deck["main"][0]["name"] == "Emberquill Volley"


def test_sideboard_via_sb_prefix():
    deck = parse("4 Emberquill Volley\nSB: 2 Rustmoor Reliquary")
    assert deck["side"][0]["name"] == "Rustmoor Reliquary"


def test_comments_not_in_sideboard_are_ignored():
    deck = parse("// Izzet Delver\n4 Emberquill Volley")
    assert len(deck["main"]) == 1
    assert deck["side"] == []


def test_accepts_quantity_with_x_suffix():
    deck = parse("4x Emberquill Volley")
    assert deck["main"][0] == {"qty": 4, "name": "Emberquill Volley"}


def test_empty_input_returns_empty_deck():
    deck = parse("")
    assert deck["main"] == [] and deck["side"] == []


def test_format_detected_from_title_comment():
    deck = parse("// Izzet Delver — Modern\n4 Emberquill Volley")
    assert deck["format"] == "Modern"


def test_format_is_none_when_comment_has_no_format_keyword():
    deck = parse("// Izzet Delver\n4 Emberquill Volley")
    assert deck["format"] is None


def test_format_is_none_when_deck_has_no_comments():
    deck = parse("4 Emberquill Volley")
    assert deck["format"] is None


def test_format_is_title_cased_regardless_of_input_case():
    deck = parse("// izzet MODERN delver\n4 Emberquill Volley")
    assert deck["format"] == "Modern"


def test_format_not_detected_from_comment_after_cards_start():
    # Format must come from the deck header, not stray comments mid-list
    deck = parse("4 Emberquill Volley\n// Modern\n4 Island")
    assert deck["format"] is None


@pytest.mark.parametrize("text", [
    "// Premodern Zorbling\n4 Emberquill Volley",
    "// Nonstandard Tribal\n4 Emberquill Volley",
    "// Modernized Zorbling\n4 Emberquill Volley",
    "// Pre-Modern Zorbling\n4 Emberquill Volley",
    "// Non-Standard Tribal\n4 Emberquill Volley",
], ids=["premodern", "nonstandard", "modernized", "pre-modern", "non-standard"])
def test_format_requires_whole_word_match(text):  # reproduces
    assert parse(text)["format"] is None


def test_format_followed_by_hyphen_still_matches():  # guard: rejecting hyphens after the format too
    assert parse("// Pauper-legal Zorbling\n4 Emberquill Volley")["format"] == "Pauper"


@pytest.mark.parametrize("text, expected", [
    ("standard Deck\n4 Emberquill Volley", "Standard"),
    ("Deck\n// Pioneer\n4 Emberquill Volley", "Pioneer"),
    ("Deck\n\n// Pioneer\n4 Emberquill Volley", "Pioneer"),
    ("// Izzet Delver\nModern Deck\n4 Emberquill Volley", "Modern"),
], ids=["plain-header", "comment-after-deck-header", "blank-between-header-lines", "later-header-line"])
def test_format_detected_from_plain_header_line(text, expected):  # reproduces
    assert parse(text)["format"] == expected


@pytest.mark.parametrize("text, expected", [
    ("// Modern or Legacy\n4 Emberquill Volley", "Modern"),
    ("// Legacy or Modern\n4 Emberquill Volley", "Legacy"),
    ("// Legacy\n// Modern\n4 Emberquill Volley", "Legacy"),
], ids=["first-in-line", "first-in-line-swapped", "first-line-wins"])
def test_format_first_in_header_text_wins(text, expected):  # decision: earliest format in text wins
    assert parse(text)["format"] == expected


def test_bare_section_header_does_not_set_format():  # guard: running the format regex on bare header lines
    deck = parse("Commander\n1 Zorbling Prime\n\nDeck\n4 Emberquill Volley")
    assert deck["format"] is None


@pytest.mark.parametrize("text, expected", [
    ("Commander\n// Pioneer\n1 Zorbling Prime", "Pioneer"),
    ("COMMANDER\n// Legacy\n4 Emberquill Volley", "Legacy"),
], ids=["header-then-title", "case-insensitive"])
def test_bare_section_header_does_not_stop_header_scan(text, expected):  # decision: bare headers are skipped, scan continues
    assert parse(text)["format"] == expected


def test_unique_names_deduplicates_across_main_and_side():
    text = "4 Emberquill Volley\n2 Emberquill Volley\n// Sideboard\n2 Emberquill Volley"
    names = unique_names(parse(text))
    assert names == ["Emberquill Volley"]


def test_unique_names_includes_both_main_and_side():
    text = "4 Emberquill Volley\n// Sideboard\n2 Rustmoor Reliquary"
    names = unique_names(parse(text))
    assert "Emberquill Volley" in names
    assert "Rustmoor Reliquary" in names


# Bug #2: blank lines only start the sideboard when the file has no explicit marker

def test_blank_lines_group_main_deck_when_sideboard_header_exists():
    text = "4 Glimmerfen Scout\n4 Emberquill Volley\n\n20 Island\n\nSideboard\n2 Rustmoor Reliquary"
    deck = parse(text)
    assert [e["name"] for e in deck["main"]] == ["Glimmerfen Scout", "Emberquill Volley", "Island"]
    assert deck["side"] == [{"qty": 2, "name": "Rustmoor Reliquary"}]


def test_blank_lines_group_main_deck_when_comment_marker_exists():
    text = "4 Glimmerfen Scout\n\n20 Island\n// Sideboard\n2 Rustmoor Reliquary"
    deck = parse(text)
    assert [e["name"] for e in deck["main"]] == ["Glimmerfen Scout", "Island"]
    assert [e["name"] for e in deck["side"]] == ["Rustmoor Reliquary"]


def test_blank_lines_group_main_deck_when_sb_prefix_exists():
    text = "4 Glimmerfen Scout\n\n20 Island\nSB: 2 Rustmoor Reliquary"
    deck = parse(text)
    assert [e["name"] for e in deck["main"]] == ["Glimmerfen Scout", "Island"]
    assert [e["name"] for e in deck["side"]] == ["Rustmoor Reliquary"]


def test_blank_lines_after_deck_header_stay_in_main():
    text = "Deck\n4 Glimmerfen Scout\n\n20 Island\n"
    deck = parse(text)
    assert [e["name"] for e in deck["main"]] == ["Glimmerfen Scout", "Island"]
    assert deck["side"] == []


def test_trailing_blank_line_after_sideboard_is_harmless():
    deck = parse("Deck\n4 Glimmerfen Scout\n\nSideboard\n2 Rustmoor Reliquary\n\n")
    assert [e["name"] for e in deck["main"]] == ["Glimmerfen Scout"]
    assert [e["name"] for e in deck["side"]] == ["Rustmoor Reliquary"]


# Bug #3: Arena section headers (Commander, Companion, Deck, Sideboard)

def test_arena_commander_export():
    text = "Commander\n1 Vessra, Tide Regent\n\nDeck\n1 Brass Orrery\n1 Island"
    deck = parse(text)
    assert deck["commander"] == [{"qty": 1, "name": "Vessra, Tide Regent"}]
    assert [e["name"] for e in deck["main"]] == ["Brass Orrery", "Island"]
    assert deck["side"] == []


def test_arena_export_with_companion_and_sideboard():
    text = (
        "Companion\n1 Mossback Warden\n\n"
        "Deck\n4 Glimmerfen Scout\n\n"
        "Sideboard\n1 Mossback Warden\n2 Rustmoor Reliquary\n"
    )
    deck = parse(text)
    assert deck["companion"] == [{"qty": 1, "name": "Mossback Warden"}]
    assert [e["name"] for e in deck["main"]] == ["Glimmerfen Scout"]
    assert [e["name"] for e in deck["side"]] == ["Mossback Warden", "Rustmoor Reliquary"]


def test_commander_section_ends_at_blank_line_without_deck_header():
    deck = parse("Commander\n1 Vessra, Tide Regent\n\n1 Brass Orrery\n1 Island")
    assert [e["name"] for e in deck["commander"]] == ["Vessra, Tide Regent"]
    assert [e["name"] for e in deck["main"]] == ["Brass Orrery", "Island"]
    assert deck["side"] == []


def test_section_headers_are_case_insensitive():
    deck = parse("COMMANDER\n1 Vessra, Tide Regent\n\ndeck\n1 Island")
    assert [e["name"] for e in deck["commander"]] == ["Vessra, Tide Regent"]
    assert [e["name"] for e in deck["main"]] == ["Island"]


def test_decks_without_commander_have_empty_commander_and_companion():
    deck = parse("4 Glimmerfen Scout")
    assert deck["commander"] == [] and deck["companion"] == []


def test_unique_names_includes_commander_and_companion():
    text = "Commander\n1 Vessra, Tide Regent\nCompanion\n1 Mossback Warden\nDeck\n1 Island"
    assert unique_names(parse(text)) == ["Island", "Mossback Warden", "Vessra, Tide Regent"]


def _only_name(line):
    return parse(line)["main"][0]["name"]


@pytest.mark.parametrize("line", [
    "4 Grumbling Toad (ABC) 123",
    "4 Grumbling Toad (ABC) 276p",
    "4 Grumbling Toad (ABC) 12a",
    "4 Grumbling Toad (ABC) 12★",
    "4 Grumbling Toad (PLST) 12",
    "4 Grumbling Toad (PLSTX) 12",
    "4 Grumbling Toad (PLST) ABC-123",
    "4 Grumbling Toad (PLST) ABC-123a",
    "4x Grumbling Toad (ABC) 276p",
])
def test_strips_set_and_collector_number_variants(line):
    assert _only_name(line) == "Grumbling Toad"


@pytest.mark.parametrize("name", [
    "Grumbling Toad (Prime)",
    # Intentional choice: Arena exports uppercase set codes, so a lowercase "(abc)" is
    # treated as part of the name rather than a set code.
    "Grumbling Toad (abc) 12",
    "Grumbling Toad 2",
    "Grumbling Toad (ABC)",
])
def test_keeps_parentheses_and_digits_that_are_not_a_set_suffix(name):
    assert _only_name(f"1 {name}") == name


def test_keeps_arena_rebalanced_prefix():
    # Scryfall names rebalanced cards with the "A-" prefix, so it must survive parsing.
    assert _only_name("2 A-Grumbling Toad (ABC) 12") == "A-Grumbling Toad"
