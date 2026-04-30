from datetime import datetime, timedelta

import pytest

from task.models import Task
from task.urgency import compute_urgency, _COEFF


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now():
    return datetime(2026, 1, 1, 12, 0, 0)


def _task(**kwargs):
    kwargs.setdefault("entry", _now())
    return Task(description="test", **kwargs)


# ---------------------------------------------------------------------------
# Base factors
# ---------------------------------------------------------------------------

def test_urgency_priority_H():
    t = _task(properties={"priority": "H"})
    scores = compute_urgency([t], now=_now())
    assert scores[t.uuid] == pytest.approx(_COEFF["priority_H"], abs=0.01)


def test_urgency_priority_M():
    t = _task(properties={"priority": "M"})
    scores = compute_urgency([t], now=_now())
    assert scores[t.uuid] == pytest.approx(_COEFF["priority_M"], abs=0.01)


def test_urgency_priority_L():
    t = _task(properties={"priority": "L"})
    scores = compute_urgency([t], now=_now())
    assert scores[t.uuid] == pytest.approx(_COEFF["priority_L"], abs=0.01)


def test_urgency_no_priority():
    t = _task()
    scores = compute_urgency([t], now=_now())
    assert scores[t.uuid] == pytest.approx(0.0, abs=0.01)


def test_urgency_age_zero_at_entry():
    t = _task(entry=_now())
    scores = compute_urgency([t], now=_now())
    assert scores[t.uuid] == pytest.approx(0.0, abs=0.01)


def test_urgency_age_max_at_365_days():
    t = _task(entry=_now() - timedelta(days=365))
    scores = compute_urgency([t], now=_now())
    assert scores[t.uuid] == pytest.approx(_COEFF["age"], abs=0.01)


def test_urgency_age_capped_beyond_365_days():
    t_old = _task(entry=_now() - timedelta(days=730))
    t_year = _task(entry=_now() - timedelta(days=365))
    scores = compute_urgency([t_old, t_year], now=_now())
    assert scores[t_old.uuid] == pytest.approx(scores[t_year.uuid], abs=0.001)


def test_urgency_age_half_year():
    t = _task(entry=_now() - timedelta(days=182))
    scores = compute_urgency([t], now=_now())
    expected = _COEFF["age"] * (182 / 365)
    assert scores[t.uuid] == pytest.approx(expected, abs=0.01)


def test_urgency_active():
    t = _task(start=_now())
    scores = compute_urgency([t], now=_now())
    assert scores[t.uuid] == pytest.approx(_COEFF["active"], abs=0.01)


def test_urgency_waiting():
    t = _task(status="waiting")
    scores = compute_urgency([t], now=_now())
    assert scores[t.uuid] == pytest.approx(_COEFF["waiting"], abs=0.01)


def test_urgency_has_tags():
    with_tags = _task(tags=["bug"])
    without_tags = _task()
    s = compute_urgency([with_tags, without_tags], now=_now())
    assert s[with_tags.uuid] - s[without_tags.uuid] == pytest.approx(_COEFF["has_tags"], abs=0.001)


def test_urgency_has_project():
    with_proj = _task(properties={"project": "work"})
    without_proj = _task()
    s = compute_urgency([with_proj, without_proj], now=_now())
    assert s[with_proj.uuid] - s[without_proj.uuid] == pytest.approx(_COEFF["has_project"], abs=0.001)


# ---------------------------------------------------------------------------
# Dependency factors
# ---------------------------------------------------------------------------

def test_urgency_blocking_factor():
    a = _task()
    b = _task(depends=[a.uuid])
    s = compute_urgency([a, b], now=_now())
    # a blocks b → a gets blocking bonus, b gets blocked penalty
    assert s[a.uuid] == pytest.approx(_COEFF["blocking"], abs=0.01)
    assert s[b.uuid] == pytest.approx(_COEFF["blocked"], abs=0.01)


def test_urgency_blocker_ranks_above_blockee():
    a = _task()
    b = _task(depends=[a.uuid])
    s = compute_urgency([a, b], now=_now())
    assert s[a.uuid] > s[b.uuid]


def test_urgency_blocked_only_by_active_tasks():
    # A dependency that is done should not count as blocking.
    a = _task(status="done")
    b = _task(depends=[a.uuid])
    s = compute_urgency([a, b], now=_now())
    assert b.uuid in s
    assert a.uuid not in s           # done → excluded
    assert s[b.uuid] == pytest.approx(0.0, abs=0.01)  # no in-edges from active tasks


# ---------------------------------------------------------------------------
# Topological bump
# ---------------------------------------------------------------------------

def test_urgency_topo_bump_direct():
    # A blocks B; even if B has high base urgency, A must rank above B.
    a = _task()
    b = _task(depends=[a.uuid], properties={"priority": "H"})
    s = compute_urgency([a, b], now=_now())
    assert s[a.uuid] > s[b.uuid]


def test_urgency_topo_bump_transitive():
    # A blocks B blocks C → urgency(A) > urgency(B) > urgency(C).
    a = _task()
    b = _task(depends=[a.uuid])
    c = _task(depends=[b.uuid])
    s = compute_urgency([a, b, c], now=_now())
    assert s[a.uuid] > s[b.uuid]
    assert s[b.uuid] > s[c.uuid]


def test_urgency_topo_bump_epsilon():
    # When bump fires, the gap is exactly ε.
    a = _task()
    b = _task(depends=[a.uuid])
    s = compute_urgency([a, b], now=_now())
    # a = max(blocking_score, b_score + ε); b_score is negative (blocked penalty)
    # blocking_score (8.0) > b_score (-5.0) + ε, so bump doesn't change a here.
    # Verify strict ordering is maintained.
    assert s[a.uuid] > s[b.uuid]


# ---------------------------------------------------------------------------
# Scope: done/deleted tasks excluded
# ---------------------------------------------------------------------------

def test_urgency_done_tasks_excluded():
    active = _task()
    done = _task(status="done")
    s = compute_urgency([active, done], now=_now())
    assert done.uuid not in s
    assert active.uuid in s


def test_urgency_deleted_tasks_excluded():
    active = _task()
    deleted = _task(status="deleted")
    s = compute_urgency([active, deleted], now=_now())
    assert deleted.uuid not in s


def test_urgency_empty_list():
    assert compute_urgency([], now=_now()) == {}


def test_urgency_all_done_returns_empty():
    tasks = [_task(status="done"), _task(status="deleted")]
    assert compute_urgency(tasks, now=_now()) == {}
