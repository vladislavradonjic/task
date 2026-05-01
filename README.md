# task

Personal [taskwarrior](https://taskwarrior.org/) clone in Python, primarily for use on Windows.

## Status

Feature-complete for personal use. Commands: `add`, `list`, `done`, `delete`,
`modify`, `query`, `context`, `start`/`stop`/`log`, `today`, `week`, `recap`,
`undo`, `help`.

## Requirements

- Python 3.12+
- [uv](https://github.com/astral-sh/uv)

## Install

**For development:**

    uv sync
    uv run tsk <args>

**To install on a machine** (puts `tsk` in PATH):

    uv build                                        # produces dist/task-1.0.0-py3-none-any.whl
    scp dist/task-*.whl user@machine:~             # or USB, shared drive, etc.
    uv tool install ~/task-1.0.0-py3-none-any.whl  # on target machine

To update: rebuild, copy, and reinstall with `--force`.

## Sync

Sync is git-based, manual. The runtime never invokes git — you pull before working
and push after.

**Setup** (per context you want to sync):

    git -C <data_dir>/work init
    git -C <data_dir>/work remote add origin <remote>

`tsk context create` writes `.gitattributes` (`events.jsonl merge=union`) and
`.gitignore` (`tasks.json`) automatically. For an existing context, add them manually.

**Workflow:**

    git -C <data_dir>/work pull          # before starting work
    tsk add Fix parser bug               # appends to events.jsonl
    git -C <data_dir>/work add -A
    git -C <data_dir>/work commit -m "snapshot"
    git -C <data_dir>/work push

`merge=union` resolves concurrent edits to `events.jsonl` by keeping all appended
lines. The runtime sorts events by timestamp on load, so line order doesn't matter.

Don't sync `state.json` or `config.toml` — active context and user prefs are
per-machine.
