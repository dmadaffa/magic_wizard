"""Fail if repo files contain real Magic card names.

Usage:
    uv run python scripts/check_ip.py            # all tracked and untracked, non-ignored files
    uv run python scripts/check_ip.py --staged   # staged changes (pre-commit hook)
    uv run python scripts/check_ip.py --refresh  # re-download the name catalog first

Names that are also plain words go in lib/ip_allowlist.txt. CLAUDE.md is exempt.
Exit code 0 if clean, 1 if any name was found.
"""

import argparse
import sys
import time
from pathlib import Path

# Allow running as a script from the project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.ip_check import check, load_allowlist, load_names, tracked_files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--staged", action="store_true", help="check staged changes only")
    parser.add_argument("--refresh", action="store_true", help="re-download the card name catalog")
    args = parser.parse_args(argv)

    start = time.perf_counter()
    names = load_names(refresh=args.refresh)
    files = tracked_files(staged=args.staged)
    hits = check(files, names, load_allowlist())
    elapsed = time.perf_counter() - start

    for path, lineno, name in hits:
        print(f"{path}:{lineno}: real card name {name!r}", file=sys.stderr)
    print(
        f"[ip-check] {len(files)} files, {len(names)} names, {len(hits)} hits in {elapsed:.2f}s",
        file=sys.stderr,
    )
    if hits:
        print("[ip-check] replace them with invented names, or add plain words to lib/ip_allowlist.txt",
              file=sys.stderr)
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
