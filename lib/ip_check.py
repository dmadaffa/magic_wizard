"""Find real Magic card names in repo files (card content is third-party IP).

The name list is Scryfall's /catalog/card-names, saved to data/card_names.json
(git-ignored) and refreshed when older than NAMES_MAX_AGE. Offline, it falls back
to the names in the local card cache.

Matching is case-sensitive and whole-phrase: the text is split into word tokens and
every run of 1..max_words tokens is looked up in a set, so the cost is per token,
not per known name.
"""

import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
NAMES_PATH = ROOT / "data" / "card_names.json"
CACHE_PATH = ROOT / "data" / "card_cache.jsonl"
ALLOWLIST_PATH = ROOT / "lib" / "ip_allowlist.txt"
NAMES_MAX_AGE = 30 * 24 * 3600  # seconds; new sets come out every few months

# Files allowed to contain real names: they are not prose.
EXEMPT_FILES = frozenset({"uv.lock", "lib/ip_allowlist.txt"})

# Apostrophes and hyphens only inside a word, so 'Name' in quotes still matches Name.
_TOKEN_RE = re.compile(r"\w+(?:['\-]\w+)*")


def _expand(names) -> set[str]:
    """Full names plus each face of a multi-face name ("A // B" -> A, B)."""
    out = set()
    for name in names:
        out.add(name)
        out.update(part.strip() for part in name.split(" // "))
    return out


def _cached_names(cache_path: Path) -> set[str]:
    if not cache_path.exists():
        return set()
    names = set()
    with open(cache_path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                card = json.loads(line)["scryfall"]
                names.add(card["name"])
                names.update(face["name"] for face in card.get("card_faces", []))
    return names


def load_names(
    refresh: bool = False,
    names_path: Path = NAMES_PATH,
    cache_path: Path = CACHE_PATH,
    fetch=None,
) -> set[str]:
    """Known card names; downloads the catalog if missing, stale or refresh=True."""
    stale = not names_path.exists() or time.time() - names_path.stat().st_mtime > NAMES_MAX_AGE
    if refresh or stale:
        if fetch is None:
            from lib.scryfall import fetch_card_names as fetch
        try:
            names = fetch()
            names_path.parent.mkdir(parents=True, exist_ok=True)
            names_path.write_text(json.dumps(names, ensure_ascii=False), encoding="utf-8")
        except Exception as e:  # noqa: BLE001 - offline, Scryfall down, ... (never block)
            print(f"[ip-check] could not download card names ({e})", file=sys.stderr)
    if names_path.exists():
        return _expand(json.loads(names_path.read_text(encoding="utf-8")))
    print("[ip-check] WARNING: no name catalog, using local card cache only", file=sys.stderr)
    return _expand(_cached_names(cache_path))


def load_allowlist(path: Path = ALLOWLIST_PATH) -> set[str]:
    if not path.exists():
        return set()
    lines = (line.split("#", 1)[0].strip() for line in path.read_text(encoding="utf-8").splitlines())
    return {line for line in lines if line}


def find_names(text: str, names: set[str], max_words: int) -> list[tuple[int, str]]:
    """(line number, name) for every known name appearing as a whole phrase."""
    hits = []
    for lineno, line in enumerate(text.splitlines(), 1):
        spans = [m.span() for m in _TOKEN_RE.finditer(line)]
        for i, (start, _) in enumerate(spans):
            for j in range(i, min(i + max_words, len(spans))):
                phrase = line[start:spans[j][1]]
                if phrase in names:
                    hits.append((lineno, phrase))
    return hits


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=True
    ).stdout


def _blob_text(*git_args: str) -> str | None:
    """Output of a git command that prints a blob, as text; None if it isn't UTF-8.

    Reads bytes and decodes here: text=True decodes in a reader thread on Windows,
    where a binary blob's error is printed instead of raised."""
    raw = subprocess.run(["git", *git_args], cwd=ROOT, capture_output=True, check=True).stdout
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


def tracked_files(staged: bool) -> list[tuple[str, str]]:
    """(path, content) for tracked and untracked, non-ignored files, or for the staged
    version of changed files."""
    if staged:
        paths = _git("diff", "--cached", "--name-only", "--diff-filter=ACMR").splitlines()
    else:
        paths = _git("ls-files", "--cached", "--others", "--exclude-standard").splitlines()
    out = []
    for path in paths:
        if path in EXEMPT_FILES:
            continue
        try:
            if staged:
                content = _blob_text("show", f":{path}")
            else:
                content = (ROOT / path).read_text(encoding="utf-8")
        except (UnicodeDecodeError, subprocess.CalledProcessError, OSError):
            continue  # binary or unreadable
        if content is None:
            continue  # binary
        out.append((path, content))
    return out


def history_files() -> list[tuple[str, str]]:
    """(label, content) for every blob reachable from any ref and every commit message.

    A blob is labelled "<path>@<short blob sha>" (trace it with `git log --find-object`),
    a commit message "commit <short sha>". A blob seen under several paths is scanned
    once, under its first path; exempt paths are skipped."""
    out = []
    seen = set()
    for line in _git("rev-list", "--objects", "--all").splitlines():
        sha, _, path = line.partition(" ")
        if not path or path in EXEMPT_FILES or sha in seen:
            continue
        seen.add(sha)
        try:
            content = _blob_text("cat-file", "blob", sha)
        except subprocess.CalledProcessError:
            continue  # tree object
        if content is None:
            continue  # binary
        out.append((f"{path}@{sha[:7]}", content))
    for entry in _git("log", "--all", "--format=%x01%H%x02%B").split("\x01")[1:]:
        sha, _, message = entry.partition("\x02")
        out.append((f"commit {sha[:7]}", message))
    return out


def check(files: list[tuple[str, str]], names: set[str], allowlist: set[str]) -> list[tuple[str, int, str]]:
    names = names - allowlist
    max_words = max((len(_TOKEN_RE.findall(n)) for n in names), default=1)
    return [
        (path, lineno, name)
        for path, content in files
        for lineno, name in find_names(content, names, max_words)
    ]
