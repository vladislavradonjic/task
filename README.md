# task

Personal [taskwarrior](https://taskwarrior.org/) clone in Python, primarily for use on Windows.

## Status

Early scaffolding. The CLI splits arguments into filter / command / modify sections and dispatches to named command stubs, but no command performs real work yet. Argument parsing — recognizing tags, properties, IDs, and descriptions — is the active focus.

## Requirements

- Python 3.12+
- [uv](https://github.com/astral-sh/uv)

## Install

    uv sync

## Run

    uv run task <args>

Example (currently just echoes the parsed argv sections):

    uv run task add Buy milk +groceries
