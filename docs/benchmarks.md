# Benchmarks

Numbers used to judge whether a feature is viable. Re-measure when something
changes a lot (repo size, catalog size, matching logic), and compare against the
thresholds before deciding to keep, improve or drop the approach.

## IP check (`scripts/check_ip.py`)

Measured 2026-09-18 on Windows 11, Python 3.12, home connection.

### 1. Card name catalog: Scryfall `/catalog/card-names`

| Metric | Value |
|---|---|
| Requests | 1 (not paginated) |
| Names in the catalog | 35,336 |
| Names after splitting `A // B` into faces | 37,100 |
| Download time (3 runs) | 1.08 s / 1.40 s / 1.88 s, median 1.40 s |
| Size over the wire (gzip) | 243 KB |
| Decoded response body | 699 KB |
| Stored file `data/card_names.json` | 734 KB |
| Write to disk | 6 ms |
| Load from disk (`json.loads`) | 10 ms |
| Single-word names | 2,668 (source of false positives, see below) |
| Longest name | 25 words (one joke card); next longest 12 |

Refreshed when older than 30 days, so this cost is paid about once a month.

### 2. Validation

Repo at the time: 36 checkable tracked files, 120 KB, 3,601 lines.
Median of 10 runs, except where noted.

| Phase | Time |
|---|---|
| Load catalog + build name set | 16 ms |
| Read tracked files (working tree) | 20 ms |
| Scan (token n-grams, set lookups) | 33 ms |
| Total inside the script | 70–80 ms |
| Full CLI wall time, including `uv run` start-up (3 runs) | 265–278 ms |
| `--staged` mode: `git show` per changed file | ~20 ms per file (38 files: 765 ms) |
| Throughput, synthetic 9.4 MB file (3 runs) | 1.32 s, about 7 MB/s |

### 3. Accuracy on the first run

- 166 hits before an allowlist. 97 were ordinary words that are also card names
  (`When`, `Return`, `X`, keywords such as `Vigilance`) or plain words inside
  invented names. 26 words went into `lib/ip_allowlist.txt`.
- Writing this feature's own files (code + this doc) added 3 more
  (`Find`, `Python`, `Catalog`): about 1 new word per 100 lines of fresh prose.
- After the allowlist: 69 hits, all real card names. One of them was a fixture
  name we believed was invented.
- A unit test found that the first tokenizer missed names in single quotes
  (`'Name'`). It was fixed before these numbers were taken.

### Thresholds: when to revisit

- Pre-commit wall time over **1 s** for a normal commit: start one Python process
  instead of `uv run`, or read staged files with a single `git cat-file --batch`
  instead of one `git show` per file.
- Scan time growing faster than repo size: limit n-grams to 12 tokens (only one
  joke card is longer).
- The allowlist growing by more than a few words per month: stop blocking on
  single-word names and only warn about them. Multi-word names are the real IP risk.
- Catalog download failing or growing past a few MB: keep the local card cache
  fallback and warn, as the script already does.

## Saved analysis extras (`/analyze-deck --save`)

Measured 2026-10-13 on two manual `--save` runs. Counted from the saved `.md`:
"chat" is the Step 4 sections (the same text shown in chat), "extras" is
`## Replacements` to the end. Lines are non-empty lines; words are whitespace-split.

| Deck | Chat (lines / words) | Extras (lines / words) | Whole file (lines / words) | File / chat words | Correction rounds |
|---|---|---|---|---|---|
| 60-card Standard, 15-card sideboard | 25 / 404 | 46 / 332 | 75 / 750 | 1.86 | 1 (one new name not legal in Standard) |
| 40-card Limited, 16-card pool sideboard, format unknown | 26 / 458 | 56 / 351 | 86 / 823 | 1.80 | 1 (sideboard count off by one after a basic-land swap) |

The suggested deck list is about two thirds of the extras lines but only about a
third of their words. Extras add roughly 0.8x the chat's words in output tokens,
and only on `--save`.
The checks themselves add no LLM call: one parser run, one fetcher call and one
card view call per round.

### Thresholds: when to revisit

- Extras over **1.5x** the chat's words: drop the deck list from the `.md` and
  keep it only in `_suggested.txt`.
- Most runs needing 2 correction rounds, or ending with `Unverified:` for cards not
  found, illegal cards or wrong counts (not for `format unknown` or `no legality
  data`, which no check can fix): give the analysis step the candidate cards'
  legality up front instead of checking after.
