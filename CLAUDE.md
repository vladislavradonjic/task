# CLAUDE.md

Personal taskwarrior clone in Python 3.12+, primarily for Windows. Author-only project, early scaffolding stage.

## Layout

- `src/task/cli.py` — splits argv into `[filter] command [modify]`, dispatches by command name. Discovery introspects `commands.py` for callables ending in `_`.
- `src/task/commands.py` — command stubs registered by trailing-underscore convention (`add_`, `list_`, `init_`). Trailing `_` avoids collisions with Python builtins like `list`.
- `tests/` — empty. Roadmap explicitly notes "Try to lead with tests next time."
- `pyproject.toml` — runtime deps (`networkx`, `polars`, `pydantic`, `python-dateutil`, `rich`); dev deps (`pytest`). Don't add new ones casually.

### Planned modules

The implementation will add (per [docs/roadmap.md](docs/roadmap.md) "Project skeleton"):

- `parse.py` — tokenizer: `argv → ParsedCommand`
- `models.py` — `Task`, `Event` (pydantic discriminated union), `ParsedCommand` / `ParsedFilter` / `ParsedModification`
- `storage.py` — data dir resolution, snapshot read/rebuild, event append
- `events.py` — `apply_event` reducer; per-event-type inverse logic for `undo`
- `render.py` — `rich.Table` list rendering (later)

Tests mirror `src/task/` under `tests/`; `conftest.py` holds shared fixtures.

## Specs (in `docs/`, gitignored — author-local)

- `docs/parsing.md` — canonical CLI parsing spec: filter/command/modify split, token kinds, dates, dependencies, daily/weekly lists, recap surface, EBNF, examples. Read before changing CLI behavior or proposing new features.
- `docs/data-model.md` — `Task` pydantic schema, status lifecycle, UUID + ephemeral display ID model, deferred fields.
- `docs/storage.md` — data dir resolution, on-disk layout (top-level `state.json` + `config.toml` + per-context subdirs each with `meta.json` / `events.jsonl` (canonical) / `tasks.json` (cache) / `recaps/`), atomicity, undo, schema versions, `init` behavior.
- `docs/contexts.md` — context concept, isolation guarantee, `context` command surface (list/use/create/delete), activation rules.
- `docs/time-tracking.md` — single-active model (`start` field + `started`/`stopped` events), `start`/`stop`/`log` commands, auto-stop, stale-session handling.
- `docs/list.md` — `list` rendering: default visible set (pending; waiting if <10 pending), data-driven columns, flag suffix on ID, `rich.Table` wrap policy, color sketch.
- `docs/urgency.md` — urgency score: factors and default coefficients, topological bump that lifts blockers above blockees, never stored.
- `docs/sync.md` — git-based sync. Per-context `git init`; `events.jsonl` tracked with `merge=union`; `tasks.json` gitignored and rebuilt from the log on load.
- `docs/config.md` — user-editable preferences in `<data_dir>/config.toml`. Optional; runtime never writes it.
- `docs/recap.md` — recap content rules, output, re-run behavior, Jinja2 templates.
- `docs/roadmap.md` — done / next / later.

`docs/` is intentionally gitignored. Don't suggest committing it. README.md *is* committed.

## Spec conventions worth knowing (non-obvious)

