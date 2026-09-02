"""The vocabularies typed after `project:` and `kind:` — usage, recency, ranking.

Pure functions over tasks, timesheet entries and config values. Nothing here touches
disk, config files or the terminal. The project namespace is shared by tasks and
entries (docs/timesheet.md), so "which projects are in use" is only answerable by
looking at both.

The two vocabularies are deliberately not symmetric. `project` is open and discovered
from data, so its candidates are windowed — a name unused for a year is dead. `kind` is
closed and declared in config.toml, so every configured value stays a candidate however
long ago it was last used, and entries only decide the order. See docs/projects.md.
"""

import re
from dataclasses import dataclass
from datetime import datetime, time

from task.dates import parse_date
from task.models import Entry, Task
from task.timesheet import DEFAULT_DAY_STARTS_AT, resolve


@dataclass
class Usage:
    """How much one vocabulary value is used, and how recently."""

    name: str
    tasks: int = 0
    entries: int = 0
    last_used: datetime = datetime.min

    @property
    def total(self) -> int:
        return self.tasks + self.entries


# --- windows -----------------------------------------------------------------

# Deliberately not reusing `dates._OFFSET`: the sign is ours to impose, and letting a
# user-supplied `-3m` through to `parse_date` as `--3m` makes dateutil read it as 00:03.
_WINDOW = re.compile(r'^-?(\d+)(min|h|d|w|m|y)$')


def window_start(raw: str, now: datetime | None = None) -> datetime | None:
    """Resolve a lookback window to a cutoff instant. `all` means no cutoff.

    Bare offsets read backwards here — `3m` is the last three months, not three months
    hence — because a window into the future would name nothing.
    """
    raw = raw.strip()
    if raw.lower() == "all":
        return None
    if now is None:
        now = datetime.now()
    if m := _WINDOW.match(raw.lower()):
        return parse_date(f"-{m.group(1)}{m.group(2)}", now)
    return parse_date(raw, now)  # an explicit date serves as a cutoff too


# --- usage -------------------------------------------------------------------


def project_usage(
    tasks: list[Task],
    entries: list[Entry],
    since: datetime | None = None,
    day_starts_at: time = DEFAULT_DAY_STARTS_AT,
) -> list[Usage]:
    """Projects named by a task or a timesheet row since `since` (None means all time).

    A task counts at the later of its entry and end timestamps — an old task closed
    yesterday is recent use of its project. An active task always counts regardless of
    the window: a pending task is current by definition, however long ago it was written.
    """
    seen: dict[str, Usage] = {}

    def touch(name: str, when: datetime, attribute: str) -> None:
        u = seen.setdefault(name, Usage(name=name))
        setattr(u, attribute, getattr(u, attribute) + 1)
        u.last_used = max(u.last_used, when)

    for task in tasks:
        name = task.properties.get("project")
        if not name:
            continue
        when = max(t for t in (task.entry, task.end) if t is not None)
        if since is not None and when < since and task.status not in ("pending", "waiting"):
            continue
        touch(name, when, "tasks")

    # Start times are derived, not stored, so a row's place on the timeline is only
    # knowable through resolve() — `from_` is None on every non-anchoring row.
    for r in resolve(entries, day_starts_at):
        if not r.entry.project or r.start is None:
            continue
        if since is not None and r.start < since:
            continue
        touch(r.entry.project, r.start, "entries")

    return sorted(seen.values(), key=lambda u: (-u.total, u.name))


def kind_usage(
    entries: list[Entry],
    kinds: list[str],
    day_starts_at: time = DEFAULT_DAY_STARTS_AT,
) -> list[Usage]:
    """The configured kinds, ordered by how much and how recently each was logged.

    Takes no window, unlike `project_usage`. `kind` is a closed vocabulary that `log_`
    validates against, so every configured value stays a legal answer however long ago
    it was last used — entries decide the order, never the membership. A kind never
    logged keeps `last_used = datetime.min`, which sorts it behind used ones without a
    special case anywhere else.
    """
    seen = {k: Usage(name=k) for k in kinds}
    for r in resolve(entries, day_starts_at):
        u = seen.get(r.entry.kind)
        if u is None:
            continue  # a kind dropped from config since the row was written
        u.entries += 1
        if r.start is not None:
            u.last_used = max(u.last_used, r.start)
    return sorted(seen.values(), key=lambda u: (-u.entries, u.name))


# --- ranking -----------------------------------------------------------------

# Tiers, best first. `difflib` alone cannot express this: it scores "a" against
# "arabia" at 0.29, below any threshold that would also reject a bad match.
_EXACT_PREFIX = 1.0
_SEGMENT_PREFIX = 0.9   # `project` is a dotted path: "acme" should find "work.acme"
_ANCHORED_SUBSEQ = 0.8  # characters in order, starting at a segment boundary
_LOOSE_SUBSEQ = 0.6     # characters in order, starting mid-word
# Below this length only the two prefix tiers apply. One or two characters carry too
# little information to fuzzy-match: without this, "b" scores 0.8 against "Arabia".
_FUZZY_MIN_CHARS = 3


def score(prefix: str, name: str) -> float:
    """How well `name` completes what was typed, in 0.0 - 1.0."""
    if not prefix:
        return 0.0
    p, n = prefix.lower(), name.lower()
    if n.startswith(p):
        return _EXACT_PREFIX
    if any(segment.startswith(p) for segment in n.split(".")):
        return _SEGMENT_PREFIX
    if len(p) < _FUZZY_MIN_CHARS:
        return 0.0

    anchors = {0, *(i + 1 for i, ch in enumerate(n) if ch in "._-")}
    best = 0.0
    for start in range(len(n)):
        if n[start] != p[0]:
            continue
        span = _shortest_span(p, n, start)
        if span is None:
            continue
        # Tighter runs score higher: "arb" in "arabia" beats "aia" spread across it.
        base = _ANCHORED_SUBSEQ if start in anchors else _LOOSE_SUBSEQ
        best = max(best, base * len(p) / span)
    if best:
        return best

    # Last resort, and the only tier that tolerates a transposition ("arabai").
    from difflib import SequenceMatcher
    return SequenceMatcher(None, p, n).ratio()


def _shortest_span(p: str, n: str, start: int) -> int | None:
    """Length of the window of `n` from `start` containing `p` in order, or None."""
    k = 0
    for i in range(start, len(n)):
        if n[i] == p[k]:
            k += 1
            if k == len(p):
                return i - start + 1
    return None


def suggest(prefix: str, usages: list[Usage], threshold: float) -> str | None:
    """The single best completion for `prefix`, or None if nothing clears `threshold`.

    Similarity leads and recency breaks ties: scores are compared at two decimals so
    that several equally-good prefix matches are decided by which was used last, which
    is what makes the suggestion track the current week's work.
    """
    ranked = [
        (round(s, 2), u.last_used, u.name)
        for u in usages
        if (s := score(prefix, u.name)) >= threshold
    ]
    if not ranked:
        return None
    name = max(ranked)[2]
    return name if name.lower() != prefix.lower() else None
