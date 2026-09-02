"""REPL behaviour: parity with one-shot mode, and the shell-layer wiring around it.

The command functions are pure and covered elsewhere; what needs testing here is the
loop in cli.py — which context it writes to, when it reloads, and how it reports errors.
"""

import json
import re

import pytest

from task import cli, commands, storage
from task.models import ParsedFilter, ParsedModification


def _init(tmp_data_dir):
    commands.init_(ParsedFilter(), ParsedModification())
    return tmp_data_dir


def _drive(monkeypatch, lines):
    """Run the REPL over a scripted set of input lines."""
    supplied = iter(lines)

    def fake_input(prompt=""):
        try:
            return next(supplied)
        except StopIteration:
            raise EOFError
    monkeypatch.setattr("builtins.input", fake_input)


def _events(context):
    path = context / "events.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# Only wall-clock fields are masked. Times the script states explicitly — `from_`, `til`,
# `due` — are left intact, so the comparison really does check that both modes place a
# timesheet row at the same moment.
_NONDETERMINISTIC = ("ts", "entry", "end", "undid_ts")


def _normalise(events):
    """Strip identity and generated timestamps so two runs can be compared."""
    seen: dict = {}

    def ident(value):
        return seen.setdefault(value, f"U{len(seen)}")

    out = []
    for event in events:
        blob = json.dumps(event, sort_keys=True)
        blob = re.sub(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            lambda m: ident(m.group(0)),
            blob,
        )
        for field in _NONDETERMINISTIC:
            blob = re.sub(rf'"{field}": "\d{{4}}-\d\d-\d\dT[\d:.]+"', f'"{field}": "TS"', blob)
        out.append(blob)
    return out


# ---------------------------------------------------------------------------
# context switching — the loop must not cache the context across commands
# ---------------------------------------------------------------------------

def test_context_use_redirects_later_writes(tmp_data_dir, monkeypatch):
    _init(tmp_data_dir)
    _drive(monkeypatch, [
        "context create work",
        "context use work",
        "add should land in work",
    ])
    cli._repl_loop(tmp_data_dir)

    assert _events(tmp_data_dir / "default") == []
    landed = _events(tmp_data_dir / "work")
    assert len(landed) == 1
    assert landed[0]["snapshot"]["description"] == "should land in work"


def test_context_use_then_back_again(tmp_data_dir, monkeypatch):
    _init(tmp_data_dir)
    _drive(monkeypatch, [
        "add in default",
        "context create work",
        "context use work",
        "add in work",
        "context use default",
        "add in default again",
    ])
    cli._repl_loop(tmp_data_dir)

    default = [e["snapshot"]["description"] for e in _events(tmp_data_dir / "default")]
    work = [e["snapshot"]["description"] for e in _events(tmp_data_dir / "work")]
    assert default == ["in default", "in default again"]
    assert work == ["in work"]


def test_bare_context_reports_where_writes_go(tmp_data_dir, monkeypatch, capsys):
    _init(tmp_data_dir)
    _drive(monkeypatch, ["context create work", "context use work", "context"])
    cli._repl_loop(tmp_data_dir)
    assert "work" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# differential parity: the REPL must emit the same events as one-shot mode
# ---------------------------------------------------------------------------

SCRIPT = [
    # tasks
    "add write the parser project:work.parse due:tomorrow",
    "add review the docs project:work",
    "add unrelated chore",
    "1 modify priority:H",
    "2 depends 1",
    "1 today",
    "2 week",
    # timesheet — explicit times only, so both runs place rows identically
    "log standup kind:meeting project:internal from:6:00 til:6:30",
    "log write the parser kind:solo project:work.parse task:1 til:8:20",
    "log slack kind:junk til:8:45",
    "log kind:call project:work til:9:15",
    "a modify til:7:00",
    "c delete",
    "day",
    # back to tasks, then undo across both tracks
    "1 done",
    "3 delete",
    "today",
    "undo",
    "undo",
]


