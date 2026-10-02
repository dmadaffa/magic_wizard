import json
import os
import subprocess
import time

from lib import ip_check
from lib.ip_check import check, find_names, load_allowlist, load_names

# Invented names standing in for the Scryfall catalog.
_CATALOG = ["Glimmerwick Oracle", "Vexmoor Hound", "Thornquill", "Quenchfire // Emberwake",
            "Brassgrove, the Undying"]
_NAMES = {"Glimmerwick Oracle", "Vexmoor Hound", "Thornquill", "Quenchfire // Emberwake",
          "Quenchfire", "Emberwake", "Brassgrove, the Undying"}


def _hits(text):
    return [name for _, name in find_names(text, _NAMES, max_words=5)]


def test_finds_multi_word_name_with_line_number():
    assert find_names("first line\n4 Glimmerwick Oracle\n", _NAMES, 5) == [(2, "Glimmerwick Oracle")]


def test_finds_name_with_punctuation_inside():
    assert _hits('"Brassgrove, the Undying" is legendary') == ["Brassgrove, the Undying"]


def test_finds_full_split_name_and_each_face():
    assert _hits("1 Quenchfire // Emberwake") == ["Quenchfire", "Quenchfire // Emberwake", "Emberwake"]


def test_name_next_to_punctuation_is_found():
    assert _hits("cards = ['Thornquill', 'Vexmoor Hound']") == ["Thornquill", "Vexmoor Hound"]


def test_part_of_a_longer_word_is_not_a_match():
    assert _hits("Thornquills Glimmerwick_Oracle Vexmoor Hounds") == []


def test_match_is_case_sensitive():
    assert _hits("glimmerwick oracle, THORNQUILL") == []


def test_allowlisted_names_are_skipped():
    files = [("a.py", "Thornquill and Vexmoor Hound")]
    assert check(files, _NAMES, allowlist={"Thornquill"}) == [("a.py", 1, "Vexmoor Hound")]


def test_allowlist_ignores_comments_and_blanks(tmp_path):
    path = tmp_path / "allow.txt"
    path.write_text("# header\n\nThornquill  # a plain word\n", encoding="utf-8")
    assert load_allowlist(path) == {"Thornquill"}


def test_missing_catalog_is_downloaded_and_split_into_faces(tmp_path):
    names_path = tmp_path / "card_names.json"
    names = load_names(names_path=names_path, cache_path=tmp_path / "none.jsonl", fetch=lambda: _CATALOG)
    assert names == _NAMES
    assert json.loads(names_path.read_text(encoding="utf-8")) == _CATALOG


def test_fresh_catalog_is_not_downloaded_again(tmp_path):
    names_path = tmp_path / "card_names.json"
    names_path.write_text(json.dumps(["Thornquill"]), encoding="utf-8")

    def fail():
        raise AssertionError("should not fetch")

    assert load_names(names_path=names_path, fetch=fail) == {"Thornquill"}


def test_stale_catalog_is_refreshed(tmp_path):
    names_path = tmp_path / "card_names.json"
    names_path.write_text(json.dumps(["Thornquill"]), encoding="utf-8")
    old = time.time() - 31 * 24 * 3600
    os.utime(names_path, (old, old))
    assert "Vexmoor Hound" in load_names(names_path=names_path, fetch=lambda: _CATALOG)


def _repo(tmp_path, monkeypatch):
    """A temp git repo with one committed clean file; lib.ip_check is pointed at it."""
    def git(*args):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
                       cwd=tmp_path, check=True, capture_output=True)
    git("init")
    (tmp_path / "clean.txt").write_text("nothing here\n", encoding="utf-8")
    git("add", "clean.txt")
    git("commit", "-m", "init")
    monkeypatch.setattr(ip_check, "ROOT", tmp_path)
    return tmp_path


def test_whole_repo_check_reads_untracked_files(tmp_path, monkeypatch):
    repo = _repo(tmp_path, monkeypatch)
    (repo / "new.py").write_text("x = 'Thornquill'\n", encoding="utf-8")
    files = ip_check.tracked_files(staged=False)
    assert ("new.py", "x = 'Thornquill'\n") in files
    assert check(files, _NAMES, set()) == [("new.py", 1, "Thornquill")]


def test_whole_repo_check_skips_git_ignored_files(tmp_path, monkeypatch):
    repo = _repo(tmp_path, monkeypatch)
    (repo / ".gitignore").write_text("secret/\n", encoding="utf-8")
    (repo / "secret").mkdir()
    (repo / "secret" / "deck.txt").write_text("4 Thornquill\n", encoding="utf-8")
    paths = [p for p, _ in ip_check.tracked_files(staged=False)]
    assert "secret/deck.txt" not in paths
    assert "clean.txt" in paths


def test_offline_without_catalog_falls_back_to_card_cache(tmp_path, capsys):
    cache_path = tmp_path / "card_cache.jsonl"
    entry = {"name": "Quenchfire // Emberwake", "scryfall": {
        "name": "Quenchfire // Emberwake", "card_faces": [{"name": "Quenchfire"}, {"name": "Emberwake"}]}}
    cache_path.write_text(json.dumps(entry) + "\n", encoding="utf-8")

    def offline():
        raise OSError("no network")

    names = load_names(names_path=tmp_path / "card_names.json", cache_path=cache_path, fetch=offline)
    assert names == {"Quenchfire // Emberwake", "Quenchfire", "Emberwake"}
    assert "WARNING" in capsys.readouterr().err
