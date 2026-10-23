from agents.deck_stats import main
from lib.cache import CardCache
from lib.card_model import from_scryfall
from lib.scryfall import trim_card
from lib.stats import deck_stats

# deck card name -> fixture file
FIXTURE_FOR = {
    "Ember Sting": "instant",
    "Cinder Flats": "land",
    "Murk Prism": "mana_rock",
    "Tidal Rite // Tidal Shore": "modal_dfc_land",
    "Hollow Engine": "x_spell",
    "Twin Ember": "hybrid",
    "Dawn Sentinel": "meld_part",
    "Quarry Brute // Rockslide": "adventure",
    "Blaze // Frost": "split",
}


def _run(tmp_path, scryfall, capsys, deck_text, cached=None):
    cache = CardCache(tmp_path / "cache.jsonl")
    for name, fixture in FIXTURE_FOR.items():
        if cached is None or name in cached:
            cache.put(name, trim_card(scryfall(fixture)))
    deck = tmp_path / "deck.txt"
    deck.write_text(deck_text, encoding="utf-8")
    code = main([str(deck)], cache=cache)
    captured = capsys.readouterr()
    return code, captured.out.splitlines(), captured.err


def _line(lines, prefix):
    matches = [ln for ln in lines if ln.startswith(prefix)]
    assert len(matches) == 1, f"{prefix!r} in {lines}"
    return matches[0]


def test_copies_land_excluded_and_five_plus_bucket(tmp_path, scryfall, capsys):
    code, out, _ = _run(
        tmp_path, scryfall, capsys,
        "4 Ember Sting\n2 Dawn Sentinel\n3 Cinder Flats\n",
    )
    assert code == 0
    assert _line(out, "Curve:") == "Curve: 0=0 1=4 2=0 3=0 4=0 5+=2"
    assert _line(out, "Average CMC:") == "Average CMC: 2.67 (6 non-land cards)"
    assert _line(out, "Lands:") == "Lands: 3"
    assert _line(out, "Sources:") == "Sources: W=0 U=0 B=0 R=3 G=0 C=0"


def test_mdfc_spell_land_is_in_curve_a_source_and_flexibility(tmp_path, scryfall, capsys):
    _, out, _ = _run(
        tmp_path, scryfall, capsys,
        "1 Tidal Rite // Tidal Shore\n2 Cinder Flats\n",
    )
    assert _line(out, "Curve:") == "Curve: 0=0 1=0 2=1 3=0 4=0 5+=0"
    assert _line(out, "Lands:") == "Lands: 2"
    assert _line(out, "Sources:") == "Sources: W=0 U=1 B=0 R=2 G=0 C=0"
    assert _line(out, "Flexible:") == "Flexible: Tidal Rite // Tidal Shore (Tidal Shore)"
    assert _line(out, "Nonland mana producers (not counted):").endswith(": none")


def test_adventure_counts_once_at_card_cmc_cheaper_half_is_flexibility(tmp_path, scryfall, capsys):
    _, out, _ = _run(tmp_path, scryfall, capsys, "2 Quarry Brute // Rockslide\n")
    assert _line(out, "Curve:") == "Curve: 0=0 1=0 2=0 3=0 4=2 5+=0"
    assert _line(out, "Flexible:") == "Flexible: Quarry Brute // Rockslide (Rockslide)"


def test_split_card_uses_combined_cmc(tmp_path, scryfall, capsys):
    _, out, _ = _run(tmp_path, scryfall, capsys, "1 Blaze // Frost\n")
    assert _line(out, "Curve:") == "Curve: 0=0 1=0 2=0 3=0 4=1 5+=0"


def test_x_spell_is_bucket_zero_and_flagged(tmp_path, scryfall, capsys):
    _, out, _ = _run(tmp_path, scryfall, capsys, "1 Hollow Engine\n1 Ember Sting\n")
    assert _line(out, "Curve:") == "Curve: 0=1 1=1 2=0 3=0 4=0 5+=0"
    assert _line(out, "X spells:") == "X spells: Hollow Engine"
    assert _line(out, "Flexible:") == "Flexible: none"


def test_hybrid_pip_counts_for_both_colors(tmp_path, scryfall, capsys):
    _, out, _ = _run(tmp_path, scryfall, capsys, "2 Twin Ember\n")
    assert _line(out, "Colors (spells/pips):") == "Colors (spells/pips): W=2/2 U=0/0 B=0/0 R=2/2 G=0/0"


def test_nonland_producer_is_listed_not_counted(tmp_path, scryfall, capsys):
    _, out, _ = _run(tmp_path, scryfall, capsys, "2 Murk Prism\n1 Cinder Flats\n")
    assert _line(out, "Sources:") == "Sources: W=0 U=0 B=0 R=1 G=0 C=0"
    assert _line(out, "Nonland mana producers (not counted):") == (
        "Nonland mana producers (not counted): Murk Prism"
    )
    assert _line(out, "Curve:") == "Curve: 0=0 1=0 2=2 3=0 4=0 5+=0"


def test_uncached_card_reported_and_rest_still_printed(tmp_path, scryfall, capsys):
    code, out, err = _run(
        tmp_path, scryfall, capsys,
        "4 Ember Sting\n2 Twin Ember\n",
        cached={"Ember Sting"},
    )
    assert code == 1
    assert "NOT CACHED: Twin Ember" in err
    assert _line(out, "Curve:") == "Curve: 0=0 1=4 2=0 3=0 4=0 5+=0"


def test_sideboard_is_ignored(tmp_path, scryfall, capsys):
    _, out, _ = _run(
        tmp_path, scryfall, capsys,
        "2 Ember Sting\n// Sideboard\n3 Dawn Sentinel\n",
    )
    assert _line(out, "Curve:") == "Curve: 0=0 1=2 2=0 3=0 4=0 5+=0"


def test_card_counts_once_per_color_but_pips_sum_over_faces(scryfall):
    card = from_scryfall(trim_card(scryfall("adventure")))  # {3}{R} + {1}{R}
    stats = deck_stats([(card, 2)])
    assert stats.color_spells["R"] == 2
    assert stats.color_pips["R"] == 4
    assert stats.color_spells["U"] == 0


def test_empty_deck_has_zero_average():
    assert deck_stats([]).average_cmc == 0