def test_repl_and_one_shot_produce_identical_events(tmp_path, monkeypatch):
    one_shot = tmp_path / "one_shot"
    repl = tmp_path / "repl"

    monkeypatch.setenv("TASK_DATA_DIR", str(one_shot))
    commands.init_(ParsedFilter(), ParsedModification())
    for line in SCRIPT:
        monkeypatch.setattr("sys.argv", ["tsk", *line.split()])
        cli.main()

    monkeypatch.setenv("TASK_DATA_DIR", str(repl))
    commands.init_(ParsedFilter(), ParsedModification())
    _drive(monkeypatch, list(SCRIPT))
    cli._repl_loop(repl)

    assert _normalise(_events(repl / "default")) == _normalise(_events(one_shot / "default"))


# ---------------------------------------------------------------------------
# loop control and command gating
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("word", ["exit", "quit"])
def test_exit_words_leave_the_loop(tmp_data_dir, monkeypatch, word):
    _init(tmp_data_dir)
    _drive(monkeypatch, [word, "add never runs"])
    cli._repl_loop(tmp_data_dir)
    assert _events(tmp_data_dir / "default") == []


def test_eof_leaves_the_loop(tmp_data_dir, monkeypatch):
    _init(tmp_data_dir)
    _drive(monkeypatch, [])
    cli._repl_loop(tmp_data_dir)  # must return rather than raise


def test_run_is_rejected_inside_the_repl(tmp_data_dir, monkeypatch, capsys):
    _init(tmp_data_dir)
    _drive(monkeypatch, ["run"])
    cli._repl_loop(tmp_data_dir)
    assert "Already in the REPL" in capsys.readouterr().err


def test_init_is_rejected_inside_the_repl(tmp_data_dir, monkeypatch, capsys):
    _init(tmp_data_dir)
    _drive(monkeypatch, ["init"])
    cli._repl_loop(tmp_data_dir)
    assert "not available in the REPL" in capsys.readouterr().err


def test_unrecognised_line_names_the_line_not_the_first_token(tmp_data_dir, monkeypatch, capsys):
    _init(tmp_data_dir)
    _drive(monkeypatch, ["project:work lst"])
    cli._repl_loop(tmp_data_dir)
    err = capsys.readouterr().err
    assert "project:work lst" in err
    assert "Unknown command: 'project:work'" not in err


def test_blank_lines_are_ignored(tmp_data_dir, monkeypatch):
    _init(tmp_data_dir)
    _drive(monkeypatch, ["", "   ", "add real task"])
    cli._repl_loop(tmp_data_dir)
    assert len(_events(tmp_data_dir / "default")) == 1


def test_unbalanced_quotes_report_a_parse_error(tmp_data_dir, monkeypatch, capsys):
    _init(tmp_data_dir)
    _drive(monkeypatch, ['add "unclosed'])
    cli._repl_loop(tmp_data_dir)
    assert "Parse error" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# error reporting
# ---------------------------------------------------------------------------

def test_command_errors_do_not_kill_the_loop(tmp_data_dir, monkeypatch):
    _init(tmp_data_dir)
    _drive(monkeypatch, ["1 modify due:notadate", "add still alive"])
    cli._repl_loop(tmp_data_dir)
    assert len(_events(tmp_data_dir / "default")) == 1


