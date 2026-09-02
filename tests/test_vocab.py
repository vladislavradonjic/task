"""Project and kind vocabularies — docs/projects.md.

The rules under test: a project is discovered from tasks *and* timesheet rows and is
windowed, a kind comes from config and is not, similarity leads the ranking with
recency as the tie-break, and a fragment too weak to identify anything suggests nothing.
"""

from datetime import datetime, timedelta

import pytest

from task.models import Entry, Task
from task.vocab import kind_usage, project_usage, score, suggest, window_start

NOW = datetime(2026, 9, 2, 10, 0)


def _t(project=None, status="pending", entry=NOW, end=None):
    props = {"project": project} if project else {}
    return Task(description="x", status=status, properties=props, entry=entry, end=end)


def _e(project=None, kind="solo", from_=None, til=None):
    return Entry(kind=kind, project=project, from_=from_, til=til)


def _row(project, kind, day_offset):
    """A closed one-hour row anchored `day_offset` days before NOW."""
    start = NOW - timedelta(days=day_offset)
    return _e(project=project, kind=kind, from_=start, til=start + timedelta(hours=1))


# --- windows -----------------------------------------------------------------


def test_bare_offsets_read_backwards():
    assert window_start("3m", NOW) == datetime(2026, 6, 2, 10, 0)
    assert window_start("2w", NOW) == datetime(2026, 8, 19, 10, 0)


def test_a_signed_offset_is_not_negated_twice():
    """`--3m` reaches dateutil as a time of day; the sign has to be ours to impose."""
    assert window_start("-3m", NOW) == window_start("3m", NOW)


def test_all_means_no_cutoff():
    assert window_start("all", NOW) is None
    assert window_start(" ALL ", NOW) is None


def test_an_explicit_date_serves_as_a_cutoff():
    assert window_start("2026-01-15", NOW) == datetime(2026, 1, 15, 0, 0)


def test_an_unparseable_window_raises():
    with pytest.raises(ValueError):
        window_start("garbage", NOW)


# --- project usage -----------------------------------------------------------


def test_projects_come_from_tasks_and_entries_alike():
    usages = project_usage([_t("alpha")], [_row("beta", "solo", 1)], None)
    assert [u.name for u in usages] == ["alpha", "beta"]


def test_counts_are_kept_apart_per_entity():
    usages = project_usage(
        [_t("alpha"), _t("alpha")],
        [_row("alpha", "solo", 1)],
        None,
    )
    u = usages[0]
    assert (u.tasks, u.entries, u.total) == (2, 1, 3)


def test_ordering_is_by_total_then_name():
    usages = project_usage([_t("zeta"), _t("alpha"), _t("alpha")], [], None)
    assert [u.name for u in usages] == ["alpha", "zeta"]


def test_the_window_drops_a_stale_closed_task():
    old = _t("ancient", status="done", entry=NOW - timedelta(days=400),
             end=NOW - timedelta(days=390))
    assert project_usage([old], [], window_start("3m", NOW)) == []


def test_a_closed_task_counts_at_its_end_not_its_entry():
    """An old task finished last week is recent use of its project."""
    recent = _t("revived", status="done", entry=NOW - timedelta(days=400),
                end=NOW - timedelta(days=3))
    usages = project_usage([recent], [], window_start("3m", NOW))
    assert [u.name for u in usages] == ["revived"]


def test_an_active_task_survives_any_window():
    """A pending task is current by definition, however long ago it was written."""
    old = _t("longhaul", entry=NOW - timedelta(days=400))
    assert [u.name for u in project_usage([old], [], window_start("3m", NOW))] == ["longhaul"]


def test_the_window_drops_a_stale_row():
    rows = [_row("old", "solo", 400), _row("new", "solo", 2)]
    assert [u.name for u in project_usage([], rows, window_start("3m", NOW))] == ["new"]


def test_a_derived_row_is_placed_by_the_row_before_it():
    """`from_` is None on a non-anchoring row, so only resolve() can date it."""
    anchor = _row("alpha", "solo", 1)
    derived = _e(project="beta", til=anchor.til + timedelta(hours=2))
    usages = project_usage([], [anchor, derived], window_start("3m", NOW))
    assert [u.name for u in usages] == ["alpha", "beta"]


def test_last_used_is_the_most_recent_touch():
    rows = [_row("alpha", "solo", 9), _row("alpha", "solo", 2)]
    assert project_usage([], rows, None)[0].last_used == NOW - timedelta(days=2)


# --- kind usage --------------------------------------------------------------


def test_every_configured_kind_is_a_candidate():
    """The vocabulary is closed, so a kind never logged still has to complete."""
    usages = kind_usage([_row("a", "chat", 1)], ["solo", "chat", "junk"])
    assert {u.name for u in usages} == {"solo", "chat", "junk"}


