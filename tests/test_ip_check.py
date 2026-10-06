import json
import os
import subprocess
import time

from lib import ip_check
from lib.ip_check import check, find_names, load_allowlist, load_names
from scripts import check_ip

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


def _git(repo, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
                          cwd=repo, check=True, capture_output=True, text=True).stdout.strip()


def _repo(tmp_path, monkeypatch):
    """A temp git repo with one committed clean file; lib.ip_check is pointed at it."""
    _git(tmp_path, "init")
    (tmp_path / "clean.txt").write_text("nothing here\n", encoding="utf-8")
    _git(tmp_path, "add", "clean.txt")
    _git(tmp_path, "commit", "-m", "init")
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


def _history_repo(tmp_path, monkeypatch):
    """Repo whose old commit has a name in a blob and another in a commit message;
    the current tree is clean."""
    _git(tmp_path, "init")
    (tmp_path / "notes.txt").write_text("ok\nsee Thornquill\n", encoding="utf-8")
    _git(tmp_path, "add", "notes.txt")
    _git(tmp_path, "commit", "-m", "add notes")
    (tmp_path / "notes.txt").write_text("ok\n", encoding="utf-8")
    _git(tmp_path, "commit", "-am", "mention Vexmoor Hound in the message")
    monkeypatch.setattr(ip_check, "ROOT", tmp_path)
    return tmp_path


def test_history_scan_finds_names_only_in_old_blobs_and_messages(tmp_path, monkeypatch):
    _history_repo(tmp_path, monkeypatch)
    assert check(ip_check.tracked_files(staged=False), _NAMES, set()) == []
    hits = check(ip_check.history_files(), _NAMES, set())
    labels = sorted((path.split("@")[0].split(" ")[0], lineno, name) for path, lineno, name in hits)
    assert labels == [("commit", 1, "Vexmoor Hound"), ("notes.txt", 2, "Thornquill")]


def test_history_hits_are_labelled_with_short_blob_or_commit_sha(tmp_path, monkeypatch):
    repo = _history_repo(tmp_path, monkeypatch)
    blob = _git(repo, "rev-parse", "HEAD~1:notes.txt")
    head = _git(repo, "rev-parse", "HEAD")
    paths = {path for path, _, _ in check(ip_check.history_files(), _NAMES, set())}
    assert paths == {f"notes.txt@{blob[:7]}", f"commit {head[:7]}"}


def test_history_scan_skips_exempt_files(tmp_path, monkeypatch):
    repo = _history_repo(tmp_path, monkeypatch)
    (repo / "uv.lock").write_text("Thornquill\n", encoding="utf-8")
    _git(repo, "add", "uv.lock")
    _git(repo, "commit", "-m", "lock")
    assert not [p for p, _, _ in check(ip_check.history_files(), _NAMES, set())
                if p.startswith("uv.lock")]


def test_history_scan_skips_binary_blobs_and_still_finds_names(tmp_path, monkeypatch):
    repo = _history_repo(tmp_path, monkeypatch)
    (repo / "image.bin").write_bytes(b"PNG\xff\xfe\x00\x80 Thornquill")
    _git(repo, "add", "image.bin")
    _git(repo, "commit", "-m", "binary")
    paths = {path.split("@")[0].split(" ")[0] for path, _, _ in check(ip_check.history_files(), _NAMES, set())}
    assert paths == {"notes.txt", "commit"}


def test_history_flag_exits_1_and_reports_hits(tmp_path, monkeypatch, capsys):
    _history_repo(tmp_path, monkeypatch)
    monkeypatch.setattr(check_ip, "load_names", lambda refresh=False: _NAMES)
    monkeypatch.setattr(check_ip, "load_allowlist", lambda: set())
    assert check_ip.main(["--history"]) == 1
    err = capsys.readouterr().err
    assert "notes.txt@" in err
    assert check_ip.main([]) == 0


def test_history_flag_honours_allowlist(tmp_path, monkeypatch, capsys):
    _history_repo(tmp_path, monkeypatch)
    monkeypatch.setattr(check_ip, "load_names", lambda refresh=False: _NAMES)
    monkeypatch.setattr(check_ip, "load_allowlist", lambda: {"Thornquill"})
    assert check_ip.main(["--history"]) == 1
    err = capsys.readouterr().err
    assert "Vexmoor Hound" in err
    assert "Thornquill" not in err


def test_claude_md_is_scanned_like_any_other_file(tmp_path, monkeypatch):
    repo = _repo(tmp_path, monkeypatch)
    (repo / "CLAUDE.md").write_text("4 Thornquill\n", encoding="utf-8")
    assert check(ip_check.tracked_files(staged=False), _NAMES, set()) == [("CLAUDE.md", 1, "Thornquill")]
