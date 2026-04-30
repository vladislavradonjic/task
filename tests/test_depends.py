from task.commands import blocks_, depends_, modify_
from task.events import apply_event
from task.models import ParsedFilter, ParsedModification, Task, UpdatedEvent
from task.storage import assign_display_ids


def _tasks(*descriptions):
    tasks = [Task(description=d) for d in descriptions]
    assign_display_ids(tasks)
    return tasks


# ---------------------------------------------------------------------------
# depends_
# ---------------------------------------------------------------------------

def test_depends_add_single():
    tasks = _tasks("a", "b")
    events, msg = depends_(tasks, ParsedFilter(ids=[1]), ParsedModification(description="2"))
    assert len(events) == 1
    assert isinstance(events[0], UpdatedEvent)
    after = apply_event(tasks, events[0])
    assert tasks[1].uuid in after[0].depends
    assert "Updated" in msg


def test_depends_add_multiple_comma_separated():
    tasks = _tasks("a", "b", "c")
    events, _ = depends_(tasks, ParsedFilter(ids=[1]), ParsedModification(description="2,3"))
    after = apply_event(tasks, events[0])
    assert tasks[1].uuid in after[0].depends
    assert tasks[2].uuid in after[0].depends


def test_depends_add_multiple_space_separated():
    tasks = _tasks("a", "b", "c")
    events, _ = depends_(tasks, ParsedFilter(ids=[1]), ParsedModification(description="2 3"))
    after = apply_event(tasks, events[0])
    assert tasks[1].uuid in after[0].depends
    assert tasks[2].uuid in after[0].depends


def test_depends_remove():
    tasks = _tasks("a", "b")
    tasks[0].depends = [tasks[1].uuid]
    events, _ = depends_(tasks, ParsedFilter(ids=[1]), ParsedModification(description="-2"))
    after = apply_event(tasks, events[0])
    assert after[0].depends == []


def test_depends_mixed_add_and_remove():
    tasks = _tasks("a", "b", "c")
    tasks[0].depends = [tasks[1].uuid]
    events, _ = depends_(tasks, ParsedFilter(ids=[1]), ParsedModification(description="3,-2"))
    after = apply_event(tasks, events[0])
    assert tasks[2].uuid in after[0].depends
    assert tasks[1].uuid not in after[0].depends


def test_depends_deduplication():
    tasks = _tasks("a", "b")
    tasks[0].depends = [tasks[1].uuid]
    events, msg = depends_(tasks, ParsedFilter(ids=[1]), ParsedModification(description="2"))
    assert events == []
    assert "Nothing" in msg


def test_depends_self_reference_is_noop():
    tasks = _tasks("a", "b")
    events, msg = depends_(tasks, ParsedFilter(ids=[1]), ParsedModification(description="1"))
    assert events == []
    assert "Nothing" in msg


def test_depends_cycle_direct_rejected():
    tasks = _tasks("a", "b")
    tasks[0].depends = [tasks[1].uuid]  # a depends on b
    events, msg = depends_(tasks, ParsedFilter(ids=[2]), ParsedModification(description="1"))
    assert events == []
    assert "cycle" in msg.lower()


def test_depends_cycle_transitive_rejected():
    tasks = _tasks("a", "b", "c")
    tasks[0].depends = [tasks[1].uuid]  # a depends on b
    tasks[1].depends = [tasks[2].uuid]  # b depends on c
    # adding c depends on a would close the cycle
    events, msg = depends_(tasks, ParsedFilter(ids=[3]), ParsedModification(description="1"))
    assert events == []
    assert "cycle" in msg.lower()


def test_depends_unknown_id():
    tasks = _tasks("a")
    events, msg = depends_(tasks, ParsedFilter(ids=[1]), ParsedModification(description="99"))
    assert events == []
    assert "Unknown" in msg


def test_depends_empty_filter():
    tasks = _tasks("a", "b")
    events, msg = depends_(tasks, ParsedFilter(), ParsedModification(description="2"))
    assert events == []
    assert "No filter" in msg


def test_depends_no_ids_given():
    tasks = _tasks("a")
    events, msg = depends_(tasks, ParsedFilter(ids=[1]), ParsedModification(description=""))
    assert events == []
    assert "No dependency" in msg


def test_depends_plus_prefix_adds():
    tasks = _tasks("a", "b")
    events, _ = depends_(tasks, ParsedFilter(ids=[1]), ParsedModification(description="+2"))
    after = apply_event(tasks, events[0])
    assert tasks[1].uuid in after[0].depends


# ---------------------------------------------------------------------------
# blocks_
# ---------------------------------------------------------------------------