def test_used_kinds_sort_ahead_of_unused_ones():
    usages = kind_usage([_row("a", "chat", 1)], ["solo", "chat"])
    assert [u.name for u in usages] == ["chat", "solo"]


def test_a_kind_dropped_from_config_is_not_resurrected_by_old_rows():
    usages = kind_usage([_row("a", "retired", 1)], ["solo"])
    assert [u.name for u in usages] == ["solo"]


def test_kinds_ignore_the_window_entirely():
    """kind_usage takes no cutoff: a kind unused for a year is still legal input."""
    usages = kind_usage([_row("a", "junk", 400)], ["solo", "junk"])
    assert [u.name for u in usages] == ["junk", "solo"]


# --- scoring -----------------------------------------------------------------


def test_a_prefix_of_the_whole_name_scores_top():
    assert score("ar", "Arabia") == 1.0


def test_matching_is_case_insensitive():
    assert score("AR", "arabia") == score("ar", "Arabia") == 1.0


def test_a_dotted_segment_prefix_scores_just_below():
    assert score("acme", "work.acme") == 0.9


def test_a_compact_subsequence_beats_a_scattered_one():
    assert score("arb", "Arabia") > score("aia", "Arabia")


def test_one_or_two_characters_only_ever_prefix_match():
    """Without the floor, "b" scores 0.8 against Arabia and the example breaks."""
    assert score("b", "Arabia") == 0.0
    assert score("bi", "Arabia") == 0.0
    assert score("b", "work.billing") == 0.9


def test_a_transposition_still_scores():
    assert score("arabai", "Arabia") > 0.6


def test_nothing_in_common_scores_nothing_much():
    assert score("xyz", "Arabia") < 0.3


# --- suggestion --------------------------------------------------------------


def _pool(*pairs):
    """Usages named and dated by (name, days-ago)."""
    return kind_usage(
        [_row(None, name, days) for name, days in pairs],
        [name for name, _ in pairs],
    )


def test_the_best_match_is_offered():
    assert suggest("aus", _pool(("Arabia", 1), ("Australia", 30)), 0.6) == "Australia"


def test_equal_similarity_is_broken_by_recency():
    """Arabia, Albania and Australia all score 1.0 on "a" — the last used one wins."""
    pool = _pool(("Arabia", 9), ("Albania", 2), ("Australia", 30))
    assert suggest("a", pool, 0.6) == "Albania"


def test_nothing_is_offered_below_the_threshold():
    assert suggest("b", _pool(("Arabia", 1), ("Albania", 2)), 0.6) is None


def test_the_threshold_is_honoured():
    pool = _pool(("Arabia", 1))
    assert suggest("arb", pool, 0.6) == "Arabia"   # scores exactly 0.6
    assert suggest("arb", pool, 0.7) is None


def test_a_complete_name_suggests_nothing_more():
    assert suggest("Arabia", _pool(("Arabia", 1)), 0.6) is None


def test_an_empty_fragment_suggests_nothing():
    assert suggest("", _pool(("Arabia", 1)), 0.6) is None


def test_an_empty_pool_suggests_nothing():
    assert suggest("a", [], 0.6) is None


# --- the `projects` command --------------------------------------------------


def _cfg(window="3m"):
    from task.config import Config, ProjectsConfig

    return Config(projects=ProjectsConfig(window=window))


def _run(tasks, entries, argv=""):
    from task.commands import projects_
    from task.parse import parse_filter, parse_modification

    return projects_(entries, tasks, parse_filter([]), parse_modification(argv.split()), _cfg())


def test_projects_command_reports_an_empty_store():
    events, message = _run([], [])
    assert events == []
    assert message == "No projects in use in the last 3m."


def test_projects_command_names_the_window_it_used():
    _, message = _run([_t("ancient", status="done",
                               entry=datetime(2020, 1, 1), end=datetime(2020, 1, 2))], [])
    assert message == "No projects in use in the last 3m."


def test_projects_command_all_drops_the_window():
    events, message = _run(
        [_t("ancient", status="done", entry=datetime(2020, 1, 1), end=datetime(2020, 1, 2))],
        [],
        argv="all",
    )
    assert (events, message) == ([], "")


def test_projects_command_renders_both_entities(capsys):
    _run([_t("alpha")], [_row("beta", "solo", 1)])
    out = capsys.readouterr().out
    assert "alpha" in out and "beta" in out
    assert "Tasks" in out and "Rows" in out


def test_projects_command_refuses_a_bad_window():
    events, message = _run([_t("alpha")], [], argv="banana")
    assert events == []
    assert "banana" in message
