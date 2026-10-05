# Loopwright project settings

The only contract between this project and the `loopwright` plugin. The `loopwright:developer` and `loopwright:code-reviewer` agents read it, and so can a skill. Keep the section labels as they are.

## Tasks dir

<!-- Folder holding bugs/, features/, unrefined/, done/ and the generated INDEX.md. -->

`{{tasks_dir}}`

## Project rules file

<!-- Project-specific rules the developer follows and the reviewer checks. They add to the generic rules. -->

`{{rules_file}}`

## Test command

<!-- The command that runs the full test suite. Write "none" if the project has no tests yet. -->

{{test_command}}

## Check commands

<!-- One bullet per check (linter, type checker, ...) the agents must run: a label, the command, and what counts as a pass. -->

{{check_commands}}

## Trailer for commit messages

<!-- Line appended to commit messages. Write "none" for no trailer. -->

{{trailer}}

## Notes

<!-- Anything else the agents need, e.g. commands only the orchestrating session can run. -->

{{notes}}
