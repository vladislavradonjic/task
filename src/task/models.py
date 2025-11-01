from pydantic import BaseModel, Field
from datetime import date, datetime
from uuid import UUID, uuid4
from typing import Literal

class Task(BaseModel):
    """Immutable task model. All operations return new instances."""
    model_config = {"frozen": True}

    uuid: UUID = Field(default_factory=uuid4)
    id: int | None # Sequential ID, None for done/deleted tasks
    title: str
    project: str | None = None
    priority: Literal["H", "M", "L"] | None = None # "H", "M", "L"
    due: date | None = None
    scheduled: date | None = None
    depends: list[UUID] = Field(default_factory=list)
    blocks: list[UUID] = Field(default_factory=list)
    started_at: datetime | None = None
    tags: list[str] = Field(default_factory=list)
    status: str = "pending" # "pending", "active", "done", "deleted"
    rank_score: float = 0.0
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    deleted_at: datetime | None = None

class Filter(BaseModel):
    """Filter criteria for querying tasks."""
    ids: list[int] = Field(default_factory=list)
    title: str | None = None
    project: str | None = None
    priority: Literal["H", "M", "L"] | None = None
    due: date | None = None
    scheduled: date | None = None
    depends: int | None = None # Task ID that this depends on
    blocks: int | None = None # Task ID that this blocks
    tags: list[str] = Field(default_factory=list)
    status: str | None = None

class Modification(BaseModel):
    """Changes to apply to tasks."""
    title: str | None = None
    project: str | None = None
    priority: Literal["H", "M", "L"] | None = None
    due: date | None = None
    scheduled: date | None = None
    depends: list[int] | None = None # Positive to add, negative to remove
    blocks: list[int] | None = None # Positive to add, negative to remove
    tags: list[str] | None = None # ["+tag1", "-tag2"]

class ParsedCommand(BaseModel):
    """Parsed command from CLI."""
    command: str
    filter: Filter | None = None
    modification: Modification | None = None

class Config(BaseModel):
    """Application configuration."""
    db_path: str
    urgency_coefficients: dict[str, float] = Field(default_factory=lambda: {
        "next_tag": 15.0,
        "due": 12.0,
        "blocking": 8.0,
        "priority_h": 6.0,
        "priority_m": 3.9,
        "priority_l": 1.8,
        "scheduled": 5.0,
        "active": 4.0,
        "age": 2.0,
        "annotations": 1.0,
        "tags": 1.0,
        "project": 1.0,
        "waiting": -3.0,
        "blocked": -5.0,
    })
    current_context: str = "default"
    contexts: dict[str, str] = Field(default_factory=dict) # context_name -> db_path

    