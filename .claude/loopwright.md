# Loopwright project settings

The only contract between this project and the `loopwright` plugin (`loopwright/`). The `loopwright:developer` and `loopwright:code-reviewer` agents read it, and so can a skill. The plugin's own generic rules live in `loopwright/rules.md`. Keep the section labels as they are.

## Tasks dir

`tasks/`

## Project rules file

`docs/agent-rules.md`

## Test command

`python -m uv run pytest -q`

## Check commands

- IP check: `python -m uv run python scripts/check_ip.py`. Every file you touched must have zero hits.
- ruff: to be added here once task #22 is done.

## Trailer for commit messages

`Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`

## Notes

- User-facing commands such as `/analyze-deck` are skills, and subagents can't invoke skills. The orchestrating session must run them and check their output; the agents report that it is needed.
