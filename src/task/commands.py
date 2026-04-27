"""Command implementations. Dummy commands for now; real logic later."""

from task.models import ParsedFilter, ParsedModification


def add_(filter_args: ParsedFilter, modify_args: ParsedModification) -> None:
    """Dummy add command."""
    print("filter_args:", filter_args)
    print("modify_args:", modify_args)


def list_(filter_args: ParsedFilter, modify_args: ParsedModification) -> None:
    """Dummy list command."""
    print("filter_args:", filter_args)
    print("modify_args:", modify_args)


def init_(filter_args: ParsedFilter, modify_args: ParsedModification) -> None:
    """Dummy init command."""
    print("filter_args:", filter_args)
    print("modify_args:", modify_args)