- Tags carry their `+`/`-` sign in the parsed filter/modify structure; sign is semantic (filter: include/exclude; modify: add/remove). On-disk task storage uses bare tag names — see [data-model.md](docs/data-model.md).
- Property values are opaque to the generic parser; per-type validators interpret them.
- No comparison operators in property syntax — they collide with shell redirection. Use the `query` command (polars filter expression) for anything beyond exact match.
- Reserved tags `+today` / `+week` back the daily/weekly list sugar commands; manual tag editing still works.
- Weekday and month names always resolve to the *next* future occurrence — never today / this month.
- Bare integers: in the filter section they're IDs (collected into a list); in the modify section they're description words. `depends` / `blocks` validators re-parse the modify description as an ID list.
- Cycle rejection on dependency add (`networkx` `DiGraph`); urgency calculation does a topo-order pass that bumps blockers above blockees.
- Contexts are a storage partition, not a task field — each context is its own data directory and the runtime never reads two in one invocation. See `contexts.md`.
- "Active" (time tracking) is orthogonal to status: `start: datetime | None` field plus `started`/`stopped` events. Single-active per context; only `pending` is startable; `done`/`delete` of an active task auto-stops first. See `time-tracking.md`.
- `done` is reachable only from `pending`. Marking a `waiting` task done is refused — clear `wait` via `modify wait:` first. The symmetry with `start` (also pending-only) keeps the lifecycle predictable. See `data-model.md`.
- `list` shows pending always and waiting only when fewer than 10 pending tasks exist; columns are data-driven (rendered only when ≥1 row has a value). See `list.md`.
- **Errors** print a one-line message to **stderr**; tracebacks are suppressed unless `TASK_DEBUG=1`. Success output goes to **stdout**. **Exit codes**: `0` success, `1` runtime error (I/O, version mismatch, broken state), `2` user error (bad input, refusal-by-design like deleting the active context).
- **Timezone**: machine-local for all date resolution and "now" computations; stored datetimes are tz-aware ISO-8601 with the local offset preserved. See `data-model.md`.
- `events.jsonl` is the canonical state; `tasks.json` is a rebuildable cache. Mutations append the event first, then refresh the snapshot. A missing or stale `tasks.json` is recoverable by replaying the log — see `storage.md` and `sync.md`.
- `modify` / `delete` / `done` with an *empty filter* are no-ops with a clear message. The runtime refuses to mass-affect every task on an unguarded command. See `parsing.md`.
- `project` is a dotted path by convention. Filter `project:work` is a dot-bounded prefix match (matches `work`, `work.parser`, `work.docs.api`); modify-section assignment is exact. See `parsing.md`.
- Schema versions: `state.json` and per-context `meta.json` carry `version`. Mismatch on load is fatal — no silent coercion. A future `task migrate` command upgrades through the event log. See `storage.md`.
- **Functional core, imperative shell.** Command functions in `commands.py` are pure: they take current state + parsed args and return `(list[Event], message: str)`. They never touch disk or print. The shell layer (`cli.py` + storage) appends the events, refreshes the snapshot via `apply_event`, and prints the message. Tests pass known state in and assert on the returned events — no I/O mocks needed.

## Working rules

These bias toward caution over speed — for trivial edits, use judgment, not ceremony. Adapted from [Karpathy's guidelines](https://github.com/forrestchang/andrej-karpathy-skills/blob/main/skills/karpathy-guidelines/SKILL.md).

- **Show code before writing it.** Don't edit files under `src/` or `tests/` unless explicitly asked. Propose the code in chat; the user decides whether to implement it themselves, ask me to apply it, or revise it. Doc edits in `docs/` and `CLAUDE.md`, and dependency edits in `pyproject.toml`, follow the normal flow — this rule is about source and tests.
- **State assumptions before implementing.** If multiple interpretations of the task exist, name them and let me redirect — don't pick silently.
- **Match the existing style** even where you'd do it differently. Reuse local primitives over inventing new ones.
- **Surgical scope.** Every changed line should trace to the request. Remove imports/vars *your* changes made unused; mention pre-existing dead code, don't delete it.
- **Verifiable success criteria.** Restate vague tasks as something checkable (a test, a build, a behavior). Where useful, sketch a brief 2-4 step plan with verifications before starting.
- **Cleanup is part of the change, not a follow-up.** No half-finished implementations.

## Working style

- When there's a real design choice, propose tradeoffs before applying. Author iterates fast via short directives ("yes apply," "redirect on this") — don't bury choices, but don't ask for permission on obvious mechanical edits either.
- Prefer reusing existing primitives over inventing new ones (e.g., reserved tags for list membership instead of a separate list store; polars for query DSL instead of inventing one).
- Keep concerns in their own doc — don't expand `parsing.md` with non-parsing content.
- Stale `.pyc` files in `src/task/__pycache__/` reference deleted modules (`db.py`, `models.py`, `parse.py`, `dates.py`, `command.py` — singular). Don't infer those still exist.
