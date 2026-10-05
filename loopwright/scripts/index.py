"""Generate INDEX.md for a directory of task files, or print the next free id.

    python index.py <tasks-dir>              write <tasks-dir>/INDEX.md
    python index.py <tasks-dir> --next-id    print the next free 3-digit id

Task files are `<tasks-dir>/**/NNN-<slug>.md`: YAML-style front matter, then a
`# N. Title` heading. Only `key: value` lines and `[a, b]` lists are read, so
this needs nothing outside the standard library. Needs Python 3.10+
(`Path.write_text(newline=)`).

Exit codes: 0 ok, 1 invalid tasks (every problem is printed to stderr and
nothing is written), 2 bad usage or missing directory.
"""

import argparse
import re
import sys
from pathlib import Path

TYPES = ("bug", "task", "story")
MODES = ("auto", "human")
STATUSES = ("open", "in-progress", "done")
PRIORITIES = ("high", "medium", "low", "backlog")
FOLDERS = ("bugs", "features", "unrefined", "done")
REQUIRED = {"type": TYPES, "mode": MODES, "status": STATUSES}
OPTIONAL = ("priority", "depends", "parent")

_FILE_RE = re.compile(r"^(\d{3})-.+\.md$")
_HEADING_RE = re.compile(r"^#\s+(?:\d+\.\s*)?(.+?)\s*$")
_ID_RE = re.compile(r"^\d+$")


class TaskError(Exception):
    pass


def _parse_front_matter(lines):
    """Return (fields, index of the first line after the front matter)."""
    if not lines or lines[0].strip() != "---":
        raise TaskError("no front matter (the file must start with '---')")
    fields = {}
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return fields, i + 1
        if not line.strip():
            continue
        key, sep, value = line.partition(":")
        if not sep:
            raise TaskError(f"front matter line is not 'key: value': {line!r}")
        fields[key.strip()] = value.strip()
    raise TaskError("front matter is not closed (missing second '---')")


def _parse_id(field, value):
    if not _ID_RE.match(value):
        raise TaskError(f"{field}: expected an id like 12, got {value!r}")
    return int(value)


def _parse_id_list(value):
    if not (value.startswith("[") and value.endswith("]")):
        raise TaskError(f"depends: expected a list like [1, 2], got {value!r}")
    items = [v.strip() for v in value[1:-1].split(",") if v.strip()]
    return [_parse_id("depends", v) for v in items]


def _parse_task(path, tasks_dir):
    task_id = int(_FILE_RE.match(path.name).group(1))
    parts = path.relative_to(tasks_dir).parts
    if len(parts) != 2 or parts[0] not in FOLDERS:
        raise TaskError(
            f"task files must sit directly in one folder of: {', '.join(FOLDERS)}"
        )
    lines = path.read_text(encoding="utf-8").splitlines()
    fields, body_start = _parse_front_matter(lines)

    unknown = sorted(set(fields) - set(REQUIRED) - set(OPTIONAL))
    if unknown:
        raise TaskError(f"unknown tag(s): {', '.join(unknown)}")
    for field, allowed in REQUIRED.items():
        if field not in fields:
            raise TaskError(f"missing tag: {field}")
        if fields[field] not in allowed:
            raise TaskError(
                f"{field}: {fields[field]!r} is not one of {' | '.join(allowed)}"
            )
    if "priority" in fields and fields["priority"] not in PRIORITIES:
        raise TaskError(
            f"priority: {fields['priority']!r} is not one of {' | '.join(PRIORITIES)}"
        )
    depends = _parse_id_list(fields["depends"]) if "depends" in fields else []
    parent = _parse_id("parent", fields["parent"]) if "parent" in fields else None

    in_done = parts[0] == "done"
    if in_done != (fields["status"] == "done"):
        raise TaskError(
            f"status is {fields['status']!r} but the file is "
            f"{'in' if in_done else 'not in'} done/ (done <=> done/)"
        )

    title = next(
        (m.group(1) for line in lines[body_start:] if (m := _HEADING_RE.match(line))),
        None,
    )
    if title is None:
        raise TaskError("no '# N. Title' heading after the front matter")

    return {
        "id": task_id,
        "type": fields["type"],
        "mode": fields["mode"],
        "status": fields["status"],
        "priority": fields.get("priority", "-"),
        "depends": depends,
        "parent": parent,
        "title": title,
        "path": path,
    }


