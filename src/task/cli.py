import json
import os
import re
import shlex
import sys
from datetime import datetime

from rich.console import Console
from task import commands, storage
from task.config import load_config
from task.events import apply_entry_event, apply_event
from task.parse import parse_filter, parse_modification


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


# Ghost-text completion fires on the value half of these properties — see
# docs/projects.md. Deliberately not command-aware: `kind:` is only legal on `log` and
# on a row `modify`, but parsing a half-typed line on every keystroke buys nothing over
# letting the command reject what you had to press Tab to accept.
_SUGGESTABLE = re.compile(r'(?:^|\s)(project|kind):(\S*)$')


def _make_suggester(cfg):
    """Ghost-text source for `project:` and `kind:`, or None if it cannot be built.

    Holds its candidate pools in a mutable attribute so the REPL can refresh them after
    a command without rebuilding the prompt session.
    """
    if not cfg.suggest.enabled:
        return None
    try:
        from prompt_toolkit.auto_suggest import AutoSuggest, Suggestion
    except ImportError:
        return None
    from task.vocab import suggest

    class _VocabSuggester(AutoSuggest):
        def __init__(self) -> None:
            self.pools: dict[str, list] = {}
            self.threshold = cfg.suggest.threshold
            # Ctrl-G has no built-in notion of "dismissed" — the suggestion is
            # recomputed from the buffer on every keystroke. Remembering the dismissed
            # text keeps it gone until the line changes, then lets it come back.
            self._dismissed: str | None = None

        def dismiss(self, text: str) -> None:
            self._dismissed = text

        def get_suggestion(self, buffer, document):
            if document.text == self._dismissed:
                return None
            m = _SUGGESTABLE.search(document.text_before_cursor)
            if not m:
                return None
            prop, typed = m.group(1), m.group(2)
            name = suggest(typed, self.pools.get(prop, []), self.threshold)
            return None if name is None else Suggestion(name[len(typed):])

    return _VocabSuggester()


def _make_prompt_session(suggester):
    """A prompt_toolkit session with ghost text, or None to fall back to `input()`.

    prompt_toolkit is imported here and nowhere else. It is 3.3 MB across 145 files — a
    real cost under the work machine's scanner — so `tsk run` pays it once per session
    and one-shot commands never import it at all. The None fallback covers a missing
    install and a non-terminal stdin, which is also what lets the tests drive the loop.
    """
    if suggester is None or not sys.stdin.isatty():
        return None
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.filters import has_suggestion
        from prompt_toolkit.key_binding import KeyBindings
    except ImportError:
        return None

    bindings = KeyBindings()

    @bindings.add("tab", filter=has_suggestion)
    def _accept(event) -> None:
        event.current_buffer.insert_text(event.current_buffer.suggestion.text)

    @bindings.add("tab")
    def _ignore(event) -> None:
        """Nothing to complete. A literal tab in a command line is never wanted."""

    # Ctrl-G rather than Esc: Esc is the Meta prefix, so prompt_toolkit must wait out
    # the escape timeout before it can tell a bare Esc from the start of an arrow key.
    @bindings.add("c-g", filter=has_suggestion)
    def _dismiss(event) -> None:
        suggester.dismiss(event.current_buffer.text)

    return PromptSession(auto_suggest=suggester, key_bindings=bindings)


def _read_line(session, prompt: str = "tsk> ") -> str:
    """One line of input, with ghost text when the terminal supports it."""
    return input(prompt) if session is None else session.prompt(prompt)


def _refresh_suggestions(suggester, tasks: list, entries: list, cfg) -> None:
    """Rebuild both candidate pools from state already in memory.

    Called wherever the standing view is rendered, which is exactly where the state
    behind them can have changed. `cfg` is read here rather than captured at
    construction because config.toml may have been edited since the REPL started.
    """
    if suggester is None:
        return
    from task.vocab import kind_usage, project_usage, window_start

    suggester.threshold = cfg.suggest.threshold
    day_starts_at = cfg.timesheet.day_starts_at
    try:
        since = window_start(cfg.projects.window, datetime.now())
    except ValueError:
        since = None  # a malformed window in config.toml must not break the prompt
    suggester.pools = {
        "project": project_usage(tasks, entries, since, day_starts_at),
        "kind": kind_usage(entries, cfg.timesheet.kinds, day_starts_at),
    }


