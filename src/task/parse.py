def separate_sections(
    arglist: list[str], commands: set[str]
) -> tuple[str | None, list[str] | None, list[str] | None]:
    """
    Separate command-line arguments into (command, filter_section, modification_section).
    """
    first_match = next(
        ((i, arg) for i, arg in enumerate(arglist) if arg.lower() in commands),
        None
    )

    if first_match is None:
        return None, None, None

    command = first_match[1].lower()
    index = first_match[0]
    filter_section = arglist[:index]
    modification_section = arglist[index + 1:]
    return command, filter_section, modification_section
