# CLAUDE.md

Personal taskwarrior clone (`tsk`) in Python 3.12+. Author-only project, v1.2, feature-complete
for daily use. The current work is cross-platform hardening, not new features.

## Target platforms — both are first-class

1. **Arch/omarchy Linux** — the development machine. Fast, unconstrained.
2. **Corporate Windows 11** — heavily locked down. Security tooling scans every file read,
   so *process startup is expensive*: each `tsk <cmd>` invocation pays ~200 ms of import
   cost on Linux and multiple seconds there.

**Consequence: the REPL (`tsk run`) is the primary interface on Windows**, because it pays
import cost once instead of per command. Anything that works in one-shot mode must work
identically inside the REPL. A feature that is one-shot-only is a bug, not a gap.

The two machines share one event log over git sync, so on-disk bytes must be
byte-identical across platforms.

## Deployment and data isolation

**The work machine cannot reach GitHub.** Code gets there by emailing a built wheel and
installing with `uv`. PyPI *is* reachable there, so dependency payload size is not a
constraint — only the 23 KB app wheel travels, and it already carries the recap templates.
Dependency weight still costs import latency under AV; see the startup-cost notes.

**The work machine is an isolated universe.** Its task data never leaves it and is never
synced with this one. Consequences: `docs/sync.md`'s cross-machine git sync is not in use;
cross-platform byte-identical output is cosmetic rather than critical; and **the work
machine's data has no backup and no remote event history to restore from**, so self-recovery
(rebuild from the log, never crash on a corrupt cache) matters more there than anywhere else.

## Layout

- `src/task/cli.py` — imperative shell. Splits argv into `[filter] command [modify]`,
  resolves state/context, dispatches, appends events, prints. Also holds `_repl_loop`.
- `src/task/commands.py` — every command, registered by trailing-underscore convention
  (`add_`, `list_`, `run_`). Trailing `_` avoids collisions with builtins like `list`.
  Discovery is `command_names()`, which introspects module globals.
- `src/task/parse.py` — `argv → ParsedFilter` / `ParsedModification`.
- `src/task/models.py` — `Task`, `Event` (pydantic discriminated union).
- `src/task/storage.py` — data dir resolution, snapshot read/rebuild, event append.
- `src/task/events.py` — `apply_event` reducer; per-event inverse logic for `undo`.
- `src/task/urgency.py` — urgency score + topological blocker bump.
- `src/task/config.py` — `config.toml` loading.
- `src/task/dates.py` — date and duration parsing.
- `src/task/templates/` — Jinja2 recap templates (`day`/`week`/`month`), shipped in the wheel.
- `tests/` — 310 tests mirroring `src/task/`; `conftest.py` holds shared fixtures.
  `test_repl.py` covers the REPL loop, including a differential test asserting the
  REPL and one-shot mode emit identical events for the same script. Keep it green.

Commands: `add`, `list`, `query`, `modify`, `done`, `delete`, `depends`, `blocks`,
`today`, `week`, `tags`, `projects`, `recap`, `undo`, `context`, `init`, `help`, `run`,
`rebuild`. Time tracking was removed in v1.4; see `docs/timesheet.md` for what replaces it.

## Tooling

- Run tests with `uv run python -m pytest tests/ -q`. 310 tests, ~0.4 s.
- Lint with `uvx ruff check src/ tests/` — ruff is **not** a dev dependency, so
  `uv run ruff` fails. There is no ruff config; the default ruleset reports ~95
  pre-existing findings (import order, naive datetimes, blind excepts). They are not
  enforced — don't fix them wholesale, just don't add new ones.
- Do not activate the venv directly or invoke `.venv/bin/*`.
- Point `TASK_DATA_DIR` at a scratch directory before running `tsk` by hand — otherwise
  you write into the author's real task data.

## Abandoned work

The `web-interface` branch added a browser canvas UI. **It was abandoned and deleted**
on 2026-08-29 (tip was `b786e8a`, never pushed; recoverable with
`git branch web-interface b786e8a` until git gc prunes it). Don't propose reviving it,
rebuilding it, or adding a web/GUI surface. The one salvageable piece was commit `590c1dc`,
which extracted `selection.py` / `query.py` / `graph.py` out of `commands.py` — worth
redoing from scratch if `commands.py` (1100 lines) needs splitting, but nothing else.

