from datetime import datetime
from uuid import UUID

import networkx as nx

from task.models import Task

# Default coefficients per urgency.md.
# due-based factors (overdue +12, approaching due 0…+12) are deferred until
# `due` is a typed first-class field on Task rather than a raw property string.
_COEFF = {
    "priority_H":  6.0,
    "priority_M":  3.9,
    "priority_L":  1.8,
    "age":         2.0,   # max contribution at 365 days
    "active":      4.0,
    "blocking":    8.0,
    "blocked":    -5.0,
    "waiting":    -5.0,
    "has_tags":    1.0,
    "has_project": 1.0,
}

_TOPO_EPS = 0.001


def _base_score(task: Task, g: nx.DiGraph, now: datetime) -> float:
    score = 0.0

    priority = task.properties.get("priority")
    if priority == "H":
        score += _COEFF["priority_H"]
    elif priority == "M":
        score += _COEFF["priority_M"]
    elif priority == "L":
        score += _COEFF["priority_L"]

    # Strip tzinfo for arithmetic so naive and aware entries both work.
    entry = task.entry.replace(tzinfo=None)
    now_naive = now.replace(tzinfo=None) if now.tzinfo is not None else now
    age_days = max(0.0, (now_naive - entry).total_seconds() / 86400)
    score += _COEFF["age"] * min(age_days / 365.0, 1.0)

    if task.start is not None:
        score += _COEFF["active"]

    if g.out_degree(task.uuid) > 0:
        score += _COEFF["blocking"]

    if g.in_degree(task.uuid) > 0:
        score += _COEFF["blocked"]

    if task.status == "waiting":
        score += _COEFF["waiting"]

    if task.tags:
        score += _COEFF["has_tags"]

    if task.properties.get("project"):
        score += _COEFF["has_project"]

    return score


def compute_urgency(tasks: list[Task], now: datetime | None = None) -> dict[UUID, float]:
    """Return urgency scores for all pending/waiting tasks.

    Done and deleted tasks are excluded; they have no defined urgency.
    The topological bump ensures every blocker ranks strictly above its blockees.
    """
    if now is None:
        now = datetime.now()

    active = [t for t in tasks if t.status in ("pending", "waiting")]
    active_uuids = {t.uuid for t in active}

    g = nx.DiGraph()
    g.add_nodes_from(active_uuids)
    for task in active:
        for dep_uuid in task.depends:
            if dep_uuid in active_uuids:
                g.add_edge(dep_uuid, task.uuid)

    scores: dict[UUID, float] = {t.uuid: _base_score(t, g, now) for t in active}

    # Topological bump: walk blockees-first (reverse topo order) so each
    # blocker X is processed after all its blockees Y are finalised.
    # urgency(X) = max(urgency(X), max(urgency(Y) for Y in successors) + ε)
    try:
        for node in reversed(list(nx.topological_sort(g))):
            successors = list(g.successors(node))
            if successors:
                max_suc = max(scores[s] for s in successors)
                scores[node] = max(scores[node], max_suc + _TOPO_EPS)
    except nx.NetworkXUnfeasible:
        pass  # cycle-free by construction; this is a safety net

    return scores
