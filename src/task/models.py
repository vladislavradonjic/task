from uuid import UUID, uuid4
from datetime import datetime
from typing import Annotated, Any, Literal, Union
from pydantic import BaseModel, Field, field_validator


class ParsedFilter(BaseModel):
    ids: list[int] = []
    letters: list[str] = []  # timesheet row addresses; see docs/timesheet.md
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
    depends: list[UUID] = []
    properties: dict[str, str] = {}

    @field_validator("properties")
    @classmethod
    def _normalise_priority(cls, properties: dict[str, str]) -> dict[str, str]:
        """Fold `priority` to upper case.

        Urgency, the list colouring and `query` all compare against literal "H"/"M"/"L",
        so `priority:h` used to be accepted, rendered lower case, and score nothing.
        Normalising here catches every path at once — `add`, `modify`, and replay of
        rows already written in lower case. Values outside H/M/L are left alone.
        """
        value = properties.get("priority")
        if value is not None and value.upper() in ("H", "M", "L"):
            return {**properties, "priority": value.upper()}
        return properties
    entry: datetime = Field(default_factory=datetime.now)
    end: datetime | None = None
    due: datetime | None = None
    wait: datetime | None = None


class Entry(BaseModel):
    """One row of the timesheet — see docs/timesheet.md.

    A separate entity from Task; the two share only the project namespace and the
    optional `task` link. Timestamps are full datetimes so a row can cross midnight
    and still measure correctly; only %H:%M is ever rendered.
    """
    uuid: UUID = Field(default_factory=uuid4)
    id: str | None = Field(default=None, exclude=True)  # ephemeral display letter
    from_: datetime | None = None  # anchor start; None means "derive from the previous row"
    til: datetime | None = None  # end; None means the row is still open
    kind: str
    project: str | None = None
    description: str = ""
    task: UUID | None = None


class LoggedEvent(BaseModel):
    type: Literal["logged"] = "logged"
    ts: datetime = Field(default_factory=datetime.now)
    entry_id: UUID
    snapshot: Entry


class EntryUpdatedEvent(BaseModel):
    type: Literal["entry_updated"] = "entry_updated"
    ts: datetime = Field(default_factory=datetime.now)
    entry_id: UUID
    changes: dict[str, "FieldChange"]


# Unlike DeletedEvent, this drops the row outright rather than flagging a status.
# Entries have no lifecycle to preserve, and undo replays the log without the event,
# so history survives in events.jsonl either way.
class EntryDeletedEvent(BaseModel):
    type: Literal["entry_deleted"] = "entry_deleted"
    ts: datetime = Field(default_factory=datetime.now)
    entry_id: UUID


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


# Legacy: emitted by the removed start/stop/log commands. Kept so pre-v1.4 logs still
# parse; they replay as no-ops (see events.apply_event) and are surfaced nowhere.
class StartedEvent(BaseModel):
    type: Literal["started"] = "started"
    ts: datetime = Field(default_factory=datetime.now)
    task_id: UUID
    note: str = ""
    affects_active: bool = True


class StoppedEvent(BaseModel):
    type: Literal["stopped"] = "stopped"
    ts: datetime = Field(default_factory=datetime.now)
    task_id: UUID
    duration_s: float
    note: str = ""
    affects_active: bool = True


class UndoneEvent(BaseModel):
    # Purely informational: replay excludes events by `undid_ts` (storage.effective_events),
    # so neither subject id is load-bearing. One of the two is set, per the event undone.
    type: Literal["undone"] = "undone"
    ts: datetime = Field(default_factory=datetime.now)
    task_id: UUID | None = None
    entry_id: UUID | None = None
    undid_ts: datetime
    undid_type: str


Event = Annotated[
    Union[
        CreatedEvent, DoneEvent, DeletedEvent, UpdatedEvent,
        LoggedEvent, EntryUpdatedEvent, EntryDeletedEvent,
        StartedEvent, StoppedEvent, UndoneEvent,
    ],
    Field(discriminator="type"),
]