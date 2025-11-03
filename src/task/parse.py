from .models import Filter, Modification
from .dates import parse_date_string

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

def _normalize_priority(priority: str) -> str | None:
    """Normalize priority to uppercase"""
    if priority.upper() in ["H", "M", "L"]:
        return priority.upper()
    else:
        return None

def extract_properties(section: list[str]) -> tuple[dict[str, str], list[str]]:
    """Extract properties from the section"""
    properties = {}
    remaining = []
    for arg in section:
        if ":" in arg and not arg.endswith(":"):
            key, value = arg.split(":", 1)
            key = key.strip()
            value = value.strip("'").strip()
            # normalize priority
            if key.strip() == "priority":
                value = _normalize_priority(value)
            # parse dates
            elif key.strip() in ["due", "scheduled"]:
                value = parse_date_string(value)
            # handle null values
            if value is None:
                continue
            properties[key.strip()] = value
        else:
            remaining.append(arg)

    return properties, remaining

def extract_ids(section: list[str]) -> tuple[list[int], list[str]]:
    """Extract IDs from the section"""
    ids = [int(arg) for arg in section if arg.isdigit()]
    remaining = [arg for arg in section if not arg.isdigit()]
    
    return ids, remaining

def parse_filter(filter_section: list[str]) -> Filter:
    """Parse the filter section into a Filter object."""
    ids, remaining = extract_ids(filter_section)
    filter_dict, remaining = extract_properties(remaining)
    tags, remaining = extract_tags(remaining)
    title = " ".join(remaining)

    filter_dict["ids"] = ids
    filter_dict["tags"] = tags
    filter_dict["title"] = title

    return Filter(**filter_dict)

def parse_modification(modification_section: list[str]) -> Modification:
    """Parse the modification section into a Modification object."""
    modification_dict, remaining = extract_properties(modification_section)
    modification_dict["tags"], remaining = extract_tags(remaining)
    modification_dict["title"] = " ".join(remaining)
    

    return Modification(**modification_dict)
