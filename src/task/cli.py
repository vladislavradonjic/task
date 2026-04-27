import sys

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
    if not (d / "state.json").exists():
        print("Not initialized. Run `task init` first.", file=sys.stderr)
        sys.exit(2)

    context = storage.active_context(d)
    tasks = storage.load_tasks(context)
    events, message = fn(tasks, parsed_filter, parsed_modification)
    for event in events:
        storage.append_event(context, event)
        tasks = apply_event(tasks, event)
    storage.save_snapshot(context, tasks)
    print(message)



if __name__ == "__main__":
    main()