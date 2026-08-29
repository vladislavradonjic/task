# tsk

A personal [taskwarrior](https://taskwarrior.org/) clone in Python, with a built-in
timesheet. Runs on Linux and on Windows; the interactive mode is the primary interface
on locked-down Windows machines, where per-process startup cost is punitive.

Full command reference: **[manual.md](manual.md)**.

## Status

Feature-complete for personal use.

**Tasks** — `add`, `list`, `modify`, `done`, `delete`, `depends`, `blocks`, `today`,
`week`, `tags`, `projects`, `query`, `recap`, `undo`

**Timesheet** — `log`, `day`

**Housekeeping** — `context`, `init`, `rebuild`, `help`, `run`

## Requirements

- Python 3.12+
- [uv](https://github.com/astral-sh/uv)

## Install

**For development:**

    uv sync
    uv run tsk <args>

**On another machine** (puts `tsk` on PATH):

    uv build                      # produces dist/task-<version>-py3-none-any.whl

Get the wheel across — email attachment, USB, shared drive — then on the target machine:

    uv tool install ~/task-<version>-py3-none-any.whl

The wheel is ~30 KB and carries its own recap templates. Dependencies are resolved from
PyPI at install time, so the target machine needs an index it can reach; nothing else
travels. To update, rebuild, copy, and reinstall with `--force`.

## Quick start

    tsk init
    tsk add write the parser project:acme due:tomorrow priority:H
    tsk list
    tsk 1 done

Log where the time actually went:

    tsk log standup kind:meeting project:internal from:9:00 til:9:30
    tsk log write the parser kind:solo project:acme task:1 til:11:20
    tsk day

Both together, refreshed after every command:

    tsk run

## Interactive mode

`tsk run` opens a prompt where commands are typed without the leading `tsk`. It pays
Python's import cost once per session instead of once per command, which matters when
security tooling scans every file read. The screen shows the task list and today's
timesheet, re-rendered after each command.

Everything available in one-shot mode works identically inside it — there is a test that
runs the same script through both and asserts the resulting event logs are identical.

## Where things live

`tsk init` creates a data directory: `~/.local/share/task` on Linux,
`%LOCALAPPDATA%\task` on Windows. Override with `TASK_DATA_DIR`.

Inside, each context is its own subdirectory holding `events.jsonl` — an append-only log
that is the single source of truth — plus `tasks.json` and `entries.json`, which are
disposable caches rebuilt from the log on demand. See [manual.md](manual.md#files) for
the layout and `tsk rebuild` for recovery.
