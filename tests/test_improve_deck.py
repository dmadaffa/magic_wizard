import pytest
import requests

from agents.improve_deck import main
from lib.scryfall import trim_card


def _results(scryfall):
    return [trim_card(scryfall("instant")), trim_card(scryfall("token_maker")),
            trim_card(scryfall("modal_dfc_transform"))]


def _search(results, calls=None):
    def search(query, order="edhrec", pages=1):
        if calls is not None:
            calls.append((query, pages))
        return results
    return search


def test_prints_compact_lines_and_logs_every_name(scryfall, tmp_path, capsys):
    results = _results(scryfall)
    log = tmp_path / "p1.log"
    assert main(["f:standard o:damage", "--log", str(log)], search=_search(results)) == 0
    out = capsys.readouterr().out.splitlines()
    assert len(out) == 3
    assert out[0].startswith("Ember Sting | {R} | Instant | ")
    assert "deals 2 damage to any target." in out[0]
    assert log.read_text(encoding="utf-8").splitlines() == [c["name"] for c in results]


def test_creature_line_has_power_toughness_and_multi_face_line_joins_faces(scryfall, capsys):
    main(["q"], search=_search(_results(scryfall)))
    out = capsys.readouterr().out.splitlines()
    assert "| Creature — Goblin Shaman | 1/1 | " in out[1]
    assert out[2].startswith("Mara Voss // Mara the Unbroken | ")
    assert "Reach, trample / Whenever this creature attacks" in out[2]
    assert "Activate only as a sorcery. // Reach, trample" in out[2]


def test_multi_face_line_keeps_the_boundary_when_a_face_has_no_text(scryfall, capsys):
    card = trim_card(scryfall("modal_dfc_transform"))
    card["card_faces"][0]["oracle_text"] = ""
    main(["q"], search=_search([card]))
    assert "| (no text) // Reach, trample / " in capsys.readouterr().out


@pytest.mark.parametrize("args", [
    [],
    ["q", "--limit", "-1"],
    ["q", "--pages", "0"],
    ["q", "--limit", "x"],
    ["q", "--log"],
    ["q", "--unknown"],
])
def test_bad_arguments_are_a_usage_error(args, capsys):
    assert main(args, search=_search([])) == 1
    assert "Usage" in capsys.readouterr().err


def test_bad_query_prints_scryfalls_details_and_fails(capsys):
    class Resp:
        status_code = 400

        def json(self):
            return {"details": "unknown keyword zzz"}

    def search(query, order="edhrec", pages=1):
        raise requests.HTTPError("400", response=Resp())

    assert main(["zzz:1"], search=search) == 1
    cap = capsys.readouterr()
    assert cap.err.strip() == "Scryfall rejected the query: unknown keyword zzz"
    assert cap.out == ""


def test_other_http_error_says_status_not_bad_query(capsys):
    class Resp:
        status_code = 503

        def json(self):
            raise ValueError("not json")

    def search(query, order="edhrec", pages=1):
        raise requests.HTTPError("503 unavailable", response=Resp())

    assert main(["q"], search=search) == 1
    err = capsys.readouterr().err.strip()
    assert err == "Scryfall error 503: 503 unavailable"


def test_limit_limits_only_the_printing(scryfall, tmp_path, capsys):
    results = _results(scryfall)
    log = tmp_path / "p1.log"
    main(["q", "--limit", "1", "--log", str(log)], search=_search(results))
    assert len(capsys.readouterr().out.splitlines()) == 1
    assert len(log.read_text(encoding="utf-8").splitlines()) == 3


def test_log_is_appended_across_searches(scryfall, tmp_path):
    results = _results(scryfall)
    log = tmp_path / "p1.log"
    main(["a", "--log", str(log)], search=_search(results))
    main(["b", "--log", str(log)], search=_search(results[:1]))
    assert len(log.read_text(encoding="utf-8").splitlines()) == 4


def test_pages_is_passed_to_the_search(scryfall):
    calls = []
    main(["q", "--pages", "2"], search=_search(_results(scryfall), calls))
    assert calls == [("q", 2)]


def test_long_oracle_text_is_truncated(scryfall, capsys):
    card = trim_card(scryfall("instant"))
    card["oracle_text"] = "word " * 200
    main(["q"], search=_search([card]))
    line = capsys.readouterr().out.splitlines()[0]
    assert len(line) < 260
    assert line.endswith("...")


def test_no_results_prints_a_marker_and_logs_nothing(tmp_path, capsys):
    log = tmp_path / "p1.log"
    assert main(["q", "--log", str(log)], search=_search([])) == 0
    assert capsys.readouterr().out.strip() == "No results."
    assert not log.exists() or log.read_text(encoding="utf-8") == ""