def _render_default_list(context, tasks: list, cfg, message: str = "", suggester=None) -> None:
    """The REPL's standing view: today's tasks, then today's timesheet.

    The timesheet lives here rather than behind a command because an unseen sheet does
    not get filled in — see docs/timesheet.md.
    """
    Console().clear()
    if message:
        print(message)
    _, msg = commands.list_(tasks, parse_filter([]), parse_modification([]))
    if msg:
        print(msg)
    entries = storage.load_entries(context)
    _, day_msg = commands.day_(entries, tasks, parse_filter([]), parse_modification([]), cfg)
    if day_msg:
        print(day_msg)
    _refresh_suggestions(suggester, tasks, entries, cfg)


# Commands that do their own I/O and take no task list (see CLAUDE.md, functional core).
_SHELL_COMMANDS = {"init", "help", "context", "undo", "rebuild"}

# Timesheet commands: pure, but take (entries, tasks, filter, modify). See docs/timesheet.md.
# `projects` is here because the project namespace spans both entities, so listing it
# needs the entries as well as the tasks — see docs/projects.md.
_ENTRY_COMMANDS = {"log", "day", "projects"}

# Shared names. `tsk c delete` addresses a timesheet row, `tsk 3 delete` a task, so the
# shell routes on which kind of id the filter carries.
_DUAL_COMMANDS = {"modify": "_entry_modify", "delete": "_entry_delete"}


def _entry_command(command: str, parsed_filter):
    """The timesheet function for this invocation, or None if it is a task command."""
    if command in _ENTRY_COMMANDS:
        return getattr(commands, f"{command}_")
    if command in _DUAL_COMMANDS and parsed_filter.letters:
        return getattr(commands, _DUAL_COMMANDS[command])
    return None


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


def _dispatch_entry_command(fn, context, parsed_filter, parsed_modification, cfg):
    """Run a timesheet command and persist whatever it returns.

    Returns (changed, message); `changed` tells the REPL whether to re-render. `day`
    emits nothing and prints its own table, so it must not trigger a second render.
    """
    tasks = storage.load_tasks(context)
    storage.assign_display_ids(tasks)
    entries = storage.load_entries(context)
    events, message = fn(entries, tasks, parsed_filter, parsed_modification, cfg)
    for event in events:
        storage.append_event(context, event)
        entries = apply_entry_event(entries, event)
    if events:
        storage.save_entries_snapshot(context, entries)
    return bool(events), message


def _repl_loop(d) -> None:
    known = commands.command_names()
    cfg, cfg_stamp = _load_cfg(d)
    context = storage.active_context(d)

    suggester = _make_suggester(cfg)
    session = _make_prompt_session(suggester)

    tasks = _load_and_prep(context, cfg)
    _render_default_list(context, tasks, cfg, suggester=suggester)

    while True:
        try:
            line = _read_line(session).strip()
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
                    _render_default_list(context, tasks, cfg, message, suggester)
                elif message:
                    print(message)
                continue

            entry_fn = _entry_command(command, parsed_filter)
            if entry_fn is not None:
                changed, message = _dispatch_entry_command(
                    entry_fn, context, parsed_filter, parsed_modification, cfg)
                if changed:
                    tasks = _load_and_prep(context, cfg)
                    _render_default_list(context, tasks, cfg, message, suggester)
                elif message:
                    print(message)
                continue

            tasks = _load_and_prep(context, cfg)

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
                _render_default_list(context, tasks, cfg, message, suggester)
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

    entry_fn = _entry_command(command, parsed_filter)
    if entry_fn is not None:
        _, message = _dispatch_entry_command(entry_fn, context, parsed_filter, parsed_modification, cfg)
        if message:
            print(message)
        return

    tasks = storage.load_tasks(context)

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