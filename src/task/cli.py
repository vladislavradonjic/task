import sys

from task import commands


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
    fn(filter_args, modify_args)


if __name__ == "__main__":
    main()