def load_tasks(tasks_dir):
    """Return (tasks sorted by id, list of error strings)."""
    tasks, errors = [], []
    # Ids come from file names, so an invalid file still counts as existing.
    paths_by_id = {}
    for path in sorted(tasks_dir.rglob("*.md")):
        match = _FILE_RE.match(path.name)
        if match:
            paths_by_id.setdefault(int(match.group(1)), []).append(path)
    for path in (p for group in paths_by_id.values() for p in group):
        rel = path.relative_to(tasks_dir).as_posix()
        try:
            tasks.append(_parse_task(path, tasks_dir))
        except TaskError as exc:
            errors.append(f"{rel}: {exc}")

    for task_id, group in sorted(paths_by_id.items()):
        if len(group) > 1:
            names = ", ".join(p.relative_to(tasks_dir).as_posix() for p in group)
            errors.append(f"duplicate id {task_id}: {names}")

    for task in tasks:
        rel = task["path"].relative_to(tasks_dir).as_posix()
        refs = [("depends", d) for d in task["depends"]]
        if task["parent"] is not None:
            refs.append(("parent", task["parent"]))
        for field, ref in refs:
            if ref not in paths_by_id:
                errors.append(f"{rel}: {field}: no task with id {ref}")

    return sorted(tasks, key=lambda t: t["id"]), errors


def render_index(tasks, tasks_dir):
    folder = tasks_dir.resolve().name
    open_tasks = [t for t in tasks if t["status"] != "done"]
    done_ids = [str(t["id"]) for t in tasks if t["status"] == "done"]

    out = [
        "# Task index",
        "",
        "Generated by `loopwright/scripts/index.py`. Do not edit by hand.",
        "Read this index, then only the task file you need.",
        "",
        "## Legend",
        "",
        f"- type: {' | '.join(TYPES)}",
        "- mode: auto (no decisions left, agents can do it) | "
        "human (needs a decision or a step only the user can do)",
        f"- status: {' | '.join(STATUSES)}",
        f"- priority: {' | '.join(PRIORITIES)}, or - when not set",
        "- depends: ids of tasks that must be done first, or - when none",
        f"- path: relative to the directory above `{folder}/`",
        "",
        "## Open tasks",
        "",
        "| id | type | mode | status | priority | depends | title | path |",
        "|----|------|------|--------|----------|---------|-------|------|",
    ]
    for t in open_tasks:
        rel = t["path"].relative_to(tasks_dir).as_posix()
        depends = ", ".join(str(d) for d in t["depends"]) or "-"
        out.append(
            f"| {t['id']} | {t['type']} | {t['mode']} | {t['status']} | "
            f"{t['priority']} | {depends} | {t['title']} | {folder}/{rel} |"
        )
    out += ["", "## Done", "", ", ".join(done_ids) if done_ids else "none", ""]
    return "\n".join(out)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("tasks_dir", type=Path)
    parser.add_argument(
        "--next-id", action="store_true", help="print the next free id and exit"
    )
    args = parser.parse_args(argv)

    if not args.tasks_dir.is_dir():
        print(f"error: tasks directory not found: {args.tasks_dir}", file=sys.stderr)
        return 2

    tasks, errors = load_tasks(args.tasks_dir)
    if errors:
        print(f"{len(errors)} problem(s) in {args.tasks_dir}:", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        return 1

    if args.next_id:
        print(f"{max((t['id'] for t in tasks), default=0) + 1:03d}")
        return 0

    (args.tasks_dir / "INDEX.md").write_text(
        render_index(tasks, args.tasks_dir), encoding="utf-8", newline="\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
