import uuid
from datetime import datetime
from typing import Annotated, Literal
from pydantic import BaseModel, Field


class ParsedFilter(BaseModel):
    ids: list[int] = []
    tags: list[str] = []
    properties: dict[str, str | None] = {}


class ParsedModification(BaseModel):
    tags: list[str] = []
    description: str = ""
    properties: dict[str, str | None] = {}


TaskStatus = Literal["pending", "waiting", "done", "deleted"]


class Task(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    description: str
    status: TaskStatus = "pending"
    tags: list[str] = []
    properties: dict[str, str] = {}
    entry: datetime = Field(default_factory=datetime.now)
    start: datetime | None = None


class CreatedEvent(BaseModel):
    type: Literal["created"] = "created"
    ts: datetime = Field(default_factory=datetime.now)
    task_id: uuid.UUID
    snapshot: Task


Event = Annotated[CreatedEvent, Field(discriminator="type")]