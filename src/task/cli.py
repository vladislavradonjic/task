import json
import os
import shlex
import sys
from datetime import datetime, timedelta

from rich.console import Console
from task import commands, storage
from task.config import load_config
from task.events import apply_event
from task.models import StoppedEvent
from task.parse import parse_filter, parse_modification


def _fmt_elapsed(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    return f"{h}h {m}m" if h else f"{m}m"


def _handle_stale_session(tasks: list, context, threshold_hours: float) -> None:
    active = next((t for t in tasks if t.start is not None), None)
    if active is None:
        return
    now = datetime.now()
    elapsed = (now - active.start.replace(tzinfo=None)).total_seconds()
    if elapsed <= threshold_hours * 3600:
        return
    if not sys.stdin.isatty():
        return  # non-TTY: keep silently

    print(f'\nTask #{active.id} "{active.description}" has been active for {_fmt_elapsed(elapsed)}.')
    print("Did you actually work that long?")
    answer = input("[k]eep, [s]top now, stop with [d]uration: ").strip().lower()

    if answer == "s":
        event = StoppedEvent(task_id=active.uuid, ts=now, duration_s=elapsed, note="")
        storage.append_event(context, event)
        apply_event(tasks, event)
    elif answer.startswith("d"):
        from task.dates import parse_duration_seconds
        dur_str = input("Duration (e.g. 2h, 30min, 1h30m): ").strip()
        try:
            dur_s = parse_duration_seconds(dur_str)
        except ValueError as e:
            print(f"Invalid duration: {e}", file=sys.stderr)
            return
        stopped_ts = active.start.replace(tzinfo=None) + timedelta(seconds=dur_s)
        event = StoppedEvent(task_id=active.uuid, ts=stopped_ts, duration_s=dur_s, note="")
        storage.append_event(context, event)
        apply_event(tasks, event)
    # "k" or anything else: keep


def _load_and_prep(context, cfg) -> list:
    tasks = storage.load_tasks(context)
    transitions = storage.lazy_wait_transitions(tasks)
    for event in transitions:
        storage.append_event(context, event)
        tasks = apply_event(tasks, event)
    if transitions:
        storage.save_snapshot(context, tasks)
    storage.assign_display_ids(tasks)
    return tasks


def _render_default_list(tasks: list, message: str = "") -> None:
    Console().clear()
    if message:
        print(message)
    _, msg = commands.list_(tasks, parse_filter([]), parse_modification([]))
    if msg:
        print(msg)


# Commands that do their own I/O and take no task list (see CLAUDE.md, functional core).
_SHELL_COMMANDS = {"init", "help", "context", "undo", "rebuild"}


def _load_cfg(d, cached=None, stamp=None):
    """Reload config.toml only when it has changed, so a long REPL picks up edits."""
    config_file = d / "config.toml"
    try:
        current = config_file.stat().st_mtime_ns if config_file.exists() else None
    except OSError:
        current = None
    if cached is not None and current == stamp:
        return cached, stamp
    return load_config(d), current


def _repl_loop(d) -> None:
    known = commands.command_names()
    cfg, cfg_stamp = _load_cfg(d)
    context = storage.active_context(d)

    tasks = storage.load_tasks(context)
    _handle_stale_session(tasks, context, cfg.time_tracking.stale_threshold_hours)
    tasks = _load_and_prep(context, cfg)
    _render_default_list(tasks)

    while True:
        try:
            line = input("tsk> ").strip()
        except EOFError:
            print()
            break
        except KeyboardInterrupt:
            print()
            continue

        if not line:
            continue
        if line in ("exit", "quit"):
            break

        try:
            args = shlex.split(line)
        except ValueError as e:
            print(f"Parse error: {e}", file=sys.stderr)
            continue

        filter_args_raw: list[str] = []
        command: str | None = None
        modify_args_raw: list[str] = []
        for i, token in enumerate(args):
            if token in known:
                filter_args_raw = args[:i]
                command = token
                modify_args_raw = args[i + 1:]
                break

        if command is None:
            print(f"No command in {line!r}. Type 'help' for available commands.", file=sys.stderr)
            continue
        if command == "run":
            print("Already in the REPL. Use 'exit' or Ctrl-D to leave.", file=sys.stderr)
            continue
        if command == "init":
            print("`init` is not available in the REPL; the store is already initialized.", file=sys.stderr)
            continue

        # config.toml may have been edited from another window since the last command.
        cfg, cfg_stamp = _load_cfg(d, cfg, cfg_stamp)

        try:
            parsed_filter = parse_filter(filter_args_raw)
            parsed_modification = parse_modification(modify_args_raw)
            fn = getattr(commands, f"{command}_")

            if command in _SHELL_COMMANDS:
                _, message = fn(parsed_filter, parsed_modification)
                # `context use` changes where every later command writes, so re-resolve
                # it rather than trusting the value captured at loop entry.
                new_context = storage.active_context(d)
                if new_context != context or command in ("undo", "rebuild"):
                    context = new_context
                    tasks = _load_and_prep(context, cfg)
                    _render_default_list(tasks, message)
                elif message:
                    print(message)
                continue

            tasks = _load_and_prep(context, cfg)
            _handle_stale_session(tasks, context, cfg.time_tracking.stale_threshold_hours)

            if command == "recap":
                _, message = fn(tasks, parsed_filter, parsed_modification, context=context, cfg=cfg)
                if message:
                    print(message)
                continue

            events, message = fn(tasks, parsed_filter, parsed_modification)
            for event in events:
                storage.append_event(context, event)
                tasks = apply_event(tasks, event)
            if events:
                storage.save_snapshot(context, tasks)
                tasks = _load_and_prep(context, cfg)
                _render_default_list(tasks, message)
            elif message:
                print(message)

        except Exception as e:
            if os.environ.get("TASK_DEBUG") == "1":
                import traceback
                traceback.print_exc()
            else:
                print(f"{type(e).__name__}: {e}", file=sys.stderr)


def _main() -> None:
    args = sys.argv[1:]
    known = commands.command_names()

    filter_args: list[str] = []
    command: str | None = None
    modify_args: list[str] = []


    for i, token in enumerate(args):
        if token in known:
            filter_args = args[:i]
            command = token
            modify_args = args[i + 1 :]
            break

    if command is None:
        print("No command given. Possible commands:", file=sys.stderr)
        for name in sorted(known):
            print(f"  {name}", file=sys.stderr)
        sys.exit(1)

    fn = getattr(commands, f"{command}_")
    parsed_filter = parse_filter(filter_args)
    parsed_modification = parse_modification(modify_args)

    if command == "init":
        _, message = fn(parsed_filter, parsed_modification)
        print(message)
        return

    if command == "help":
        _, message = fn(parsed_filter, parsed_modification)
        if message:
            print(message)
        return

    d = storage.data_dir()
    state_file = d / "state.json"
    if not state_file.exists():
        print("Not initialized. Run `tsk init` first.", file=sys.stderr)
        sys.exit(2)

    state = json.loads(state_file.read_text(encoding="utf-8"))
    if state.get("version") != storage.CURRENT_STATE_VERSION:
        print(
          f"state.json version {state.get('version')} not supported "
          f"(expected {storage.CURRENT_STATE_VERSION}); run `task migrate` or update the binary.",
          file=sys.stderr,
        )
        sys.exit(1)

    cfg = load_config(d)

    if command == "context":
        _, message = fn(parsed_filter, parsed_modification)
        print(message)
        return

    context = storage.active_context(d)
    meta_file = context / "meta.json"
    if not meta_file.exists():
        print(f"Context {context.name} not initialized. Run `tsk context list`.", file=sys.stderr)
        sys.exit(1)

    meta = json.loads(meta_file.read_text(encoding="utf-8"))
    if meta.get("version") != storage.CURRENT_CONTEXT_VERSION:
        print(
          f"Context meta.json version {meta.get('version')} not supported "
          f"(expected {storage.CURRENT_CONTEXT_VERSION}); run `task migrate` or update the binary.",
          file=sys.stderr,
        )
        sys.exit(1)

    if command in ("undo", "rebuild"):
        _, message = fn(parsed_filter, parsed_modification)
        if message:
            print(message)
        return

    if command == "run":
        _repl_loop(d)
        return

    tasks = storage.load_tasks(context)

    _handle_stale_session(tasks, context, cfg.time_tracking.stale_threshold_hours)

    transitions = storage.lazy_wait_transitions(tasks)
    for event in transitions:
        storage.append_event(context, event)
        tasks = apply_event(tasks, event)
    if transitions:
        storage.save_snapshot(context, tasks)

    storage.assign_display_ids(tasks)

    if command == "recap":
        _, message = fn(tasks, parsed_filter, parsed_modification, context=context, cfg=cfg)
        if message:
            print(message)
        return

    events, message = fn(tasks, parsed_filter, parsed_modification)
    for event in events:
        storage.append_event(context, event)
        tasks = apply_event(tasks, event)
    storage.save_snapshot(context, tasks)
    print(message)



def main() -> None:
    """Entry point. Keeps tracebacks off the terminal unless TASK_DEBUG=1."""
    try:
        _main()
    except SystemExit:
        raise
    except KeyboardInterrupt:
        print(file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        if os.environ.get("TASK_DEBUG") == "1":
            raise
        print(f"{type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()