def test_task_debug_prints_a_traceback(tmp_data_dir, monkeypatch, capsys):
    _init(tmp_data_dir)
    monkeypatch.setenv("TASK_DEBUG", "1")
    monkeypatch.setattr(commands, "add_", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    _drive(monkeypatch, ["add anything"])
    cli._repl_loop(tmp_data_dir)
    assert "Traceback" in capsys.readouterr().err


def test_without_task_debug_only_one_line_is_printed(tmp_data_dir, monkeypatch, capsys):
    _init(tmp_data_dir)
    monkeypatch.delenv("TASK_DEBUG", raising=False)
    monkeypatch.setattr(commands, "add_", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    _drive(monkeypatch, ["add anything"])
    cli._repl_loop(tmp_data_dir)
    err = capsys.readouterr().err.strip()
    assert err == "RuntimeError: boom"


# ---------------------------------------------------------------------------
# config reload
# ---------------------------------------------------------------------------

def test_config_edits_are_picked_up_without_restarting(tmp_data_dir):
    _init(tmp_data_dir)
    config = tmp_data_dir / "config.toml"
    config.write_text('[list]\nsort = "entry"\n', encoding="utf-8")
    cfg_a, stamp_a = cli._load_cfg(tmp_data_dir)
    assert cfg_a.list.sort == "entry"

    config.write_text('[list]\nsort = "urgency"\n', encoding="utf-8")
    cfg_b, stamp_b = cli._load_cfg(tmp_data_dir, cfg_a, stamp_a)
    assert cfg_b.list.sort == "urgency"
    assert stamp_b != stamp_a


def test_config_is_not_reparsed_when_unchanged(tmp_data_dir):
    _init(tmp_data_dir)
    (tmp_data_dir / "config.toml").write_text("[list]\nsort = \"urgency\"\n", encoding="utf-8")
    cfg_a, stamp_a = cli._load_cfg(tmp_data_dir)
    cfg_b, stamp_b = cli._load_cfg(tmp_data_dir, cfg_a, stamp_a)
    assert cfg_b is cfg_a
    assert stamp_b == stamp_a


# ---------------------------------------------------------------------------
# one-shot entry point: tracebacks stay off the terminal unless asked for
# ---------------------------------------------------------------------------

def test_main_reports_unexpected_errors_on_one_line(tmp_data_dir, monkeypatch, capsys):
    _init(tmp_data_dir)
    monkeypatch.delenv("TASK_DEBUG", raising=False)
    monkeypatch.setattr(cli, "_main", lambda: (_ for _ in ()).throw(RuntimeError("disk on fire")))
    with pytest.raises(SystemExit) as exit_info:
        cli.main()
    assert exit_info.value.code == 1
    assert capsys.readouterr().err.strip() == "RuntimeError: disk on fire"


def test_main_reraises_under_task_debug(tmp_data_dir, monkeypatch):
    _init(tmp_data_dir)
    monkeypatch.setenv("TASK_DEBUG", "1")
    monkeypatch.setattr(cli, "_main", lambda: (_ for _ in ()).throw(RuntimeError("disk on fire")))
    with pytest.raises(RuntimeError):
        cli.main()


def test_main_passes_through_deliberate_exits(tmp_data_dir, monkeypatch):
    _init(tmp_data_dir)
    monkeypatch.setattr(cli, "_main", lambda: (_ for _ in ()).throw(SystemExit(2)))
    with pytest.raises(SystemExit) as exit_info:
        cli.main()
    assert exit_info.value.code == 2


def test_corrupt_cache_does_not_crash_the_cli(tmp_data_dir, monkeypatch, capsys):
    _init(tmp_data_dir)
    monkeypatch.setattr("sys.argv", ["tsk", "add", "alpha"])
    cli.main()
    (tmp_data_dir / "default" / "tasks.json").write_text("{ truncated", encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["tsk", "list"])
    cli.main()
    assert "alpha" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# rebuild
# ---------------------------------------------------------------------------

def test_rebuild_restores_the_timesheet_cache_too(tmp_data_dir, monkeypatch):
    """rebuild is the documented recovery path, so it must cover both caches."""
    _init(tmp_data_dir)
    _drive(monkeypatch, ["log standup kind:meeting from:6:00 til:6:30"])
    cli._repl_loop(tmp_data_dir)
    context = tmp_data_dir / "default"
    (context / "entries.json").unlink()

    _, message = commands.rebuild_(ParsedFilter(), ParsedModification())
    assert (context / "entries.json").exists()
    assert "1 timesheet row" in message


def test_rebuild_reports_both_counts(tmp_data_dir, monkeypatch):
    _init(tmp_data_dir)
    monkeypatch.setattr("sys.argv", ["tsk", "add", "a task"])
    cli.main()
    _, message = commands.rebuild_(ParsedFilter(), ParsedModification())
    assert "1 task(s)" in message and "0 timesheet row(s)" in message


def test_rebuild_restores_the_cache_from_the_log(tmp_data_dir, monkeypatch):
    _init(tmp_data_dir)
    monkeypatch.setattr("sys.argv", ["tsk", "add", "from the log"])
    cli.main()
    (tmp_data_dir / "default" / "tasks.json").unlink()

    _, message = commands.rebuild_(ParsedFilter(), ParsedModification())
    assert "Rebuilt 1 task" in message
    assert storage.load_tasks(tmp_data_dir / "default")[0].description == "from the log"


def test_rebuild_is_a_no_op_on_an_empty_store(tmp_data_dir):
    _init(tmp_data_dir)
    _, message = commands.rebuild_(ParsedFilter(), ParsedModification())
    assert "Rebuilt 0 task" in message


def test_rebuild_in_the_repl_rerenders(tmp_data_dir, monkeypatch, capsys):
    _init(tmp_data_dir)
    _drive(monkeypatch, ["add alpha", "rebuild"])
    cli._repl_loop(tmp_data_dir)
    assert "Rebuilt 1 task" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# routing: shared command names reach different functions by id kind
# ---------------------------------------------------------------------------

def test_letters_route_modify_to_the_timesheet():
    from task.models import ParsedFilter
    assert cli._entry_command("modify", ParsedFilter(letters=["b"])) is commands._entry_modify


def test_digits_route_modify_to_tasks():
    from task.models import ParsedFilter
    assert cli._entry_command("modify", ParsedFilter(ids=[3])) is None


def test_letters_route_delete_to_the_timesheet():
    from task.models import ParsedFilter
    assert cli._entry_command("delete", ParsedFilter(letters=["c"])) is commands._entry_delete


def test_log_and_day_are_always_timesheet_commands():
    from task.models import ParsedFilter
    assert cli._entry_command("log", ParsedFilter()) is commands.log_
    assert cli._entry_command("day", ParsedFilter()) is commands.day_


def test_unrelated_commands_are_never_timesheet_commands():
    from task.models import ParsedFilter
    assert cli._entry_command("add", ParsedFilter(letters=["b"])) is None


def test_repl_logs_and_edits_a_row(tmp_data_dir, monkeypatch, capsys):
    _init(tmp_data_dir)
    _drive(monkeypatch, [
        "log standup kind:meeting from:6:00 til:6:30",
        "log deep work kind:solo til:8:00",
        "a modify til:7:00",
        "day",
    ])
    cli._repl_loop(tmp_data_dir)
    out = capsys.readouterr().out
    assert "07:00" in out and "1:00" in out


def test_repl_deletes_a_row(tmp_data_dir, monkeypatch):
    _init(tmp_data_dir)
    _drive(monkeypatch, [
        "log standup kind:meeting from:6:00 til:6:30",
        "log deep work kind:solo til:8:00",
        "b delete",
    ])
    cli._repl_loop(tmp_data_dir)
    entries = storage.load_entries(tmp_data_dir / "default")
    assert [e.description for e in entries] == ["standup"]


def test_repl_task_delete_still_targets_tasks(tmp_data_dir, monkeypatch):
    _init(tmp_data_dir)
    _drive(monkeypatch, ["add a task", "1 delete"])
    cli._repl_loop(tmp_data_dir)
    tasks = storage.load_tasks(tmp_data_dir / "default")
    assert [t.status for t in tasks] == ["deleted"]


# ---------------------------------------------------------------------------
# the standing view: tasks above, timesheet below
# ---------------------------------------------------------------------------

def test_default_view_shows_the_timesheet_under_the_tasks(tmp_data_dir, monkeypatch, capsys):
    _init(tmp_data_dir)
    _drive(monkeypatch, [
        "add write the parser",
        "log standup kind:meeting from:6:00 til:6:30",
    ])
    cli._repl_loop(tmp_data_dir)
    out = capsys.readouterr().out
    assert out.index("write the parser") < out.index("standup")
    assert "0:30 tracked" in out


def test_logging_a_row_re_renders_the_whole_view(tmp_data_dir, monkeypatch, capsys):
    _init(tmp_data_dir)
    _drive(monkeypatch, [
        "add a task",
        "log standup kind:meeting from:6:00 til:6:30",
    ])
    cli._repl_loop(tmp_data_dir)
    out = capsys.readouterr().out
    assert out.count("a task") >= 2  # re-rendered after the log, not just after the add


def test_editing_a_row_re_renders(tmp_data_dir, monkeypatch, capsys):
    _init(tmp_data_dir)
    _drive(monkeypatch, [
        "log standup kind:meeting from:6:00 til:6:30",
        "a modify til:7:00",
    ])
    cli._repl_loop(tmp_data_dir)
    assert "1:00" in capsys.readouterr().out


def test_day_does_not_trigger_a_second_render(tmp_data_dir, monkeypatch, capsys):
    _init(tmp_data_dir)
    _drive(monkeypatch, ["log standup kind:meeting from:6:00 til:6:30", "day"])
    cli._repl_loop(tmp_data_dir)
    out = capsys.readouterr().out
    # once from the log's re-render, once from `day` itself — not three times
    assert out.count("06:00") == 2


def test_empty_timesheet_still_nudges(tmp_data_dir, monkeypatch, capsys):
    _init(tmp_data_dir)
    _drive(monkeypatch, ["add a task"])
    cli._repl_loop(tmp_data_dir)
    assert "Nothing logged" in capsys.readouterr().out


# --- ghost-text completion ---------------------------------------------------
#
# The suggester is exercised through prompt_toolkit's own Document, which is what it
# will be handed at runtime; the pools are filled the way _refresh_suggestions fills
# them. See docs/projects.md.

prompt_toolkit = pytest.importorskip("prompt_toolkit")


def _suggester_with(tasks=(), entries=(), cfg=None):
    from task.config import Config

    cfg = cfg or Config()
    suggester = cli._make_suggester(cfg)
    cli._refresh_suggestions(suggester, list(tasks), list(entries), cfg)
    return suggester


def _ghost(suggester, text):
    from prompt_toolkit.document import Document

    suggestion = suggester.get_suggestion(None, Document(text, len(text)))
    return None if suggestion is None else suggestion.text


def _task(project):
    from task.models import Task

    return Task(description="x", properties={"project": project})


def test_a_project_prefix_is_completed():
    s = _suggester_with(tasks=[_task("arabia")])
    assert _ghost(s, "add thing project:ara") == "bia"


def test_completion_only_fires_on_the_value_half():
    s = _suggester_with(tasks=[_task("arabia")])
    assert _ghost(s, "add thing proj") is None
    assert _ghost(s, "add arabia") is None


def test_a_weak_fragment_offers_nothing():
    """The point of the threshold: project:B with no B project stays silent."""
    s = _suggester_with(tasks=[_task("arabia"), _task("albania")])
    assert _ghost(s, "add thing project:b") is None


def test_kinds_complete_from_config_not_from_use():
    """No rows logged at all, yet every configured kind is still offered."""
    s = _suggester_with()
    assert _ghost(s, "log standup kind:me") == "eting"


def test_an_unknown_property_is_not_completed():
    s = _suggester_with(tasks=[_task("arabia")])
    assert _ghost(s, "add thing priority:a") is None


def test_ctrl_g_dismisses_until_the_line_changes():
    s = _suggester_with(tasks=[_task("arabia")])
    assert _ghost(s, "add thing project:ara") == "bia"
    s.dismiss("add thing project:ara")
    assert _ghost(s, "add thing project:ara") is None
    # One more character is a different line, so the suggestion comes back.
    assert _ghost(s, "add thing project:arab") == "ia"


def test_disabling_suggestions_builds_no_suggester():
    from task.config import Config, SuggestConfig

    assert cli._make_suggester(Config(suggest=SuggestConfig(enabled=False))) is None


def test_a_malformed_window_in_config_does_not_break_the_prompt():
    from task.config import Config, ProjectsConfig

    cfg = Config(projects=ProjectsConfig(window="banana"))
    s = _suggester_with(tasks=[_task("arabia")], cfg=cfg)
    assert _ghost(s, "add thing project:ara") == "bia"


def test_the_prompt_session_is_skipped_off_a_terminal():
    """This fallback is what lets the REPL tests drive the loop through input()."""
    assert cli._make_prompt_session(_suggester_with()) is None
