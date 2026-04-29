from uuid import UUID, uuid4
from datetime import datetime
from typing import Annotated, Any, Literal, Union
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
    uuid: UUID = Field(default_factory=uuid4)
    id: int | None = Field(default=None, exclude=True)
    description: str
    status: TaskStatus = "pending"
    tags: list[str] = []
    properties: dict[str, str] = {}
    entry: datetime = Field(default_factory=datetime.now)
    end: datetime | None = None
    start: datetime | None = None
    


class CreatedEvent(BaseModel):
    type: Literal["created"] = "created"
    ts: datetime = Field(default_factory=datetime.now)
    task_id: UUID
    snapshot: Task


class DoneEvent(BaseModel):
    type: Literal["done"] = "done"
    ts: datetime = Field(default_factory=datetime.now)
    task_id: UUID


class DeletedEvent(BaseModel):
    type: Literal["deleted"] = "deleted"
    ts: datetime = Field(default_factory=datetime.now)
    task_id: UUID


class FieldChange(BaseModel):
    before: Any
    after: Any


class UpdatedEvent(BaseModel):
    type: Literal["updated"] = "updated"
    ts: datetime = Field(default_factory=datetime.now)
    task_id: UUID
    changes: dict[str, FieldChange]


Event = Annotated[
    Union[CreatedEvent, DoneEvent, DeletedEvent, UpdatedEvent],
    Field(discriminator="type"),
]