The `main` branch and `origin/cmd_add` / `origin/cmd_show` are a scrapped first attempt
(different module layout: `command.py`, `db.py`). `master` restarted from scratch at
`f33d15d`. `origin/HEAD` still points at `main`, which is dead code. `v1-2-repl` is a
plain ancestor of `master` with nothing unique.

## Specs (in `docs/`, gitignored — author-local)

- `docs/parsing.md` — canonical CLI parsing spec: filter/command/modify split, token kinds,
  dates, dependencies, daily/weekly lists, recap surface, EBNF, examples. Read before
  changing CLI behavior or proposing new features.
- `docs/data-model.md` — `Task` pydantic schema, status lifecycle, UUID + ephemeral display ID.
- `docs/storage.md` — data dir resolution, on-disk layout (top-level `state.json` +
  `config.toml` + per-context subdirs each with `meta.json` / `events.jsonl` (canonical) /
  `tasks.json` (cache) / `recaps/`), atomicity, undo, schema versions, `init` behavior.
- `docs/contexts.md` — context concept, isolation guarantee, `context` command surface.
- `docs/timesheet.md` — **the time model going forward.** Day-timeline entries, separate
  entity from `Task`, derived start times, letter addressing, kinds, shortcuts.
- `docs/time-tracking.md` — **superseded** by `timesheet.md`. Describes the `start`/`stop`/`log`
  session model being removed; kept only to explain legacy events in old logs.
- `docs/list.md` — `list` rendering: default visible set, data-driven columns, flag suffix,
  `rich.Table` wrap policy, color.
- `docs/urgency.md` — urgency factors and coefficients, topological bump, never stored.
- `docs/sync.md` — git-based sync. Per-context `git init`; `events.jsonl` tracked with
  `merge=union`; `tasks.json` gitignored and rebuilt from the log on load.
- `docs/config.md` — user preferences in `<data_dir>/config.toml`. Runtime never writes it.
- `docs/recap.md` — recap content rules, output, re-run behavior, Jinja2 templates.
- `docs/roadmap.md` — done / next / later.

`docs/` is intentionally gitignored. Don't suggest committing it. README.md *is* committed.

## Cross-platform rules (non-obvious, and currently violated in places)

- **Always pass `encoding="utf-8"` explicitly** on every read and write; `newline="\n"` on
  writes. Windows text mode defaults to cp1252, which cannot encode `č`, `ć`, or `đ` — a
  task like "počisti bazu" raises `UnicodeEncodeError` inside `append_event` and the task is
  lost. Every I/O call site already does this; keep new ones consistent.
- **Never assume a TTY.** Windows console and the Linux terminal differ on clear-screen,
  ANSI colour, and Unicode box-drawing. `rich` handles most of it; anything outside `rich`
  is suspect.
- **Startup imports are a cost on Windows, not a rounding error.** `polars` and `networkx`
  are imported *inside* the functions that need them (`query_`, `_is_acyclic`,
  `_build_graph`, `compute_urgency`), following the same idiom as `storage.data_dir()`.
  Keep them that way, and prefer lazy imports for anything similarly heavy. `import
  task.cli` is ~90 ms; it was 176 ms with both at module level.
- Use `pathlib` and `os.replace` for atomic swaps; `Path.rename` fails on Windows when the
  target exists.

## Spec conventions worth knowing (non-obvious)

- Tags carry their `+`/`-` sign in the parsed filter/modify structure; sign is semantic
  (filter: include/exclude; modify: add/remove). On-disk storage uses bare tag names.
- Property values are opaque to the generic parser; per-type validators interpret them.
- No comparison operators in property syntax — they collide with shell redirection. Use the
  `query` command (polars filter expression) for anything beyond exact match.
- Reserved tags `+today` / `+week` back the daily/weekly list sugar commands.
- Weekday and month names always resolve to the *next* future occurrence — never today.
- Bare integers: in the filter section they're IDs; in the modify section they're
  description words. `depends` / `blocks` validators re-parse the modify description as IDs.
- Cycle rejection on dependency add (`networkx` `DiGraph`); urgency does a topo-order pass
  that bumps blockers above blockees.
