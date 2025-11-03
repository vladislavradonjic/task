from .models import Filter, Modification

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

def extract_tags(section: list[str]) -> tuple[list[str], list[str]]:
    """Extract tags from the section"""
    tags = []
    remaining = []
    for arg in section:
        if arg.startswith("+") or arg.startswith("-"):
            tags.append(arg)
        else:
            remaining.append(arg)
    
    return tags, remaining

def extract_properties(section: list[str]) -> tuple[dict[str, str], list[str]]:
    """Extract properties from the section"""
    properties = {}
    remaining = []
    for arg in section:
        if ":" in arg and not arg.endswith(":"):
            key, value = arg.split(":", 1)
            value = value.strip("'")
            properties[key.strip()] = value
        else:
            remaining.append(arg)

    return properties, remaining

def parse_modification(modification_section: list[str]) -> Modification:
    """Parse the modification section into a Modification object."""
    modification_dict, remaining = extract_properties(modification_section)
    modification_dict["tags"], remaining = extract_tags(remaining)
    modification_dict["title"] = " ".join(remaining)
    

    return Modification(**modification_dict)