def test_blocks_add():
    tasks = _tasks("a", "b")
    # task 1 blocks task 2 → task 2 depends on task 1
    events, msg = blocks_(tasks, ParsedFilter(ids=[1]), ParsedModification(description="2"))
    assert len(events) == 1
    after = apply_event(tasks, events[0])
    assert tasks[0].uuid in after[1].depends
    assert "Updated" in msg


def test_blocks_add_multiple_targets():
    tasks = _tasks("a", "b", "c")
    events, _ = blocks_(tasks, ParsedFilter(ids=[1]), ParsedModification(description="2,3"))
    result = tasks[:]
    for e in events:
        result = apply_event(result, e)
    blocker_uuid = tasks[0].uuid
    assert blocker_uuid in result[1].depends
    assert blocker_uuid in result[2].depends


def test_blocks_remove():
    tasks = _tasks("a", "b")
    tasks[1].depends = [tasks[0].uuid]  # b depends on a (a blocks b)
    events, _ = blocks_(tasks, ParsedFilter(ids=[1]), ParsedModification(description="-2"))
    after = apply_event(tasks, events[0])
    assert after[1].depends == []


def test_blocks_deduplication():
    tasks = _tasks("a", "b")
    tasks[1].depends = [tasks[0].uuid]
    events, msg = blocks_(tasks, ParsedFilter(ids=[1]), ParsedModification(description="2"))
    assert events == []
    assert "Nothing" in msg


def test_blocks_cycle_rejected():
    tasks = _tasks("a", "b")
    tasks[0].depends = [tasks[1].uuid]  # a depends on b (b blocks a)
    # adding a blocks b would mean b depends on a → cycle
    events, msg = blocks_(tasks, ParsedFilter(ids=[1]), ParsedModification(description="2"))
    assert events == []
    assert "cycle" in msg.lower()


def test_blocks_empty_filter():
    tasks = _tasks("a", "b")
    events, msg = blocks_(tasks, ParsedFilter(), ParsedModification(description="2"))
    assert events == []
    assert "No filter" in msg


def test_blocks_no_targets_given():
    tasks = _tasks("a")
    events, msg = blocks_(tasks, ParsedFilter(ids=[1]), ParsedModification(description=""))
    assert events == []
    assert "No target" in msg


def test_blocks_unknown_id():
    tasks = _tasks("a")
    events, msg = blocks_(tasks, ParsedFilter(ids=[1]), ParsedModification(description="99"))
    assert events == []
    assert "Unknown" in msg


# ---------------------------------------------------------------------------
# modify depends:
# ---------------------------------------------------------------------------

def test_modify_depends_add():
    tasks = _tasks("a", "b")
    events, _ = modify_(tasks, ParsedFilter(ids=[1]), ParsedModification(properties={"depends": "2"}))
    after = apply_event(tasks, events[0])
    assert tasks[1].uuid in after[0].depends


def test_modify_depends_remove():
    tasks = _tasks("a", "b")
    tasks[0].depends = [tasks[1].uuid]
    events, _ = modify_(tasks, ParsedFilter(ids=[1]), ParsedModification(properties={"depends": "-2"}))
    after = apply_event(tasks, events[0])
    assert after[0].depends == []


def test_modify_depends_mixed():
    tasks = _tasks("a", "b", "c")
    tasks[0].depends = [tasks[1].uuid]
    events, _ = modify_(tasks, ParsedFilter(ids=[1]), ParsedModification(properties={"depends": "3,-2"}))
    after = apply_event(tasks, events[0])
    assert tasks[2].uuid in after[0].depends
    assert tasks[1].uuid not in after[0].depends


def test_modify_depends_clear():
    tasks = _tasks("a", "b", "c")
    tasks[0].depends = [tasks[1].uuid, tasks[2].uuid]
    events, _ = modify_(tasks, ParsedFilter(ids=[1]), ParsedModification(properties={"depends": None}))
    after = apply_event(tasks, events[0])
    assert after[0].depends == []


def test_modify_depends_cycle_rejected():
    tasks = _tasks("a", "b")
    tasks[0].depends = [tasks[1].uuid]
    events, msg = modify_(tasks, ParsedFilter(ids=[2]), ParsedModification(properties={"depends": "1"}))
    assert events == []
    assert "cycle" in msg.lower()


def test_modify_depends_unknown_id():
    tasks = _tasks("a")
    events, msg = modify_(tasks, ParsedFilter(ids=[1]), ParsedModification(properties={"depends": "99"}))
    assert events == []
    assert "Unknown" in msg
