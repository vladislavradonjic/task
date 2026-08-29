"""Cross-platform guards that a Linux-only test run would otherwise miss.

CLAUDE.md makes Windows a first-class target, but the test suite only ever runs here.
These check the source itself for constructs that work on glibc and fail on Windows.
"""

import ast
import pathlib
import re

SRC = pathlib.Path(__file__).resolve().parent.parent / "src" / "task"

# `%-d` / `%-H` strip zero padding on glibc; Windows' strftime raises
# "ValueError: Invalid format string" and spells it `%#d` instead.
_GLIBC_ONLY = re.compile(r"%[-#]\w")


def _format_specs(tree):
    """Every f-string format spec and strftime argument in a module."""
    for node in ast.walk(tree):
        if isinstance(node, ast.FormattedValue) and node.format_spec is not None:
            for part in ast.walk(node.format_spec):
                if isinstance(part, ast.Constant) and isinstance(part.value, str):
                    yield part.value
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "strftime"
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            yield node.args[0].value


def test_no_platform_specific_strftime_in_source():
    offenders = []
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        offenders += [
            f"{path.name}: {spec!r}" for spec in _format_specs(tree) if _GLIBC_ONLY.search(spec)
        ]
    assert not offenders, (
        "glibc-only strftime directives; Windows raises ValueError on these: "
        + ", ".join(offenders)
    )


def test_no_platform_specific_strftime_in_templates():
    offenders = [
        f"{path.name}: {m.group(0)}"
        for path in sorted((SRC / "templates").glob("*.j2"))
        for m in _GLIBC_ONLY.finditer(path.read_text(encoding="utf-8"))
    ]
    assert not offenders, f"glibc-only strftime directives in templates: {offenders}"


def test_the_guard_actually_catches_the_bug_it_was_written_for():
    """v1.4 shipped `f"{day:%A %-d %b}"`, which crashed the REPL on Windows."""
    tree = ast.parse('day = 1\nx = f"{day:%A %-d %b}"\n')
    assert any(_GLIBC_ONLY.search(spec) for spec in _format_specs(tree))


def test_the_guard_accepts_portable_directives():
    tree = ast.parse('d = 1\nx = f"{d:%A %b %Y}"\ny = d.strftime("%H:%M")\n')
    assert not any(_GLIBC_ONLY.search(spec) for spec in _format_specs(tree))
