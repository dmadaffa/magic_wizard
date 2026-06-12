from lib.deck_parser import parse, unique_names


def test_parses_card_quantities():
    deck = parse("4 Cinder Dart\n2 Island")
    assert deck["main"] == [{"qty": 4, "name": "Cinder Dart"}, {"qty": 2, "name": "Island"}]


def test_sideboard_via_comment_marker():
    deck = parse("4 Cinder Dart\n// Sideboard\n2 Gravel Warden")
    assert len(deck["main"]) == 1
    assert deck["side"] == [{"qty": 2, "name": "Gravel Warden"}]


def test_sideboard_via_blank_line():
    deck = parse("4 Cinder Dart\n\n2 Gravel Warden")
    assert deck["side"][0]["name"] == "Gravel Warden"
    assert deck["main"][0]["name"] == "Cinder Dart"


def test_sideboard_via_sb_prefix():
    deck = parse("4 Cinder Dart\nSB: 2 Gravel Warden")
    assert deck["side"][0]["name"] == "Gravel Warden"


def test_comments_not_in_sideboard_are_ignored():
    deck = parse("// Izzet Delver\n4 Cinder Dart")
    assert len(deck["main"]) == 1
    assert deck["side"] == []


def test_accepts_quantity_with_x_suffix():
    deck = parse("4x Cinder Dart")
    assert deck["main"][0] == {"qty": 4, "name": "Cinder Dart"}


def test_empty_input_returns_empty_deck():
    deck = parse("")
    assert deck["main"] == [] and deck["side"] == []


def test_format_detected_from_title_comment():
    deck = parse("// Izzet Delver — Modern\n4 Cinder Dart")
    assert deck["format"] == "Modern"


def test_format_is_none_when_comment_has_no_format_keyword():
    deck = parse("// Izzet Delver\n4 Cinder Dart")
    assert deck["format"] is None


def test_format_is_none_when_deck_has_no_comments():
    deck = parse("4 Cinder Dart")
    assert deck["format"] is None


def test_format_is_title_cased_regardless_of_input_case():
    deck = parse("// izzet MODERN delver\n4 Cinder Dart")
    assert deck["format"] == "Modern"


def test_format_not_detected_from_comment_after_cards_start():
    # Format must come from the deck header, not stray comments mid-list
    deck = parse("4 Cinder Dart\n// Modern\n4 Island")
    assert deck["format"] is None


def test_unique_names_deduplicates_across_main_and_side():
    text = "4 Cinder Dart\n2 Cinder Dart\n// Sideboard\n2 Cinder Dart"
    names = unique_names(parse(text))
    assert names == ["Cinder Dart"]


def test_unique_names_includes_both_main_and_side():
    text = "4 Cinder Dart\n// Sideboard\n2 Gravel Warden"
    names = unique_names(parse(text))
    assert "Cinder Dart" in names
    assert "Gravel Warden" in names