- Contexts are a storage partition, not a task field — each context is its own data
  directory and the runtime never reads two in one invocation.
- **No time tracking on `Task`.** `start`/`stop`/`log`, `Task.start`, auto-stop, and stale
  sessions were removed in v1.4. `StartedEvent`/`StoppedEvent` remain in the discriminated
  union so pre-v1.4 logs still parse, but they replay as no-ops (they simply fall through
  `apply_event`) and are surfaced nowhere. The replacement is `docs/timesheet.md`.
- `done` is reachable only from `pending`. Marking a `waiting` task done is refused — clear
  `wait` via `modify wait:` first.
- `list` shows pending always and waiting only when fewer than 10 pending tasks exist;
  columns are data-driven (rendered only when ≥1 row has a value).
- **Errors** print a one-line message to **stderr**; tracebacks are suppressed unless
  `TASK_DEBUG=1`. Success output goes to **stdout**. **Exit codes**: `0` success, `1`
  runtime error, `2` user error (bad input, refusal-by-design).
- **Timezone**: machine-local for all date resolution and "now". Stored datetimes are
  **naive** ISO-8601 with no offset — `datetime.now()` throughout, verified on disk
  (`"ts":"2026-08-29T10:13:21.555707"`). This file previously claimed tz-aware storage;
  that was never true. Keep new code naive so comparisons stay consistent, and note that
  a row spanning a DST change measures by wall clock, not elapsed time.
- `events.jsonl` is canonical; `tasks.json` is a rebuildable cache. Mutations append the
  event first, then refresh the snapshot.
- `modify` / `delete` / `done` with an *empty filter* are no-ops with a clear message.
- `project` is a dotted path. Filter `project:work` is a dot-bounded prefix match; modify
  assignment is exact.
- Schema versions: `state.json` and per-context `meta.json` carry `version`. Mismatch on
  load is fatal — no silent coercion. A future `tsk migrate` upgrades through the log.
- **Functional core, imperative shell.** Command functions in `commands.py` are pure: they
  take current state + parsed args and return `(list[Event], message: str)`. They never
  touch disk or print. The shell layer (`cli.py` + storage) appends events, refreshes the
  snapshot via `apply_event`, and prints. Tests pass known state in and assert on returned
  events — no I/O mocks. **`context_`, `init_`, `undo_` are the exceptions**: they do their
  own I/O and take no task list. This is why the REPL dispatch special-cases them — and why
  mid-session `context use` is currently broken (see below).

## Working rules

These bias toward caution over speed — for trivial edits, use judgment, not ceremony.
Adapted from [Karpathy's guidelines](https://github.com/forrestchang/andrej-karpathy-skills/blob/main/skills/karpathy-guidelines/SKILL.md).

- **Show code before writing it.** Don't edit files under `src/` or `tests/` unless
  explicitly asked. Propose the code in chat; the user decides whether to implement it
  themselves, ask me to apply it, or revise it. Doc edits in `docs/` and `CLAUDE.md`, and
  dependency edits in `pyproject.toml`, follow the normal flow.
- **State assumptions before implementing.** If multiple interpretations exist, name them.
- **Match the existing style** even where you'd do it differently. Reuse local primitives.
- **Surgical scope.** Every changed line should trace to the request. Remove imports/vars
  *your* changes made unused; mention pre-existing dead code, don't delete it.
- **Verifiable success criteria.** Restate vague tasks as something checkable.
- **Cleanup is part of the change, not a follow-up.** No half-finished implementations.
- **Don't add dependencies casually.** Every new import is startup cost on the Windows box.

## Working style

- When there's a real design choice, propose tradeoffs before applying. Author iterates fast
  via short directives ("yes apply," "redirect on this") — don't bury choices, but don't ask
  permission on obvious mechanical edits either.
- Prefer reusing existing primitives over inventing new ones (reserved tags for list
  membership instead of a separate store; polars for the query DSL instead of a custom one).
- Keep concerns in their own doc — don't expand `parsing.md` with non-parsing content.
- Stale `.pyc` files in `src/task/__pycache__/` may reference deleted modules (`db.py`,
  `command.py` — singular). Don't infer those still exist.
