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


def test_unique_names_deduplicates_across_main_and_side():
    text = "4 Emberquill Volley\n2 Emberquill Volley\n// Sideboard\n2 Emberquill Volley"
    names = unique_names(parse(text))
    assert names == ["Emberquill Volley"]


def test_unique_names_includes_both_main_and_side():
    text = "4 Emberquill Volley\n// Sideboard\n2 Rustmoor Reliquary"
    names = unique_names(parse(text))
    assert "Emberquill Volley" in names
    assert "Rustmoor Reliquary" in names
