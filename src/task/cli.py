import sys
import json

from task import commands, storage
from task.events import apply_event
from task.parse import parse_filter, parse_modification


def _command_names() -> set[str]:
    """Command names are exported functions in commands.py (name without trailing _)."""
    return {
        name[:-1]
        for name in dir(commands)
        if name.endswith("_")
        and not name.startswith("_")
        and callable(getattr(commands, name))
    }


def main() -> None:
    args = sys.argv[1:]
    known = _command_names()

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
    
    d = storage.data_dir()
    state_file = d / "state.json"
    if not state_file.exists():
        print("Not initialized. Run `task init` first.", file=sys.stderr)
        sys.exit(2)

    state = json.loads(state_file.read_text())
    if state.get("version") != storage.CURRENT_STATE_VERSION:
        print(
          f"state.json version {state.get('version')} not supported "
          f"(expected {storage.CURRENT_STATE_VERSION}); run `task migrate` or update the binary.",
          file=sys.stderr,
        )
        sys.exit(1)

    if command == "context":
        _, message = fn(parsed_filter, parsed_modification)
        print(message)
        return

    context = storage.active_context(d)
    meta_file = context / "meta.json"
    if not meta_file.exists():
        print(f"Context {context.name} not initialized. Run `task context list`.", file=sys.stderr)
        sys.exit(1)

    meta = json.loads(meta_file.read_text())
    if meta.get("version") != storage.CURRENT_CONTEXT_VERSION:
        print(
          f"Context meta.json version {meta.get('version')} not supported "
          f"(expected {storage.CURRENT_CONTEXT_VERSION}); run `task migrate` or update the binary.",
          file=sys.stderr,
        )
        sys.exit(1)

    tasks = storage.load_tasks(context)

    transitions = storage.lazy_wait_transitions(tasks)
    for event in transitions:
        storage.append_event(context, event)
        tasks = apply_event(tasks, event)
    if transitions:
        storage.save_snapshot(context, tasks)

    storage.assign_display_ids(tasks)

    events, message = fn(tasks, parsed_filter, parsed_modification)
    for event in events:
        storage.append_event(context, event)
        tasks = apply_event(tasks, event)
    storage.save_snapshot(context, tasks)
    print(message)



if __name__ == "__main__":
    main()