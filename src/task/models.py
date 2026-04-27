from pydantic import BaseModel


class ParsedFilter(BaseModel):
    ids: list[int] = []
    tags: list[str] = []
    properties: dict[str, str | None] = {}


class ParsedModification(BaseModel):
    tags: list[str] = []
    description: str = ""
    properties: dict[str, str | None] = {}
