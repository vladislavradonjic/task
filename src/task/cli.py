import shlex
import sys
import json
from datetime import datetime, timedelta

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


def _render_default_list(tasks: list) -> None:
    _, msg = commands.list_(tasks, parse_filter([]), parse_modification([]))
    if msg:
        print(msg)


def _repl_loop(cfg, context) -> None:
    known = commands.command_names() - {"run"}

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
        if line == "exit":
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
            print(f"Unknown command: {args[0]!r}. Type 'help' for available commands.", file=sys.stderr)
            continue

        try:
            parsed_filter = parse_filter(filter_args_raw)
            parsed_modification = parse_modification(modify_args_raw)
            fn = getattr(commands, f"{command}_")

            if command in ("init", "help", "context"):
                _, message = fn(parsed_filter, parsed_modification)
                if message:
                    print(message)

            elif command == "undo":
                _, message = fn(parsed_filter, parsed_modification)
                if message:
                    print(message)
                tasks = _load_and_prep(context, cfg)
                _render_default_list(tasks)

            elif command == "recap":
                tasks = _load_and_prep(context, cfg)
                _, message = fn(tasks, parsed_filter, parsed_modification, context=context, cfg=cfg)
                if message:
                    print(message)

            else:
                tasks = _load_and_prep(context, cfg)
                events, message = fn(tasks, parsed_filter, parsed_modification)
                for event in events:
                    storage.append_event(context, event)
                    tasks = apply_event(tasks, event)
                if events:
                    storage.save_snapshot(context, tasks)
                if message:
                    print(message)
                if events:
                    tasks = _load_and_prep(context, cfg)
                    _render_default_list(tasks)

        except Exception as e:
            print(str(e), file=sys.stderr)


def main() -> None:
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

    state = json.loads(state_file.read_text())
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

    meta = json.loads(meta_file.read_text())
    if meta.get("version") != storage.CURRENT_CONTEXT_VERSION:
        print(
          f"Context meta.json version {meta.get('version')} not supported "
          f"(expected {storage.CURRENT_CONTEXT_VERSION}); run `task migrate` or update the binary.",
          file=sys.stderr,
        )
        sys.exit(1)

    if command == "undo":
        _, message = fn(parsed_filter, parsed_modification)
        if message:
            print(message)
        return

    if command == "run":
        _repl_loop(cfg, context)
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



if __name__ == "__main__":
    main()