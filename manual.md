# tsk — manual

Two things live in one store: a **task list** (what to do next) and a **timesheet**
(where the day went). They are separate entities that share a project namespace and an
optional link.

- [Command line shape](#command-line-shape)
- [Interactive mode](#interactive-mode)
- [Tasks](#tasks)
- [Dates and durations](#dates-and-durations)
- [Dependencies](#dependencies)
- [Daily and weekly lists](#daily-and-weekly-lists)
- [Urgency](#urgency)
- [Query](#query)
- [Timesheet](#timesheet)
- [Recap](#recap)
- [Contexts](#contexts)
- [Undo](#undo)
- [Configuration](#configuration)
- [Files](#files)
- [Errors and exit codes](#errors-and-exit-codes)

---

## Command line shape

Every invocation is three parts:

    tsk [filter] <command> [modify]

The first token that names a command splits the line. Everything before it selects what
to act on; everything after it says what to do.

    tsk 3 modify priority:H
        └┬┘ └──┬─┘ └────┬───┘
      filter command  modify

**In the filter section**, bare integers are task IDs and one-or-two lowercase letters
are timesheet rows. `tsk 3 delete` deletes a task; `tsk c delete` deletes a timesheet
row. **In the modify section**, bare integers are ordinary description words.

Tokens take these forms anywhere:

| form | meaning |
|---|---|
| `+tag` | in a filter, "has this tag"; in a modify, "add this tag" |
| `-tag` | in a filter, "does not have"; in a modify, "remove" |
| `name:value` | a property |
| `name:` | clear the property (modify only) |

There are no comparison operators — they collide with shell redirection. Use
[`query`](#query) for anything beyond exact match.

Display IDs are **ephemeral**. They are assigned when the list is rendered and change as
tasks are completed or rows deleted. They are not stored; the underlying identity is a
UUID.

---

## Interactive mode

    tsk run

Opens a prompt. Type commands without the leading `tsk`. The screen clears and re-renders
after every command that changes something, showing the task list with today's timesheet
beneath it.

| key | effect |
|---|---|
| `exit` / `quit` / Ctrl-D | leave |
| Ctrl-C | cancel the current line, stay in the session |

`init` and `run` are refused inside a session. `config.toml` is re-read when it changes,
so edits take effect without restarting.

This mode exists because starting Python once per command is expensive on machines where
security software scans every file read. It is the intended way to use `tsk` there.

---

## Tasks

### add

    tsk add <description> [+tag] [-tag] [property:value]

    tsk add write the parser project:acme.parse due:friday priority:H +urgent

Recognised properties: `project`, `priority`, `due`, `wait`. Anything else is stored as a
free-form property and shown by `query`.

`priority` is **case-sensitive**: only `H`, `M`, `L` count toward
[urgency](#urgency). `priority:h` is stored verbatim and scores nothing.

`project` is a dotted path. `project:work.parse` sits under `work`.

`wait:<date>` makes the task `waiting` — hidden from the default list until the date
passes, at which point it becomes `pending` on its own.

### list

    tsk [filter] list [status:pending|waiting|done] [project:<prefix>]

Shows pending tasks always, and waiting ones only when fewer than ten pending exist.
Columns appear only when at least one row has a value for them, so the table stays narrow.

`project:work` matches `work` and everything under `work.` — a dot-bounded prefix, so
`workshop` does not match.

The ID column carries a flag: `d` for the daily list, `w` for weekly, `*` for both.

### modify

    tsk <id> modify [description] [+tag] [-tag] [property:value] [property:]

    tsk 3 modify priority:M +blocked
    tsk 3 modify wait:                # clear the field

An empty value clears a property. With an empty filter, `modify` is a no-op that says so
rather than touching everything.

### done, delete

    tsk <id> done
    tsk <id> delete

`done` is reachable only from `pending`. A `waiting` task is refused — clear `wait:`
first. Both accept several IDs. Both refuse an empty filter.

---

## Dates and durations

Any property taking a date accepts:

| form | example | resolves to |
|---|---|---|
| keyword | `now`, `today`, `eod`, `eow`, `eom`, `eoy` | end of day/week/month/year |
| weekday | `monday`, `friday` | the **next** such day, never today |
| month | `march` | the 1st of the next such month |
| offset | `+3d`, `-1w`, `+2h`, `+30min`, `+1y` | relative to now |
| clock | `9:15`, `13:40` | that time (see [timesheet](#timesheet) for the past-midnight rule) |
| ISO | `2026-12-25` | midnight that day |

Durations, used by `for:`, take the forms `2h`, `30min`, `45m`, `1h30m`.

---

## Dependencies

    tsk <id> depends <id>[,<id>...]     # this task waits on those
    tsk <id> blocks  <id>[,<id>...]     # those tasks wait on this

    tsk 5 depends 3
    tsk 5 depends -3                    # remove

`A blocks B` and `B depends A` say the same thing. Cycles are rejected outright. Blocked
tasks render dim, and blockers are pulled above what they block in the urgency ordering.

---

## Daily and weekly lists

    tsk <ids> today        # add to the daily list
    tsk today              # show it
    tsk today clear        # empty it

    tsk <ids> week         # same, weekly

These are backed by the reserved tags `+today` and `+week`, which are hidden from the
Tags column. Lists persist until cleared — nothing rolls over automatically.

---

## Urgency

`list` sorts by a computed score. It is never stored, and it is recalculated on every
render.

| factor | weight |
|---|---|
| `priority:H` / `M` / `L` | +6.0 / +3.9 / +1.8 |
| overdue | +12.0 |
| approaching due | up to +12.0, scaling from 14 days out |
| age | up to +2.0 at one year |
| blocking something | +8.0 |
| blocked by something | −5.0 |
| waiting | −5.0 |
| has tags / has project | +1.0 each |

After scoring, a topological pass lifts every blocker just above what it blocks, so a
prerequisite never sorts below the thing waiting on it.

---

## Query

    tsk query "<polars expression>"

    tsk query "col('priority') == 'H'"
    tsk query "col('project').str.starts_with('acme') & (col('status') == 'pending')"

For anything the filter grammar cannot express. Use `&` and `|`, not `and`/`or`.

Columns: `uuid`, `id`, `description`, `status`, `tags`, `entry`, `due`, `wait`, `end`,
plus every property name in use.

This is the only command that loads `polars`, which is why it is imported lazily.

---

## Timesheet

The timesheet records **where the day went** — including the meetings, calls, chat and
dead time that will never be tasks. It has no start verb and no stop verb. It has rows,
which you add and then edit, the way a spreadsheet row works.

### The one rule worth knowing

> **A row's start is derived, not stored:** it is the end of the row before it, unless
> you set `from:` explicitly.

You type end times; starts follow. Three things fall out of that:

- **Extending a row cascades.** A meeting that ran long is one edit — `b modify til:11:30`
  — and every row after it shifts. Note this *shrinks* the next row rather than pushing
  its end later, exactly as a spreadsheet formula would.
- **Deleting a row hands its slot to the next one**, with no further edits.
- **An explicit `from:` breaks the chain**, which is both the manual override and the way
  a gap is expressed.

### log

    tsk log [description...] kind:<k> [project:<p>] [task:<id>] [from:<t>] [til:<t>] [for:<d>]

    tsk log standup kind:meeting project:internal from:9:00 til:9:30
    tsk log write the parser kind:solo project:acme task:1 til:11:20
    tsk log slack and coffee kind:junk til:11:45
    tsk log kind:meeting project:acme til:12:30      # description optional
    tsk log deep work kind:solo til:                 # leave the row open

- `til:` defaults to **now**, so the common case is one command when you finish something.
- Give at most two of `from:`, `til:`, `for:` — the third is implied.
- `kind:` is required and must be one of the [configured kinds](#configuration).
- `task:<id>` links the row to a task, which the day view shows as `→1`.
- `til:` with no value leaves the row **open**. At most one row may be open; close it with
  `<letter> modify til:<time>` before logging the next.
- A future end time is refused.

### day

    tsk day [<date>]

```
Saturday 29 Aug   3:45 tracked
  a  06:00–06:30   0:30   meeting   internal    standup
  b  06:30–08:20   1:50   solo      acme.parse  write the parser   →1
  c  08:20–08:45   0:25   junk                  slack
  d  08:45–09:15   0:30   call      acme
     09:15–10:00   0:45                         untracked
  e  10:00–10:30   0:30   solo      acme.parse

  solo 2:20  call 0:30  meeting 0:30  junk 0:25
  acme.parse 2:20  acme 0:30  internal 0:30  — 0:25
```

Gaps are shown rather than absorbed — unaccounted time is information. The two footer
lines are the rollups the timesheet exists to produce.

An argument names a calendar date and shows that date's logical day: `tsk day yesterday`,
`tsk day 2026-08-27`.

### Editing rows

    tsk <letter> modify [description] [kind:] [project:] [task:] [from:] [til:]
    tsk <letter> delete

    tsk b modify til:11:30       # it ran long; everything after shifts
    tsk d modify from:11:50      # it moved; leaves a gap before it
    tsk c delete                 # never happened; d absorbs the slot

An empty value clears a field: `til:` reopens a row, `from:` hands it back to the chain.
`kind:` cannot be cleared.

**Letters address today only.** A past day's rows can be logged with explicit `from:` and
`til:`, but not yet corrected.

### Logical days and midnight

A day runs from **04:00 to 04:00** by default, configurable. A row started at 23:30 and
ended at 00:45 is one row of 1 hour 15 minutes, and it stays with the evening it belongs
to rather than splitting across two dates.

Bare clock times resolve inside the current logical day, not the current calendar day. At
00:50, `from:23:30` means last night and `til:00:30` means twenty minutes ago.

The derivation chain never crosses a day boundary, so the first row of a morning cannot
accidentally start where last night's ended. That first row is an anchor: give it `from:`,
or let it default to now.

---

## Recap

    tsk recap day|week|month

Writes a markdown summary to `<data_dir>/<context>/recaps/recap-<period>-<date>.md`:
what was planned, what got done, and where the time went, with rollups by kind and by
project. The day recap also lists the timeline. Prompts before overwriting; refuses
rather than prompting when not attached to a terminal.

Templates are Jinja2 and can be overridden per user — see
[configuration](#configuration). Available variables:

| variable | contents |
|---|---|
| `date`, `period` | the period being reported |
| `today_list`, `week_list` | reserved-tag lists (day and week recaps) |
| `due_in_period`, `overdue_in_period`, `done_in_period` | task lists |
| `total_tracked_in_period` | seconds of tracked time |
| `time_by_kind`, `time_by_project` | `{name: seconds}`, ordered by descending total |
| `rows_in_period` | `day`, `start`, `end`, `duration_s`, `kind`, `project`, `description`, `open` |

The `hm` filter renders seconds as `H:MM` — `{{ total_tracked_in_period | hm }}`.

---

## Contexts

    tsk context                  # which one is active
    tsk context list
    tsk context create work
    tsk context use work
    tsk context delete work

A context is a **storage partition**, not a task field. Each is its own directory with
its own log, and the runtime never reads two in one invocation. Deleting the active
context is refused.

`TASK_CONTEXT` overrides the active context for a single invocation.

---

## Undo

    tsk undo

Reverses the most recent change — task or timesheet — by appending an `undone` event and
replaying the log without the undone entry. Repeatable. Because it works by exclusion
rather than by computing inverses, it handles every event type the same way.

---

## Configuration

`<data_dir>/config.toml`, read on every run and never written by `tsk`.

```toml
[list]
# Documented but not yet honoured; the sort is currently fixed at urgency, then entry.
sort = "urgency,-entry"

[timesheet]
# Closed vocabulary for kind:. An unrecognised kind is refused, listing these.
kinds = ["solo", "chat", "meeting", "call", "junk"]
# A logical day runs from here to here.
day_starts_at = "04:00"

[timesheet.shortcuts]
# Field defaults for recurring rows, expanded when the name is the FIRST word of the
# description. Anything given explicitly wins; trailing words replace the description.
standup = { description = "team standup", kind = "meeting", project = "internal" }
email   = { description = "email + teams", kind = "chat" }
mtg     = { kind = "meeting" }

[recap]
output_dir = "~/Documents/recaps"
template_dir = "~/.config/task/templates"
```

With those shortcuts:

    tsk log standup til:9:30              → team standup · meeting · internal
    tsk log mtg project:acme til:11:00    → meeting · acme, no description
    tsk log email urgent thread           → "urgent thread" · chat

Unknown keys are ignored.

---

## Files

    <data_dir>/
    ├── state.json           # which context is active
    ├── config.toml          # your preferences
    └── <context>/
        ├── meta.json
        ├── events.jsonl     # append-only; the single source of truth
        ├── tasks.json       # cache, rebuildable
        ├── entries.json     # cache, rebuildable
        └── recaps/

`<data_dir>` is `~/.local/share/task` on Linux and `%LOCALAPPDATA%\task` on Windows;
`TASK_DATA_DIR` overrides it.

**`events.jsonl` is canonical.** Both caches are derived from it and can be deleted at
any time — a missing or corrupt one is detected on read and rebuilt automatically, so
nothing is lost either way.

`tsk rebuild` forces a rebuild of `tasks.json` by hand. It does **not** touch
`entries.json`, which currently only repairs itself on the next read.

Everything is written as UTF-8 with Unix line endings, so `č`, `ć`, and `đ` survive on
Windows, where the platform default encoding would refuse them.

---

## Errors and exit codes

Errors print one line to stderr. Set `TASK_DEBUG=1` for a full traceback.

| code | meaning |
|---|---|
| `0` | success |
| `1` | runtime error |
| `2` | user error |

The mapping is not yet consistent: refusals such as an invalid date currently print to
stdout and exit `0`, and an unknown command exits `1` where `2` would be right. Do not
script against these codes yet.
