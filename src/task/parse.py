import re
import sys
from task.models import ParsedFilter, ParsedModification

_TAG = re.compile(r'^[+-][A-Za-z][A-Za-z0-9_-]*$')
# Timesheet rows are addressed by letter, tasks by digit — see docs/timesheet.md.
# One or two lowercase letters only, so ordinary words stay unknown tokens.
_ROW = re.compile(r'^[a-z]{1,2}$')
_PROPERTY = re.compile(r'^([A-Za-z][A-Za-z0-9_-]*):(.*)$')


def parse_filter(tokens: list[str]) -> ParsedFilter:
    ids, letters, tags, properties = [], [], [], {}
    for token in tokens:
        if token.isdigit():
            ids.append(int(token))
        elif _ROW.match(token):
            letters.append(token)
        elif _TAG.match(token):
            tags.append(token)
        elif m := _PROPERTY.match(token):
            properties[m.group(1)] = m.group(2) or None
        else:
            print(f"filter: ignored unknown token {token!r}", file=sys.stderr)

    return ParsedFilter(ids=ids, letters=letters, tags=tags, properties=properties)


def parse_modification(tokens: list[str]) -> ParsedModification:
    tags, properties, desc = [], {}, []
    for token in tokens:
        if _TAG.match(token):
            tags.append(token)
        elif m := _PROPERTY.match(token):
            properties[m.group(1)] = m.group(2) or None
        else:
            desc.append(token)

    return ParsedModification(tags=tags, properties=properties, description=" ".join(desc))
